import os
import time
import string
import random
import threading
import logging
import utils.language_support as lang

from moviepy import VideoFileClip
from concurrent.futures import ThreadPoolExecutor, as_completed


_RESOLUTION_LOCK = threading.Lock()
_CLAIMED = set()


class ConversionCancelled(Exception):
    # Raised at a per-file boundary when the running job was cancelled
    pass


def _claim_name(candidate: str) -> bool:
    # reserve for the caller within this process
    # False when the candidate is already claimed
    with _RESOLUTION_LOCK:
        if candidate in _CLAIMED or os.path.exists(candidate):
            return False
        _CLAIMED.add(candidate)
        return True


def _release_name(candidate: str) -> None:
    # Drop a reservation once the real output exists on disk
    with _RESOLUTION_LOCK:
        _CLAIMED.discard(candidate)


def resolve_out_dir_conflict(dir_path: str, timeout: float = 2.0) -> str:
    candidat_dir = os.path.abspath(dir_path)
    if _claim_name(candidat_dir):
        return candidat_dir
    base_dir = candidat_dir
    claim_t0 = time.time()
    suffix_counter = 1
    while time.time() - claim_t0 < timeout:
        cand = f"{base_dir}_{suffix_counter}"
        if _claim_name(cand):
            return cand
        suffix_counter += 1
        time.sleep(0.001)
    claim_t0 = time.time()  # Fallback to another run for alphanumeric suffixes
    while time.time() - claim_t0 < timeout:
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=5)
        )
        cand = f"{base_dir}_{random_suffix}"
        if _claim_name(cand):
            return cand
        time.sleep(0.001)
    # Callers rmtree() result, handing back candidat_dir here would delete user data
    for _ in range(100):
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        cand = f"{base_dir}_{random_suffix}"
        if _claim_name(cand):
            return cand
    raise FileExistsError(f"Could not resolve a free directory for {base_dir}")


def safe_output_dir(base_dir: str, timeout: float = 2.0) -> str:
    # Return non-colliding dir path: base unchanged when free, else base_1/_2/... or base_<random>
    resolved = resolve_out_dir_conflict(base_dir, timeout=timeout)
    if isinstance(resolved, str) and resolved:
        return resolved
    raise FileExistsError(f"Could not resolve a free directory for {base_dir}")


def sort_frame_filenames(filenames: list) -> list:
    # Order extracted frame file names by the numeric index in their stem,
    # Names without a numeric suffix sort after, by name
    def _key(filename: str) -> tuple:
        index = os.path.splitext(filename)[0].rsplit("-", 1)[-1]
        return (0, int(index)) if index.isdigit() else (1, filename)

    return sorted(filenames, key=_key)


def resolve_worker_count(default: int = 1) -> int:
    try:
        requested = int(os.environ.get("Any2Any_MAX_WORKERS", str(default)))
    except (TypeError, ValueError):
        requested = default
    requested = max(1, requested)
    try:
        cpu = os.cpu_count()
    except Exception:
        cpu = None
    if isinstance(cpu, int):
        requested = min(requested, max(1, cpu - 1))
    return max(1, requested)


def worker_count_for(file_handler, default: int = 1) -> int:
    snapshot = getattr(file_handler, "max_workers", None)
    if isinstance(snapshot, int) and not isinstance(snapshot, bool):
        return max(1, snapshot)
    return resolve_worker_count(default)


def effective_fps(clip_fps, requested=None, default: int = 24):
    # Resolve the frame rate for write_videofile/write_audiofile
    if requested is not None:
        return requested
    return clip_fps if clip_fps else default


def run_parallel(items, fn, max_workers):
    items = list(items)
    if len(items) <= 1 or max_workers <= 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fn, item) for item in items]
        return [future.result() for future in as_completed(futures)]


