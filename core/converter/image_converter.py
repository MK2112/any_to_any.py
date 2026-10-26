import os
import sys
import docx
import pptx
import pymupdf as pypdf
import utils.language_support as lang

from PIL import Image
from tqdm import tqdm
from io import BytesIO
from moviepy import VideoFileClip
from utils.category import Category
from core.utils.file_handler import run_parallel, worker_count_for
from core.utils.file_handler import safe_output_dir as _safe_out_dir


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

_SAVE_FORMAT = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "heic": "HEIF",
    "heif": "HEIF",
    "avif": "AVIF",
}

_RASTER_CONVERTIBLE = frozenset(
    (
        "png",
        "jpeg",
        "jpg",
        "bmp",
        "webp",
        "tiff",
        "tga",
        "ico",
        "pcx",
        "ppm",
        "im",
        "ps",
        "eps",
        "jpeg2000",
        "heic",
        "heif",
        "avif",
    )
)


def _save_format(format: str) -> str:
    if format in _SAVE_FORMAT:
        return _SAVE_FORMAT[format]
    return format.upper()


_ALPHA_TARGETS = frozenset(
    ("png", "tiff", "tif", "webp", "heic", "heif", "avif", "tga", "jpeg2000", "im")
)


def _has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )


def _mode_for_target(img: Image.Image, format: str) -> Image.Image:
    if _has_alpha(img):
        if format in _ALPHA_TARGETS:
            return img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, img.convert("RGBA")).convert("RGB")
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _unsupported_source_msg(path: str, locale: str, reason: str = "") -> str:
    msg = (
        f'[!] {lang.get_translation("skipping", locale)} "{path}" - '
        f"{lang.get_translation('unsupported_format', locale)}"
    )
    return f"{msg} ({reason})" if reason else msg


def _write_office_frame(img_bytes: bytes, out_path: str, format: str) -> None:
    target = _save_format(format)
    try:
        with Image.open(BytesIO(img_bytes)) as img:
            if img.format != target:
                _mode_for_target(img, format).save(out_path, format=target)
                return
    except Exception:
        pass
    with open(out_path, "wb") as f:
        f.write(img_bytes)


def office_to_frames(
    doc_path_set: tuple,
    format: str,
    output: str,
    delete: bool,
    file_handler,
    event_logger,
    out_dir: str = None,
    prog_logger=None,
) -> str | None:
    # Extract imgs from office (docx, pptx), save as frames in specified format
    full_path = file_handler.join_back(doc_path_set)
    if out_dir is None:
        out_dir = _safe_out_dir(os.path.join(output, doc_path_set[1]))
    out_path = None
    os.makedirs(out_dir, exist_ok=True)
    try:
        if doc_path_set[2] == "docx":
            doc = docx.Document(full_path)
            rels = doc.part.rels.values()
            for i, rel in tqdm(enumerate(rels), desc=f"{doc_path_set[1]}"):
                if prog_logger is not None:
                    prog_logger.update_shared(
                        f"{doc_path_set[1]} ({i + 1}/{len(rels)})", i + 1, len(rels)
                    )
                if "image" in rel.reltype:
                    img_bytes = rel.target_part.blob
                    out_path = os.path.join(out_dir, f"{doc_path_set[1]}-{i}.{format}")
                    _write_office_frame(img_bytes, out_path, format)
            if out_path is not None:
                file_handler.post_process(doc_path_set, out_path, delete)
        elif doc_path_set[2] == "pptx":
            prs = pptx.Presentation(full_path)
            slides = prs.slides
            img_count = 0
            for i, slide in tqdm(enumerate(slides), desc=f"{doc_path_set[1]}"):
                if prog_logger is not None:
                    prog_logger.update_shared(
                        f"{doc_path_set[1]} ({i + 1}/{len(slides)})",
                        i + 1,
                        len(slides),
                    )
                for shape in slide.shapes:
                    if shape.shape_type == 13:  # Picture type
                        image = shape.image
                        img_bytes = image.blob
                        out_path = os.path.join(
                            out_dir, f"{doc_path_set[1]}-{img_count}.{format}"
                        )
                        _write_office_frame(img_bytes, out_path, format)
                        img_count += 1
            if out_path is not None:
                file_handler.post_process(doc_path_set, out_path, delete)
    except Exception as e:
        event_logger.error(e)
    return out_dir


