import os
import utils.language_support as lang
from utils.category import Category
from moviepy import AudioFileClip, VideoFileClip

class AudioConverter:

    def __init__(self, file_handler, prog_logger, event_logger, locale: str = "English"):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def to_audio(self,
                 file_paths: dict,
                 format: str,
                 codec: str,
                 recursive: bool,
                 bitrate: str,    # self._audio_bitrate(format, self.quality),
                 input: str,
                 output: str,
                 delete: str) -> None:
        # Audio to audio conversion
        for audio_path_set in file_paths[Category.AUDIO]:
            if audio_path_set[2] == format:
                continue
            audio = AudioFileClip(self.file_handler.join_back(audio_path_set))
            # If recursive, create file outright where its source was found
            if not recursive or input != output:
                out_path = os.path.abspath(os.path.join(output, f"{audio_path_set[1]}.{format}"))
            else:
                out_path = os.path.abspath(os.path.join(audio_path_set[0], f"{audio_path_set[1]}.{format}"))
            # Write audio to file
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
                    fps=48000,
                    logger=self.prog_logger,
                )
            audio.close()
            self.file_handler.post_process(audio_path_set, out_path, delete)

        # Movie to audio conversion
        for movie_path_set in file_paths[Category.MOVIE]:
            out_path = os.path.abspath(
                os.path.join(output, f"{movie_path_set[1]}.{format}")
            )

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
                        f"[!] {lang.get_translation('no_audio', self.locale).replace('[path]', f'"{self.file_handler.join_back(movie_path_set)}"')} - {lang.get_translation('skipping', self.locale)}\n"
                    )
                    video.close()
                    continue

                audio.write_audiofile(
                    out_path,
                    codec=codec,
                    bitrate=bitrate,
                    logger=self.prog_logger,
                )

                audio.close()
                video.close()
            else:
                try:
                    # AudioFileClip works for audio-only video files
                    audio = AudioFileClip(self.file_handler.join_back(movie_path_set))
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=bitrate,
                        logger=self.prog_logger,
                    )
                    audio.close()
                except Exception as _:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('audio_extract_fail', self.locale).replace('[path]', f'"{self.file_handler.join_back(movie_path_set)}"')} - {lang.get_translation('skipping', self.locale)}\n"
                    )
                    continue
            self.file_handler.post_process(movie_path_set, out_path, delete)