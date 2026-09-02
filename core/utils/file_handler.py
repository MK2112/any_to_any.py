import os
import time
import string
import random
import logging
import utils.language_support as lang

from moviepy import VideoFileClip


def resolve_out_dir_conflict(dir_path: str, timeout: float = 2.0) -> str:
    # Return dir path not colliding with existing user data
    candidate = os.path.abspath(dir_path)
    if not os.path.exists(candidate):
        return candidate
    base = candidate
    start_time = time.time()
    suffix_counter = 1
    while time.time() - start_time < timeout:
        cand = f"{base}_{suffix_counter}"
        if not os.path.exists(cand):
            return cand
        suffix_counter += 1
    random_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"{base}_{random_suffix}"


def safe_output_dir(base_dir: str, timeout: float = 2.0) -> str:
    # Single shared helper for all converters (C2). Returns a non-colliding
    # directory path: base unchanged when free, else base_1/_2/... Never
    # raises and never returns a non-string: falls back to base_dir so
    # callers always get a usable path.
    try:
        resolved = resolve_out_dir_conflict(base_dir, timeout=timeout)
        if isinstance(resolved, str) and resolved:
            return resolved
    except Exception:
        pass
    return base_dir


class FileHandler:
    def __init__(self, event_logger: logging.Logger, locale: str = "English"):
        self.event_logger = event_logger
        self.locale = locale
        self.CONFLICT_RESOLUTION_TIMEOUT = 2.0  # numeric suffix loop attempt time in s
        self.metadata_callback = None

    def join_back(self, file_path_set: tuple) -> str:
        # Join back the file path set to a concurrent path
        return os.path.abspath(
            f"{file_path_set[0]}{file_path_set[1]}.{file_path_set[2]}"
        )

    def _resolve_output_file_conflict(self, output_path: str) -> str:
        # Resolve filename conflicts when output file already exists.
        # Strategy:
        #  1. Try numeric suffixes (file_1.mp3, file_2.mp3, etc.) for up to 2 seconds
        #  2. If timeout exceeded, fallback to random alphanumeric string (5 chars)
        output_path = os.path.abspath(output_path)
        
        if not os.path.exists(output_path):
            return output_path
        
        # Split the output path into directory, name, and extension
        directory = os.path.dirname(output_path)
        filename = os.path.basename(output_path)
        name, ext = os.path.splitext(filename)
        
        start_time = time.time()
        suffix_counter = 1
        
        # Try numeric suffixes with timeout
        while time.time() - start_time < self.CONFLICT_RESOLUTION_TIMEOUT:
            candidate_name = f"{name}_{suffix_counter}{ext}"
            candidate_path = os.path.join(directory, candidate_name)
            if not os.path.exists(candidate_path):
                return candidate_path
            suffix_counter += 1
        
        # Fallback: Use random alphanumeric string (5 characters seems more than enough)
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=5)
        )
        fallback_name = f"{name}_{random_suffix}{ext}"
        return os.path.join(directory, fallback_name)

    def _resolve_output_dir_conflict(self, dir_path: str) -> str:
        # Instance wrapper for converters; delegates to the shared helper so
        # timeout handling and fallback live in exactly one place.
        return safe_output_dir(dir_path, timeout=self.CONFLICT_RESOLUTION_TIMEOUT)

    def post_process(
        self,
        file_path_set: tuple,
        out_path: str,
        delete: bool,
        show_status: bool = True,
    ) -> str:
        try:
            source_path = self.join_back(file_path_set)
            resolved_out_path = os.path.abspath(out_path)
            if show_status and os.path.isfile(resolved_out_path):
                self.event_logger.info(
                    f"[>] {lang.get_translation('converted', self.locale)} "
                    f'"{source_path}" -> "{resolved_out_path}"'
                )

            if os.path.isfile(resolved_out_path) and self.metadata_callback is not None:
                try:
                    self.metadata_callback(
                        source_path, resolved_out_path, file_path_set[2]
                    )
                except Exception as e:
                    self.event_logger.debug(
                        f"Metadata handling skipped for {resolved_out_path}: {e}"
                    )

            if (
                delete
                and os.path.isfile(resolved_out_path)
                and os.path.isfile(source_path)
            ):
                try:
                    os.remove(source_path)
                    self.event_logger.info(
                        f'[-] {lang.get_translation("removed", self.locale)} "{source_path}"'
                    )
                except OSError as e:
                    self.event_logger.warning(
                        f"[!] {lang.get_translation('error', self.locale)}: "
                        f'{lang.get_translation("could_not_remove", self.locale)} "{source_path}": {str(e)}'
                    )
            
            return resolved_out_path

        except Exception as e:
            self.event_logger.error(
                f"[!] {lang.get_translation('error', self.locale)} in post_process: {str(e)}"
            )
            raise

    def has_visuals(self, file_path_set: tuple) -> bool:
        try:
            VideoFileClip(self.join_back(file_path_set)).iter_frames()
            return True
        except Exception as _:
            pass
        return False

    def get_file_paths(
        self,
        input: str,
        file_paths: dict = None,
        supported_formats: dict = None,
    ) -> dict:
        file_paths = file_paths or {}
        supported_formats = supported_formats or {}
        # Get media files from input directory
        def process_file(file_path: str) -> tuple:
            # Dissect "path/to/file.txt" into [path/to, file, txt]
            base_name, file_type = os.path.splitext(file_path)
            file_type = file_type[1:].lower()
            file_name = os.path.basename(base_name)
            path_to_file = os.path.dirname(file_path) + os.sep
            return path_to_file, file_name, file_type

        def schedule_file(file_info: tuple) -> None:
            # If supported, add file to respective category schedule
            for category in supported_formats.keys():
                if file_info[2] in supported_formats[category]:
                    file_paths[category].append(file_info)
                    self.event_logger.info(
                        f"[+] {lang.get_translation('scheduling', self.locale)}: {file_info[1]}.{file_info[2]}"
                    )
                    break

        self.event_logger.info(
            f"[>] {lang.get_translation('scanning', self.locale)}: {input}"
        )

        # Check if file_paths is an empty dict
        if len(file_paths) == 0:
            file_paths = {category: [] for category in supported_formats}

        if input is not None and os.path.isfile(input):
            file_info = process_file(os.path.abspath(input))
            schedule_file(file_info)
        else:
            for directory in [input]:
                if not os.path.exists(directory):
                    raise FileNotFoundError
            for file_name in os.listdir(input):
                file_path = os.path.abspath(os.path.join(input, file_name))
                file_info = process_file(file_path)
                schedule_file(file_info)
        return file_paths
