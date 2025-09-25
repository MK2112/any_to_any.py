import os
import re
import fitz
import time
import logging
import threading
import utils.language_support as lang
from pathlib import Path
from utils.category import Category
from utils.prog_logger import ProgLogger
from core.utils.exit import end_with_msg
from core.audio_converter import AudioConverter
from core.movie_converter import MovieConverter
from core.utils.file_handler import FileHandler
from core.image_converter import ImageConverter
from core.doc_converter import DocumentConverter
from core.utils.directory_watcher import DirectoryWatcher
from moviepy import (
    AudioFileClip,
    VideoFileClip,
    ImageClip,
    concatenate_videoclips,
    concatenate_audioclips,
    clips_array,
)


class Controller:
    """
    Taking an input directory of files, convert them to a multitude of formats.
    Interact with the script using the command line arguments or the web interface.
    Run via any_to_any.py script.
    """

    def __init__(self, job_id=None, shared_progress_dict=None, locale=None):
        # Setting up progress logger with optional web progress tracking
        self.prog_logger = ProgLogger(
            job_id=job_id, shared_progress_dict=shared_progress_dict
        )
    
        self.locale = lang.get_system_language() if locale is None else locale
        # Setting up event logger and format
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.event_logger = logging.getLogger(__name__)
        self.file_handler = FileHandler(self.event_logger, self.locale)
        # Setup distinct converters
        self.audio_converter = AudioConverter(
            self.file_handler, self.prog_logger, self.event_logger, self.locale
        )
        self.movie_converter = MovieConverter(
            self.file_handler, self.prog_logger, self.event_logger, self.locale
        )
        self.doc_converter = DocumentConverter(
            self.file_handler, self.prog_logger, self.event_logger, self.locale
        )
        self.image_converter = ImageConverter(
            self.file_handler, self.prog_logger, self.event_logger, self.locale
        )
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
                "gif": self.image_converter.to_gif,
                "png": self.image_converter.to_frames,
                "jpeg": self.image_converter.to_frames,
                "jpg": self.image_converter.to_frames,
                "bmp": self.image_converter.to_bmp,
                "webp": self.image_converter.to_webp,
                "tiff": self.image_converter.to_frames,
                "tga": self.image_converter.to_frames,
                "ps": self.image_converter.to_frames,
                "ico": self.image_converter.to_frames,
                "eps": self.image_converter.to_frames,
                "jpeg2000": self.image_converter.to_frames,
                "im": self.image_converter.to_frames,
                "pcx": self.image_converter.to_frames,
                "ppm": self.image_converter.to_frames,
            },
            Category.DOCUMENT: {
                "md": self.doc_converter.to_markdown,
                "pdf": self.doc_converter.to_pdf,
                "docx": self.doc_converter.to_office,
                "pptx": self.doc_converter.to_office,
                "srt": self.doc_converter.to_subtitles,
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

        # Indicates if the script is being run from the web interface
        self.web_flag = False
        # Host address for the web interface
        self.web_host = None
        # Quality step indicators
        self.high, self.medium, self.low = "high", "medium", "low"

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
                self.high: "500k",
                self.medium: "320k",
                self.low: "192k",
            }.get(quality, None)
        else:
            return {
                self.high: "320k",
                self.medium: "192k",
                self.low: "128k",
            }.get(quality, None)

    def run(
        self,
        input_path_args: list,
        format: str,
        output: str,
        framerate: int,
        quality: str,
        split: str,
        merge: bool,
        concat: bool,
        delete: bool,
        across: bool,
        recursive: bool,
        dropzone: bool,
        language: str,
        workers: int,
    ) -> None:
        # Convert media files to defined formats or 
        # merge or concatenate, according to the arguments
        #
        # Set environment for worker count
        if workers is not None:
            try:
                os.environ["A2A_MAX_WORKERS"] = str(max(1, int(workers)))
            except Exception:
                pass

        # Prepare input paths
        input_path_args = (
            input_path_args
            if input_path_args is not None
            else [os.path.dirname(os.getcwd())]
        )
        input_paths = []
        for _, arg in enumerate(input_path_args):
            if arg.startswith("-") and arg[1:].isdigit():
                input_paths.append(arg[2:])
            else:
                try:
                    input_paths[-1] = (input_paths[-1] + f" {arg}").strip()
                except IndexError:
                    input_paths.append(arg)

        # Set flags and parameters
        self.across = across
        self.recursive = recursive
        self.merging = merge
        self.concatenating = concat
        self.page_ranges = split
        self.target_format = format.lower() if format is not None else None
        self.framerate = framerate
        self.delete = delete
        self.quality = (
            (
                quality.lower()
                if quality and quality.lower() in [self.high, self.medium, self.low]
                else None
            )
            if quality is not None
            else None
        )

        # Language setting if not set already
        if language is not None and self.locale is None:
            if re.match(r"^[a-z]{2}_[A-Z]{2}$", language) and language in list(
                lang.LANGUAGE_CODES.keys()
            ):
                self.locale = lang.LANGUAGE_CODES[language]
            else:
                self.event_logger.warning(
                    f"[!] {lang.get_translation('lang_not_supported', self.locale)}"
                )

        # Output path
        if len(input_paths) == 1:
            self.output = output if output is not None else input_paths[0]
        else:
            self.output = (
                output
                if output is not None
                else (os.path.dirname(os.getcwd()) if across else None)
            )

        if self.output is not None and not os.path.exists(self.output):
            os.makedirs(self.output)

        file_paths = {}
        was_none, found_files = False, False
        for input_path in input_paths:
            input_path = os.path.abspath(input_path)
            try:
                file_paths = self.file_handler.get_file_paths(
                    input_path, file_paths, self._supported_formats
                )
            except FileNotFoundError:
                end_with_msg(
                    self.event_logger,
                    FileNotFoundError,
                    f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('no_dir_exist', self.locale).replace('[dir]', f'{input_path}')}",
                )
            self.input = Path(input_path)
            self.output = Path(self.output)

            if not self.output:
                end_with_msg(
                    self.event_logger,
                    ValueError,
                    f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('no_out_multi_in', self.locale)}",
                )
            if os.path.isfile(self.output):
                self.output = os.path.dirname(self.output)

            # Dropzone
            if dropzone:
                if self.input == self.output or self.input in self.output.parents:
                    end_with_msg(
                        self.event_logger,
                        None,
                        f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('dropzone_diff', self.locale)}",
                    )
                self.event_logger.info(
                    f"[>] {lang.get_translation('dropzone_active', self.locale)} {self.input}"
                )
                self.watchdropzone(self.input)
                return

            # Recursion
            if self.recursive:
                if any(entry.is_dir() for entry in os.scandir(self.input)):
                    file_paths = {}
                    for root, _, files in os.walk(self.input):
                        try:
                            file_paths = self.file_handler.get_file_paths(
                                root, file_paths, self._supported_formats
                            )
                        except FileNotFoundError:
                            end_with_msg(
                                self.event_logger,
                                FileNotFoundError,
                                f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('no_dir_exist', self.locale).replace('[dir]', f'{root}')}",
                            )

            if not any(file_paths.values()):
                if len(input_paths) > 1:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('no_media_found', self.locale).replace('[path]', f"'{str(input_path)}'")} - {lang.get_translation('skipping', self.locale)}"
                    )
                else:
                    end_with_msg(
                        self.event_logger,
                        None,
                        f"[!] {lang.get_translation('no_media_found', self.locale).replace('[path]', f"'{str(input_path)}'")}",
                    )
                continue

            if not across:
                if self.output is None or was_none:
                    self.output = os.path.dirname(input_path)
                    was_none = True
                self.process_file_paths(file_paths)
                found_files = len(file_paths) > 0 if not found_files else found_files
                file_paths = {}

        if across:
            if self.output is None:
                self.output = os.path.dirname(input_paths[0])
            self.process_file_paths(file_paths)

        if (across and len(file_paths) == 0) or not found_files:
            self.event_logger.warning(
                f"{lang.get_translation('no_media_general', self.locale)}"
            )
        self.event_logger.info(
            f"[+] {lang.get_translation('job_finished', self.locale)}"
        )

    def process_file_paths(self, file_paths: dict) -> None:
        # Check if value associated to format is tuple/string or function to call specific conversion
        if self.target_format in self._supported_formats[Category.MOVIE].keys():
            self.movie_converter.to_movie(
                input=self.input,
                output=self.output,
                recursive=self.recursive,
                file_paths=file_paths,
                format=self.target_format,
                framerate=self.framerate,
                codec=self._supported_formats[Category.MOVIE][self.target_format],
                delete=self.delete,
            )
        elif self.target_format in self._supported_formats[Category.AUDIO].keys():
            self.audio_converter.to_audio(
                file_paths=file_paths,
                format=self.target_format,
                codec=self._supported_formats[Category.AUDIO][self.target_format],
                recursive=self.recursive,
                bitrate=self._audio_bitrate(self.target_format, self.quality),
                input=self.input,
                output=self.output,
                delete=self.delete,
            )
        elif (
            self.target_format in self._supported_formats[Category.MOVIE_CODECS].keys()
        ):
            self.movie_converter.to_codec(
                input=self.input,
                output=self.output,
                format=self.target_format,
                recursive=self.recursive,
                file_paths=file_paths,
                framerate=self.framerate,
                codec=self._supported_formats[Category.MOVIE_CODECS][
                    self.target_format
                ],
                delete=self.delete,
            )
        elif self.target_format in self._supported_formats[Category.IMAGE].keys():
            self._supported_formats[Category.IMAGE][self.target_format](
                self.input,
                self.output,
                file_paths,
                self._supported_formats,
                self.framerate,
                self.target_format,
                self.delete,
            )
        elif self.target_format in self._supported_formats[Category.DOCUMENT].keys():
            self._supported_formats[Category.DOCUMENT][self.target_format](
                self.output, file_paths, self.target_format, self.delete
            )
        elif self.target_format in self._supported_formats[Category.PROTOCOLS].keys():
            self.movie_converter.to_protocol(
                output=self.output,
                file_paths=file_paths,
                supported_formats=self._supported_formats,
                protocol=self._supported_formats[Category.PROTOCOLS][
                    self.target_format
                ],
                delete=self.delete,
            )
        elif self.merging:
            self.merge(file_paths, getattr(self, "across", False))
        elif self.concatenating:
            self.concat(file_paths, self.target_format)
        elif self.page_ranges is not None:
            self.split(file_paths, self.page_ranges)
        else:
            # Handle unsupported formats here
            end_with_msg(
                self.event_logger,
                ValueError,
                f"[!] {lang.get_translation('error', self.locale)}: {lang.get_translation('output_list', self.locale).replace('[list]', str(list(self.supported_formats)))}",
            )

    def watchdropzone(self, watch_path: str) -> None:
        # Watch a directory for new files and process them automatically
        def handle_file_event(event_type: str, file_path: str) -> None:
            if event_type == "created":
                try:
                    self.event_logger.info(
                        f"[>] {lang.get_translation('dropzone_new_file', self.locale)}: {file_path}"
                    )
                    if os.path.isfile(file_path):
                        # Create a temporary instance within, with distinct settings
                        dropzone_controller = self.__class__()
                        # Configure the instance with current settings
                        dropzone_controller.output = self.output
                        dropzone_controller.delete = (
                            True  # Delete original files after processing
                        )
                        dropzone_controller.locale = self.locale
                        dropzone_controller.framerate = self.framerate
                        dropzone_controller.quality = self.quality
                        dropzone_controller.merging = self.merging
                        dropzone_controller.concatenating = self.concatenating
                        dropzone_controller.recursive = True
                        dropzone_controller.event_logger = self.event_logger
                        dropzone_controller.file_handler = self.file_handler

                        # Process the file
                        file_paths = dropzone_controller.file_handler.get_file_paths(
                            [file_path]
                        )
                        if file_paths:
                            try:
                                dropzone_controller.process_files(file_paths)
                            except Exception as e:
                                self.event_logger.error(
                                    f"{lang.get_translation('error', self.locale)}: {file_path} - {str(e)}"
                                )
                except Exception as e:
                    self.event_logger.error(
                        f"{lang.get_translation('error', self.locale)}: {file_path} - {str(e)}"
                    )

        try:
            # Validate watch path
            watch_path = os.path.abspath(watch_path)
            if not os.path.exists(watch_path):
                self.event_logger.error(
                    f"{lang.get_translation('not_exist_not_dir', self.locale)}: {watch_path}"
                )
                return
            if not os.path.isdir(watch_path):
                self.event_logger.error(
                    f"{lang.get_translation('watch_not_dir', self.locale)}: {watch_path}"
                )
                return

            self.event_logger.info(
                f"[>] {lang.get_translation('watch_start', self.locale)}: {watch_path}"
            )
            self.event_logger.info(
                f"[>] {lang.get_translation('watch_stop', self.locale)}"
            )

            # Start the directory watcher with error handling
            with DirectoryWatcher(watch_path, handle_file_event) as watcher:
                watcher.watch()

        except KeyboardInterrupt:
            self.event_logger.info(
                f"\n[!] {lang.get_translation('watch_halt', self.locale)}"
            )
        except Exception as e:
            self.event_logger.error(
                f"{lang.get_translation('error', self.locale)}: {str(e)}"
            )
            raise

    def split(self, file_paths: dict, page_ranges) -> None:
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if (
                hasattr(self.prog_logger, "shared_progress_dict")
                and self.prog_logger.shared_progress_dict
            ):
                with threading.Lock():
                    if self.prog_logger.job_id in self.prog_logger.shared_progress_dict:
                        self.prog_logger.shared_progress_dict[
                            self.prog_logger.job_id
                        ].update(
                            {
                                "status": f"splitting {doc_path_set[1]}",
                                "last_updated": time.time(),
                            }
                        )
            if doc_path_set[2] == "pdf":
                self.doc_converter.split_pdf(
                    output=self.output,
                    doc_path_set=doc_path_set,
                    format="pdf",
                    delete=self.delete,
                    page_ranges=page_ranges,
                )

    def concat(self, file_paths: dict, format: str) -> None:
        # Concatenate files of same type (img/movie/audio) back to back
        # Concatenate audio files
        if file_paths[Category.AUDIO] and (
            format is None or format in self._supported_formats[Category.AUDIO]
        ):
            concat_audio = concatenate_audioclips(
                [
                    AudioFileClip(self.file_handler.join_back(audio_path_set))
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
                else getattr(concat_audio, "bitrate", "192k"),
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
                        self.file_handler.join_back(movie_path_set),
                        audio=True,
                        fps_source="tbr",
                    )
                    for movie_path_set in file_paths[Category.MOVIE]
                ],
                method="compose",
            )
            format = "mp4" if format is None else format
            video_out_path = os.path.join(self.output, f"concatenated_video.{format}")
            concat_vid.write_videofile(
                video_out_path,
                fps=concat_vid.fps if self.framerate is None else self.framerate,
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
                    [
                        ImageClip(
                            self.file_handler.join_back(image_path_set)
                        ).with_duration(
                            1 / 12 if self.framerate is None else 1 / self.framerate
                        )
                    ]
                    for image_path_set in file_paths[Category.IMAGE]
                ]
            )
            concatenated_image.write_gif(
                gif_out_path, fps=self.framerate, logger=self.prog_logger
            )
            concatenated_image.close()  # Added for consistency

        # Concatenate document files (keep respective document format)
        if file_paths[Category.DOCUMENT] and (
            format is None or format in self._supported_formats[Category.DOCUMENT]
        ):
            pdf_out_path = os.path.join(self.output, "concatenated.pdf")
            pdfs = sorted(
                [
                    doc_path_set if doc_path_set[2] == "pdf" else None
                    for doc_path_set in file_paths[Category.DOCUMENT]
                ],
                key=lambda x: x[1] if x else "",  # Handle None values
            )
            pdfs = [pdf for pdf in pdfs if pdf is not None]  # Filter out None values

            srt_out_path = os.path.join(self.output, "concatenated_subtitles.srt")
            srts = sorted(
                [
                    doc_path_set if doc_path_set[2] == "srt" else None
                    for doc_path_set in file_paths[Category.DOCUMENT]
                ],
                key=lambda x: x[1] if x else "",  # Handle None values
            )
            srts = [srt for srt in srts if srt is not None]  # Filter out None values

            if len(pdfs) > 0:
                # Produce a single pdf file
                # Set up manual progress tracking for PDF concatenation
                if hasattr(self.prog_logger, "job_id") and self.prog_logger.job_id:
                    total_pdfs = len(pdfs)
                    for i, doc_path_set in enumerate(pdfs):
                        # Update progress manually since PDF operations don't have built-in progress
                        if (
                            hasattr(self.prog_logger, "shared_progress_dict")
                            and self.prog_logger.shared_progress_dict
                        ):
                            with threading.Lock():
                                if (
                                    self.prog_logger.job_id
                                    in self.prog_logger.shared_progress_dict
                                ):
                                    self.prog_logger.shared_progress_dict[
                                        self.prog_logger.job_id
                                    ].update(
                                        {
                                            "progress": i,
                                            "total": total_pdfs,
                                            "status": f"processing PDF {i + 1}/{total_pdfs}",
                                            "last_updated": time.time(),
                                        }
                                    )

                doc = fitz.open()
                for doc_path_set in pdfs:
                    pdf_path = self.file_handler.join_back(doc_path_set)
                    pdf_document = fitz.open(pdf_path)
                    doc.insert_pdf(pdf_document)
                    pdf_document.close()
                doc.save(pdf_out_path)
                doc.close()

            if len(srts) > 0:
                # Set up manual progress tracking for SRT concatenation
                if hasattr(self.prog_logger, "job_id") and self.prog_logger.job_id:
                    total_srts = len(srts)
                    for i, doc_path_set in enumerate(srts):
                        # Update progress manually
                        if (
                            hasattr(self.prog_logger, "shared_progress_dict")
                            and self.prog_logger.shared_progress_dict
                        ):
                            with threading.Lock():
                                if (
                                    self.prog_logger.job_id
                                    in self.prog_logger.shared_progress_dict
                                ):
                                    self.prog_logger.shared_progress_dict[
                                        self.prog_logger.job_id
                                    ].update(
                                        {
                                            "progress": i,
                                            "total": total_srts,
                                            "status": f"processing SRT {i + 1}/{total_srts}",
                                            "last_updated": time.time(),
                                        }
                                    )

                for doc_path_set in srts:
                    # Produce a single srt file
                    srt_path = self.file_handler.join_back(doc_path_set)
                    with open(srt_path, "r") as srt_file:
                        srt_content = srt_file.read()
                    # Insert the SRT content into the concatenated file
                    with open(srt_out_path, "a") as srt_file:
                        srt_file.write(srt_content)
                        srt_file.write("\n")

        # Post-processing with progress tracking
        total_categories = sum(len(files) for files in file_paths.values())
        processed_files = 0

        for category in file_paths.keys():
            # Iterate over each input category and post-process respective files
            for i, file_path in enumerate(file_paths[category]):
                # Manual progress update for post-processing
                if hasattr(self.prog_logger, "job_id") and self.prog_logger.job_id:
                    if (
                        hasattr(self.prog_logger, "shared_progress_dict")
                        and self.prog_logger.shared_progress_dict
                    ):
                        with threading.Lock():
                            if (
                                self.prog_logger.job_id
                                in self.prog_logger.shared_progress_dict
                            ):
                                self.prog_logger.shared_progress_dict[
                                    self.prog_logger.job_id
                                ].update(
                                    {
                                        "progress": processed_files,
                                        "total": total_categories,
                                        "status": f"post-processing files ({processed_files + 1}/{total_categories})",
                                        "last_updated": time.time(),
                                    }
                                )

                self.file_handler.post_process(
                    file_path, self.output, self.delete, show_status=(i == 0)
                )
                processed_files += 1

        self.event_logger.info(
            f"[+] {lang.get_translation('concat_success', self.locale)}"
        )

    def merge(self, file_paths: dict, across: bool = False) -> None:
        # For movie files and equally named audio file, merge them together under same name
        # (movie with audio with '_merged' addition to name)
        # If only a video file is provided, look for a matching audio file in the same directory
        found_audio = False
        audio_exts = list(self._supported_formats[Category.AUDIO].keys())

        total_movies = len(file_paths[Category.MOVIE])
        processed_movies = 0

        for movie_path_set in file_paths[Category.MOVIE]:
            # Manual progress update for merge operations
            if hasattr(self.prog_logger, "job_id") and self.prog_logger.job_id:
                if (
                    hasattr(self.prog_logger, "shared_progress_dict")
                    and self.prog_logger.shared_progress_dict
                ):
                    with threading.Lock():
                        if (
                            self.prog_logger.job_id
                            in self.prog_logger.shared_progress_dict
                        ):
                            self.prog_logger.shared_progress_dict[
                                self.prog_logger.job_id
                            ].update(
                                {
                                    "progress": processed_movies,
                                    "total": total_movies,
                                    "status": f"merging video {processed_movies + 1}/{total_movies}",
                                    "last_updated": time.time(),
                                }
                            )

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
                        if audio_set[1] == movie_path_set[1]
                        and audio_set[0] == movie_path_set[0]
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
                    video = VideoFileClip(self.file_handler.join_back(movie_path_set))
                    audio = AudioFileClip(self.file_handler.join_back(audio_fit))
                    video = video.with_audio(audio)
                    merged_out_path = os.path.join(
                        self.output, f"{movie_path_set[1]}_merged.{movie_path_set[2]}"
                    )
                    video.write_videofile(
                        merged_out_path,
                        fps=video.fps if self.framerate is None else self.framerate,
                        codec=self._supported_formats[Category.MOVIE][
                            movie_path_set[2]
                        ],
                        logger=self.prog_logger,
                    )
                except Exception as e:
                    # Handle errors gracefully and update progress logger
                    if hasattr(self.prog_logger, "set_error"):
                        self.prog_logger.set_error(
                            f"Error merging {movie_path_set[1]}: {str(e)}"
                        )
                    raise
                finally:
                    if audio is not None:
                        audio.close()
                    if video is not None:
                        video.close()

                self.file_handler.post_process(
                    movie_path_set, merged_out_path, self.delete
                )
                # Only delete the audio file if it was in the input set, not if just found in dir
                if audio_fit in file_paths[Category.AUDIO]:
                    self.file_handler.post_process(
                        audio_fit, merged_out_path, self.delete, show_status=False
                    )

            processed_movies += 1

        if not found_audio:
            self.event_logger.warning(
                f"[!] {lang.get_translation('no_audio_movie_match', self.locale)}"
            )

        # Final progress update
        if hasattr(self.prog_logger, "job_id") and self.prog_logger.job_id:
            if (
                hasattr(self.prog_logger, "shared_progress_dict")
                and self.prog_logger.shared_progress_dict
            ):
                with threading.Lock():
                    if self.prog_logger.job_id in self.prog_logger.shared_progress_dict:
                        self.prog_logger.shared_progress_dict[
                            self.prog_logger.job_id
                        ].update(
                            {
                                "progress": total_movies,
                                "total": total_movies,
                                "status": "merge completed",
                                "last_updated": time.time(),
                            }
                        )
