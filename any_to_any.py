import os
import re
import fitz
import time
import PyPDF2
import logging
import argparse
import subprocess
import numpy as np
import modules.language_support as lang
from PIL import Image
from pathlib import Path
from modules.category import Category
from watchdog.observers import Observer
from modules.prog_logger import ProgLogger
from modules.watchdog_handler import WatchDogFileHandler
from moviepy import (AudioFileClip, VideoFileClip, VideoClip,
                     ImageSequenceClip, ImageClip, concatenate_videoclips,
                     concatenate_audioclips, clips_array)

class AnyToAny:
    """
    Taking an input directory of mp4 files, convert them to a multitude of formats using moviepy.
    Interact with the script using the command line arguments defined at the bottom of this file.
    """

    def __init__(self):
        # Setting up progress logger
        self.prog_logger = ProgLogger()
        # Get locale
        self.locale = lang.get_system_language()
        # Setting up event logger and format
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.event_logger = logging.getLogger(__name__)
        # Setting up a dictionary of supported formats and respective information
        self._supported_formats = {
            Category.AUDIO: {
                "mp3": "libmp3lame",
                "flac": "flac",
                "aac": "aac",
                "ac3": "ac3",
                "dts": "dts",
                "ogg": "libvorbis",
                "wma": "wmav2",
                "wav": "pcm_s16le",
                "m4a": "aac",
                "aiff": "pcm_s16le",
                "weba": "libopus",
                "mka": "libvorbis",
                "wv": "wavpack",
                "tta": "tta",
                "m4b": "aac",
                "eac3": "eac3",
                "spx": "libvorbis",
                "mp2": "mp2",
                "caf": "pcm_s16be",
                "au": "pcm_s16be",
                "oga": "libvorbis",
                "opus": "libopus",
                "m3u8": "pcm_s16le",
                "w64": "pcm_s16le",
                "mlp": "mlp",
                "adts": "aac",
                "sbc": "sbc",
                "thd": "truehd",
            },
            Category.IMAGE: {
                "gif": self.to_gif,
                "png": self.to_frames,
                "jpeg": self.to_frames,
                "jpg": self.to_frames,
                "bmp": self.to_bmp,
                "webp": self.to_webp,
                "tiff": self.to_frames,
                "tga": self.to_frames,
                "ps": self.to_frames,
                "ico": self.to_frames,
                "eps": self.to_frames,
                "jpeg2000": self.to_frames,
                "im": self.to_frames,
                "pcx": self.to_frames,
                "ppm": self.to_frames,
            },
            Category.DOCUMENT: {
                "pdf": self.to_frames,
                "srt": self.to_subtitles,
            },
            Category.MOVIE: {
                "webm": "libvpx",
                "mov": "libx264",
                "mkv": "libx264",
                "avi": "libx264",
                "mp4": "libx264",
                "wmv": "wmv2",
                "flv": "libx264",
                "mjpeg": "mjpeg",
                "m2ts": "mpeg2video",
                "3gp": "libx264",
                "3g2": "libx264",
                "asf": "wmv2",
                "vob": "mpeg2video",
                "ts": "hevc",
                "raw": "rawvideo",
                "mpg": "mpeg2video",
                "mxf": "mpeg2video",
                "drc": "libx265",
                "swf": "flv",
                "f4v": "libx264",
                "m4v": "libx264",
                "mts": "mpeg2video",
                "m2v": "mpeg2video",
                "yuv": "rawvideo",
            },
            Category.MOVIE_CODECS: {
                "av1": ["libaom-av1", "mkv"],  # [lib, fallback]
                "avc": ["libx264", "mp4"],
                "vp9": ["libvpx-vp9", "mp4"],
                "h265": ["libx265", "mkv"],
                "h264": ["libx264", "mkv"],
                "h263p": ["h263p", "mkv"],
                "xvid": ["libxvid", "mp4"],
                "mpeg4": ["mpeg4", "mp4"],
                "theora": ["libtheora", "ogv"],
                "mpeg2": ["mpeg2video", "mp4"],
                "mpeg1": ["mpeg1video", "mp4"],
                "hevc": ["libx265", "mkv"],
                "prores": ["prores", "mkv"],
                "vp8": ["libvpx", "webm"],
                "huffyuv": ["huffyuv", "mkv"],
                "ffv1": ["ffv1", "mkv"],
                "ffvhuff": ["ffvhuff", "mkv"],
                "v210": ["v210", "mkv"],
                "v410": ["v410", "mkv"],
                "v308": ["v308", "mkv"],
                "v408": ["v408", "mkv"],
                "zlib": ["zlib", "mkv"],
                "qtrle": ["qtrle", "mkv"],
                "snow": ["snow", "mkv"],
                "svq1": ["svq1", "mkv"],
                "utvideo": ["utvideo", "mkv"],
                "cinepak": ["cinepak", "mkv"],
                "msmpeg4": ["msmpeg4", "mkv"],
                "h264_nvenc": ["h264_nvenc", "mp4"],
                "vpx": ["libvpx", "webm"],
                "h264_rgb": ["libx264rgb", "mkv"],
                "mpeg2video": ["mpeg2video", "mpg"],
                "prores_ks": ["prores_ks", "mkv"],
                "vc2": ["vc2", "mkv"],
                "flv1": ["flv", "flv"],
            },
            Category.PROTOCOLS: {
                "hls": ["hls", "mkv"],
                "dash": ["dash", "mkv"],
            },
        }

        # Used in CLI information output
        self.supported_formats = [
            format
            for formats in self._supported_formats.values()
            for format in formats.keys()
        ]

        self.web_flag = False # Indicates if the script is being run from the web interface
        self.web_host = None  # Host address for the web interface

    def _end_with_msg(self, exception: Exception, msg: str) -> None:
        # Single point of exit
        if exception is not None:
            self.event_logger.warning(msg)
            raise exception(msg)
        else:
            self.event_logger.info(msg)
            exit(1)

    def _audio_bitrate(self, format: str, quality: str) -> str:
        # Return bitrate for audio conversion
        # If formats allow for a higher bitrate, we shift our scale accordingly
        if format in [
            "flac",
            "wav",
            "aac",
            "aiff",
            "eac3",
            "dts",
            "au",
            "wv",
            "tta",
            "mlp",
        ]:
            return {
                "high": "500k",
                "medium": "320k",
                "low": "192k",
            }.get(quality, None)
        else:
            return {
                "high": "320k",
                "medium": "192k",
                "low": "128k",
            }.get(quality, None)

    def run(
        self,
        input_path_args: list,
        format: str,
        output: str,
        framerate: int,
        quality: str,
        merge: bool,
        concat: bool,
        delete: bool,
        across: bool,
        recursive: bool,
        dropzone: bool,
        language: str,
    ) -> None:
        # Main function, convert media files to defined formats
        # or merge or concatenate, according to the arguments
        input_paths = []
        input_path_args = (
            input_path_args
            if input_path_args is not None
            else [os.path.dirname(os.getcwd())]
        )

        self.across = across
        self.recursive = recursive

        # User-set Language
        if language is not None:
            # we expect a language code like "en_US" or "pl_PL"
            if re.match(r"^[a-z]{2}_[A-Z]{2}$", language) and language in list(lang.LANGUAGE_CODES.keys()):
                self.locale = lang.LANGUAGE_CODES[language]
            else:
                self.event_logger.warning(f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('lang_not_supported', self.locale)}")

        print()
        print(self.locale)
        print()

        for _, arg in enumerate(input_path_args):
            # Custom handling of multiple input paths
            # (e.g. "-1 path1 -2 path2 -n pathn")
            if arg.startswith("-") and arg[1:].isdigit():
                input_paths.append(arg[2:])
            else:
                try:
                    input_paths[-1] = (input_paths[-1] + f" {arg}").strip()
                except IndexError:
                    input_paths.append(arg)

        if len(input_paths) == 1:
            self.output = output if output is not None else input_paths[0]
        else:
            # len(input_paths) > 1
            if not across:
                self.output = output if output is not None else None
            else:
                self.output = (
                    output if output is not None else os.path.dirname(os.getcwd())
                )

        # Check if the output dir exists - Create it otherwise
        if self.output is not None and not os.path.exists(self.output):
            os.makedirs(self.output)

        # No format means no conversion (but maybe merge || concat)
        self.target_format = (format.lower() if format is not None else None)
        self.framerate = framerate  # Possibly no framerate means same as input
        self.delete = delete  # Delete mp4 files after conversion
        # Check if quality is set, if not, set it to None
        self.quality = (
            (quality.lower() if quality.lower() in ["high", "medium", "low"] else None)
            if quality is not None
            else None
        )

        # Merge movie files with equally named audio files
        self.merging = merge
        # Concatenate files of same type (img/movie/audio) back to back
        self.concatenating = concat

        file_paths = {}
        was_none = False
        found_files = False

        # Check if input paths are given
        for input_path in input_paths:
            input_path = os.path.abspath(input_path)
            file_paths = self._get_file_paths(input_path, file_paths)
            # Make self.input hold a directory
            if os.path.isfile(str(input_path)):
                self.input = os.path.dirname(input_path)
            else:
                self.input = input_path

            # If no output path set or derived by the script by now, throw an error
            if not self.output:
                self._end_with_msg(ValueError, f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('no_out_multi_in', self.locale)}")

            # If output is just a file for whatever reason, turn it into directory
            if os.path.isfile(self.output):
                self.output = os.path.dirname(self.output)

            # Unify path formatting, still works like any other string
            self.input, self.output = Path(self.input), Path(self.output)

            # Cut setup for media conversion short, begin dropzone mode
            if dropzone:
                if self.input == self.output or self.input in self.output.parents:
                    self._end_with_msg(None, f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('dropzone_diff', self.locale)}")
                self.event_logger.info(f"[+] {lang.get_translation('dropzone_active', self.locale)} {self.input}")
                self.watchdropzone(self.input)
                return

            # What if that directory contains subdirectories?
            if self.recursive:
                # Check if there is any subdirectory in the input path
                if any(entry.is_dir() for entry in os.scandir(self.input)):
                    file_paths = {} # Reset, we go through everything again to be sure
                    # If the user set the recursive option, also scan every non-empty subdirectory
                    for root, _, files in os.walk(self.input):
                        # root should be a directory with >=1 file to be considered
                        file_paths = self._get_file_paths(root, file_paths)

            if not any(file_paths.values()):
                if len(input_paths) > 1:
                    self.event_logger.info(f"[!] {lang.get_translation('no_media_found', self.locale).replace('[path]', f"'{str(input_path)}'")} - {lang.get_translation('skipping', self.locale)}")
                else:
                    self._end_with_msg(None, f"[!] {lang.get_translation('no_media_found', self.locale).replace('[path]', f"'{str(input_path)}'")}")
                continue

            # If no output given, output is set to the input path
            if not across:
                if self.output is None or was_none:
                    self.output = os.path.dirname(input_path)
                    was_none = True
                self.process_file_paths(file_paths)
                found_files = len(file_paths) > 0 if not found_files else found_files
                file_paths = {}

        # If multiple input paths are given, yet no output, output is set to the first input path
        if across:
            if self.output is None:
                self.output = os.path.dirname(input_paths[0])
            self.process_file_paths(file_paths)

        # Check if file_paths is empty
        if across and len(file_paths) == 0 or not found_files:
            self.event_logger.warning(f"{lang.get_translation('no_media_general', self.locale)}")
        self.event_logger.info(f"[+] {lang.get_translation('job_finished', self.locale)}")

    def process_file_paths(self, file_paths: dict) -> None:
        # Check if value associated to format is tuple/string or function to call specific conversion
        if self.target_format in self._supported_formats[Category.MOVIE].keys():
            self.to_movie(
                file_paths=file_paths,
                format=self.target_format,
                codec=self._supported_formats[Category.MOVIE][self.target_format],
            )
        elif self.target_format in self._supported_formats[Category.AUDIO].keys():
            self.to_audio(
                file_paths=file_paths,
                format=self.target_format,
                codec=self._supported_formats[Category.AUDIO][self.target_format],
            )
        elif self.target_format in self._supported_formats[Category.MOVIE_CODECS].keys():
            self.to_codec(
                file_paths=file_paths,
                codec=self._supported_formats[Category.MOVIE_CODECS][self.target_format],
            )
        elif self.target_format in self._supported_formats[Category.IMAGE].keys():
            self._supported_formats[Category.IMAGE][self.target_format](
                file_paths, self.target_format
            )
        elif self.target_format in self._supported_formats[Category.DOCUMENT].keys():
            self._supported_formats[Category.DOCUMENT][self.target_format](
                file_paths, self.target_format
            )
        elif self.target_format in self._supported_formats[Category.PROTOCOLS].keys():
            self.to_protocol(
                file_paths=file_paths,
                protocol=self._supported_formats[Category.PROTOCOLS][self.target_format],
            )
        elif self.merging:
            self.merge(file_paths, getattr(self, 'across', False))
        elif self.concatenating:
            self.concat(file_paths, self.target_format)
        else:
            # Handle unsupported formats here
            self._end_with_msg(
                ValueError,
                f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('output_list', self.locale).replace('[list]', str(list(self.supported_formats)))}",
            )

    def _get_file_paths(self, input: str, file_paths: dict = {}) -> dict:
        # Get media files from input directory
        def process_file(file_path: str) -> tuple:
            # Dissect "path/to/file.txt" into [path/to, file, txt]
            file_type = file_path.split(".")[-1].lower()
            file_name = os.path.basename(file_path)
            file_name = file_name[: file_name.rfind(".")]
            path_to_file = os.path.dirname(file_path) + os.sep
            return path_to_file, file_name, file_type

        def schedule_file(file_info: tuple) -> None:
            # If supported, add file to respective category schedule
            for category in self._supported_formats.keys():
                if file_info[2] in self._supported_formats[category]:
                    file_paths[category].append(file_info)
                    self.event_logger.info(f"[+] {lang.get_translation('scheduling', self.locale)}: {file_info[1]}.{file_info[2]}")
                    break

        self.event_logger.info(f"[>] {lang.get_translation('scanning', self.locale)}: {input}")

        # Check if file_paths is an empty dict
        if len(file_paths) == 0:
            file_paths = {category: [] for category in self._supported_formats}

        if input is not None and os.path.isfile(input):
            file_info = process_file(os.path.abspath(input))
            schedule_file(file_info)
        else:
            for directory in [input]:
                if not os.path.exists(directory):
                    self._end_with_msg(FileNotFoundError, f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('no_dir_exist', self.locale).replace('[dir]', f'{directory}')}")
            for file_name in os.listdir(input):
                file_path = os.path.abspath(os.path.join(input, file_name))
                file_info = process_file(file_path)
                schedule_file(file_info)
        return file_paths

    def watchdropzone(self, watch_path: str) -> None:
        # Watch a folder for new media files, process each as it arrives.
        watchdog_any = AnyToAny()

        # Setup a watchdog-specific AnyToAny instance
        # Link it to the current instance to share settings and loggers
        watchdog_any.target_format = self.target_format
        watchdog_any.output = self.output
        watchdog_any.framerate = self.framerate
        watchdog_any.quality = self.quality
        watchdog_any.merging = self.merging
        watchdog_any.concatenating = self.concatenating
        watchdog_any.delete = True
        watchdog_any.across = False
        watchdog_any.recursive = True
        watchdog_any.dropzone = False  # This one is not in dropzone mode
        watchdog_any.event_logger = self.event_logger
        watchdog_any.prog_logger = self.prog_logger
        
        event_handler = WatchDogFileHandler(watchdog_any)
        observer = Observer()
        observer.schedule(event_handler, watch_path, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1) # Polling interval, adjust as needed
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def _has_visuals(self, file_path_set: tuple) -> bool:
        try:
            VideoFileClip(self._join_back(file_path_set)).iter_frames()
            return True
        except Exception as _:
            pass
        return False

    def to_audio(self, file_paths: dict, format: str, codec: str) -> None:
        # Convert to audio
        # Audio to audio conversion
        for audio_path_set in file_paths[Category.AUDIO]:
            if audio_path_set[2] == format:
                continue
            audio = AudioFileClip(self._join_back(audio_path_set))
            # If recursive, create file outright where its source was found
            if not self.recursive or self.input != self.output:
                out_path = os.path.abspath(os.path.join(self.output, f"{audio_path_set[1]}.{format}"))
            else:
                out_path = os.path.abspath(os.path.join(audio_path_set[0], f"{audio_path_set[1]}.{format}"))
            # Write audio to file
            try:
                audio.write_audiofile(
                    out_path,
                    codec=codec,
                    bitrate=self._audio_bitrate(format, self.quality),
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
                    bitrate=self._audio_bitrate(format, self.quality),
                    fps=48000,
                    logger=self.prog_logger,
                )
            audio.close()
            self._post_process(audio_path_set, out_path, self.delete)

        # Movie to audio conversion
        for movie_path_set in file_paths[Category.MOVIE]:
            out_path = os.path.abspath(
                os.path.join(self.output, f"{movie_path_set[1]}.{format}")
            )

            if self._has_visuals(movie_path_set):
                video = VideoFileClip(
                    self._join_back(movie_path_set), audio=True, fps_source="tbr"
                )
                audio = video.audio
                # Check if audio was found
                if audio is None:
                    self.event_logger.info(
                        f'[!] {lang.get_translation('no_audio', self.locale).replace('[path]', f'"{self._join_back(movie_path_set)}"')} - {lang.get_translation('skipping', self.locale)}\n'
                    )
                    video.close()
                    continue

                audio.write_audiofile(
                    out_path,
                    codec=codec,
                    bitrate=self._audio_bitrate(format, self.quality),
                    logger=self.prog_logger,
                )

                audio.close()
                video.close()
            else:
                try:
                    # AudioFileClip works for audio-only video files
                    audio = AudioFileClip(self._join_back(movie_path_set))
                    audio.write_audiofile(
                        out_path,
                        codec=codec,
                        bitrate=self._audio_bitrate(format, self.quality),
                        logger=self.prog_logger,
                    )
                    audio.close()
                except Exception as _:
                    self.event_logger.info(
                        f'[!] {lang.get_translation('audio_extract_fail', self.locale).replace("[path]", f'"{self._join_back(movie_path_set)}"')} - {lang.get_translation('skipping', self.locale)}\n'
                    )
                    continue

            # Post process (delete mp4, print success)
            self._post_process(movie_path_set, out_path, self.delete)

    def to_codec(self, file_paths: dict, codec: dict) -> None:
        # Convert movie to same movie with different codec
        for codec_path_set in file_paths[Category.MOVIE]:
            if not self.recursive or self.input != self.output:
                out_path = os.path.abspath(os.path.join(self.output, f"{codec_path_set[1]}_{self.target_format}.{codec[1]}"))
            else:
                out_path = os.path.abspath(os.path.join(codec_path_set[0], f"{codec_path_set[1]}.{format}"))
            if self._has_visuals(codec_path_set):
                video = VideoFileClip(self._join_back(codec_path_set), audio=True, fps_source="tbr")
                try:
                    video.write_videofile(
                        out_path,
                        codec=codec[0],
                        fps=video.fps if self.framerate is None else self.framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                except Exception as _:
                    if os.path.exists(out_path):
                        # There might be some residue left, remove it
                        os.remove(out_path)
                    self.event_logger.info(
                        f"\n\n[!] {lang.get_translation('codec_fallback', self.locale).replace("[path]", f'"{codec_path_set[2]}"').replace("[format]", f'{codec[1]}')}\n"
                    )

                    video.write_videofile(
                        out_path,
                        codec=codec[0],
                        fps=video.fps if self.framerate is None else self.framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                video.close()
            else:
                # Audio-only video file
                audio = AudioFileClip(self._join_back(codec_path_set))

                # Create new VideoClip with audio only
                clip = VideoClip(
                    lambda t: np.zeros(
                        (16, 16, 3), dtype=np.uint8
                    ),  # 16 black pixels required by moviepy
                    duration=audio.duration,
                )
                clip = clip.set_audio(audio)
                clip.write_videofile(
                    out_path,
                    codec=codec[0],
                    fps=24 if self.framerate is None else self.framerate,
                    audio=True,
                    logger=self.prog_logger,
                )

                clip.close()
                audio.close()

            self._post_process(codec_path_set, out_path, self.delete)

    def to_movie(self, file_paths: dict, format: str, codec: str) -> None:
        # Convert to movie with specified format
        pngs = bmps = jpgs = []
        for image_path_set in file_paths[Category.IMAGE]:
            # Depending on the format, different fragmentation is required
            if image_path_set[2] == "gif":
                clip = VideoFileClip(self._join_back(image_path_set), audio=False)
                # If recursive, create file outright where its source was found
                if not self.recursive or self.input != self.output:
                    out_path = os.path.abspath(os.path.join(self.output, f"{image_path_set[1]}.{format}"))
                else:
                    out_path = os.path.abspath(os.path.join(image_path_set[0], f"{image_path_set[1]}.{format}"))
                clip.write_videofile(
                    out_path,
                    codec=codec,
                    fps=clip.fps if self.framerate is None else self.framerate,
                    audio=False,
                    logger=self.prog_logger,
                )
                clip.close()
                self._post_process(image_path_set, out_path, self.delete)
            elif image_path_set[2] == "png":
                pngs.append(ImageClip(self._join_back(image_path_set)).set_duration(1))
            elif image_path_set[2] == "jpeg":
                jpgs.append(ImageClip(self._join_back(image_path_set)).set_duration(1))
            elif image_path_set[2] == "bmp":
                bmps.append(ImageClip(self._join_back(image_path_set)).set_duration(1))

        # Pics to movie
        for pics in [pngs, jpgs, bmps]:
            if len(pics) > 0:
                final_clip = concatenate_videoclips(pics, method="compose")
                out_path = os.path.abspath(
                    os.path.join(self.output, f"merged.{format}")
                )
                final_clip.write_videofile(
                    out_path,
                    fps=24 if self.framerate is None else self.framerate,
                    codec=codec,
                    logger=self.prog_logger,
                )
                final_clip.close()

        # Movie to different movie
        for movie_path_set in file_paths[Category.MOVIE]:
            if not movie_path_set[2] == format:
                out_path = os.path.abspath(
                    os.path.join(self.output, f"{movie_path_set[1]}.{format}")
                )
                if self._has_visuals(movie_path_set):
                    video = VideoFileClip(
                        self._join_back(movie_path_set), audio=True, fps_source="tbr"
                    )
                    video.write_videofile(
                        out_path,
                        codec=codec,
                        fps=video.fps if self.framerate is None else self.framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                    video.close()
                else:
                    # Audio-only video file
                    audio = AudioFileClip(self._join_back(movie_path_set))

                    # Create new VideoClip with audio only
                    clip = VideoClip(
                        lambda t: np.zeros(
                            (16, 16, 3), dtype=np.uint8
                        ),  # 16 black pixels required by moviepy
                        duration=audio.duration,
                    )

                    clip = clip.set_audio(audio)

                    clip.write_videofile(
                        out_path,
                        codec=codec,
                        fps=24 if self.framerate is None else self.framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )

                    clip.close()
                    audio.close()

                self._post_process(movie_path_set, out_path, self.delete)

    def to_protocol(self, file_paths: dict, protocol: list) -> None:
        # Convert movie files into adaptive streaming formats HLS (.m3u8) or DASH (.mpd).
        if protocol[0] not in list(self._supported_formats[Category.PROTOCOLS].keys()):
            print("\n", protocol, "\n")
            self._end_with_msg(None, f"{lang.get_translation('unsupported_stream', self.locale)} {protocol[0]}")

        for movie_path_set in file_paths[Category.MOVIE]:
            input_file = os.path.abspath(self._join_back(movie_path_set))
            base_name = os.path.splitext(movie_path_set[-1])[0]
            current_out_dir = os.path.abspath(os.path.join(self.output, f"{base_name}_{protocol[0]}"))
            os.makedirs(current_out_dir, exist_ok=True)

            if protocol[0] == "hls":
                renditions = [("426x240", "400k", "64k"),
                              ("640x360", "800k", "96k"),
                              ("842x480", "1400k", "128k"),
                              ("1280x720", "2800k", "128k"),
                              ("1920x1080", "5000k", "192k")]
                variant_playlist = "#EXTM3U\n"
                cmd = ["ffmpeg", "-y", "-i", input_file]

                for i, (resolution, v_bitrate, a_bitrate) in enumerate(renditions):
                    os.makedirs(os.path.join(current_out_dir, f"{renditions[i][0]}"), exist_ok=True)
                    self.event_logger.info(f"[+] {lang.get_translation('get_hls', self.locale)} {self._join_back(movie_path_set)}: {resolution} at {v_bitrate} video, {a_bitrate} audio")
                    stream = [
                        "-map", "0:v:0",
                        "-map", "0:a:0",
                        "-c:v", "h264",
                        "-b:v", v_bitrate,
                        "-s", resolution,
                        "-c:a", "aac",
                        "-b:a", a_bitrate,
                        "-hls_time", "4",
                        "-hls_playlist_type", "vod",
                        "-hls_segment_filename", os.path.join(os.path.join(current_out_dir, f"{renditions[i][0]}"), f"{renditions[i][0]}_%03d.ts"),
                        os.path.join(os.path.join(current_out_dir, f"{renditions[i][0]}"), f"{renditions[i][0]}.m3u8")
                    ]
                    cmd += stream
                    variant_playlist += f'#EXT-X-STREAM-INF:BANDWIDTH={int(v_bitrate[:-1]) * 1000},RESOLUTION={resolution}\n{i}.m3u8\n'
                self.event_logger.info(f"[+] {lang.get_translation('get_hls_master', self.locale)} {self._join_back(movie_path_set)}")
                master_playlist_path = os.path.join(current_out_dir, "master.m3u8")

                try:
                    self._run_command(cmd)
                    with open(master_playlist_path, "w") as f:
                        f.write(variant_playlist)
                    self._post_process(movie_path_set, master_playlist_path, self.delete)
                except Exception as e:
                    self._end_with_msg(None, f"{lang.get_translation('get_hls_fail', self.locale)} {e}")
            elif protocol[0] == "dash":
                self.event_logger.info(f"[+] {lang.get_translation('create_dash', self.locale)} {self._join_back(movie_path_set)}")
                out_path = os.path.join(current_out_dir, "manifest.mpd")
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", input_file,
                    "-map", "0",
                    "-b:v", "1500k",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-bf", "1",
                    "-keyint_min", "120",
                    "-g", "120",
                    "-sc_threshold", "0",
                    "-b_strategy", "0",
                    "-ar", "48000",
                    "-use_timeline", "1",
                    "-use_template", "1",
                    "-adaptation_sets", "id=0,streams=v id=1,streams=a",
                    "-f", "dash",
                    out_path
                ]
                try:
                    self._run_command(cmd)
                    self._post_process(movie_path_set, out_path, self.delete)
                except Exception as e:
                    self._end_with_msg(movie_path_set, f"{lang.get_translation('dash_fail', self.locale)} {e}")

    def _run_command(self, command: list) -> None:
        try:
            _ = subprocess.run(command,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    check=True,
                                    text=True)
        except subprocess.CalledProcessError as e:
            error_msg = f"Error: {' '.join(command)}\n\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}"
            raise RuntimeError(error_msg)

    def to_subtitles(self, file_paths: dict, format: str) -> None:
        for movie_path_set in file_paths[Category.MOVIE]:
            input_path = self._join_back(movie_path_set)
            out_path = os.path.abspath(os.path.join(self.output, f"{movie_path_set[1]}.srt"))
            self.event_logger.info(f"[+] {lang.get_translation('extract_subtitles', self.locale)} '{input_path}'")
            try:
                # Use FFmpeg to extract subtitles
                _ = subprocess.run(["ffmpeg",
                                    "-i",
                                    input_path,
                                    "-map",
                                    "0:s:0",  # Selects first subtitle stream
                                    "-c:s",
                                    "srt",
                                    out_path],
                    capture_output=True,
                    text=True,
                )

                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    self.event_logger.info(f"[+] {lang.get_translation('subtitles_success', self.locale)} '{out_path}'")
                    self._post_process(
                        movie_path_set, out_path, self.delete, show_status=False
                    )
                else:
                    # Try extracting closed captions when direct extract fails (found mostly in MP4 and MKV)
                    self.event_logger.info(
                        f"[!] {lang.get_translation('extract_subtitles_alt', self.locale)}"
                    )
                    _ = subprocess.run(
                        ["ffmpeg", "-i", input_path, "-c:s", format, out_path],
                        capture_output=True,
                        text=True,
                    )
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        self.event_logger.info(
                            f"[+] {lang.get_translation('embed_subtitles_success')} '{out_path}'"
                        )
                        self._post_process(
                            movie_path_set, out_path, self.delete, show_status=False
                        )
                    else:
                        self.event_logger.info(f"[!] {lang.get_translation('embed_subtitles_fail', self.locale)} '{input_path}'")
            except Exception as e:
                self.event_logger.info(f"[!] {lang.get_translation('extract_subtitles_fail', self.locale)} {str(e)}")
                try:
                    subprocess.run(["ffmpeg", "-version"], capture_output=True)
                except FileNotFoundError:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('ffmpeg_not_found', self.locale)}"
                    )
                    break

    def to_frames(self, file_paths: dict, format: str) -> None:
        # Converting to image frame sets
        # This works for images and movies only
        format = "jpeg" if format == "jpg" else format
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == format:
                continue
            if image_path_set[2] == "gif":
                clip = VideoFileClip(self._join_back(image_path_set), audio=False)

                # Calculate zero-padding width based on total number of frames
                total_frames = int(clip.duration * clip.fps)
                num_digits = len(str(total_frames))

                # Create a dedicated folder for the gif to have its frames in
                os.makedirs(os.path.join(self.output, image_path_set[1]), exist_ok=True)

                for i, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8")):
                    frame_filename = f"{image_path_set[1]}-{i:0{num_digits}d}.{format}"
                    frame_path = os.path.abspath(os.path.join(self.output, image_path_set[1], frame_filename))
                    Image.fromarray(frame).save(frame_path, format=format.upper())

                clip.close()
                self._post_process(image_path_set, self.output, self.delete)
            else:
                if not os.path.exists(os.path.join(self.output, image_path_set[1])):
                    self.output = self.input
                img_path = os.path.abspath(
                    os.path.join(self.output, f"{image_path_set[1]}.{format}")
                )
                with Image.open(self._join_back(image_path_set)) as img:
                    img.convert("RGB").save(img_path, format=format)
                self._post_process(image_path_set, img_path, self.delete)

        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == format:
                continue
            if not os.path.exists(os.path.join(self.output, doc_path_set[1])):
                try:
                    os.makedirs(os.path.join(self.output, doc_path_set[1]))
                except OSError as e:
                    self.event_logger.info(f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {self.input}")
                    self.output = self.input

            if doc_path_set[2] == "pdf":
                # Per page, convert pdf to image
                pdf_path = self._join_back(doc_path_set)
                pdf = PyPDF2.PdfReader(pdf_path)
                img_path = os.path.abspath(
                    os.path.join(
                        os.path.join(self.output, doc_path_set[1]),
                        f"{doc_path_set[1]}-%{len(str(len(pdf.pages)))}d.{format}",
                    )
                )

                try:
                    os.makedirs(os.path.dirname(img_path), exist_ok=True)
                    self.output = os.path.dirname(img_path)
                except OSError as e:
                    self.event_logger.info(f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {self.input}")
                    self.output = self.input

                pdf_document = fitz.open(pdf_path)

                for page_num in range(len(pdf_document)):
                    pix = pdf_document[page_num].get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img_file = img_path % (page_num + 1)
                    img.save(img_file, format.upper())

                pdf_document.close()
                self._post_process(doc_path_set, img_path, self.delete)

        # Audio cant be image-framed, movies certrainly can
        for movie_path_set in file_paths[Category.MOVIE]:
            if movie_path_set[2] not in self._supported_formats[Category.MOVIE]:
                self.event_logger.info(f"[!] {lang.get_translation('movie_format_unsupported', self.locale)} {movie_path_set[2]} - {lang.get_translation('skipping', self.locale)}")
                continue
            if self._has_visuals(movie_path_set):
                video = VideoFileClip(
                    self._join_back(movie_path_set), audio=False, fps_source="tbr"
                )
                if not os.path.exists(os.path.join(self.output, movie_path_set[1])):
                    try:
                        os.makedirs(os.path.join(self.output, movie_path_set[1]))
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {self.input}"
                        )
                        self.output = self.input
                img_path = os.path.abspath(
                    os.path.join(
                        os.path.join(self.output, movie_path_set[1]),
                        f"{movie_path_set[1]}-%{len(str(int(video.duration * video.fps)))}d.{format}",
                    )
                )

                video.write_images_sequence(img_path, fps=video.fps, logger=self.prog_logger)
                video.close()
                self._post_process(movie_path_set, img_path, self.delete)
            else:
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(movie_path_set)}" - {lang.get_translation('audio_only_video', self.locale)}'
                )

            if format == "pdf":
                # Merge all freshly created 1-page pdfs into one big pdf
                pdf_out_path = os.path.join(
                    self.output, movie_path_set[1], "merged.pdf"
                )
                pdfs = [
                    os.path.join(self.output, movie_path_set[1], file)
                    for file in os.listdir(os.path.join(self.output, movie_path_set[1]))
                    if file.endswith("pdf")
                ]
                self.event_logger.info(f"[+] {lang.get_translation('merging_pdfs', self.locale).replace("[count]", str(len(pdfs))).replace("[path]", str(pdf_out_path))}")
                pdfs.sort()
                pdf_merger = PyPDF2.PdfMerger()
                for pdf in pdfs:
                    pdf_merger.append(pdf)
                pdf_merger.write(pdf_out_path)
                pdf_merger.close()
                for pdf in pdfs:
                    os.remove(pdf)
                self._post_process(movie_path_set, pdf_out_path, self.delete)
            else:
                self._post_process(movie_path_set, img_path, self.delete)

    def to_gif(self, file_paths: dict, format: str) -> None:
        # All images in the input directory are merged into one gif
        if len(file_paths[Category.IMAGE]) > 0:
            images = []
            for image_path_set in file_paths[Category.IMAGE]:
                if image_path_set[2] == format:
                    continue
                with Image.open(self._join_back(image_path_set)) as image:
                    images.append(image.convert("RGB"))
            images[0].save(
                os.path.join(self.output, f"merged.{format}"),
                save_all=True,
                append_images=images[1:],
            )

        # Movies are converted to gifs as well, retaining 1/3 of the frames
        for movie_path_set in file_paths[Category.MOVIE]:
            if self._has_visuals(movie_path_set):
                video = VideoFileClip(
                    self._join_back(movie_path_set), audio=False, fps_source="tbr"
                )
                gif_path = os.path.join(self.output, f"{movie_path_set[1]}.{format}")
                video.write_gif(gif_path, fps=video.fps // 3, logger=self.prog_logger)
                video.close()
                self._post_process(movie_path_set, gif_path, self.delete)
            else:
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(movie_path_set)}" - {lang.get_translation('audio_only_video', self.locale)}'
                )

    def to_bmp(self, file_paths: dict, format: str) -> None:
        # Movies are converted to bmps frame by frame
        for movie_path_set in file_paths[Category.MOVIE]:
            if self._has_visuals(movie_path_set):
                video = VideoFileClip(
                    self._join_back(movie_path_set), audio=False, fps_source="tbr"
                )
                bmp_path = os.path.join(self.output, f"{movie_path_set[1]}.{format}")
                # Split video into individual bmp frame images at original framerate
                for _, frame in enumerate(
                    video.iter_frames(fps=video.fps, dtype="uint8")
                ):
                    frame.save(
                        f"{bmp_path}-%{len(str(int(video.duration * video.fps)))}d.{format}",
                        format=format,
                    )
                self._post_process(movie_path_set, bmp_path, self.delete)
            else:
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(movie_path_set)}" - {lang.get_translation('audio_only_video', self.locale)}'
                )

        # Pngs and gifs are converted to bmps as well
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == format:
                continue
            if image_path_set[2] in ["png", "jpeg", "tiff", "tga", "eps"]:
                bmp_path = os.path.join(self.output, f"{image_path_set[1]}.{format}")
                with Image.open(self._join_back(image_path_set)) as img:
                    img.convert("RGB").save(bmp_path, format=format)
            elif image_path_set[2] == "gif":
                clip = VideoFileClip(self._join_back(image_path_set))
                for _, frame in enumerate(
                    clip.iter_frames(fps=clip.fps, dtype="uint8")
                ):
                    frame_path = os.path.join(
                        self.output,
                        f"{image_path_set[1]}-%{len(str(int(clip.duration * clip.fps)))}d.{format}",
                    )
                    Image.fromarray(frame).convert("RGB").save(
                        frame_path, format=format
                    )
            else:
                # Handle unsupported file types here
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(image_path_set)}" - {lang.get_translation('unsupported_format', self.locale)}'
                )

    def to_webp(self, file_paths: dict, format: str) -> None:
        # Convert frames in webp format
        # Movies are converted to webps, frame by frame
        for movie_path_set in file_paths[Category.MOVIE]:
            if self._has_visuals(movie_path_set):
                video = VideoFileClip(
                    self._join_back(movie_path_set), audio=False, fps_source="tbr"
                )
                if not os.path.exists(os.path.join(self.output, movie_path_set[1])):
                    try:
                        os.makedirs(os.path.join(self.output, movie_path_set[1]))
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {self.input}"
                        )
                        self.output = self.input
                img_path = os.path.abspath(
                    os.path.join(
                        os.path.join(self.output, movie_path_set[1]),
                        f"{movie_path_set[1]}-%{len(str(int(video.duration * video.fps)))}d.{format}",
                    )
                )
                video.write_images_sequence(img_path, fps=video.fps, logger=self.prog_logger)
                video.close()
                self._post_process(movie_path_set, img_path, self.delete)
            else:
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(movie_path_set)}" - {lang.get_translation('audio_only_video', self.locale)}'
                )

        # Pngs and gifs are converted to webps as well
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == format:
                continue
            if image_path_set[2] in ["png", "jpeg", "tiff", "tga", "eps"]:
                webp_path = os.path.join(self.output, f"{image_path_set[1]}.{format}")
                with Image.open(self._join_back(image_path_set)) as img:
                    img.convert("RGB").save(webp_path, format=format)
            elif image_path_set[2] == "gif":
                clip = VideoFileClip(self._join_back(image_path_set))
                for _, frame in enumerate(
                    clip.iter_frames(fps=clip.fps, dtype="uint8")
                ):
                    frame_path = os.path.join(
                        self.output,
                        f"{image_path_set[1]}-%{len(str(int(clip.duration * clip.fps)))}d.{format}",
                    )
                    Image.fromarray(frame).convert("RGB").save(
                        frame_path, format=format
                    )
            else:
                # Handle unsupported file types here
                self.event_logger.info(
                    f'[!] {lang.get_translation('skipping', self.locale)} "{self._join_back(image_path_set)}" - {lang.get_translation('unsupported_format', self.locale)}'
                )

    def concat(self, file_paths: dict, format: str) -> None:
        # Concatenate files of same type (img/movie/audio) back to back
        # Concatenate audio files
        if file_paths[Category.AUDIO] and (
            format is None or format in self._supported_formats[Category.AUDIO]
        ):
            concat_audio = concatenate_audioclips(
                [
                    AudioFileClip(self._join_back(audio_path_set))
                    for audio_path_set in file_paths[Category.AUDIO]
                ]
            )
            format = "mp3" if format is None else format
            audio_out_path = os.path.join(self.output, f"concatenated_audio.{format}")
            concat_audio.write_audiofile(
                audio_out_path,
                codec=self._supported_formats[Category.AUDIO][format],
                bitrate=self._audio_bitrate(format, self.quality)
                if self.quality is not None
                else getattr(concat_audio, 'bitrate', '192k'),
                logger=self.prog_logger,
            )
            concat_audio.close()
        # Concatenate movie files
        if file_paths[Category.MOVIE] and (
            format is None or format in self._supported_formats[Category.MOVIE]
        ):
            concat_vid = concatenate_videoclips(
                [
                    VideoFileClip(
                        self._join_back(movie_path_set), audio=True, fps_source="tbr"
                    )
                    for movie_path_set in file_paths[Category.MOVIE]
                ],
                method="compose",
            )
            format = "mp4" if format is None else format
            video_out_path = os.path.join(self.output, f"concatenated_video.{format}")
            concat_vid.write_videofile(
                video_out_path,
                fps=concat_vid.fps if self.framerate is None else concat_vid.fps,
                codec=self._supported_formats[Category.MOVIE][format],
                logger=self.prog_logger,
            )
            concat_vid.close()
        # Concatenate image files (make a gif out of them)
        if file_paths[Category.IMAGE] and (
            format is None or format in self._supported_formats[Category.IMAGE]
        ):
            gif_out_path = os.path.join(self.output, "concatenated_image.gif")
            concatenated_image = clips_array(
                [
                    [ImageClip(self._join_back(image_path_set)).set_duration(1)]
                    for image_path_set in file_paths[Category.IMAGE]
                ]
            )
            concatenated_image.write_gif(gif_out_path, fps=self.framerate, logger=self.prog_logger)

        for category in file_paths.keys():
            for i, file_path in enumerate(file_paths[category]):
                self._post_process(
                    file_path, self.output, self.delete, show_status=(i == 0)
                )
        self.event_logger.info(f"[+] {lang.get_translation('concat_success', self.locale)}")

    def merge(self, file_paths: dict, across: bool = False) -> None:
        # For movie files and equally named audio file, merge them together under same name
        # (movie with audio with '_merged' addition to name)
        # If only a video file is provided, look for a matching audio file in the same directory
        found_audio = False
        audio_exts = list(self._supported_formats[Category.AUDIO].keys())

        for movie_path_set in file_paths[Category.MOVIE]:
            # Try to find a corresponding audio file in the input set
            # (e.g. "-1 path1 -2 path2 -n pathn")
            if across:
                # Allow matching audio from any input directory
                audio_fit = next(
                    (
                        audio_set
                        for audio_set in file_paths[Category.AUDIO]
                        if audio_set[1] == movie_path_set[1]
                    ),
                    None,
                )
            else:
                # Only match audio from the same directory as the video
                audio_fit = next(
                    (
                        audio_set
                        for audio_set in file_paths[Category.AUDIO]
                        if audio_set[1] == movie_path_set[1] and audio_set[0] == movie_path_set[0]
                    ),
                    None,
                )

            # If not found, look for a matching audio file in the video's directory
            if audio_fit is None:
                video_dir = movie_path_set[0]
                video_basename = movie_path_set[1]
                for ext in audio_exts:
                    candidate = os.path.join(video_dir, f"{video_basename}.{ext}")
                    if os.path.isfile(candidate):
                        audio_fit = (video_dir, video_basename, ext)
                        break

            if audio_fit is not None:
                found_audio = True
                # Merge movie and audio file
                audio = None
                video = None
                try:
                    video = VideoFileClip(self._join_back(movie_path_set))
                    audio = AudioFileClip(self._join_back(audio_fit))
                    video = video.set_audio(audio)
                    merged_out_path = os.path.join(
                        self.output, f"{movie_path_set[1]}_merged.{movie_path_set[2]}"
                    )
                    video.write_videofile(
                        merged_out_path,
                        fps=video.fps if self.framerate is None else self.framerate,
                        codec=self._supported_formats[Category.MOVIE][movie_path_set[2]],
                        logger=self.prog_logger,
                    )
                finally:
                    if audio is not None:
                        audio.close()
                    if video is not None:
                        video.close()
                self._post_process(movie_path_set, merged_out_path, self.delete)
                # Only delete the audio file if it was in the input set, not if just found in dir
                if audio_fit in file_paths[Category.AUDIO]:
                    self._post_process(audio_fit, merged_out_path, self.delete, show_status=False)
            
        if not found_audio:
            self.event_logger.warning(f"[!] {lang.get_translation('no_audio_movie_match', self.locale)}")


    def _post_process(
        self,
        file_path_set: tuple,
        out_path: str,
        delete: bool,
        show_status: bool = True,
    ) -> None:
        # Post process after conversion, print, delete source file if desired
        if show_status:
            self.event_logger.info(
                f'[+] {lang.get_translation('converted', self.locale)} "{self._join_back(file_path_set)}" 🡢 "{out_path}"'
            )
        if delete:
            os.remove(self._join_back(file_path_set))
            self.event_logger.info(
                f'[-] {lang.get_translation('removed', self.locale)} "{self._join_back(file_path_set)}"'
            )

    def _join_back(self, file_path_set: tuple) -> str:
        # Join back the file path set to a concurrent path
        return os.path.abspath(
            f"{file_path_set[0]}{file_path_set[1]}.{file_path_set[2]}"
        )