def gif_to_frames(
    output: str, file_paths: dict, file_handler, format: str = "png"
) -> dict:
    # Convert GIFs to frames in the requested image format, place those in
    # a folder
    format = "jpeg" if format == "jpg" else format
    gifs = [
        image_path
        for image_path in file_paths[Category.IMAGE]
        if image_path[2] == "gif"
    ]

    if not gifs:
        return {}

    created: dict = {}

    def _extract_gif_frames(image_path_set: tuple):
        base_dir = os.path.abspath(os.path.join(output, image_path_set[1]))
        out_dir = _safe_out_dir(base_dir)
        os.makedirs(out_dir, exist_ok=True)
        created[image_path_set[1]] = out_dir
        clip = VideoFileClip(file_handler.join_back(image_path_set), audio=False)
        try:
            total_frames = int(clip.duration * clip.fps)
            num_digits = len(str(total_frames))
            for i, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8")):
                Image.fromarray(frame).convert("RGB").save(
                    os.path.join(
                        out_dir, f"{image_path_set[1]}-{i:0{num_digits}d}.{format}"
                    ),
                    format=_save_format(format),
                )
        finally:
            clip.close()

    run_parallel(gifs, _extract_gif_frames, worker_count_for(file_handler))
    return created


def _save_clip_frames(
    clip: VideoFileClip, out_dir: str, base_name: str, fmt: str
) -> str | None:
    # Return path of last frame written, or None for a clip without frames
    os.makedirs(out_dir, exist_ok=True)
    num_digits = len(str(int(clip.duration * clip.fps)))
    last_frame = None
    for i, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8")):
        last_frame = os.path.join(out_dir, f"{base_name}-{i:0{num_digits}d}.{fmt}")
        Image.fromarray(frame).convert("RGB").save(last_frame, format=_save_format(fmt))
    return last_frame


class ImageConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def _per_file_out_dir(self, path_set: tuple, input: str, output: str) -> str:
        # When in_dir doubles as out_dir: place outputs next to source
        if input == output:
            return path_set[0]
        return output

    def to_frames(
        self,
        input: str,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # self._supported_formats
        framerate: int,
        format: str,
        delete: bool,
    ) -> None:
        # Converting to image frame sets
        # This works for images and movies only
        format = "jpeg" if format == "jpg" else format

        # Handle GIF files first (frames in the requested target format)
        gif_frames = gif_to_frames(output, file_paths, self.file_handler, format)

        # Process regular image files
        for image_path_set in file_paths[Category.IMAGE]:
            try:
                if image_path_set[2] == format:
                    continue

                if image_path_set[2] == "gif":
                    # gif_to_frames already extracted the frames; report the
                    # last frame (and delete the source when requested)
                    frame_dir = gif_frames.get(
                        image_path_set[1], os.path.join(output, image_path_set[1])
                    )
                    try:
                        last_frame = max(os.listdir(frame_dir), default=None)
                    except OSError:
                        last_frame = None
                    if last_frame is not None:
                        self.file_handler.post_process(
                            image_path_set,
                            os.path.join(frame_dir, last_frame),
                            delete,
                        )
                    continue

                # Ensure output dir exists (single images are placed directly in output)
                os.makedirs(output, exist_ok=True)

                out_dir = self._per_file_out_dir(image_path_set, input, output)
                img_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(
                        os.path.join(out_dir, f"{image_path_set[1]}.{format}")
                    )
                )

                # Convert and save the image
                try:
                    source = Image.open(self.file_handler.join_back(image_path_set))
                except (OSError, ValueError) as e:
                    self.event_logger.info(
                        _unsupported_source_msg(
                            self.file_handler.join_back(image_path_set),
                            self.locale,
                            str(e),
                        )
                    )
                    continue
                with source as img:
                    img = _mode_for_target(img, format)
                    img.save(img_path, format=_save_format(format))

                self.file_handler.post_process(image_path_set, img_path, delete)

            except Exception as e:
                self.event_logger.error(
                    f"[!] {lang.get_translation('error', self.locale)} "
                    f"converting {self.file_handler.join_back(image_path_set)}: {str(e)}"
                )
                # Don't delete source file if conversion failed
                delete = False
                continue
        # Convert documents to image frames
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == format:
                continue
            _base_doc_dir = (
                os.path.join(doc_path_set[0], doc_path_set[1])
                if input == output
                else os.path.join(output, doc_path_set[1])
            )
            doc_out_dir = _safe_out_dir(_base_doc_dir)
            try:
                os.makedirs(doc_out_dir, exist_ok=True)
            except OSError as e:
                self.event_logger.info(
                    f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                )
                output = input
                doc_out_dir = _safe_out_dir(os.path.join(output, doc_path_set[1]))
                os.makedirs(doc_out_dir, exist_ok=True)
            if doc_path_set[2] in ["docx", "pptx"]:
                office_to_frames(
                    doc_path_set=doc_path_set,
                    format=format,
                    output=output,
                    delete=delete,
                    file_handler=self.file_handler,
                    event_logger=self.event_logger,
                    out_dir=doc_out_dir,
                    prog_logger=self.prog_logger,
                )
            if doc_path_set[2] == "pdf":
                last_frame = self._write_pdf_pages(
                    doc_path_set, doc_out_dir, format, start_index=1
                )
                if last_frame is not None:
                    self.file_handler.post_process(doc_path_set, last_frame, delete)

        # Audio cant be image-framed, movies certrainly can
        def _movie_to_frames(movie_path_set: tuple):
            if movie_path_set[2] not in supported_formats[Category.MOVIE]:
                self.event_logger.info(
                    f"[!] {lang.get_translation('movie_format_unsupported', self.locale)} {movie_path_set[2]} - {lang.get_translation('skipping', self.locale)}"
                )
                return None
            video = VideoFileClip(
                self.file_handler.join_back(movie_path_set),
                audio=False,
                fps_source="tbr",
            )
            try:
                if not self.file_handler.has_visuals(movie_path_set, clip=video):
                    self.event_logger.info(
                        f'[!] {lang.get_translation("skipping", self.locale)} "{self.file_handler.join_back(movie_path_set)}" - {lang.get_translation("audio_only_video", self.locale)}'
                    )
                    return None
                movie_out_dir = _safe_out_dir(
                    os.path.join(movie_path_set[0], movie_path_set[1])
                    if input == output
                    else os.path.join(output, movie_path_set[1])
                )
                try:
                    os.makedirs(movie_out_dir, exist_ok=True)
                except OSError as e:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                    )
                    return None
                img_path = os.path.abspath(
                    os.path.join(
                        movie_out_dir,
                        f"{movie_path_set[1]}-%0{len(str(int(video.duration * video.fps)))}d.{format}",
                    )
                )
                frame_names = video.write_images_sequence(
                    img_path, fps=video.fps, logger=self.prog_logger
                )
                return (movie_path_set, frame_names[-1]) if frame_names else None
            finally:
                video.close()

        for res in filter(
            None,
            run_parallel(
                file_paths[Category.MOVIE],
                _movie_to_frames,
                worker_count_for(self.file_handler),
            ),
        ):
            self.file_handler.post_process(res[0], res[1], delete)

    def _convert_stills(
        self,
        convertible_images: list,
        input: str,
        output: str,
        format: str,
        delete: bool,
        save,
    ) -> None:
        def _convert(image_path_set: tuple):
            out_dir = self._per_file_out_dir(image_path_set, input, output)
            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(out_dir, f"{image_path_set[1]}.{format}"))
            )
            try:
                source = Image.open(self.file_handler.join_back(image_path_set))
            except (OSError, ValueError) as e:
                self.event_logger.info(
                    _unsupported_source_msg(
                        self.file_handler.join_back(image_path_set), self.locale, str(e)
                    )
                )
                return None
            with source as img:
                save(img, out_path)
            return (image_path_set, out_path)

        for src, out_path in filter(
            None,
            run_parallel(
                convertible_images, _convert, worker_count_for(self.file_handler)
            ),
        ):
            self.file_handler.post_process(src, out_path, delete)

    def _convert_gifs_and_skips(
        self, file_paths: dict, output: str, format: str, delete: bool
    ) -> None:
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] == format or image_path_set[2] in _RASTER_CONVERTIBLE:
                continue
            if image_path_set[2] == "gif":
                clip = VideoFileClip(self.file_handler.join_back(image_path_set))
                try:
                    gif_frame_out_dir = _safe_out_dir(
                        os.path.abspath(os.path.join(output, image_path_set[1]))
                    )
                    frame_path = _save_clip_frames(
                        clip, gif_frame_out_dir, image_path_set[1], format
                    )
                finally:
                    clip.close()
                if frame_path is not None:
                    self.file_handler.post_process(image_path_set, frame_path, delete)
            else:
                # Unsupported file types wash up here
                self.event_logger.info(
                    f'[!] {lang.get_translation("skipping", self.locale)} "{self.file_handler.join_back(image_path_set)}" - {lang.get_translation("unsupported_format", self.locale)}'
                )

    def _movies_to_frames(
        self, file_paths: dict, format: str, delete: bool, write_frames
    ) -> None:
        # Movies are converted frame by frame (innovative, I know)
        for movie_path_set in file_paths[Category.MOVIE]:
            video = VideoFileClip(
                self.file_handler.join_back(movie_path_set),
                audio=False,
                fps_source="tbr",
            )
            frame_path = None
            try:
                if not self.file_handler.has_visuals(movie_path_set, clip=video):
                    self.event_logger.info(
                        f'[!] {lang.get_translation("skipping", self.locale)} "{self.file_handler.join_back(movie_path_set)}" - {lang.get_translation("audio_only_video", self.locale)}'
                    )
                    continue
                frame_path = write_frames(video, movie_path_set)
            finally:
                video.close()
            if frame_path is not None:
                self.file_handler.post_process(movie_path_set, frame_path, delete)

    def _write_pdf_pages(
        self, doc_path_set: tuple, frame_out_dir: str, format: str, start_index: int = 0
    ) -> str | None:
        # Render every page of a PDF into frame_out_dir -> return the last frame
        pdf_path = self.file_handler.join_back(doc_path_set)
        doc = pypdf.open(pdf_path)
        total_pages = len(doc)
        num_digits = len(str(total_pages))
        last_frame = None
        for page_num in tqdm(
            range(total_pages), desc=f"{doc_path_set[1]}", unit="page"
        ):
            self.prog_logger.update_shared(
                f"{doc_path_set[1]} ({page_num + 1}/{total_pages})",
                page_num + 1,
                total_pages,
            )
            pix = doc[page_num].get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            last_frame = os.path.join(
                frame_out_dir,
                f"{doc_path_set[1]}-{page_num + start_index:0{num_digits}}.{format}",
            )
            img.save(last_frame, format=_save_format(format))
        doc.close()
        return last_frame

    def _pdf_to_frames(
        self, doc_path_set: tuple, input: str, output: str, format: str, delete: bool
    ) -> None:
        # Save each page of a PDF as a frame file
        frame_out_dir = _safe_out_dir(os.path.join(output, doc_path_set[1]))
        try:
            os.makedirs(frame_out_dir, exist_ok=True)
        except OSError as e:
            self.event_logger.info(
                f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
            )
            output = input
            frame_out_dir = _safe_out_dir(os.path.join(output, doc_path_set[1]))
        last_frame = self._write_pdf_pages(doc_path_set, frame_out_dir, format)
        if last_frame is not None:
            self.file_handler.post_process(doc_path_set, last_frame, delete)

    def _docs_to_frames(
        self, file_paths: dict, input: str, output: str, format: str, delete: bool
    ) -> None:
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] in ("docx", "pptx"):
                office_to_frames(
                    doc_path_set=doc_path_set,
                    format=format,
                    output=output,
                    delete=delete,
                    file_handler=self.file_handler,
                    event_logger=self.event_logger,
                    prog_logger=self.prog_logger,
                )
            if doc_path_set[2] == "pdf":
                self._pdf_to_frames(doc_path_set, input, output, format, delete)

    def to_bmp(
        self,
        input: str,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # unused, aligns signature with to_frames, so keep it
        framerate: int,
        format: str,
        delete: bool,
    ) -> None:
        # Movies are converted frame-by-frame to bmps
        self._movies_to_frames(
            file_paths,
            format,
            delete,
            lambda video, movie_path_set: _save_clip_frames(
                video,
                _safe_out_dir(
                    os.path.join(movie_path_set[0], movie_path_set[1])
                    if input == output
                    else os.path.join(output, movie_path_set[1])
                ),
                movie_path_set[1],
                format,
            ),
        )
        self._convert_stills(
            [
                ips
                for ips in file_paths[Category.IMAGE]
                if ips[2] != format and ips[2] in _RASTER_CONVERTIBLE
            ],
            input,
            output,
            format,
            delete,
            lambda img, out_path: _mode_for_target(img, format).save(
                out_path, format=format
            ),
        )
        self._convert_gifs_and_skips(file_paths, output, format, delete)
        self._docs_to_frames(file_paths, input, output, format, delete)

    def to_webp(
        self,
        input: str,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # unused, aligns signature with to_frames, keep
        framerate: int,  # equally unused, same thing
        format: str,
        delete: bool,
    ) -> None:
        # Convert frames in webp format
        # Movies are converted to webps, frame by frame
        def _write_frames(video, movie_path_set):
            nonlocal output
            webp_frame_out_dir = _safe_out_dir(os.path.join(output, movie_path_set[1]))
            try:
                os.makedirs(webp_frame_out_dir, exist_ok=True)
            except OSError as e:
                self.event_logger.info(
                    f"[!] {lang.get_translation('error', self.locale)}: {e} - {lang.get_translation('set_out_dir', self.locale)} {input}"
                )
                output = input
                webp_frame_out_dir = _safe_out_dir(
                    os.path.join(output, movie_path_set[1])
                )
            img_path = os.path.abspath(
                os.path.join(
                    webp_frame_out_dir,
                    f"{movie_path_set[1]}-%0{len(str(int(video.duration * video.fps)))}d.{format}",
                )
            )
            frame_names = video.write_images_sequence(
                img_path, fps=video.fps, logger=self.prog_logger
            )
            return frame_names[-1] if frame_names else None

        self._movies_to_frames(file_paths, format, delete, _write_frames)
        # pngs and gifs are converted to webps as well
        self._convert_stills(
            [
                ips
                for ips in file_paths[Category.IMAGE]
                if ips[2] != format and ips[2] in _RASTER_CONVERTIBLE
            ],
            input,
            output,
            format,
            delete,
            lambda img, out_path: _mode_for_target(img, format).save(
                out_path, format=format
            ),
        )

        self._convert_gifs_and_skips(file_paths, output, format, delete)
        self._docs_to_frames(file_paths, input, output, format, delete)

    def to_heic(
        self,
        input: str,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # unused, aligns signature with to_frames
        framerate: int,
        format: str,
        delete: bool,
    ) -> None:
        # Convert still images, PDF, office docs to HEIF/HEIC/AVIF, not movies tho
        if pillow_heif is None:
            self.event_logger.error(
                f"[!] {lang.get_translation('error', self.locale)}: "
                f"pillow-heif is required for {format} conversion. "
                f"Install it with: pip install pillow-heif"
            )
            return

        def _save(img, out_path):
            _mode_for_target(img, format).save(out_path, format=_save_format(format))

        self._convert_stills(
            [
                ips
                for ips in file_paths[Category.IMAGE]
                if ips[2] not in ("heic", "heif", "avif")
            ],
            input,
            output,
            format,
            delete,
            _save,
        )
        self._docs_to_frames(file_paths, input, output, format, delete)

    def to_gif(
        self,
        input: str,
        output: str,
        file_paths: dict,
        supported_formats: dict,  # unused, aligns signature with to_frames, so keep it
        framerate: int,
        format: str,
        delete: bool,
    ) -> None:
        # All images in the input directory are merged into one gif
        if file_paths[Category.IMAGE]:
            images = []
            participants = []
            total_images = len(file_paths[Category.IMAGE])

            # Create tqdm progress bar
            progress_bar = tqdm(
                total=total_images,
                unit="img",
                leave=False,
                disable=False,
            )

            try:
                for i, image_path_set in enumerate(file_paths[Category.IMAGE], 1):
                    self.prog_logger.update_shared(
                        f"gif ({i}/{total_images})", i, total_images
                    )
                    if image_path_set[2] == format:
                        progress_bar.update(1)  # Update for skipped images too
                        continue

                    try:
                        with Image.open(
                            self.file_handler.join_back(image_path_set)
                        ) as image:
                            images.append(image.convert("RGB"))
                        participants.append(image_path_set)

                        progress_bar.set_postfix(
                            {"current": os.path.basename(image_path_set[1])},
                            refresh=False,
                        )
                        progress_bar.update(1)

                    except Exception as e:
                        error_msg = f"Error processing image {os.path.basename(image_path_set[1])}: {str(e)}"
                        if hasattr(self, "prog_logger"):
                            self.prog_logger.log(error_msg)
                        progress_bar.write(error_msg)  # Show error in tqdm output
                        raise  # Re-raise to maintain original error handling

            finally:
                progress_bar.close()

            if images:
                output_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"merged.{format}"))
                )

                try:
                    gif_fps = framerate or 12
                    images[0].save(
                        output_path,
                        save_all=True,
                        append_images=images[1:],
                        duration=1000 // gif_fps,
                        loop=0,
                    )
                    # Report the merged gif (and remove the participating
                    # source images when requested) only after it was written
                    for idx, participant in enumerate(participants):
                        self.file_handler.post_process(
                            participant,
                            output_path,
                            delete,
                            show_status=(idx == 0),
                        )
                except Exception as e:
                    if hasattr(self, "prog_logger"):
                        self.prog_logger.log(
                            f"Error saving GIF {output_path}: {str(e)}"
                        )
                    raise
        # Movies are frame by frame converted to gifs, retaining 1/3 of the frames
        for movie_path_set in file_paths[Category.MOVIE]:
            try:
                video = VideoFileClip(
                    self.file_handler.join_back(movie_path_set),
                    audio=False,
                    fps_source="tbr",
                )
            except Exception:
                video = None
            if video is None or not self.file_handler.has_visuals(
                movie_path_set, clip=video
            ):
                if video is not None:
                    video.close()
                self.event_logger.info(
                    f'[!] {lang.get_translation("skipping", self.locale)} "{self.file_handler.join_back(movie_path_set)}" - {lang.get_translation("audio_only_video", self.locale)}'
                )
                continue
            try:
                gif_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(
                        os.path.join(output, f"{movie_path_set[1]}.{format}")
                    )
                )
                target_fps = max(1, int(video.fps // 3))

                video.write_gif(
                    gif_path,
                    fps=target_fps,
                    logger=self.prog_logger,
                )

                video.close()
                self.file_handler.post_process(movie_path_set, gif_path, delete)
            except Exception as e:
                if hasattr(self, "prog_logger"):
                    self.prog_logger.log(
                        f"Error converting video {movie_path_set} to GIF: {str(e)}"
                    )
                raise
        # Documents may be convertable to gifs, e.g. pdfs
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == "pdf":
                pdf_path = self.file_handler.join_back(doc_path_set)
                gif_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{doc_path_set[1]}.{format}"))
                )

                doc = pypdf.open(pdf_path)
                images = []
                total_pages = len(doc)
                for page_num in tqdm(
                    range(total_pages), desc=f"{doc_path_set[1]}", unit="page"
                ):
                    self.prog_logger.update_shared(
                        f"{doc_path_set[1]} ({page_num + 1}/{total_pages})",
                        page_num + 1,
                        total_pages,
                    )
                    pix = doc.load_page(page_num).get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    images.append(img)
                if images:
                    images[0].save(
                        gif_path,
                        save_all=True,
                        append_images=images[1:],
                        duration=(len(images) * 1000 // len(images))
                        // (12 if framerate is None else framerate),
                        loop=0,
                    )
                doc.close()
                self.file_handler.post_process(doc_path_set, gif_path, delete)
            elif doc_path_set[2] in ["docx", "pptx"]:
                input_path = self.file_handler.join_back(doc_path_set)
                gif_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{doc_path_set[1]}.{format}"))
                )

                images = []
                if doc_path_set[2] == "docx":
                    doc = docx.Document(input_path)
                    rels = doc.part.rels.values()
                    for rel_index, rel in enumerate(
                        tqdm(rels, desc=f"{doc_path_set[1]}", unit="img"), 1
                    ):
                        self.prog_logger.update_shared(
                            f"{doc_path_set[1]} ({rel_index}/{len(rels)})",
                            rel_index,
                            len(rels),
                        )
                        if "image" in rel.reltype:
                            img = Image.open(BytesIO(rel.target_part.blob))
                            images.append(img.convert("RGB"))
                    frame_count = len(doc.paragraphs) or 1
                else:
                    prs = pptx.Presentation(input_path)
                    slides = prs.slides
                    for slide_index, slide in enumerate(
                        tqdm(slides, desc=f"{doc_path_set[1]}", unit="slide"), 1
                    ):
                        self.prog_logger.update_shared(
                            f"{doc_path_set[1]} ({slide_index}/{len(slides)})",
                            slide_index,
                            len(slides),
                        )
                        for shape in slide.shapes:
                            if shape.shape_type == 13:  # Picture
                                image = shape.image
                                img_bytes = image.blob
                                img = Image.open(BytesIO(img_bytes))
                                images.append(img.convert("RGB"))
                    frame_count = len(prs.slides) or 1
                if images:
                    images[0].save(
                        gif_path,
                        save_all=True,
                        append_images=images[1:],
                        duration=(len(images) * 1000 // frame_count)
                        // (12 if framerate is None else framerate),
                        loop=0,
                    )
                self.file_handler.post_process(doc_path_set, gif_path, delete)