class FileHandler:
    def __init__(self, event_logger: logging.Logger, locale: str = "English"):
        self.event_logger = event_logger
        self.locale = locale
        self.CONFLICT_RESOLUTION_TIMEOUT = 2.0  # numeric suffix loop attempt time in s
        self.metadata_callback = None
        self.cancel_event = None
        self.max_workers = resolve_worker_count()

    def join_back(self, file_path_set: tuple) -> str:
        # Join back the file path set to a concurrent path
        path = os.path.abspath(
            f"{file_path_set[0]}{file_path_set[1]}.{file_path_set[2]}"
        )
        if not os.path.isfile(path):
            # Extensions get normalized to lowercase during scanning
            # We have to recover the original spelling on case-sensitive filesystems (e.g. DEMO.MP3)
            target = f"{file_path_set[1]}.{file_path_set[2]}".lower()
            try:
                for entry in os.listdir(file_path_set[0]):
                    candidate = os.path.join(file_path_set[0], entry)
                    if entry.lower() == target and os.path.isfile(candidate):
                        return os.path.abspath(candidate)
            except OSError:
                pass
        return path

    def _resolve_output_file_conflict(self, output_path: str) -> str:
        # Resolve filename conflicts when output file already exists.
        # Strategy:
        #  1. Try numeric suffixes (file_1.mp3, file_2.mp3, etc.) for up to 2 seconds
        #  2. If timeout exceeded, fallback to random alphanumeric string (5 chars)
        output_path = os.path.abspath(output_path)

        if _claim_name(output_path):
            return output_path

        # Split the output path into directory, name, and extension
        directory = os.path.dirname(output_path)
        filename = os.path.basename(output_path)
        name, ext = os.path.splitext(filename)

        cand_t0 = time.time()
        suffix_counter = 1

        # Numeric suffixes with timeout
        while time.time() - cand_t0 < self.CONFLICT_RESOLUTION_TIMEOUT:
            candidate_name = f"{name}_{suffix_counter}{ext}"
            candidate_path = os.path.join(directory, candidate_name)
            if _claim_name(candidate_path):
                return candidate_path
            suffix_counter += 1

        cand_t0 = time.time()
        # Alphanumeric random suffixes with timeout for fallback
        while time.time() - cand_t0 < self.CONFLICT_RESOLUTION_TIMEOUT:
            random_suffix = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=5)
            )
            fallback_name = f"{name}_{random_suffix}{ext}"
            candidate_path = os.path.join(directory, fallback_name)
            if _claim_name(candidate_path):
                return candidate_path
        # Last-ditch attempt
        for _ in range(100):
            random_suffix = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            candidate_path = os.path.join(directory, f"{name}_{random_suffix}{ext}")
            if _claim_name(candidate_path):
                return candidate_path
        raise FileExistsError(f"Could not resolve a free filename for {output_path}")

    def _resolve_output_dir_conflict(self, dir_path: str) -> str:
        return safe_output_dir(dir_path, timeout=self.CONFLICT_RESOLUTION_TIMEOUT)

    def check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ConversionCancelled("Conversion cancelled")

    def post_process(
        self,
        file_path_set: tuple,
        out_path: str,
        delete: bool,
        show_status: bool = True,
    ) -> str:
        self.check_cancelled()
        try:
            source_path = self.join_back(file_path_set)
            resolved_out_path = os.path.abspath(out_path)
            if os.path.isfile(resolved_out_path):
                _release_name(resolved_out_path)
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

    def has_visuals(self, file_path_set: tuple, clip=None) -> bool:
        close_clip = clip is None
        try:
            if clip is None:
                clip = VideoFileClip(self.join_back(file_path_set))
            next(clip.iter_frames())
            return True
        except Exception as _:
            pass
        finally:
            if close_clip and clip is not None:
                try:
                    clip.close()
                except Exception:
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
        # Get media files from input dir
        def process_file(file_path: str) -> tuple:
            # Dissect "path/to/file.txt" into ["path/to", "file", "txt"]
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

        # Check if file_paths is empty dict
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
