import os
import json

from pathlib import Path
from datetime import datetime


class MetadataHandler:
    # Manages metadata extraction, preservation, and tagging for converted files.
    # Supports ID3 (audio), EXIF (images), and custom tags.
    def __init__(self, event_logger, locale: str = "English"):
        self.event_logger = event_logger
        self.locale = locale
        self.metadata_dir = None

    def set_metadata_dir(self, output_dir: str) -> None:
        # Set the directory where metadata JSON files will be stored
        self.metadata_dir = os.path.join(output_dir, ".metadata")
        os.makedirs(self.metadata_dir, exist_ok=True)

    def extract_audio_metadata(self, file_path: str) -> dict:
        # Extract metadata from audio files (ID3 tags, basic info)
        metadata = {
            "format": "audio",
            "extracted_at": datetime.now().isoformat(),
            "tags": {},
        }

        try:
            from moviepy import AudioFileClip

            audio = None
            try:
                audio = AudioFileClip(file_path)
                # Extract basic audio properties
                metadata["tags"]["duration"] = float(audio.duration)
                metadata["tags"]["fps"] = int(audio.fps) if audio.fps else 48000
                metadata["tags"]["nchannels"] = (
                    audio.nchannels if hasattr(audio, "nchannels") else 2
                )
            finally:
                if audio is not None:
                    audio.close()

            # Try to extract ID3 tags
            try:
                from mutagen.easyid3 import EasyID3

                try:
                    tags = EasyID3(file_path)
                    for key, value in tags.items():
                        metadata["tags"][key] = value[0] if isinstance(value, list) else value
                except Exception:
                    # File doesn't have ID3 tags or mutagen not available
                    pass
            except ImportError:
                pass  # mutagen not installed

        except Exception as e:
            self.event_logger.debug(f"Could not extract audio metadata from {file_path}: {e}")

        return metadata

    def extract_image_metadata(self, file_path: str) -> dict:
        # Extract metadata from image files (EXIF, basic info)
        metadata = {
            "format": "image",
            "extracted_at": datetime.now().isoformat(),
            "tags": {},
        }

        try:
            from PIL import Image
            from PIL.ExifTags import TAGS

            with Image.open(file_path) as img:
                # Basic image info
                metadata["tags"]["width"] = img.width
                metadata["tags"]["height"] = img.height
                metadata["tags"]["format"] = img.format
                metadata["tags"]["mode"] = img.mode

                # Extract EXIF data if available
                if hasattr(img, "_getexif") and img._getexif() is not None:
                    exif_data = img._getexif()
                    for tag_id, value in exif_data.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        try:
                            metadata["tags"][tag_name] = str(value)
                        except Exception:
                            pass

        except Exception as e:
            self.event_logger.debug(f"Could not extract image metadata from {file_path}: {e}")

        return metadata

    def extract_document_metadata(self, file_path: str) -> dict:
        # Extract metadata from document files (creation date, properties, etc)
        metadata = {
            "format": "document",
            "extracted_at": datetime.now().isoformat(),
            "tags": {},
        }

        try:
            # File system metadata (universal)
            stat_info = os.stat(file_path)
            metadata["tags"]["created"] = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
            metadata["tags"]["modified"] = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
            metadata["tags"]["size"] = stat_info.st_size

            # Format-specific metadata
            file_ext = Path(file_path).suffix.lower().lstrip(".")

            if file_ext == "pdf":
                try:
                    import fitz

                    doc = fitz.open(file_path)
                    metadata["tags"]["pages"] = len(doc)
                    if doc.metadata:
                        for key, value in doc.metadata.items():
                            if value:
                                metadata["tags"][key] = str(value)
                    doc.close()
                except Exception as e:
                    self.event_logger.debug(f"Could not extract PDF metadata: {e}")

            elif file_ext == "docx":
                try:
                    from docx import Document

                    doc = Document(file_path)
                    core_props = doc.core_properties
                    metadata["tags"]["title"] = core_props.title or ""
                    metadata["tags"]["author"] = core_props.author or ""
                    metadata["tags"]["subject"] = core_props.subject or ""
                    metadata["tags"]["keywords"] = core_props.keywords or ""
                except Exception as e:
                    self.event_logger.debug(f"Could not extract DOCX metadata: {e}")

            elif file_ext == "pptx":
                try:
                    from pptx import Presentation

                    prs = Presentation(file_path)
                    core_props = prs.core_properties
                    metadata["tags"]["title"] = core_props.title or ""
                    metadata["tags"]["author"] = core_props.author or ""
                    metadata["tags"]["subject"] = core_props.subject or ""
                    metadata["tags"]["slides"] = len(prs.slides)
                except Exception as e:
                    self.event_logger.debug(f"Could not extract PPTX metadata: {e}")

        except Exception as e:
            self.event_logger.debug(f"Could not extract document metadata from {file_path}: {e}")

        return metadata

    def extract_metadata(self, file_path: str, file_type: str) -> dict:
        # Extract metadata based on file type
        if file_type == "audio":
            return self.extract_audio_metadata(file_path)
        elif file_type == "image":
            return self.extract_image_metadata(file_path)
        elif file_type == "document":
            return self.extract_document_metadata(file_path)
        else:
            return {"format": file_type, "extracted_at": datetime.now().isoformat(), "tags": {}}

    def save_metadata(self, file_path: str, metadata: dict, output_file_path: str) -> str:
        # Save metadata to a JSON file in the .metadata directory
        # Returns the path to the metadata JSON file
        if self.metadata_dir is None:
            return None

        # Create metadata filename based on output file
        output_filename = Path(output_file_path).stem
        metadata_file = os.path.join(self.metadata_dir, f"{output_filename}.metadata.json")

        try:
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            return metadata_file
        except Exception as e:
            self.event_logger.debug(f"Could not save metadata to {metadata_file}: {e}")
            return None

    def add_custom_tags(self, metadata: dict, custom_tags: dict) -> dict:
        if "custom_tags" not in metadata:
            metadata["custom_tags"] = {}
        metadata["custom_tags"].update(custom_tags)
        return metadata

    def parse_custom_tags(self, tag_args: list) -> dict:
        # Parse custom tag arguments in format: key:value key2:value2
        # Returns a dictionary of custom tags
        custom_tags = {}
        if tag_args:
            for tag in tag_args:
                if ":" in tag:
                    key, value = tag.split(":", 1)
                    custom_tags[key.strip()] = value.strip()
        return custom_tags

    def load_metadata(self, metadata_file: str) -> dict:
        # Load metadata from a JSON file
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.event_logger.debug(f"Could not load metadata from {metadata_file}: {e}")
            return {}

    def apply_metadata_to_file(self, output_file: str, metadata: dict) -> bool:
        # Apply metadata tags back to the output file (when possible).
        # Currently supporting ID3 tags for audio files
        file_ext = Path(output_file).suffix.lower().lstrip(".")
        
        if file_ext in ["mp3", "flac", "m4a", "ogg", "wma"]:
            try:
                from mutagen.easyid3 import EasyID3
                from mutagen.wave import WAVE
                from mutagen.flac import FLAC

                tags_dict = metadata.get("tags", {})
                
                try:
                    if file_ext == "mp3":
                        audio_tags = EasyID3(output_file)
                    elif file_ext == "flac":
                        audio_tags = FLAC(output_file)
                    elif file_ext in ["m4a", "ogg", "wma"]:
                        audio_tags = EasyID3(output_file)
                    else:
                        return False

                    # Apply common tags if they exist in original
                    tag_mapping = {
                        "title": "TIT2",
                        "artist": "TPE1",
                        "album": "TALB",
                        "date": "TDRC",
                    }

                    for src_key, dst_key in tag_mapping.items():
                        if src_key in tags_dict:
                            try:
                                audio_tags[dst_key] = str(tags_dict[src_key])
                            except Exception:
                                pass

                    audio_tags.save()
                    return True
                except Exception as e:
                    self.event_logger.debug(f"Could not apply ID3 tags to {output_file}: {e}")
                    return False
            except ImportError:
                # mutagen not installed
                return False

        return False

    def strip_metadata(self, file_path: str, file_type: str) -> bool:
        # Strip metadata from a file
        #  For audio: removes ID3 tags
        #  For images: creates a copy without EXIF
        #  For documents: basic stripping support
        try:
            if file_type == "audio":
                # For audio, we'll just remove ID3 tags
                try:
                    from mutagen import File as MutagenFile

                    audio_file = MutagenFile(file_path)
                    if audio_file is not None and audio_file.tags is not None:
                        audio_file.delete()
                        return True
                except ImportError:
                    pass  # mutagen not installed
                return False

            elif file_type == "image":
                # For images, create a new image without EXIF
                try:
                    from PIL import Image

                    with Image.open(file_path) as img:
                        # Remove EXIF by converting and re-saving
                        if hasattr(img, "info"):
                            img.info.pop("exif", None)
                        # Convert to RGB to strip metadata
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(file_path, "JPEG", quality=95)
                        return True
                except Exception:
                    return False

        except Exception as e:
            self.event_logger.debug(f"Could not strip metadata from {file_path}: {e}")
            return False

        return False
