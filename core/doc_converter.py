import os
import fitz
import docx
import pptx
import shutil
import mammoth
from PIL import Image
from tqdm import tqdm
from weasyprint import HTML
from moviepy import VideoFileClip
from markdownify import markdownify
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

class DocumentConverter:

    def __init__(self, file_handler, prog_logger, event_logger, locale: str = "English"):
        self.file_handler = file_handler
        self.prog_logger = prog_logger
        self.event_logger = event_logger
        self.locale = locale

    def to_markdown(self,
                    input: str,
                    output: str,
                    file_paths: dict, 
                    format: str,
                    delete: bool) -> None:
        for doc_path_set in file_paths[Category.DOCUMENT]:
            if doc_path_set[2] == "docx":
                docx_path = self.file_handler.join_back(doc_path_set)
                output_basename = doc_path_set[1]
                md_path = os.path.abspath(
                    os.path.join(output, f"{output_basename}.{format}")
                )
                image_md_dir = os.path.join(output, f"{output_basename}_images")
                os.makedirs(image_md_dir, exist_ok=True)
                image_index = 0

                # Custom image converter for mammoth
                def convert_image(image):
                    nonlocal image_index
                    extension = image.content_type.split("/")[-1]
                    image_filename = f"{output_basename}_{image_index}.{extension}"
                    image_path = os.path.join(image_md_dir, image_filename)
                    with image.open() as image_bytes:
                        buf = image_bytes.read()
                    with open(image_path, "wb") as img_file:
                        # Write the image to the file byte by byte
                        # image is of type Image
                        img_file.write(buf)
                    image_index += 1
                    # Return src attribute that points to the relative image path
                    rel_image_path = os.path.abspath(image_path)
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