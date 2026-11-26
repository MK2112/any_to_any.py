from __future__ import annotations

import os
import time
import uuid
import shutil
import tempfile
import threading

from dataclasses import dataclass
from gui.timeline import media_kind
from core.controller import Controller
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils.file_handler import ConversionCancelled, FFmpegProcessTracker


@dataclass
class RenderStep:
    inputs: list
    output: str
    formats: list | None = None
    merge: bool = False
    concat: bool = False
    trim: str | None = None
    split_at: str | None = None
    label: str = ""
    collect_to: int | None = None  # store newly produced files under this index

    def as_kwargs(self, job: dict, inputs: list | None = None) -> dict:
        return dict(
            input_path_args=list(self.inputs if inputs is None else inputs),
            format=list(self.formats) if self.formats else None,
            output=self.output,
            framerate=job.get("framerate") or None,
            quality=job.get("quality") or None,
            split=None,
            merge=self.merge,
            concat=self.concat,
            delete=False,
            across=False,
            recursive=False,
            dropzone=False,
            language=None,
            workers=job.get("workers", 1),
            preserve_meta=bool(job.get("preserve_meta")),
            add_tag=list(job.get("add_tag") or []),
            strip_meta=bool(job.get("strip_meta")),
            resolution=job.get("resolution") or None,
            burn_subs=bool(job.get("burn_subs")),
            trim=self.trim,
            split_at=self.split_at,
        )


def _fmt_seconds(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _compose_audio(clip, volume: float, muted: bool, start: float):
    if muted or volume <= 0:
        return None
    if volume != 1.0:
        clip = clip.with_volume_scaled(volume)
    return clip.with_start(start)


def _trim_spec(clip: dict) -> str | None:
    # Return a --trim range for a clip, or None when not trimmed
    in_point = float(clip.get("in") or 0.0)
    out_point = clip.get("out")
    duration = float(clip.get("duration") or 0.0)
    if out_point is None:
        out_point = duration if duration > 0 else None
    else:
        out_point = float(out_point)
    if (
        in_point <= 0.01
        and out_point is not None
        and duration > 0
        and out_point >= duration - 0.01
    ):
        return None
    if in_point <= 0.01 and out_point is None:
        return None
    end = f"{_fmt_seconds(out_point)}" if out_point is not None else "end"
    return f"{_fmt_seconds(in_point)}-{end}"


def build_steps(job: dict, temp_dir: str) -> tuple[list[RenderStep], int]:
    # Translate a job description into ordered Controller calls
    modes = {
        "stitch": "Stitching clips",
        "trim": "Trimming",
        "split": "Splitting",
        "merge": "Merging",
    }
    label = modes.get(job.get("mode", "stitch"), "Rendering")
    formats = job.get("format") or None
    first_format = [formats[0]] if formats else None
    output = job["output_dir"]
    steps: list[RenderStep] = []

    if job.get("mode") == "stitch":
        segments = []
        for index, clip in enumerate(job["clips"]):
            path = clip["path"]
            trim = _trim_spec(clip)
            if trim is None:
                segments.append(path)
                continue
            part_dir = os.path.join(temp_dir, f"segment_{index:04d}")
            os.makedirs(part_dir, exist_ok=True)
            steps.append(
                RenderStep(
                    inputs=[path],
                    output=part_dir,
                    formats=first_format,
                    trim=trim,
                    label=f"{label} ({index + 1})",
                    collect_to=len(segments),
                )
            )
            segments.append(("@collect", len(segments)))
        steps.append(
            RenderStep(
                inputs=segments,
                output=output,
                formats=formats,
                concat=True,
                label="Concatenating segments",
            )
        )
    elif job.get("mode") == "split":
        steps.append(
            RenderStep(
                inputs=[job["source_path"]],
                output=output,
                formats=formats,
                split_at=",".join(_fmt_seconds(p) for p in job["split_points"]),
                label=label,
            )
        )
    elif job.get("mode") == "merge":
        steps.append(
            RenderStep(
                inputs=list(job["inputs"]),
                output=output,
                formats=formats,
                merge=True,
                label=label,
            )
        )
    else:
        clip = job["clips"][0]
        steps.append(
            RenderStep(
                inputs=[clip["path"]],
                output=output,
                formats=formats,
                trim=_trim_spec(clip),
                label=label,
            )
        )
    return steps, len(job["clips"]) if job.get("mode") == "stitch" else len(steps)


def render_timeline(job: dict, cancel_event, output_path: str, report) -> None:
    # Compose every clip at its exact timeline position (with overlaps)
    from moviepy import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
    )

    clips = sorted(
        job["clips"],
        key=lambda item: (
            int(item.get("track") or 0),
            float(item.get("start") or 0.0),
        ),
    )

    tracks = job.get("track_states") or {}

    any_solo = any(
        bool(state.get("solo")) for state in tracks.values() if isinstance(state, dict)
    )

    movie_segments: list = []
    audio_segments: list = []
    opened: list = []
    composites: list = []

    try:
        for index, item in enumerate(clips):
            if cancel_event.is_set():
                raise ConversionCancelled()
            path = item["path"]
            in_point = float(item.get("in") or 0.0)
            out_point = item.get("out")
            duration = float(item.get("duration") or 0.0)
            source_end = float(out_point) if out_point is not None else duration
            if source_end <= in_point + 0.01:
                continue
            start = float(item.get("start") or 0.0)
            track = int(item.get("track") or 0)
            track_state = tracks.get(track) or {}
            track_volume = float(track_state.get("volume", 1.0) or 1.0)
            muted = (
                bool(item.get("muted"))
                or bool(track_state.get("muted"))
                or (any_solo and not bool(track_state.get("solo")))
            )
            volume = float(item.get("volume", 1.0) or 1.0) * track_volume
            report(
                int(70 * (index + 1) / max(1, len(clips))),
                f"Compositing {index + 1}/{len(clips)}",
            )
            kind = media_kind(path)
            if kind == "image":
                image = ImageClip(path).with_duration(source_end - in_point)
                opened.append(image)
                movie_segments.append(image.with_start(start))
            elif kind == "movie":
                source = VideoFileClip(path)
                opened.append(source)
                end = min(source_end, source.duration)
                if end <= in_point + 0.01:
                    continue
                segment = source.subclipped(in_point, end).with_start(start)
                movie_segments.append(segment)
                if segment.audio is not None:
                    audio = _compose_audio(segment.audio, volume, muted, start)
                    if audio is not None:
                        audio_segments.append(audio)
            else:
                source = AudioFileClip(path)
                opened.append(source)
                end = min(source_end, source.duration)
                if end <= in_point + 0.01:
                    continue
                audio = _compose_audio(
                    source.subclipped(in_point, end), volume, muted, start
                )
                if audio is not None:
                    audio_segments.append(audio)

        if not movie_segments and not audio_segments:
            raise RuntimeError("No usable clips on the timeline")

        report(80, "Building composition")
        if movie_segments:
            size = None
            resolution = job.get("resolution")
            if resolution:
                try:
                    width, height = (
                        int(part) for part in str(resolution).lower().split("x")[:2]
                    )
                    size = (width, height)
                except (ValueError, TypeError):
                    size = None
            composite = CompositeVideoClip(movie_segments, size=size)
            composites.append(composite)
            if audio_segments:
                composite = composite.with_audio(CompositeAudioClip(audio_segments))
                composites.append(composite.audio)
            framerate = job.get("framerate") or composite.fps or 24
            report(90, "Writing video")
            composite.write_videofile(
                output_path,
                fps=framerate,
                codec=job.get("video_codec") or "libx264",
                logger=None,
            )
        else:
            composite = CompositeAudioClip(audio_segments)
            composites.append(composite)
            report(90, "Writing audio")
            composite.write_audiofile(
                output_path,
                codec=job.get("audio_codec") or "libmp3lame",
                logger=None,
            )
        if cancel_event.is_set():
            raise ConversionCancelled()
        report(100, "Render complete")
    finally:
        for clip in composites + opened:
            try:
                clip.close()
            except Exception:
                pass


