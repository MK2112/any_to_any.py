import os
import fitz
import shutil
import numpy as np
import utils.language_support as lang
from PIL import Image
from tqdm import tqdm
from utils.category import Category
from core.doc_converter import office_to_frames
from moviepy import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    VideoClip,
    concatenate_videoclips,
)


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
        pngs = bmps = jpgs = []
        for image_path_set in file_paths[Category.IMAGE]:
            # Depending on the format, different fragmentation is required
            if image_path_set[2] == "gif":
                clip = VideoFileClip(
                    self.file_handler.join_back(image_path_set), audio=False
                )
                # If recursive, create file outright where its source was found
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
                clip.close()
                self.file_handler.post_process(image_path_set, out_path, delete)
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

        # Movie to different movie
        for movie_path_set in file_paths[Category.MOVIE]:
            if not movie_path_set[2] == format:
                out_path = os.path.abspath(
                    os.path.join(output, f"{movie_path_set[1]}.{format}")
                )
                if self.file_handler.has_visuals(movie_path_set):
                    video = VideoFileClip(
                        self.file_handler.join_back(movie_path_set),
                        audio=True,
                        fps_source="tbr",
                    )
                    video.write_videofile(
                        out_path,
                        codec=codec,
                        fps=video.fps if framerate is None else framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                    video.close()
                else:
                    # Audio-only video file
                    audio = AudioFileClip(self.file_handler.join_back(movie_path_set))
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
                        fps=24 if framerate is None else framerate,
                        audio=True,
                        logger=self.prog_logger,
                    )
                    clip.close()
                    audio.close()
                self.file_handler.post_process(movie_path_set, out_path, delete)

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
                        fps=video.fps if self.framerate is None else self.framerate,
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
                clip = clip.set_audio(audio)
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