if __name__ == "__main__":
    # An object is interacted with through a CLI-interface
    # Check if required libraries are installed
    for lib in ["moviepy", "PIL"]:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f"Please install {lib}: {ie}")
            exit(1)

    any_to_any = AnyToAny()

    parser = argparse.ArgumentParser(
        description=f"{lang.get_translation('description', any_to_any.locale)}",
    )
    parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        help=f"{lang.get_translation('input_help', any_to_any.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-o",
        "--output",
        help=f"{lang.get_translation('output_help', any_to_any.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-f",
        "--format",
        help=f"{lang.get_translation('format_help', any_to_any.locale)} ({', '.join(any_to_any.supported_formats)})",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-m",
        "--merge",
        help=f"{lang.get_translation('merge_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-c",
        "--concat",
        help=f"{lang.get_translation('concat_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-fps",
        "--framerate",
        help=f"{lang.get_translation('framerate_help', any_to_any.locale)}",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-q",
        "--quality",
        help=f"{lang.get_translation('quality_help', any_to_any.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delete",
        help=f"{lang.get_translation('delete_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-w",
        "--web",
        help=f"{lang.get_translation('web_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-a",
        "--across",
        help=f"{lang.get_translation('across_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-r",
        "--recursive",
        help=f"{lang.get_translation('recursive_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-z",
        "--dropzone",
        help=f"{lang.get_translation('dropzone_help', any_to_any.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-l",
        "--language",
        help=f"{lang.get_translation('locale_help', any_to_any.locale)}",
        type=str,
        required=False,
    )

    args = vars(parser.parse_args())

    if args["web"]:
        # Check for web frontend request
        if os.name in ["nt"]:
            subprocess.run("python ./web_to_any.py", shell=True)
        else:
            subprocess.run("python3 ./web_to_any.py", shell=True)
    else:
        # Run main function with parsed arguments
        any_to_any.run(
            input_path_args=args["input"],
            format=args["format"],
            output=args["output"],
            framerate=args["framerate"],
            quality=args["quality"],
            merge=args["merge"],
            concat=args["concat"],
            delete=args["delete"],
            across=args["across"],
            recursive=args["recursive"],
            dropzone=args["dropzone"],
            language=args["locale"],
        )
