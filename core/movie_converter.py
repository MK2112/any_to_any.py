import os
import fitz
import shutil
import subprocess
import numpy as np
import utils.language_support as lang
from PIL import Image
from tqdm import tqdm
from utils.category import Category
from core.utils.exit import end_with_msg
from core.image_converter import office_to_frames
from moviepy import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    VideoClip,
    concatenate_videoclips,
)
from concurrent.futures import ThreadPoolExecutor, as_completed


class MovieConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

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
    ) -> None:
        # Convert to movie with specified format
        # Determine worker count
        try:
            env_workers = int(os.environ.get("Any2Any_MAX_WORKERS", "1"))
            env_workers = 1 if env_workers < 1 else env_workers
            env_workers = (
                os.cpu_count() - 1 if env_workers >= os.cpu_count() else env_workers
            )
        except ValueError:
            # If this variable doesn't exist, flag wasn't invoked: Default to 1
            env_workers = 1

        pngs = bmps = jpgs = []

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
                clip.write_videofile(
                    out_path,
                    codec=codec,
                    fps=clip.fps if framerate is None else framerate,
                    audio=False,
                    logger=self.prog_logger,
                )
                return (image_path_set, out_path)
            finally:
                if clip:
                    clip.close()

        # Collect image items first, dispatch GIFs in parallel
        gif_items = []
        for image_path_set in file_paths[Category.IMAGE]:
            # Depending on the format, different fragmentation is required
            if image_path_set[2] == "gif":
                gif_items.append(image_path_set)
            elif image_path_set[2] == "png":
                pngs.append(
                    ImageClip(
                        self.file_handler.join_back(image_path_set)
                    ).with_duration(1 / 24 if framerate is None else 1 / framerate)
                )
            elif image_path_set[2] == "jpeg" or image_path_set[2] == "jpg":
                jpgs.append(
                    ImageClip(
                        self.file_handler.join_back(image_path_set)
                    ).with_duration(1 / 24 if framerate is None else 1 / framerate)
                )
            elif image_path_set[2] == "bmp":
                bmps.append(
                    ImageClip(
                        self.file_handler.join_back(image_path_set)
                    ).with_duration(1 / 24 if framerate is None else 1 / framerate)
                )
            # No post_process here, we just accumulated for processing if not .gif

        if len(gif_items) == 1:
            res = _gif_to_video(gif_items[0])
            if res is not None:
                src, out_path = res
                self.file_handler.post_process(src, out_path, delete)
        elif len(gif_items) > 1:
            with ThreadPoolExecutor(max_workers=env_workers) as ex:
                futures = [ex.submit(_gif_to_video, g) for g in gif_items]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res is None:
                        continue
                    src, out_path = res
                    self.file_handler.post_process(src, out_path, delete)

        # Pics to movie
        for pics in [pngs, jpgs, bmps]:
            if len(pics) > 0:
                final_clip = concatenate_videoclips(pics, method="compose")
                out_path = os.path.abspath(os.path.join(output, f"merged.{format}"))
                final_clip.write_videofile(
                    out_path,
                    fps=24 if framerate is None else framerate,
                    codec=codec,
                    logger=self.prog_logger,
                )
                final_clip.close()
                self.file_handler.post_process(image_path_set, out_path, delete)

        # Movie to different movie (parallel per file)
        def _movie_to_movie(movie_path_set: tuple):
            if movie_path_set[2] == format:
                return None
            out_path_local = os.path.abspath(
                os.path.join(output, f"{movie_path_set[1]}.{format}")
            )
            video = None
            audio = None
            try:
                if self.file_handler.has_visuals(movie_path_set):
                    video = VideoFileClip(
                        self.file_handler.join_back(movie_path_set), audio=True
                    )
                    audio = video.audio
                    video.write_videofile(
                        out_path_local,
                        fps=video.fps if framerate is None else framerate,
                        codec=codec,
                        audio=bool(audio),
                        logger=self.prog_logger,
                    )
                else:
                    try:
                        audio = AudioFileClip(
                            self.file_handler.join_back(movie_path_set)
                        )
                        video_clip = VideoClip(
                            lambda t: np.zeros((720, 1280, 3), dtype=np.uint8)
                        )
                        duration = audio.duration
                        video_clip = video_clip.with_duration(duration)
                        video_clip = video_clip.with_fps(
                            24 if framerate is None else framerate
                        )
                        video_clip = video_clip.with_audio(audio)
                        video_clip.write_videofile(
                            out_path_local,
                            codec=codec,
                            audio=True,
                            logger=self.prog_logger,
                        )
                    except Exception as _:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('audio_only_video', self.locale)}: {self.file_handler.join_back(movie_path_set)} - {lang.get_translation('skipping', self.locale)}\n"
                        )
                        return None
                return (movie_path_set, out_path_local)
            finally:
                if audio:
                    audio.close()
                if video:
                    video.close()

        movie_items = list(file_paths[Category.MOVIE])
        if len(movie_items) == 1:
            res = _movie_to_movie(movie_items[0])
            if res is not None:
                src, out_path = res
                self.file_handler.post_process(src, out_path, delete)
        elif len(movie_items) > 1:
            with ThreadPoolExecutor(max_workers=env_workers) as ex:
                futures = [ex.submit(_movie_to_movie, m) for m in movie_items]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res is None:
                        continue
                    src, out_path = res
                    self.file_handler.post_process(src, out_path, delete)

        # Document to movie (because why the hell not)
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == "docx":
                # Convert docx to list of images first
                # Stitch that together, convert to movie
                office_to_frames(
                    doc_path_set,
                    "jpeg",
                    output,
                    delete,
                    self.file_handler,
                    self.event_logger,
                )
                # This creates a folder named docx_path_set[1] in the output directory
                # with all the images in it
                # Now we can convert that to a movie
                pics = [
                    image
                    for image in os.listdir(doc_path_set[1])
                    if image.endswith(".jpeg")
                ]
                if len(pics) > 0:
                    final_clip = concatenate_videoclips(pics, method="compose")
                    out_path = os.path.abspath(os.path.join(output, f".{format}"))
                    final_clip.write_videofile(
                        out_path,
                        fps=24 if framerate is None else framerate,
                        codec=codec,
                        logger=self.prog_logger,
                    )
                    final_clip.close()
                    self.file_handler.post_process(doc_path_set, out_path, delete)
            elif doc_path_set[2] == "pdf":
                pdf_path = self.file_handler.join_back(doc_path_set)
                movie_path = os.path.abspath(
                    os.path.join(output, f"{doc_path_set[1]}.{format}")
                )
                doc = fitz.open(pdf_path)
                image_files = []
                if not os.path.exists(os.path.join(output, doc_path_set[1])):
                    try:
                        os.makedirs(
                            os.path.join(output, doc_path_set[1]), exist_ok=True
                        )
                    except OSError as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                        )
                        output = input
                for i, page_num in tqdm(enumerate(range(len(doc)))):
                    pix = doc.load_page(page_num).get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img = img.convert("RGB")
                    # Save each page as a separate JPEG file
                    img.save(
                        os.path.join(
                            output,
                            doc_path_set[1],
                            f"{doc_path_set[1]}-{i:0{len(str(len(doc)))}}.jpeg",
                        ),
                        format="JPEG",
                    )
                    image_files.append(
                        f"{doc_path_set[1]}-{i:0{len(str(len(doc)))}}.jpeg"
                    )
                doc.close()

                # Convert the JPEG files to a video
                image_files = sorted(image_files)
                image_clips = [
                    ImageClip(os.path.join(output, doc_path_set[1], img)).with_duration(
                        (1 / framerate) if framerate is not None else 1 / 24
                    )
                    for img in image_files
                ]
                final_clip = concatenate_videoclips(image_clips, method="compose")
                final_clip.write_videofile(
                    movie_path,
                    fps=24 if framerate is None else framerate,
                    codec=codec,
                    logger=self.prog_logger,
                )
                final_clip.close()

                # Remove the temporary image files
                shutil.rmtree(os.path.join(output, doc_path_set[1]))
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
    ) -> None:
        # Convert movie to same movie with different codec
        for codec_path_set in file_paths[Category.MOVIE]:
            if not recursive or input != output:
                out_path = os.path.abspath(
                    os.path.join(
                        output,
                        f"{codec_path_set[1]}_{format}.{codec[1]}",
                    )
                )
            else:
                out_path = os.path.abspath(
                    os.path.join(codec_path_set[0], f"{codec_path_set[1]}.{format}")
                )
            if self.file_handler.has_visuals(codec_path_set):
                video = VideoFileClip(
                    self.file_handler.join_back(codec_path_set),
                    audio=True,
                    fps_source="tbr",
                )
                try:
                    video.write_videofile(
                        out_path,
                        codec=codec[0],
                        fps=video.fps if framerate is None else framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                except Exception as _:
                    if os.path.exists(out_path):
                        # There might be some residue left, remove it
                        os.remove(out_path)
                    self.event_logger.info(
                        f"\n\n[!] {lang.get_translation('codec_fallback', self.locale).replace('[path]', f'"{codec_path_set[2]}"').replace('[format]', f'{codec[1]}')}\n"
                    )
                    video.write_videofile(
                        out_path,
                        codec=codec[0],
                        fps=video.fps if framerate is None else framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                video.close()
            else:
                # Audio-only video file
                audio = AudioFileClip(self.file_handler.join_back(codec_path_set))
                # Create new VideoClip with audio only
                clip = VideoClip(
                    lambda t: np.zeros(
                        (16, 16, 3), dtype=np.uint8
                    ),  # 16 black pixels at least, required by moviepy
                    duration=audio.duration,
                )
                clip = clip.with_audio(audio)
                clip.write_videofile(
                    out_path,
                    codec=codec[0],
                    fps=24 if framerate is None else framerate,
                    audio=True,
                    logger=self.prog_logger,
                )
                clip.close()
                audio.close()
            self.file_handler.post_process(codec_path_set, out_path, delete)

    def to_protocol(
        self,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # self._supported_formats
        protocol: list,
        delete: bool,
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
            base_name = os.path.splitext(movie_path_set[-1])[0]
            current_out_dir = os.path.abspath(
                os.path.join(output, f"{base_name}_{protocol[0]}")
            )

            if current_out_dir is not None and not os.path.exists(current_out_dir):
                os.makedirs(current_out_dir)

            if protocol[0] == "hls":
                renditions = [
                    ("426x240", "400k", "64k"),
                    ("640x360", "800k", "96k"),
                    ("842x480", "1400k", "128k"),
                    ("1280x720", "2800k", "128k"),
                    ("1920x1080", "5000k", "192k"),
                ]
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
                    stream = [
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a:0",
                        "-c:v",
                        "h264",
                        "-b:v",
                        v_bitrate,
                        "-s",
                        resolution,
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
                    variant_playlist += f"#EXT-X-STREAM-INF:BANDWIDTH={int(v_bitrate[:-1]) * 1000},RESOLUTION={resolution}\n{i}.m3u8\n"
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
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    input_file,
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

    def _run_command(self, command: list) -> None:
        try:
            _ = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            error_msg = f"Error: {' '.join(command)}\n\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}"
            raise RuntimeError(error_msg)
