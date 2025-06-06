import os
import docx
import pptx
import fitz
import PyPDF2
import utils.language_support as lang
from PIL import Image
from tqdm import tqdm
from moviepy import VideoFileClip
from utils.category import Category

def office_to_frames(
    doc_path_set: tuple,
    format: str,
    output: str,
    delete: bool,
    file_handler,
    event_logger,
) -> None:
    # Utility function available beyond DocumentConverter scope
    # Used e.g. in MovieConverter, placing it here makes it accessible easily
    full_path = file_handler.join_back(doc_path_set)
    output_dir = os.path.join(output, doc_path_set[1])
    os.makedirs(output_dir, exist_ok=True)
    try:
        if doc_path_set[2] == "docx":
            doc = docx.Document(full_path)
            for i, rel in tqdm(
                enumerate(doc.part.rels.values()), desc=f"{doc_path_set[1]}"
            ):
                if "image" in rel.reltype:
                    img_bytes = rel.target_part.blob
                    out_path = os.path.join(
                        output_dir, f"{doc_path_set[1]}-{i}.{format}"
                    )
                    with open(out_path, "wb") as f:
                        f.write(img_bytes)
            file_handler.post_process(doc_path_set, out_path, delete)
        elif doc_path_set[2] == "pptx":
            prs = pptx.Presentation(full_path)
            img_count = 0
            for i, slide in tqdm(enumerate(prs.slides), desc=f"{doc_path_set[1]}"):
                for shape in slide.shapes:
                    if shape.shape_type == 13:  # Picture type
                        image = shape.image
                        img_bytes = image.blob
                        out_path = os.path.join(
                            output_dir, f"{doc_path_set[1]}-{img_count}.{format}"
                        )
                        with open(out_path, "wb") as f:
                            f.write(img_bytes)
                        img_count += 1
            file_handler.post_process(doc_path_set, out_path, delete)
    except Exception as e:
        event_logger.error(e)

def gif_to_frames(output: str, file_paths: dict, file_handler) -> None:
    # Convert GIFs to frames, place those in a folder
    gifs = [
        image_path
        for image_path in file_paths[Category.IMAGE]
        if image_path[2] == "gif"
    ]
    if len(gifs) > 0:
        for image_path_set in gifs:
            clip = VideoFileClip(file_handler.join_back(image_path_set), audio=False)
            # Calculate zero-padding width based on total number of frames
            total_frames = int(clip.duration * clip.fps)
            num_digits = len(str(total_frames))
            # Create a dedicated folder for the gif to store its frames
            if not os.path.exists(os.path.join(output, image_path_set[1])):
                os.makedirs(os.path.join(output, image_path_set[1]), exist_ok=True)
            for i, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8")):
                frame_filename = f"{image_path_set[1]}-{i:0{num_digits}d}.png"
                frame_path = os.path.abspath(
                    os.path.join(output, image_path_set[1], frame_filename)
                )
                Image.fromarray(frame).save(frame_path, format="PNG")
            clip.close()

class ImageConverter:

    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def to_frames(self,
                  input: str,
                  output: str,
                  file_paths: dict, 
                  supported_formats: dict, # self._supported_formats
                  format: str,
                  delete: bool) -> None:
        # Converting to image frame sets
        # This works for images and movies only
        format = "jpeg" if format == "jpg" else format
        gif_to_frames(output, file_paths, self.file_handler)
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == format:
                continue
            if image_path_set[2] == "gif":
                # gif_to_frames did that out of loop already, just logging here
                self.file_handler.post_process(image_path_set, output, delete)
            else:
                if not os.path.exists(os.path.join(output, image_path_set[1])):
                    output = input
                img_path = os.path.abspath(
                    os.path.join(output, f"{image_path_set[1]}.{format}")
                )
                with Image.open(self.file_handler.join_back(image_path_set)) as img:
                    img.convert("RGB").save(img_path, format=format)
                self.file_handler.post_process(image_path_set, img_path, delete)
        # Convert documents to image frames
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == format:
                continue
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
            if doc_path_set[2] in ["docx", "pptx"]:
                # Read all images from docx, write to os.path.join(self.output, doc_path_set[1])
                office_to_frames(
                    doc_path_set=doc_path_set,
                    format=format,
                    output=output,
                    delete=delete,
                    file_handler=self.file_handler,
                    event_logger=self.event_logger,
                )
            if doc_path_set[2] == "pdf":
                # Per page, convert pdf to image
                pdf_path = self.file_handler.join_back(doc_path_set)
                pdf = PyPDF2.PdfReader(pdf_path)
                img_path = os.path.abspath(
                    os.path.join(
                        os.path.join(output, doc_path_set[1]),
                        f"{doc_path_set[1]}-%{len(str(len(pdf.pages)))}d.{format}",
                    )
                )

                try:
                    if not os.path.exists(os.path.dirname(img_path)):
                        os.makedirs(os.path.dirname(img_path), exist_ok=True)
                    output = os.path.dirname(img_path)
                except OSError as e:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                    )
                    output = input

                pdf_document = fitz.open(pdf_path)

                for page_num in range(len(pdf_document)):
                    pix = pdf_document[page_num].get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img_file = img_path % (page_num + 1)
                    img.save(img_file, format.upper())

                pdf_document.close()
                self.file_handler.post_process(doc_path_set, img_path, delete)

        # Audio cant be image-framed, movies certrainly can
        for movie_path_set in file_paths[Category.MOVIE]:
            if movie_path_set[2] not in supported_formats[Category.MOVIE]:
                self.event_logger.info(
                    f"[!] {lang.get_translation('movie_format_unsupported', self.locale)} {movie_path_set[2]} - {lang.get_translation('skipping', self.locale)}"
                )
                continue
            if self.file_handler.has_visuals(movie_path_set):
                video = VideoFileClip(
                    self.file_handler.join_back(movie_path_set),
                    audio=False,
                    fps_source="tbr",
                )
                try:
                    if not os.path.exists(os.path.join(output, movie_path_set[1])):
                        os.makedirs(
                            os.path.join(output, movie_path_set[1]), exist_ok=True
                        )
                except OSError as e:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                    )
                    output = input
                img_path = os.path.abspath(
                    os.path.join(
                        os.path.join(output, movie_path_set[1]),
                        f"{movie_path_set[1]}-%{len(str(int(video.duration * video.fps)))}d.{format}",
                    )
                )

                video.write_images_sequence(
                    img_path, fps=video.fps, logger=self.prog_logger
                )
                video.close()
                self.file_handler.post_process(movie_path_set, img_path, delete)
            else:
                self.event_logger.info(
                    f'[!] {lang.get_translation("skipping", self.locale)} "{self.file_handler.join_back(movie_path_set)}" - {lang.get_translation("audio_only_video", self.locale)}'
                )
                self.file_handler.post_process(movie_path_set, img_path, delete)