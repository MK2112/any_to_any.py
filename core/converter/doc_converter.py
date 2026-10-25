import io
import os
import sys
import docx
import pptx
import shutil
import mammoth
import subprocess
import platform
import pymupdf as pypdf
import utils.language_support as lang

from PIL import Image
from tqdm import tqdm
from moviepy import VideoFileClip
from markdownify import markdownify
from utils.category import Category
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.pagesizes import A4
from core.utils.file_handler import sort_frame_filenames
from core.converter.image_converter import gif_to_frames
from core.utils.file_handler import safe_output_dir as _safe_out_dir


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    if platform.system() != "Windows":
        from weasyprint import HTML
    else:
        HTML = None
except Exception:
    HTML = None


class DocumentConverter:
    def __init__(
        self, file_handler, prog_logger, event_logger, locale: str = "English"
    ):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def _gif_frame_dirs_for(self, output: str, file_paths: dict) -> tuple:
        pre_existing: dict = {}
        try:
            for _ips in file_paths.get(Category.IMAGE, []):
                if len(_ips) == 3 and _ips[2] == "gif":
                    try:
                        _base = os.path.join(output, _ips[1])
                        pre_existing[_ips[1]] = bool(os.path.exists(_base))
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            gif_frame_dirs = gif_to_frames(output, file_paths, self.file_handler) or {}
        except Exception:
            gif_frame_dirs = {}
        if not isinstance(gif_frame_dirs, dict):
            gif_frame_dirs = {}
        return gif_frame_dirs, pre_existing

    def _cleanup_gif_frame_dir(
        self,
        gif_frame_dir: str,
        gif_name: str,
        output: str,
        mapped: bool,
        pre_existing: bool,
    ) -> None:
        try:
            _abs_frame = os.path.abspath(gif_frame_dir)
            _abs_out = os.path.abspath(output)
            _contained = _abs_frame != _abs_out and _abs_frame.startswith(
                _abs_out + os.sep
            )
            if mapped:
                if _contained:
                    shutil.rmtree(gif_frame_dir)
            else:
                if not pre_existing:
                    if _contained:
                        shutil.rmtree(gif_frame_dir)
                else:
                    try:
                        entries = os.listdir(gif_frame_dir)
                    except OSError:
                        entries = []
                    for e in entries:
                        if e.startswith(f"{gif_name}-") and e.endswith(".png"):
                            try:
                                os.remove(os.path.join(gif_frame_dir, e))
                            except OSError:
                                pass
        except OSError as e:
            self.event_logger.info(
                f"[!] {lang.get_translation('error', self.locale)}: {e}"
            )

    def to_markdown(
        self, output: str, file_paths: dict, format: str, delete: bool
    ) -> None:
        # Convert Documents to Markdown
        md_dir = os.path.abspath(output)
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == "docx":
                docx_path = self.file_handler.join_back(doc_path_set)
                out_basename = doc_path_set[1]
                md_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{out_basename}.{format}"))
                )

                image_md_out_dir = _safe_out_dir(
                    os.path.join(output, f"{out_basename}_images")
                )
                os.makedirs(image_md_out_dir, exist_ok=True)
                image_idx = 0

                # Custom image converter for mammoth
                def convert_image(image):
                    nonlocal image_idx
                    extension = image.content_type.split("/")[-1]
                    image_filename = f"{out_basename}_{image_idx}.{extension}"
                    image_path = os.path.join(image_md_out_dir, image_filename)
                    with image.open() as image_bytes:
                        buf = image_bytes.read()
                    with open(image_path, "wb") as img_file:
                        # Write the image to the file byte by byte
                        # image is of type Image
                        img_file.write(buf)
                    image_idx += 1
                    # Return src attribute that points to the relative image path
                    rel_image_path = os.path.relpath(image_path, start=md_dir).replace(
                        os.sep, "/"
                    )
                    return {"src": rel_image_path}

                with open(docx_path, "rb") as docx_file:
                    document = mammoth.convert_to_html(
                        docx_file,
                        convert_image=mammoth.images.img_element(convert_image),
                    )
                html_content = document.value  # Already a str, no need to encode

                # Convert HTML to Markdown
                markdown_text = markdownify(html_content)

                # Write Markdown file
                with open(md_path, "w", encoding="utf-8") as md_file:
                    md_file.write(markdown_text)
                self.file_handler.post_process(doc_path_set, md_path, delete)

    def to_pdf(self, output: str, file_paths: dict, format: str, delete: bool) -> None:
        # Convert GIFs to Frames using to_frames
        # Produces a folder with gif frame for each gif
        _gif_frame_dirs, _pre_existing = self._gif_frame_dirs_for(output, file_paths)

        # Convert Images to PDF
        for image_path_set in file_paths[Category.IMAGE]:
            if image_path_set[2] != "gif":
                doc = pypdf.open()
                img = pypdf.Pixmap(self.file_handler.join_back(image_path_set))
                rect = pypdf.Rect(0, 0, img.width, img.height)
                page = doc.new_page(width=rect.width, height=rect.height)
                page.insert_image(rect, pixmap=img)
                pdf_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(
                        os.path.join(output, f"{image_path_set[1]}.{format}")
                    )
                )
                doc.save(pdf_path)
                doc.close()
                self.file_handler.post_process(image_path_set, pdf_path, delete)
            elif image_path_set[2] == "gif":
                # We suppose the gif was converted to frames and we have a folder of pngs
                # All pngs shall be merged into one pdf
                gif_frame_path = _gif_frame_dirs.get(
                    image_path_set[1], os.path.join(output, image_path_set[1])
                )
                pdf_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(
                        os.path.join(output, f"{image_path_set[1]}.{format}")
                    )
                )

                doc = pypdf.open()
                try:
                    _frames = sort_frame_filenames(os.listdir(gif_frame_path))
                except OSError:
                    _frames = []
                for frame in _frames:
                    if frame.endswith(".png"):
                        img = pypdf.Pixmap(os.path.join(gif_frame_path, frame))
                        rect = pypdf.Rect(0, 0, img.width, img.height)
                        page = doc.new_page(width=rect.width, height=rect.height)
                        page.insert_image(rect, pixmap=img)
                doc.save(pdf_path)
                doc.close()
                self._cleanup_gif_frame_dir(
                    gif_frame_path,
                    image_path_set[1],
                    output,
                    image_path_set[1] in _gif_frame_dirs,
                    _pre_existing.get(image_path_set[1], False),
                )
                self.file_handler.post_process(image_path_set, pdf_path, delete)
        # Convert Movies to PDF, because we can
        for movie_path_set in file_paths[Category.MOVIE]:
            try:
                clip = VideoFileClip(
                    self.file_handler.join_back(movie_path_set),
                    audio=False,
                    fps_source="tbr",
                )
            except Exception:
                clip = None
            if clip is None or not self.file_handler.has_visuals(
                movie_path_set, clip=clip
            ):
                if clip is not None:
                    clip.close()
                continue
            pdf_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"{movie_path_set[1]}.{format}"))
            )

            doc = pypdf.open()
            total_frames = max(1, int(clip.duration * clip.fps))
            for frame_index, frame in enumerate(
                tqdm(clip.iter_frames(fps=clip.fps, dtype="uint8")), 1
            ):
                self.prog_logger.update_shared(
                    f"{movie_path_set[1]} ({frame_index}/{total_frames})",
                    frame_index,
                    total_frames,
                )
                h, w = frame.shape[:2]
                pix = pypdf.Pixmap(pypdf.csRGB, w, h, frame.tobytes(), stride=w * 3)
                rect = pypdf.Rect(0, 0, w, h)
                page = doc.new_page(width=rect.width, height=rect.height)
                page.insert_image(rect, pixmap=pix)
            doc.save(pdf_path)
            doc.close()
            clip.close()
            self.file_handler.post_process(movie_path_set, pdf_path, delete)
        # Convert Documents to PDF
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == "pdf":
                # If document is already a pdf, skip
                continue
            if doc_path_set[2] == "srt":
                pdf_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{doc_path_set[1]}.{format}"))
                )

                with open(
                    self.file_handler.join_back(doc_path_set), "r", encoding="utf-8-sig"
                ) as srt_file:
                    srt_content = srt_file.read()

                # Insert the SRT content into the PDF
                doc = pypdf.open()

                page = doc.new_page()
                page.insert_text((50, 50), srt_content, fontsize=12)

                doc.save(pdf_path)
                doc.close()

                self.file_handler.post_process(doc_path_set, pdf_path, delete)
            elif doc_path_set[2] == "docx":
                pdf_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(os.path.join(output, f"{doc_path_set[1]}.{format}"))
                )

                docx_path = self.file_handler.join_back(doc_path_set)
                if platform.system() == "Windows" or HTML is None:
                    self._docx_to_pdf_reportlab(docx_path, pdf_path)
                else:
                    docx_doc = open(docx_path, "rb")
                    # Convert docx to HTML as intermediary
                    document = mammoth.convert_to_html(docx_doc)
                    docx_doc.close()
                    # Convert html to PDF, save that
                    HTML(string=document.value.encode("utf-8")).write_pdf(pdf_path)
                self.file_handler.post_process(doc_path_set, pdf_path, delete)

    def _docx_to_pdf_reportlab(self, docx_path: str, pdf_path: str) -> None:
        doc = docx.Document(docx_path)
        # Default page dimensions, margins for PDFs
        page_width, page_height = A4
        left_margin = 0.75 * inch
        right_margin = 0.75 * inch
        top_margin = page_height - (0.75 * inch)
        bottom_margin = 0.75 * inch
        line_height = 12

        c = canvas.Canvas(pdf_path, pagesize=A4)
        c.setFont("Helvetica", 10)
        y = top_margin

        for paragraph in doc.paragraphs:
            # If empty paragraph, move down by line height, check for page break
            text = paragraph.text
            if not text:
                y -= line_height
                if y < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = top_margin
                continue

            words = text.split()
            line = ""
            for word in words:
                # Next word could exceed page width
                candidate = f"{line} {word}".strip()
                if (
                    c.stringWidth(candidate, "Helvetica", 10)
                    <= page_width - left_margin - right_margin
                ):
                    line = candidate
                else:
                    c.drawString(left_margin, y, line)
                    y -= line_height
                    if y < bottom_margin:
                        c.showPage()
                        c.setFont("Helvetica", 10)
                        y = top_margin
                    line = word

            if line:
                # Draw paragraph's last line
                c.drawString(left_margin, y, line)
                y -= line_height
                if y < bottom_margin:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = top_margin
        c.save()

    def to_subtitles(
        self, output: str, file_paths: dict, format: str, delete: bool
    ) -> None:
        # Extract subtitles from movies
        for movie_path_set in file_paths[Category.MOVIE]:
            input_path = self.file_handler.join_back(movie_path_set)
            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"{movie_path_set[1]}.srt"))
            )
            self.event_logger.info(
                f"[>] {lang.get_translation('extract_subtitles', self.locale)} '{input_path}'"
            )
            try:
                # Outsource this to ffmpeg for subtitle extraction
                subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        input_path,
                        "-map",
                        "0:s:0",  # Selects first subtitle stream
                        "-c:s",
                        "srt",
                        out_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    self.event_logger.info(
                        f"[>] {lang.get_translation('subtitles_success', self.locale)} '{out_path}'"
                    )
                    self.file_handler.post_process(
                        movie_path_set, out_path, delete, show_status=False
                    )
                else:
                    # Try extracting closed captions when direct extract fails (found mostly in MP4 and MKV)
                    self.event_logger.info(
                        f"[!] {lang.get_translation('extract_subtitles_alt', self.locale)}"
                    )
                    subprocess.run(
                        ["ffmpeg", "-i", input_path, "-c:s", format, out_path],
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        self.event_logger.info(
                            f"[>] {lang.get_translation('embed_subtitles_success', self.locale)} '{out_path}'"
                        )
                        self.file_handler.post_process(
                            movie_path_set, out_path, delete, show_status=False
                        )
                    else:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('embed_subtitles_fail', self.locale)} '{input_path}'"
                        )
            except Exception as e:
                self.event_logger.info(
                    f"[!] {lang.get_translation('extract_subtitles_fail', self.locale)} {str(e)}"
                )
                try:
                    subprocess.run(["ffmpeg", "-version"], capture_output=True)
                except FileNotFoundError:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('ffmpeg_not_found', self.locale)}"
                    )
                    break

    def to_office(
        self, output: str, file_paths: dict, format: str, delete: bool
    ) -> None:
        # Convert Images and Movies to Office Documents
        def _new_container():
            # Type-specific container creation
            return pptx.Presentation() if format == "pptx" else docx.Document()

        def _add_page(container):
            # Add a new page to the container, regardless of format
            return (
                container.slides.add_slide(container.slide_layouts[5])
                if format == "pptx"
                else container
            )

        def _place_img(page, img_path, full_page=False):
            # Place an image on the page, adjusting size for full page if needed
            with Image.open(img_path) as im:
                w, h = im.size
            if format == "pptx":
                max_h, max_w = container.slide_height, container.slide_width
                if full_page or h > max_h or w > max_w:
                    if h / max_h >= w / max_w:
                        page.shapes.add_picture(img_path, 0, 0, height=max_h)
                    else:
                        page.shapes.add_picture(img_path, 0, 0, width=max_w)
                else:
                    page.shapes.add_picture(img_path, 0, 0)
            elif format == "docx":
                try:
                    page.add_picture(img_path, height=docx.shared.Inches(7))
                except docx.image.exceptions.UnexpectedEndOfFileError as e:
                    self.event_logger.info(e)

        _gif_frame_dirs, _pre_existing = self._gif_frame_dirs_for(output, file_paths)

        for image_path_set in file_paths[Category.IMAGE]:
            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"{image_path_set[1]}.{format}"))
            )

            container = _new_container()
            if image_path_set[2] == "gif":
                gif_frame_dir = _gif_frame_dirs.get(
                    image_path_set[1], os.path.join(output, image_path_set[1])
                )
                try:
                    _frames = sort_frame_filenames(os.listdir(gif_frame_dir))
                except OSError:
                    _frames = []
                for frame_index, frame in enumerate(tqdm(_frames), 1):
                    self.prog_logger.update_shared(
                        f"{image_path_set[1]} ({frame_index}/{len(_frames)})",
                        frame_index,
                        len(_frames),
                    )
                    if not frame.endswith(".png"):
                        continue
                    page = _add_page(container)
                    _place_img(page, os.path.join(gif_frame_dir, frame), full_page=True)
                    if format == "docx":
                        page.add_paragraph(f"Image: {frame}")
                        page.add_page_break()
                self._cleanup_gif_frame_dir(
                    gif_frame_dir,
                    image_path_set[1],
                    output,
                    image_path_set[1] in _gif_frame_dirs,
                    _pre_existing.get(image_path_set[1], False),
                )
            else:
                page = _add_page(container)
                _place_img(
                    page, self.file_handler.join_back(image_path_set), full_page=True
                )
                if format == "docx":
                    page.add_paragraph(f"Image: {image_path_set[1]}")
            container.save(out_path)
            self.file_handler.post_process(image_path_set, out_path, delete)

        for movie_path_set in file_paths[Category.MOVIE]:
            try:
                clip = VideoFileClip(
                    self.file_handler.join_back(movie_path_set),
                    audio=False,
                    fps_source="tbr",
                )
            except Exception:
                clip = None
            if clip is None or not self.file_handler.has_visuals(
                movie_path_set, clip=clip
            ):
                if clip is not None:
                    clip.close()
                continue

            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, f"{movie_path_set[1]}.{format}"))
            )

            container = _new_container()
            total_frames = max(1, int(clip.duration * clip.fps))
            for idx, frame in tqdm(
                enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8"))
            ):
                self.prog_logger.update_shared(
                    f"{movie_path_set[1]} ({idx + 1}/{total_frames})",
                    idx + 1,
                    total_frames,
                )
                buf = io.BytesIO()
                Image.fromarray(frame).save(buf, format="PNG")
                buf.seek(0)
                page = _add_page(container)
                _place_img(page, buf, full_page=format == "pptx")
                if format == "docx":
                    page.add_paragraph(f"Frame: {idx}")
                    page.add_page_break()
                buf.close()

            clip.close()
            container.save(out_path)
            self.file_handler.post_process(movie_path_set, out_path, delete)

        if format == "docx":
            for document_path_set in file_paths[Category.DOCUMENT]:
                if document_path_set[2] == format:
                    continue

                # out_path is only resolved once there is real content, so a
                # skipped source never claims an output name
                doc = docx.Document()

                if document_path_set[2] == "pptx":
                    pptx_path = self.file_handler.join_back(document_path_set)
                    presentation = pptx.Presentation(pptx_path)
                    slides = presentation.slides
                    for slide_index, slide in enumerate(
                        tqdm(slides, desc=f"{document_path_set[1]}"), 1
                    ):
                        self.prog_logger.update_shared(
                            f"{document_path_set[1]} ({slide_index}/{len(slides)})",
                            slide_index,
                            len(slides),
                        )
                        title = slide.shapes.title
                        title_text = (
                            title.text if title is not None and title.text else ""
                        )
                        if title_text != "":
                            # Add title to the document
                            doc.add_paragraph(
                                f"Slide {slide.slide_id} Title: {title_text}"
                            )
                        for shape in slide.shapes:
                            if hasattr(shape, "image"):
                                img = shape.image
                                slide_img_path = self.file_handler._resolve_output_file_conflict(
                                    os.path.abspath(
                                        os.path.join(
                                            output,
                                            f"{document_path_set[1]}-slide{slide.slide_id}.{img.ext}",
                                        )
                                    )
                                )
                                with open(slide_img_path, "wb") as f:
                                    f.write(img.blob)
                                doc.add_paragraph(f"Slide {slide.slide_id} Image:")
                                doc.add_picture(
                                    slide_img_path, width=docx.shared.Inches(5)
                                )
                                try:
                                    os.remove(slide_img_path)
                                except OSError:
                                    pass
                            if hasattr(shape, "text"):
                                if shape.text != "":
                                    doc.add_paragraph(
                                        f"Slide {slide.slide_id} Text: {shape.text}"
                                    )
                        doc.add_page_break()
                elif document_path_set[2] == "pdf":
                    pdf = pypdf.open(self.file_handler.join_back(document_path_set))
                    total_pages = len(pdf)
                    for pnum in tqdm(range(total_pages)):
                        self.prog_logger.update_shared(
                            f"{document_path_set[1]} ({pnum + 1}/{total_pages})",
                            pnum + 1,
                            total_pages,
                        )
                        page = pdf.load_page(pnum)
                        txt = page.get_text().strip()
                        if txt:
                            doc.add_paragraph(f"Page {pnum + 1} Text:")
                            for line in txt.splitlines():
                                doc.add_paragraph(line)
                        imgs = page.get_images(full=True)
                        if imgs:
                            doc.add_paragraph(f"Page {pnum + 1} Images:")
                        for i, img in enumerate(imgs):
                            xref = img[0]
                            pix = pdf.extract_image(xref)
                            img_bytes, img_ext = pix["image"], pix["ext"]
                            tmp_img = self.file_handler._resolve_output_file_conflict(
                                os.path.abspath(
                                    os.path.join(
                                        output,
                                        f"{document_path_set[1]}-page{pnum + 1}-{i}.{img_ext}",
                                    )
                                )
                            )
                            with open(tmp_img, "wb") as f:
                                f.write(img_bytes)
                            doc.add_picture(tmp_img, width=docx.shared.Inches(5))
                            try:
                                os.remove(tmp_img)
                            except OSError:
                                pass
                        doc.add_page_break()
                elif document_path_set[2] in ("srt", "md"):
                    try:
                        with open(
                            self.file_handler.join_back(document_path_set),
                            "r",
                            encoding="utf-8-sig",
                        ) as text_file:
                            for line in text_file.read().splitlines():
                                doc.add_paragraph(line)
                    except (OSError, UnicodeDecodeError) as e:
                        self.event_logger.info(
                            f"[!] {lang.get_translation('error', self.locale)}: {e}"
                        )

                if not doc.paragraphs:
                    self.event_logger.info(
                        f"[!] {lang.get_translation('skipping', self.locale)}: "
                        f'"{self.file_handler.join_back(document_path_set)}"'
                    )
                    continue

                out_path = self.file_handler._resolve_output_file_conflict(
                    os.path.abspath(
                        os.path.join(output, f"{document_path_set[1]}.docx")
                    )
                )
                doc.save(out_path)
                self.file_handler.post_process(document_path_set, out_path, delete)

    def split_pdf(
        self,
        output: str,
        doc_path_set: tuple,
        page_ranges: str,
        delete: bool,
        format: str = "pdf",
    ):
        # output: str - output directory
        # doc_path_set: tuple - (path, name, format)
        # page_ranges: str - page ranges to split the document into
        # delete: bool - delete the original document after completion
        # format: str - format of the document
        doc_path = self.file_handler.join_back(doc_path_set)
        if format != "pdf":
            self.event_logger.warning(
                f"[!] split: unsupported format '{format}' for "
                f'"{doc_path_set[1]}.{doc_path_set[2]}" - '
                f"{lang.get_translation('skipping', self.locale)}"
            )
            return
        pdf = pypdf.open(doc_path)
        total_pages = len(pdf)
        if total_pages == 0:
            pdf.close()
            self.event_logger.warning(
                f"[!] split: no pages in "
                f'"{doc_path_set[1]}.{doc_path_set[2]}" - '
                f"{lang.get_translation('skipping', self.locale)}"
            )
            return
        # Parse page_ranges right into list of tuples
        parsed_ranges = self._parse_page_ranges(page_ranges, total_pages)
        if parsed_ranges is None:
            pdf.close()
            self.event_logger.warning(
                f"[!] split: no valid page ranges in '{page_ranges}' for "
                f'"{doc_path_set[1]}.{doc_path_set[2]}" '
                f"({total_pages} pages) - "
                f"{lang.get_translation('skipping', self.locale)}"
            )
            return

        os.makedirs(output, exist_ok=True)
        split_outputs = []
        for i, (start, end) in enumerate(parsed_ranges):
            new_pdf = pypdf.open()
            new_pdf.insert_pdf(pdf, from_page=start - 1, to_page=end - 1)
            if len(parsed_ranges) == 1:
                out_filename = f"{doc_path_set[1]}_{start}-{end}.{format}"
            else:
                out_filename = f"{doc_path_set[1]}_split_{i + 1}_{start}-{end}.{format}"
            out_path = self.file_handler._resolve_output_file_conflict(
                os.path.abspath(os.path.join(output, out_filename))
            )
            new_pdf.save(out_path)
            new_pdf.close()
            split_outputs.append(out_path)
            self.event_logger.info(
                f"[>] {lang.get_translation('split_produced', self.locale)}: {out_path}"
            )
        pdf.close()
        for i, split_path in enumerate(split_outputs):
            self.file_handler.post_process(
                doc_path_set, split_path, delete, show_status=(i == 0)
            )

    def _parse_page_ranges(
        self, page_ranges: str, total_pages: int
    ) -> list[tuple[int, int]] | None:
        # Parse page_ranges string into list of (start, end) tuples.
        # Handles: None, '1-5', '2-5,3-4', '3-6, 8-20, 23-45, rest', 'all', 'rest',
        #   '3-6;15-22', '1-7;8-15;20-22;rest', '3', '35', '12-end', '2-end',
        #   '2-5, 3-6, 12-end', '2-end, 3-6, 12-end', '2-end, 3-6'
        if not page_ranges or page_ranges.strip() == "":
            return None
        page_ranges = page_ranges.strip()
        lowered = page_ranges.lower()
        if lowered == "all":
            return [(page, page) for page in range(1, total_pages + 1)]
        if lowered == "rest":
            return [(1, total_pages)]

        # Split on both comma and semicolon, "1-2,3-4;5-6" keeps every range just alike
        ranges = [
            r.strip() for r in page_ranges.replace(";", ",").split(",") if r.strip()
        ]
        if not ranges:
            # No delimiters found
            ranges = [page_ranges.strip()]

        parsed_ranges = []
        # Track where 'rest' should start
        rest_start = 1

        for range_str in ranges:
            range_str = range_str.strip()
            if range_str.lower() == "rest":
                # 'rest': from highest processed page + 1 to end
                if parsed_ranges:
                    # Find highest end page processed so far
                    max_end = max(end for _, end in parsed_ranges)
                    rest_start = max_end + 1
                parsed_ranges.append((rest_start, total_pages))
                continue

            # Handle single page numbers
            if range_str.isdigit():
                page_num = int(range_str)
                if 1 <= page_num <= total_pages:
                    parsed_ranges.append((page_num, page_num))
                    rest_start = max(rest_start, page_num + 1)
                continue

            # Handle ranges like "1-5", "12-end", "2-end"
            if "-" in range_str:
                parts = range_str.split("-", 1)
                if len(parts) == 2:
                    start_str, end_str = parts[0].strip(), parts[1].strip()

                    # Parse start
                    try:
                        start = int(start_str)
                    except ValueError:
                        continue  # Some invalid range

                    # Parse end
                    if end_str.lower() in ("end", "rest"):
                        end = total_pages
                    else:
                        try:
                            end = int(end_str)
                        except ValueError:
                            continue  # Some invalid range

                    # Validate, add range
                    if (
                        1 <= start <= total_pages
                        and 1 <= end <= total_pages
                        and start <= end
                    ):
                        parsed_ranges.append((start, end))
                        rest_start = max(rest_start, end + 1)

        # Remove duplicate range tuples, preserve order
        # Ranges still are allowed to overlap, must each be unique though
        return list(dict.fromkeys(parsed_ranges)) or None
