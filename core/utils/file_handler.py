import os
import logging
from moviepy import VideoFileClip
import utils.language_support as lang


class FileHandler:
    def __init__(self, event_logger: logging.Logger, locale: str = "English"):
        self.event_logger = event_logger
        self.locale = locale

    def join_back(self, file_path_set: tuple) -> str:
        # Join back the file path set to a concurrent path
        return os.path.abspath(
            f"{file_path_set[0]}{file_path_set[1]}.{file_path_set[2]}"
        )
    
    def post_process(
        self,
        file_path_set: tuple,
        out_path: str,
        delete: bool,
        show_status: bool = True,
    ) -> None:
        # Post process after conversion, print, delete source file if desired
        if show_status:
            self.event_logger.info(
                f'[+] {lang.get_translation("converted", self.locale)} "{self.join_back(file_path_set)}" 🡢 "{out_path}"'
            )
        if delete:
            os.remove(self.join_back(file_path_set))
            self.event_logger.info(
                f'[-] {lang.get_translation("removed", self.locale)} "{self.join_back(file_path_set)}"'
            )

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
            file_type = file_path.split(".")[-1].lower()
            file_name = os.path.basename(file_path)
            file_name = file_name[: file_name.rfind(".")]
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
