import os
import sys
import shutil
import subprocess
import numpy as np
import pymupdf as pypdf
import utils.language_support as lang

from PIL import Image
from tqdm import tqdm
from utils.category import Category
from core.utils.exit import end_with_msg
from core.converter.image_converter import office_to_frames
from core.utils.file_handler import safe_output_dir as _safe_out_dir
from core.utils.resolution import (
    available_resolutions,
    parse_resolution,
    resolution_allowed,
)
from core.utils.file_handler import (
    effective_fps,
    run_parallel,
    sort_frame_filenames,
    worker_count_for,
)
from core.utils.time_ranges import (
    normalize_split_points,
    normalize_trim,
    plan_time_segments,
)
from moviepy import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    concatenate_videoclips,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_AUDIO_PLACEHOLDER_WIDTH = 1280
_AUDIO_PLACEHOLDER_HEIGHT = 720
_FFMPEG_TIMEOUT_SECONDS = 3600
_FALLBACK_CODECS = {
    "mkv": "libx264",
    "mp4": "libx264",
    "webm": "libvpx",
    "ogv": "libtheora",
    "flv": "flv1",
    "mpg": "mpeg2video",
}


def _subtitles_filter(srt_path: str) -> str:
    # Escape a path for use as an ffmpeg subtitles filtergraph option
    escaped = os.path.abspath(srt_path)
    for char in ("\\", ":", "'", "[", "]", ",", ";"):
        escaped = escaped.replace(char, "\\" + char)
    return f"subtitles='{escaped}'"


class MovieConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def _segment_out_path(
        self,
        stem: str,
        format: str,
        directory: str,
        part_number: int = None,
    ) -> str:
        if part_number is not None:
            stem = f"{stem}_part_{part_number}"
        return self.file_handler._resolve_output_file_conflict(
            os.path.abspath(os.path.join(directory, f"{stem}.{format}"))
        )

    def _segments_for(self, clip, trim, split_at):
        segments = plan_time_segments(
            getattr(clip, "duration", None), trim, split_at
        )
        return [(None, None)] if segments is None else segments

    def _paired_subtitles(self, movie_path_set: tuple) -> str:
        # Same-stem .srt next to the movie (mirrors -f srt output naming)
        srt_path = os.path.join(movie_path_set[0], f"{movie_path_set[1]}.srt")
        return srt_path if os.path.isfile(srt_path) else None

    def _write_audio_only(
        self,
        out_path: str,
        audio,
        codec: str,
        framerate: int,
        resolution: str = None,
    ):
        # (Audio-only) Placeholder (black) video carries the audio track
        clip = ImageClip(
            np.zeros(
                (_AUDIO_PLACEHOLDER_HEIGHT, _AUDIO_PLACEHOLDER_WIDTH, 3),
                dtype=np.uint8,
            )
        )
        if resolution is not None:
            clip = clip.resized(new_size=parse_resolution(resolution))
        clip = clip.with_duration(audio.duration)
        clip = clip.with_fps(24 if framerate is None else framerate)
        clip = clip.with_audio(audio)
        clip.write_videofile(
            out_path,
            codec=codec,
            fps=24 if framerate is None else framerate,
            audio=True,
            logger=self.prog_logger,
        )
        return clip

    def _frames_to_movie(
        self,
        frames_dir: str,
        image_files: list,
        out_path: str,
        codec: str,
        framerate: int,
        resolution: str = None,
    ) -> None:
        # Stitch frame sequence together as movie
        image_files = sort_frame_filenames(image_files)
        image_clips = [
            ImageClip(os.path.join(frames_dir, img)).with_duration(
                (1 / framerate) if framerate is not None else 1 / 24
            )
            for img in image_files
        ]
        final_clip = concatenate_videoclips(image_clips, method="compose")

        if resolution is not None:
            final_clip = final_clip.resized(new_size=parse_resolution(resolution))

        try:
            final_clip.write_videofile(
                out_path,
                fps=24 if framerate is None else framerate,
                codec=codec,
                logger=self.prog_logger,
            )
        finally:
            final_clip.close()

    def to_movie(
        self,
        input: str,
        output: str,
        recursive: bool,
        file_paths: dict,
        format: str,
        framerate: int,
        codec: str,
        delete: bool,
        resolution: str = None,
        burn_subs: bool = False,
        trim=None,
        split_at=None,
    ) -> None:
        trim = normalize_trim(trim)
        split_at = normalize_split_points(split_at)
        time_edit = trim is not None or split_at is not None
        env_workers = worker_count_for(self.file_handler)

        # Helper for per-GIF conversion to video
        def _gif_to_video(image_path_set: tuple):
            clip = None
            try:
                clip = VideoFileClip(
                    self.file_handler.join_back(image_path_set), audio=False
                )
                if not recursive or input != output:
                    out_path = os.path.abspath(
                        os.path.join(output, f"{image_path_set[1]}.{format}")
                    )
                else:
                    out_path = os.path.abspath(
                        os.path.join(image_path_set[0], f"{image_path_set[1]}.{format}")
                    )

                out_path = self.file_handler._resolve_output_file_conflict(out_path)

                if resolution is not None:
                    clip = clip.resized(new_size=parse_resolution(resolution))

                clip.write_videofile(
                    out_path,
                    codec=codec,
                    fps=effective_fps(clip.fps, framerate),
                    audio=False,
                    logger=self.prog_logger,
                )
                return (image_path_set, out_path)
            finally:
                if clip:
                    clip.close()

        all_pics = []
        gif_paths = []

        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == "gif":
                gif_paths.append(image_path_set)
                continue
            try:
                clip = ImageClip(
                    self.file_handler.join_back(image_path_set)
                ).with_duration(1 / (framerate or 24))
            except Exception as e:
                self.event_logger.error(
                    f"[!] {lang.get_translation('error', self.locale)} "
                    f"converting {self.file_handler.join_back(image_path_set)}: {str(e)}"
                )
                continue
            all_pics.append((clip, image_path_set))
            # No post_process here, we just accumulated for processing

        all_pics.sort(key=lambda item: item[1][1])

        for res in filter(None, run_parallel(gif_paths, _gif_to_video, env_workers)):
            src, out_path = res
            self.file_handler.post_process(src, out_path, delete)

        # Pics to movie, exclude gifs, already individually converted
        if all_pics:
            final_clip = concatenate_videoclips(
                [clip for clip, _ in all_pics], method="compose"
            )
            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"merged.{format}"))
            )

            if resolution is not None:
                final_clip = final_clip.resized(new_size=parse_resolution(resolution))

            final_clip.write_videofile(
                out_path,
                fps=24 if framerate is None else framerate,
                codec=codec,
                logger=self.prog_logger,
            )
            final_clip.close()
            # Only report/remove sources that actually made it into the video
            merged_sources = [source for _, source in all_pics]
            for i, src in enumerate(merged_sources):
                self.file_handler.post_process(
                    src, out_path, delete, show_status=(i == 0)
                )

        # Movie to different movie (parallel per file)
        def _movie_to_movie(movie_path_set: tuple):
            srt_path = self._paired_subtitles(movie_path_set) if burn_subs else None
            if (
                movie_path_set[2] == format
                and not resolution
                and not framerate
                and srt_path is None
                and not time_edit
            ):
                return None
            if burn_subs and srt_path is None:
                self.event_logger.warning(
                    f"[!] No equally named .srt found for "
                    f"{self.file_handler.join_back(movie_path_set)} - "
                    f"subtitle burn-in skipped"
                )

            video = None
            audio = None
            edit_clip = None
            out_paths = []
            pending_path = None
            try:
                try:
                    video = VideoFileClip(
                        self.file_handler.join_back(movie_path_set), audio=True
                    )
                except Exception:
                    video = None
                if video is not None and self.file_handler.has_visuals(
                    movie_path_set, clip=video
                ):
                    edit_clip = video
                    if resolution is not None:
                        edit_clip = video.resized(
                            new_size=parse_resolution(resolution)
                        )
                    segments = self._segments_for(edit_clip, trim, split_at)
                    if not segments:
                        self.event_logger.warning(
                            f"[!] {lang.get_translation('skipping', self.locale)}: "
                            f'no valid time range for "{self.file_handler.join_back(movie_path_set)}"'
                        )
                        return None
                    for index, (start, end) in enumerate(segments):
                        segment = (
                            edit_clip
                            if start is None
                            else edit_clip.subclipped(start, end)
                        )
                        out_path_local = self._segment_out_path(
                            movie_path_set[1],
                            format,
                            output,
                            index + 1 if split_at is not None else None,
                        )
                        pending_path = out_path_local
                        segment.write_videofile(
                            out_path_local,
                            fps=effective_fps(segment.fps, framerate),
                            codec=codec,
                            audio=segment.audio is not None,
                            ffmpeg_params=(
                                ["-vf", _subtitles_filter(srt_path)]
                                if srt_path is not None
                                else None
                            ),
                            logger=self.prog_logger,
                        )
                        out_paths.append((movie_path_set, out_path_local))
                        pending_path = None
                    return out_paths
                if video is not None:
                    video.close()
                    video = None
                try:
                    audio = AudioFileClip(
                        self.file_handler.join_back(movie_path_set)
                    )
                except Exception:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('audio_only_video', self.locale)}: {self.file_handler.join_back(movie_path_set)} - {lang.get_translation('skipping', self.locale)}\n"
                    )
                    return None
                segments = self._segments_for(audio, trim, split_at)
                if not segments:
                    self.event_logger.warning(
                        f"[!] {lang.get_translation('skipping', self.locale)}: "
                        f'no valid time range for "{self.file_handler.join_back(movie_path_set)}"'
                    )
                    return None
                for index, (start, end) in enumerate(segments):
                    segment_audio = (
                        audio if start is None else audio.subclipped(start, end)
                    )
                    out_path_local = self._segment_out_path(
                        movie_path_set[1],
                        format,
                        output,
                        index + 1 if split_at is not None else None,
                    )
                    pending_path = out_path_local
                    video_clip = self._write_audio_only(
                        out_path_local,
                        segment_audio,
                        codec,
                        framerate,
                        resolution,
                    )
                    try:
                        video_clip.close()
                    except Exception:
                        pass
                    out_paths.append((movie_path_set, out_path_local))
                    pending_path = None
                return out_paths
            finally:
                if edit_clip is not None:
                    try:
                        edit_clip.close()
                    except Exception:
                        pass
                elif video is not None:
                    try:
                        video.close()
                    except Exception:
                        pass
                if audio is not None:
                    try:
                        audio.close()
                    except Exception:
                        pass
                if (
                    isinstance(pending_path, (str, bytes, os.PathLike))
                    and os.path.isfile(pending_path)
                ):
                    try:
                        os.remove(pending_path)
                    except OSError:
                        pass

        for results in filter(
            None,
            run_parallel(file_paths[Category.MOVIE], _movie_to_movie, env_workers),
        ):
            for src, out_path in results:
                self.file_handler.post_process(src, out_path, delete)

        # Document to movie (because why the hell not)
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] in ("docx", "pptx"):
                # Convert to list of images first
                # Stitch that together, convert to movie
                frames_dir = office_to_frames(
                    doc_path_set,
                    "jpeg",
                    output,
                    False,
                    self.file_handler,
                    self.event_logger,
                    prog_logger=self.prog_logger,
                )
                frames_owned = isinstance(frames_dir, str) and bool(frames_dir)
                if not frames_owned:
                    frames_dir = os.path.join(output, doc_path_set[1])
                # This creates a folder named docx_path_set[1] in the output directory
                # with all the images in it
                # Now we can convert that to a movie
                try:
                    try:
                        pics = [
                            image
                            for image in os.listdir(frames_dir)
                            if image.lower().endswith(".jpeg")
                        ]
                    except OSError:
                        pics = []
                    if pics:
                        out_path = self.file_handler._resolve_output_file_conflict(
                            os.path.abspath(
                                os.path.join(output, f"{doc_path_set[1]}.{format}")
                            )
                        )
                        self._frames_to_movie(
                            frames_dir, pics, out_path, codec, framerate, resolution
                        )
                        self.file_handler.post_process(doc_path_set, out_path, delete)
                finally:
                    try:
                        _abs_frames = os.path.abspath(frames_dir)
                        _abs_out = os.path.abspath(output)
                        if (
                            frames_owned
                            and _abs_frames != _abs_out
                            and _abs_frames.startswith(_abs_out + os.sep)
                        ):
                            shutil.rmtree(frames_dir)
                            self.file_handler.release_claim(frames_dir)
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e}"
                        )
            elif doc_path_set[2] == "pdf":
                pdf_path = self.file_handler.join_back(doc_path_set)
                movie_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{doc_path_set[1]}.{format}"))
                )

                image_files = []
                # Never reuse output/<basename> as scratch (C2): it may hold
                # pre-existing user data which rmtree would then delete.
                scratch_dir = _safe_out_dir(os.path.join(output, doc_path_set[1]))
                scratch_owned = not os.path.exists(scratch_dir)
                if not os.path.exists(scratch_dir):
                    try:
                        os.makedirs(scratch_dir, exist_ok=True)
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                        )
                        output = input
                        scratch_dir = _safe_out_dir(
                            os.path.join(output, doc_path_set[1])
                        )
                        scratch_owned = not os.path.exists(scratch_dir)
                        os.makedirs(scratch_dir, exist_ok=True)
                completed = False
                try:
                    doc = pypdf.open(pdf_path)
                    total_pages = len(doc)
                    for i, page_num in tqdm(enumerate(range(total_pages))):
                        self.prog_logger.update_shared(
                            f"{doc_path_set[1]} ({i + 1}/{total_pages})",
                            i + 1,
                            total_pages,
                        )
                        pix = doc.load_page(page_num).get_pixmap()
                        img = Image.frombytes(
                            "RGB", [pix.width, pix.height], pix.samples
                        )
                        img = img.convert("RGB")
                        # Save each page as a separate JPEG file
                        img.save(
                            os.path.join(
                                scratch_dir,
                                f"{doc_path_set[1]}-{i:0{len(str(total_pages))}}.jpeg",
                            ),
                            format="JPEG",
                        )
                        image_files.append(
                            f"{doc_path_set[1]}-{i:0{len(str(total_pages))}}.jpeg"
                        )
                    doc.close()

                    # Convert the JPEG files to a video
                    self._frames_to_movie(
                        scratch_dir,
                        image_files,
                        movie_path,
                        codec,
                        framerate,
                        resolution,
                    )
                    completed = True
                except Exception as e:
                    self.file_handler.check_cancelled()
                    self.event_logger.error(
                        f"[!] {lang.get_translation('error', self.locale)} "
                        f"{pdf_path}: {str(e)}"
                    )
                finally:
                    try:
                        _abs_scratch = os.path.abspath(scratch_dir)
                        _abs_out = os.path.abspath(output)
                        if (
                            scratch_owned
                            and _abs_scratch != _abs_out
                            and _abs_scratch.startswith(_abs_out + os.sep)
                        ):
                            shutil.rmtree(scratch_dir)
                            self.file_handler.release_claim(scratch_dir)
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e}"
                        )
                if completed:
                    self.file_handler.post_process(doc_path_set, movie_path, delete)

    def to_codec(
        self,
        input: str,
        output: str,
        format: str,
        recursive: bool,
        file_paths: dict,
        framerate: int,
        codec: dict,
        delete: bool,
        resolution: str = None,
        burn_subs: bool = False,
        trim=None,
        split_at=None,
    ) -> None:
        trim = normalize_trim(trim)
        split_at = normalize_split_points(split_at)
        for codec_path_set in file_paths[Category.MOVIE]:
            srt_path = (
                self._paired_subtitles(codec_path_set) if burn_subs else None
            )
            directory = (
                output
                if not recursive or input != output
                else codec_path_set[0]
            )
            base_stem = f"{codec_path_set[1]}_{format}"
            video = None
            audio = None
            editor = None
            try:
                try:
                    video = VideoFileClip(
                        self.file_handler.join_back(codec_path_set),
                        audio=True,
                        fps_source="tbr",
                    )
                except Exception:
                    video = None
                if video is not None and self.file_handler.has_visuals(
                    codec_path_set, clip=video
                ):
                    editor = video
                    if resolution is not None:
                        editor = video.resized(new_size=parse_resolution(resolution))
                    segments = self._segments_for(editor, trim, split_at)
                    if not segments:
                        self.event_logger.warning(
                            f"[!] {lang.get_translation('skipping', self.locale)}: "
                            f'no valid time range for "{self.file_handler.join_back(codec_path_set)}"'
                        )
                        continue
                    for index, (start, end) in enumerate(segments):
                        segment = (
                            editor if start is None else editor.subclipped(start, end)
                        )
                        out_path = self._segment_out_path(
                            base_stem,
                            codec[1],
                            directory,
                            index + 1 if split_at is not None else None,
                        )
                        try:
                            segment.write_videofile(
                                out_path,
                                codec=codec[0],
                                fps=effective_fps(segment.fps, framerate),
                                audio=segment.audio is not None,
                                ffmpeg_params=(
                                    ["-vf", _subtitles_filter(srt_path)]
                                    if srt_path is not None
                                    else None
                                ),
                                logger=self.prog_logger,
                            )
                        except Exception:
                            if os.path.exists(out_path):
                                os.remove(out_path)
                            codec_path_str = f'"{codec_path_set[2]}"'
                            self.event_logger.info(
                                f"\n\n[!] {lang.get_translation('codec_fallback', self.locale).replace('[path]', codec_path_str).replace('[format]', f'{codec[1]}')}\n"
                            )
                            segment.write_videofile(
                                out_path,
                                codec=_FALLBACK_CODECS.get(codec[1], codec[0]),
                                fps=effective_fps(segment.fps, framerate),
                                audio=segment.audio is not None,
                                ffmpeg_params=(
                                    ["-vf", _subtitles_filter(srt_path)]
                                    if srt_path is not None
                                    else None
                                ),
                                logger=self.prog_logger,
                            )
                        self.file_handler.post_process(
                            codec_path_set, out_path, delete
                        )
                else:
                    if video is not None:
                        video.close()
                        video = None
                    audio = AudioFileClip(
                        self.file_handler.join_back(codec_path_set)
                    )
                    segments = self._segments_for(audio, trim, split_at)
                    if not segments:
                        self.event_logger.warning(
                            f"[!] {lang.get_translation('skipping', self.locale)}: "
                            f'no valid time range for "{self.file_handler.join_back(codec_path_set)}"'
                        )
                        continue
                    for index, (start, end) in enumerate(segments):
                        segment_audio = (
                            audio if start is None else audio.subclipped(start, end)
                        )
                        out_path = self._segment_out_path(
                            base_stem,
                            codec[1],
                            directory,
                            index + 1 if split_at is not None else None,
                        )
                        clip = self._write_audio_only(
                            out_path,
                            segment_audio,
                            codec[0],
                            framerate,
                            resolution,
                        )
                        clip.close()
                        self.file_handler.post_process(
                            codec_path_set, out_path, delete
                        )
            finally:
                if editor is not None and editor is not video:
                    try:
                        editor.close()
                    except Exception:
                        pass
                if video is not None:
                    try:
                        video.close()
                    except Exception:
                        pass
                if audio is not None:
                    try:
                        audio.close()
                    except Exception:
                        pass

    def to_protocol(
        self,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # self._supported_formats
        protocol: list,
        delete: bool,
        resolution: str = None,
    ) -> None:
        # Convert movie files into adaptive streaming formats HLS (.m3u8) or DASH (.mpd).
        if protocol[0] not in list(supported_formats[Category.PROTOCOLS].keys()):
            end_with_msg(
                self.event_logger,
                None,
                f"{lang.get_translation('unsupported_stream', self.locale)} {protocol[0]}",
            )

        for movie_path_set in file_paths[Category.MOVIE]:
            input_file = os.path.abspath(self.file_handler.join_back(movie_path_set))
            base_name = movie_path_set[1]
            current_out_dir = _safe_out_dir(
                os.path.abspath(os.path.join(output, f"{base_name}_{protocol[0]}"))
            )
            os.makedirs(current_out_dir, exist_ok=True)

            if protocol[0] == "hls":
                renditions = [
                    ("426x240", "400k", "64k"),
                    ("640x360", "800k", "96k"),
                    ("854x480", "1400k", "128k"),
                    ("1280x720", "2800k", "128k"),
                    ("1920x1080", "5000k", "192k"),
                ]
                if resolution is not None:
                    matching = [r for r in renditions if r[0] == resolution]
                    if not matching:
                        available = ", ".join(r[0] for r in renditions)
                        end_with_msg(
                            self.event_logger,
                            ValueError,
                            f"[!] {lang.get_translation('error', self.locale)}: "
                            f"Resolution '{resolution}' is not supported for 'hls'. "
                            f"Available resolutions for 'hls': {available}.",
                        )
                    renditions = matching
                variant_playlist = "#EXTM3U\n"
                cmd = ["ffmpeg", "-y", "-i", input_file]

                for i, (resolution, v_bitrate, a_bitrate) in enumerate(renditions):
                    if not os.path.exists(
                        os.path.join(current_out_dir, f"{renditions[i][0]}")
                    ):
                        os.makedirs(
                            os.path.join(current_out_dir, f"{renditions[i][0]}"),
                            exist_ok=True,
                        )
                    self.event_logger.info(
                        f"[>] {lang.get_translation('get_hls', self.locale)} {self.file_handler.join_back(movie_path_set)}: {resolution} at {v_bitrate} video, {a_bitrate} audio"
                    )
                    width, height = resolution.split("x")
                    stream = [
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a?",
                        "-c:v",
                        "libx264",
                        "-b:v",
                        v_bitrate,
                        "-vf",
                        f"scale={width}:{height}",
                        "-c:a",
                        "aac",
                        "-b:a",
                        a_bitrate,
                        "-hls_time",
                        "4",
                        "-hls_playlist_type",
                        "vod",
                        "-hls_segment_filename",
                        os.path.join(
                            os.path.join(current_out_dir, f"{renditions[i][0]}"),
                            f"{renditions[i][0]}_%03d.ts",
                        ),
                        os.path.join(
                            os.path.join(current_out_dir, f"{renditions[i][0]}"),
                            f"{renditions[i][0]}.m3u8",
                        ),
                    ]
                    cmd += stream
                    variant_playlist += f"#EXT-X-STREAM-INF:BANDWIDTH={(int(v_bitrate[:-1]) + int(a_bitrate[:-1])) * 1000},RESOLUTION={resolution}\n{resolution}/{resolution}.m3u8\n"
                self.event_logger.info(
                    f"[>] {lang.get_translation('get_hls_master', self.locale)} {self.file_handler.join_back(movie_path_set)}"
                )
                master_playlist_path = os.path.join(current_out_dir, "master.m3u8")

                try:
                    self._run_command(cmd)
                    with open(master_playlist_path, "w") as f:
                        f.write(variant_playlist)
                    self.file_handler.post_process(
                        movie_path_set, master_playlist_path, delete
                    )
                except Exception as e:
                    end_with_msg(
                        self.event_logger,
                        None,
                        f"{lang.get_translation('get_hls_fail', self.locale)} {e}",
                    )
            elif protocol[0] == "dash":
                self.event_logger.info(
                    f"[>] {lang.get_translation('create_dash', self.locale)} {self.file_handler.join_back(movie_path_set)}"
                )
                out_path = os.path.join(current_out_dir, "manifest.mpd")
                scale_filter = None
                if resolution is not None:
                    if not resolution_allowed(
                        supported_formats[Category.PROTOCOLS], protocol[0], resolution
                    ):
                        available = available_resolutions(
                            supported_formats[Category.PROTOCOLS], protocol[0]
                        )
                        end_with_msg(
                            self.event_logger,
                            ValueError,
                            f"[!] {lang.get_translation('error', self.locale)}: "
                            f"Resolution '{resolution}' is not supported for 'dash'. "
                            f"Available resolutions for 'dash': {', '.join(available)}.",
                        )
                    width, height = resolution.split("x")
                    scale_filter = f"scale={width}:{height}"
                cmd = ["ffmpeg", "-y", "-i", input_file]
                if scale_filter is not None:
                    cmd += ["-vf", scale_filter]
                cmd += [
                    "-map",
                    "0",
                    "-b:v",
                    "1500k",
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-bf",
                    "1",
                    "-keyint_min",
                    "120",
                    "-g",
                    "120",
                    "-sc_threshold",
                    "0",
                    "-b_strategy",
                    "0",
                    "-ar",
                    "48000",
                    "-use_timeline",
                    "1",
                    "-use_template",
                    "1",
                    "-adaptation_sets",
                    "id=0,streams=v id=1,streams=a",
                    "-f",
                    "dash",
                    out_path,
                ]
                try:
                    self._run_command(cmd)
                    self.file_handler.post_process(movie_path_set, out_path, delete)
                except Exception as e:
                    end_with_msg(
                        self.event_logger,
                        None,
                        f"{lang.get_translation('dash_fail', self.locale)} {e}",
                    )

    def _run_command(self, command: list, timeout: int = None) -> None:
        if timeout is None:
            timeout = _FFMPEG_TIMEOUT_SECONDS
        try:
            subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            error_msg = f"Error: {' '.join(command)}\n\nTimed out after {timeout}s"
            raise RuntimeError(error_msg) from e
        except subprocess.CalledProcessError as e:
            error_msg = f"Error: {' '.join(command)}\n\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}"
            raise RuntimeError(error_msg)
