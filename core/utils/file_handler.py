import os
import time
import string
import random
import logging
import utils.language_support as lang

from moviepy import VideoFileClip


class FileHandler:
    def __init__(self, event_logger: logging.Logger, locale: str = "English"):
        self.event_logger = event_logger
        self.locale = locale
        self.CONFLICT_RESOLUTION_TIMEOUT = 2.0  # numeric suffix loop attempt time in s

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
                self.event_logger.info(
                    f"[>] {lang.get_translation('output_exists', self.locale) if hasattr(lang, 'get_translation') and 'output_exists' in dir(lang) else '[>] Output file exists, auto-renaming to'}: {candidate_name}"
                )
                return candidate_path
            
            suffix_counter += 1
        
        # Fallback: Use random alphanumeric string (5 characters seems more than enough)
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
        fallback_name = f"{name}_{random_suffix}{ext}"
        fallback_path = os.path.join(directory, fallback_name)
        self.event_logger.info(
            f"[>] {lang.get_translation('output_exists', self.locale) if hasattr(lang, 'get_translation') and 'output_exists' in dir(lang) else '[>] Numeric suffix timeout, using random string'}: {fallback_name}"
        )
        return fallback_path

    def post_process(
        self,
        file_path_set: tuple,
        out_path: str,
        delete: bool,
        show_status: bool = True,
    ) -> str:
        try:
            source_path = self.join_back(file_path_set)
            
            # Resolve filename conflicts
            resolved_out_path = self._resolve_output_file_conflict(out_path)

            # Only log if the conversion was successful and output exists
            if show_status and os.path.exists(resolved_out_path):
                self.event_logger.info(
                    f"[>] {lang.get_translation('converted', self.locale)} "
                    f'"{source_path}" 🡢 "{resolved_out_path}"'
                )

            # Only delete source file if requested, output exists, and source exists
            if delete and os.path.exists(resolved_out_path) and os.path.exists(source_path):
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
        file_paths: dict = {},
        supported_formats: dict = {},
    ) -> dict:
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
