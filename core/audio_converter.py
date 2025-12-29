import os
import utils.language_support as lang
from utils.category import Category
from moviepy import AudioFileClip, VideoFileClip
from concurrent.futures import ThreadPoolExecutor, as_completed


class AudioConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        # These aren't supposed to be copies, but, like here, references
        # to the original objects that got passed
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
        try:
            # Decide worker count with env variable if present
            # Prob most elegant in this setting
            env_workers = int(os.environ.get("Any2Any_MAX_WORKERS", "1"))
            env_workers = 1 if env_workers < 1 else env_workers
            env_workers = (
                os.cpu_count() - 1 if env_workers >= os.cpu_count() else env_workers
            )
        except ValueError:
            # If this variable doesn't exist, flag wasn't invoked: Default to 1
            env_workers = 1

        # Helper to convert a single audio file
        def _convert_audio_file(audio_path_set: tuple):
            if audio_path_set[2] == format:
                return None
            audio = None
            out_path = None
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
                try:
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        fps=audio.fps,
                        logger=self.prog_logger,
                    )
                except Exception as _:
                    self.event_logger.info(
                        f"\n\n[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('source_rate_incompatible', self.locale).replace('[format]', f'{format}')}\n"
                    )
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        fps=self.default_audio_fps,
                        logger=self.prog_logger,
                    )
                return (audio_path_set, out_path)
            finally:
                if audio is not None:
                    audio.close()

        audio_items = list(file_paths[Category.AUDIO])
        if len(audio_items) <= 1:
            # Fallback to sequential for 0/1 items
            result = _convert_audio_file(audio_items[0]) if audio_items else None
            if result is not None:
                src, out_path = result
                self.file_handler.post_process(src, out_path, delete)
        else:
            max_workers = env_workers if env_workers > 1 else 1
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_convert_audio_file, a) for a in audio_items]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res is None:
                        continue
                    src, out_path = res
                    self.file_handler.post_process(src, out_path, delete)

        # Movie to audio conversion
        def _extract_from_movie(movie_path_set: tuple):
            out_path_local = os.path.abspath(
                os.path.join(output, f"{movie_path_set[1]}.{format}")
            )
            video = None
            audio = None
            try:
                if self.file_handler.has_visuals(movie_path_set):
                    video = VideoFileClip(
                        self.file_handler.join_back(movie_path_set),
                        audio=True,
                        fps_source="tbr",
                    )
                    audio = video.audio
                    # Check if audio was found
                    if audio is None:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('no_audio', self.locale).replace('[path]', f'\"{self.file_handler.join_back(movie_path_set)}\"')} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
                    audio.write_audiofile(
                        out_path_local,
                        codec=codec,
                        bitrate=bitrate,
                        logger=self.prog_logger,
                    )
                else:
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
                        self.event_logger.info(
                            f"[!] {lang.get_translation('audio_extract_fail', self.locale).replace('[path]', f'"{self.file_handler.join_back(movie_path_set)}"')} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
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

        movie_items = list(file_paths[Category.MOVIE])
        if len(movie_items) <= 1:
            res = _extract_from_movie(movie_items[0]) if movie_items else None
            if res is not None:
                src, out_path = res
                self.file_handler.post_process(src, out_path, delete)
        else:
            with ThreadPoolExecutor(max_workers=env_workers) as ex:
                futures = [ex.submit(_extract_from_movie, m) for m in movie_items]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res is None:
                        continue
                    src, out_path = res
                    self.file_handler.post_process(src, out_path, delete)
