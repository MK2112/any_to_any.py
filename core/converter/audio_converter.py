import os
import sys
import utils.language_support as lang

from utils.category import Category
from moviepy import AudioFileClip, VideoFileClip
from core.utils.file_handler import (
    effective_fps,
    run_parallel,
    worker_count_for,
)
from core.utils.time_ranges import (
    normalize_split_points,
    normalize_trim,
    plan_time_segments,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class AudioConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale
        self.default_audio_fps = 48000

    def _segment_out_path(
        self,
        path_set: tuple,
        format: str,
        recursive: bool,
        input: str,
        output: str,
        part_number: int = None,
    ) -> str:
        stem = path_set[1]
        if part_number is not None:
            stem = f"{stem}_part_{part_number}"
        if recursive and input == output:
            directory = path_set[0]
        else:
            directory = output
        return self.file_handler._resolve_output_file_conflict(
            os.path.abspath(os.path.join(directory, f"{stem}.{format}"))
        )

    def _write_segment(self, audio, out_path, codec, bitrate, format) -> None:
        try:
            audio.write_audiofile(
                out_path,
                codec=codec,
                bitrate=bitrate,
                fps=effective_fps(audio.fps, default=self.default_audio_fps)
                if format != "g722"
                else 16000,
                logger=self.prog_logger,
            )
        except Exception:
            self.file_handler.check_cancelled()
            self.event_logger.info(
                f"\n\n[!] {lang.get_translation('error', self.locale)}: "
                f"{lang.get_translation('source_rate_incompatible', self.locale).replace('[format]', f'{format}')}\n"
            )
            audio.write_audiofile(
                out_path,
                codec=codec,
                bitrate=bitrate,
                fps=self.default_audio_fps if format != "g722" else 16000,
                logger=self.prog_logger,
            )

    def _segments_for(self, clip, trim, split_at):
        segments = plan_time_segments(
            getattr(clip, "duration", None), trim, split_at
        )
        return [(None, None)] if segments is None else segments

    def to_audio(
        self,
        file_paths: dict,
        format: str,
        codec: str,
        recursive: bool,
        bitrate: str,
        input: str,
        output: str,
        delete: bool,
        trim=None,
        split_at=None,
    ) -> None:
        trim = normalize_trim(trim)
        split_at = normalize_split_points(split_at)
        time_edit = trim is not None or split_at is not None
        env_workers = worker_count_for(self.file_handler)

        def _convert_audio_file(audio_path_set: tuple):
            if audio_path_set[2] == format and not time_edit:
                return None
            audio = None
            out_paths = []
            pending_path = None
            try:
                audio = AudioFileClip(self.file_handler.join_back(audio_path_set))
                segments = self._segments_for(audio, trim, split_at)
                if not segments:
                    self.event_logger.warning(
                        f"[!] {lang.get_translation('skipping', self.locale)}: "
                        f'no valid time range for "{self.file_handler.join_back(audio_path_set)}"'
                    )
                    return None
                for index, (start, end) in enumerate(segments):
                    segment = (
                        audio if start is None else audio.subclipped(start, end)
                    )
                    out_path = self._segment_out_path(
                        audio_path_set,
                        format,
                        recursive,
                        input,
                        output,
                        index + 1 if split_at is not None else None,
                    )
                    pending_path = out_path
                    self._write_segment(segment, out_path, codec, bitrate, format)
                    out_paths.append((audio_path_set, out_path))
                    pending_path = None
                return out_paths or None
            except Exception as e:
                self.file_handler.check_cancelled()
                self.event_logger.error(
                    f"[!] {lang.get_translation('error', self.locale)} "
                    f"{self.file_handler.join_back(audio_path_set)}: {str(e)}"
                )
                for _, out_path in out_paths:
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                return None
            finally:
                try:
                    if audio is not None:
                        audio.close()
                finally:
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
            run_parallel(file_paths[Category.AUDIO], _convert_audio_file, env_workers),
        ):
            for src, out_path in results:
                self.file_handler.post_process(src, out_path, delete)

        def _extract_from_movie(movie_path_set: tuple):
            video, audio = None, None
            out_paths = []
            pending_path = None
            try:
                try:
                    video = VideoFileClip(
                        self.file_handler.join_back(movie_path_set),
                        audio=True,
                        fps_source="tbr",
                    )
                except Exception:
                    self.file_handler.check_cancelled()
                    video = None
                if video is not None and self.file_handler.has_visuals(
                    movie_path_set, clip=video
                ):
                    audio = video.audio
                    if audio is None:
                        movie_path_str = (
                            f'"{self.file_handler.join_back(movie_path_set)}"'
                        )
                        self.event_logger.info(
                            f"[!] {lang.get_translation('no_audio', self.locale).replace('[path]', movie_path_str)} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
                    segments = self._segments_for(audio, trim, split_at)
                else:
                    if video is not None:
                        video.close()
                        video = None
                    try:
                        audio = AudioFileClip(
                            self.file_handler.join_back(movie_path_set)
                        )
                    except Exception:
                        self.file_handler.check_cancelled()
                        movie_path_str = (
                            f'"{self.file_handler.join_back(movie_path_set)}"'
                        )
                        self.event_logger.info(
                            f"[!] {lang.get_translation('audio_extract_fail', self.locale).replace('[path]', movie_path_str)} - {lang.get_translation('skipping', self.locale)}\n"
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
                    segment = (
                        audio if start is None else audio.subclipped(start, end)
                    )
                    out_path = self._segment_out_path(
                        movie_path_set,
                        format,
                        recursive,
                        input,
                        output,
                        index + 1 if split_at is not None else None,
                    )
                    pending_path = out_path
                    segment.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        logger=self.prog_logger,
                    )
                    out_paths.append((movie_path_set, out_path))
                    pending_path = None
                return out_paths or None
            except Exception as e:
                self.file_handler.check_cancelled()
                self.event_logger.error(
                    f"[!] {lang.get_translation('error', self.locale)} "
                    f"{self.file_handler.join_back(movie_path_set)}: {str(e)}"
                )
                for _, out_path in out_paths:
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                return None
            finally:
                try:
                    if audio is not None:
                        audio.close()
                except Exception:
                    pass
                try:
                    if video is not None:
                        video.close()
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
            run_parallel(file_paths[Category.MOVIE], _extract_from_movie, env_workers),
        ):
            for src, out_path in results:
                self.file_handler.post_process(src, out_path, delete)
