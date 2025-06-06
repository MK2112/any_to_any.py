import os
from tqdm import tqdm
import docx
import pptx


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