class EditExportThread(QThread):
    progress_updated = pyqtSignal(dict)
    edit_finished = pyqtSignal(str, str, bool)  # job_id, output_dir, produced_files
    error_occurred = pyqtSignal(str)
    edit_cancelled = pyqtSignal(str)

    def __init__(self, job: dict):
        super().__init__()
        self.job = job
        self.job_id = uuid.uuid4().hex[:8]
        self.shared_progress: dict = {}
        self._cancel_event = threading.Event()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self._cancel_event.set()

    @staticmethod
    def _files(directory: str) -> set[str]:
        found = set()
        for root, _, names in os.walk(os.path.abspath(directory)):
            for name in names:
                found.add(os.path.join(root, name))
        return found

    def _run_timeline_render(self) -> None:
        output_dir = self.job["output_dir"]
        ext = self.job.get("output_ext") or (
            "mp4" if self.job.get("has_video") else "mp3"
        )
        before = self._files(output_dir)
        output_path = os.path.join(output_dir, f"timeline.{ext}")
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(output_dir, f"timeline_{counter}.{ext}")
            counter += 1

        def report(percent, message):
            self.progress_updated.emit(
                {
                    "progress": percent,
                    "message": message,
                    "status": "running",
                    "error": None,
                }
            )

        try:
            with FFmpegProcessTracker(self._cancel_event):
                render_timeline(self.job, self._cancel_event, output_path, report)
            if self._cancelled:
                self.progress_updated.emit(
                    {
                        "progress": 0,
                        "message": "Render cancelled",
                        "status": "cancelled",
                        "error": None,
                    }
                )
                self.edit_cancelled.emit(self.job_id)
                return
            produced = self._files(output_dir) - before
            self.progress_updated.emit(
                {
                    "progress": 100,
                    "message": "Render complete",
                    "status": "done",
                    "error": None,
                }
            )
            self.edit_finished.emit(self.job_id, output_dir, bool(produced))
        except SystemExit as exc:
            self.error_occurred.emit(str(exc) or "Rendering stopped early")
        except ConversionCancelled:
            self.progress_updated.emit(
                {
                    "progress": 0,
                    "message": "Render cancelled",
                    "status": "cancelled",
                    "error": None,
                }
            )
            self.edit_cancelled.emit(self.job_id)
        except Exception as exc:
            self.error_occurred.emit(f"{type(exc).__name__}: {exc}")

    def run(self) -> None:
        if self.job.get("mode") == "timeline":
            self._run_timeline_render()
            return
        temp_dir = None
        try:
            self.progress_updated.emit(
                {
                    "progress": None,
                    "message": "Preparing render...",
                    "status": "starting",
                    "error": None,
                }
            )
            temp_dir = tempfile.mkdtemp(prefix="any2any_edit_")
            steps, _ = build_steps(self.job, temp_dir)
            total_steps = max(1, len(steps))
            outputs_before = self._files(self.job["output_dir"])

            controller = Controller(
                job_id=self.job_id,
                shared_progress_dict=self.shared_progress,
                is_web=True,
            )
            controller.file_handler.cancel_event = self._cancel_event
            collected_files: dict[int, list[str]] = {}
            done_steps = 0
            error_holder: dict = {}
            work_done = threading.Event()

            def work():
                nonlocal done_steps
                try:
                    with FFmpegProcessTracker(self._cancel_event):
                        for index, step in enumerate(steps):
                            self.progress_updated.emit(
                                {
                                    "progress": int(100 * index / total_steps),
                                    "message": step.label,
                                    "status": "running",
                                    "error": None,
                                }
                            )
                            inputs = []
                            for segment in step.inputs:
                                if (
                                    isinstance(segment, tuple)
                                    and segment[0] == "@collect"
                                ):
                                    inputs.extend(collected_files.get(segment[1], []))
                                else:
                                    inputs.append(segment)
                            if not inputs:
                                raise RuntimeError(
                                    "No media segments were produced for the stitch pass"
                                )
                            before = (
                                self._files(step.output)
                                if step.collect_to is not None
                                else set()
                            )
                            controller.run(**step.as_kwargs(self.job, inputs))
                            if step.collect_to is not None:
                                produced = sorted(self._files(step.output) - before)
                                if not produced:
                                    raise RuntimeError(
                                        f"No output produced while trimming segment {step.collect_to + 1}"
                                    )
                                collected_files[step.collect_to] = produced
                            done_steps = index + 1
                except SystemExit as exc:
                    error_holder["error"] = str(exc) or "Rendering stopped early"
                except ConversionCancelled:
                    pass
                except BaseException as exc:
                    error_holder["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    work_done.set()

            worker = threading.Thread(target=work, daemon=True, name="edit-render")
            worker.start()

            last_snapshot = None
            while not work_done.is_set() and not self._cancelled:
                prog = self.shared_progress.get(self.job_id, {})
                progress = prog.get("progress")
                total = prog.get("total", 100)
                fraction = 0.0
                if progress is not None and total:
                    try:
                        fraction = min(1.0, max(0.0, float(progress) / float(total)))
                    except (TypeError, ValueError, ZeroDivisionError):
                        fraction = 0.0
                percent = int(100 * min(1.0, (done_steps + fraction) / total_steps))
                status = prog.get("status", "running")
                message = prog.get("message") or prog.get("status") or ""
                snapshot = (percent, message, status)
                if snapshot != last_snapshot:
                    self.progress_updated.emit(
                        {
                            "progress": percent,
                            "message": message,
                            "status": status,
                            "error": None,
                        }
                    )
                    last_snapshot = snapshot
                time.sleep(0.1)

            if self._cancelled:
                self.progress_updated.emit(
                    {
                        "progress": None,
                        "message": "Cancelling...",
                        "status": "cancelling",
                        "error": None,
                    }
                )
                while worker.is_alive():
                    worker.join(timeout=0.5)
                self.progress_updated.emit(
                    {
                        "progress": 0,
                        "message": "Render cancelled",
                        "status": "cancelled",
                        "error": None,
                    }
                )
                self.edit_cancelled.emit(self.job_id)
                return

            worker.join(timeout=30.0)
            if worker.is_alive():
                error_holder["error"] = "Render worker did not finish in time"

            if "error" in error_holder:
                self.progress_updated.emit(
                    {
                        "progress": None,
                        "message": error_holder["error"],
                        "status": "error",
                        "error": error_holder["error"],
                    }
                )
                self.error_occurred.emit(error_holder["error"])
                return

            produced = self._files(self.job["output_dir"]) - outputs_before
            self.progress_updated.emit(
                {
                    "progress": 100,
                    "message": "Render complete",
                    "status": "done",
                    "error": None,
                }
            )
            self.edit_finished.emit(self.job_id, self.job["output_dir"], bool(produced))
        except Exception as exc:
            self.error_occurred.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
