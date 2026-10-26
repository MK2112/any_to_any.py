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

    def to_audio(
        self,
        file_paths: dict,
        format: str,
        codec: str,
        recursive: bool,
        bitrate: str,  # self._audio_bitrate(format, self.quality),
        input: str,
        output: str,
        delete: bool,
    ) -> None:
        env_workers = worker_count_for(self.file_handler)

        # Helper, converts a single audio file
        def _convert_audio_file(audio_path_set: tuple):
            if audio_path_set[2] == format:
                return None  # Skip conversion from target format
            audio = None
            out_path = None
            completed = False
            try:
                audio = AudioFileClip(self.file_handler.join_back(audio_path_set))
                # If recursive, create file outright where its source was found
                if not recursive or input != output:
                    out_path = os.path.abspath(
                        os.path.join(output, f"{audio_path_set[1]}.{format}")
                    )
                else:
                    out_path = os.path.abspath(
                        os.path.join(audio_path_set[0], f"{audio_path_set[1]}.{format}")
                    )

                out_path = self.file_handler._resolve_output_file_conflict(out_path)

                try:
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        fps=effective_fps(audio.fps, default=self.default_audio_fps)
                        if format != "g722"
                        else 16000,  # g722 clamps to 16kHz
                        logger=self.prog_logger,
                    )
                except Exception as _:
                    self.file_handler.check_cancelled()
                    self.event_logger.info(
                        f"\n\n[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('source_rate_incompatible', self.locale).replace('[format]', f'{format}')}\n"
                    )
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        fps=self.default_audio_fps if format != "g722" else 16000,
                        logger=self.prog_logger,
                    )
                completed = True
                return (audio_path_set, out_path)
            finally:
                try:
                    if audio is not None:
                        audio.close()
                finally:
                    if (
                        not completed
                        and isinstance(out_path, (str, bytes, os.PathLike))
                        and os.path.isfile(out_path)
                    ):
                        try:
                            os.remove(out_path)
                        except OSError:
                            pass

        for res in filter(
            None,
            run_parallel(file_paths[Category.AUDIO], _convert_audio_file, env_workers),
        ):
            src, out_path = res
            self.file_handler.post_process(src, out_path, delete)

        # Movie to audio conversion
        def _extract_from_movie(movie_path_set: tuple):
            out_path_local = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"{movie_path_set[1]}.{format}"))
            )

            video, audio = None, None
            completed = False
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
                    # Check if audio was found
                    if audio is None:
                        movie_path_str = (
                            f'"{self.file_handler.join_back(movie_path_set)}"'
                        )
                        self.event_logger.info(
                            f"[!] {lang.get_translation('no_audio', self.locale).replace('[path]', movie_path_str)} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
                    audio.write_audiofile(
                        out_path_local,
                        codec=codec,
                        bitrate=bitrate,
                        logger=self.prog_logger,
                    )
                else:
                    if video is not None:
                        video.close()
                        video = None
                    try:
                        # AudioFileClip works for audio-only video files
                        audio = AudioFileClip(
                            self.file_handler.join_back(movie_path_set)
                        )
                        audio.write_audiofile(
                            out_path_local,
                            codec=codec,
                            bitrate=bitrate,
                            logger=self.prog_logger,
                        )
                    except Exception as _:
                        self.file_handler.check_cancelled()
                        movie_path_str = (
                            f'"{self.file_handler.join_back(movie_path_set)}"'
                        )
                        self.event_logger.info(
                            f"[!] {lang.get_translation('audio_extract_fail', self.locale).replace('[path]', movie_path_str)} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
                completed = True
                return (movie_path_set, out_path_local)
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
                    not completed
                    and isinstance(out_path_local, (str, bytes, os.PathLike))
                    and os.path.isfile(out_path_local)
                ):
                    try:
                        os.remove(out_path_local)
                    except OSError:
                        pass

        for res in filter(
            None,
            run_parallel(file_paths[Category.MOVIE], _extract_from_movie, env_workers),
        ):
            src, out_path = res
            self.file_handler.post_process(src, out_path, delete)
