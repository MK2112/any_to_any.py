import os
import re
import sys
import json
import uuid
import time
import shutil
import platform
import threading
import subprocess
from pathlib import Path
from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QComboBox,
    QLineEdit,
    QCheckBox,
    QProgressBar,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QDialog,
    QTextEdit,
    QSpinBox,
    QGroupBox,
    QGridLayout,
    QMenu,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import utils.language_support as lang
from core.controller import Controller
from core.utils.resolution import available_resolutions
from utils.category import Category
from utils.version import VERSION
from utils.version_check import check_for_update

if "--version" in sys.argv or "--self-test" in sys.argv:
    print(VERSION)
    sys.exit(0)

APP_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = str(Path.home() / ".any_to_any_gui_settings.json")

STYLE_CONVERT_BTN = """
    QPushButton {
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
    }
    QPushButton:hover { background-color: #43A047; }
    QPushButton:pressed { background-color: #388E3C; }
    QPushButton:disabled { background-color: #777777; }
"""

STYLE_CANCEL_BTN = """
    QPushButton {
        background-color: #f44336;
        color: white;
        font-weight: bold;
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
    }
    QPushButton:hover { background-color: #e53935; }
    QPushButton:pressed { background-color: #c62828; }
    QPushButton:disabled { background-color: #777777; }
"""

PROGRESS_STYLE_DONE = (
    "QProgressBar {background: #e0ffe0;} QProgressBar::chunk {background: #4CAF50;}"
)
PROGRESS_STYLE_CANCELLED = (
    "QProgressBar {background: #fff3e0;} QProgressBar::chunk {background: #ff9800;}"
)
PROGRESS_STYLE_ERROR = (
    "QProgressBar {background: #ffe0e0;} QProgressBar::chunk {background: #e53935;}"
)

DRAG_OVER_STYLE_LIST = "QListWidget { border: None; background-color: #606060; }"
DRAG_OVER_STYLE_WINDOW = "QListWidget { border: None; background-color: #404040; }"

GENERIC_STATUS_TOKENS = {"", "starting", "preparing", "waiting", "processing", "running", "done"}

SPLIT_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+|end|rest)$", re.IGNORECASE)
SPLIT_SINGLE_RE = re.compile(r"^(?:\d+|end|rest)$", re.IGNORECASE)


def tr_key(key, locale=None):
    # Resolve a translation with graceful fallback to English, mirroring the
    # web interface behaviour: untranslated keys never surface as raw keys.
    language = locale if locale is not None else lang.get_system_language()
    text = lang.TRANSLATIONS.get(language, lang.TRANSLATIONS["English"]).get(key)
    if text is None:
        text = lang.TRANSLATIONS["English"].get(key, key)
    return text


class UpdateCheckBridge(QObject):
    # Bridges results of the background update check onto the GUI thread.
    update_available = pyqtSignal(str)


def start_update_check(bridge) -> None:
    # Daemonized on purpose: the check never delays startup and quitting the
    # app while a slow request is in flight cannot crash teardown (a running
    # QThread destroyed at exit would abort the process).
    def job():
        latest = check_for_update()
        if latest:
            bridge.update_available.emit(latest)

    threading.Thread(target=job, daemon=True, name="update-check").start()


class ConversionThread(QThread):
    progress_updated = pyqtSignal(dict)
    conversion_finished = pyqtSignal(str, str)  # job_id, output_dir
    error_occurred = pyqtSignal(str)
    conversion_cancelled = pyqtSignal(str)  # job_id

    def __init__(
        self,
        input_files,
        output_format,
        output_dir,
        merge=False,
        concat=False,
        framerate=None,
        quality=None,
        recursive=False,
        delete=False,
        workers=1,
        resolution=None,
        split=None,
        preserve_meta=False,
        strip_meta=False,
    ):
        super().__init__()
        self.input_files = input_files
        self.output_format = output_format
        self.output_dir = output_dir
        self.merge = merge
        self.concat = concat
        self.framerate = framerate
        self.quality = quality
        self.recursive = recursive
        self.delete = delete
        self.workers = workers
        self.resolution = resolution
        self.split = split
        self.preserve_meta = preserve_meta
        self.strip_meta = strip_meta
        self.job_id = uuid.uuid4().hex[:8]
        self.shared_progress = {}
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress_updated.emit(
                {
                    "progress": None,
                    "message": "Starting conversion...",
                    "status": "starting",
                    "error": None,
                }
            )

            controller = Controller(
                job_id=self.job_id,
                shared_progress_dict=self.shared_progress,
                is_web=True,
            )

            # The backend derives concrete output file names itself; reporting
            # the directory stays correct across convert/merge/concat/split/
            # resize-only jobs alike.
            output_path = str(Path(self.output_dir))

            conversion_done = threading.Event()
            error_holder = {}

            def conversion_job():
                try:
                    controller.run(
                        input_path_args=self.input_files,
                        format=self.output_format,
                        output=output_path,
                        framerate=self.framerate,
                        quality=self.quality,
                        split=self.split,
                        merge=self.merge,
                        concat=self.concat,
                        delete=self.delete,
                        across=False,
                        recursive=self.recursive,
                        dropzone=False,
                        language=None,
                        workers=self.workers,
                        preserve_meta=self.preserve_meta,
                        add_tag=[],
                        strip_meta=self.strip_meta,
                        resolution=self.resolution,
                    )
                except SystemExit as exc:
                    # The core exits gracefully (sys.exit) e.g. when no media
                    # was found; SystemExit is a BaseException and would
                    # otherwise bypass error reporting entirely.
                    error_holder["error"] = str(exc) or "Processing stopped early"
                except BaseException as exc:
                    error_holder["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    conversion_done.set()

            worker = threading.Thread(target=conversion_job, daemon=True)
            worker.start()

            last_snapshot = None
            # Poll shared progress every 100ms, emitting only on change
            while not conversion_done.is_set() and not self._cancelled:
                prog = self.shared_progress.get(self.job_id, {})
                progress = prog.get("progress")
                total = prog.get("total", 100)
                percent = None
                if progress is not None and total:
                    try:
                        percent = int(100 * float(progress) / float(total))
                    except Exception:
                        percent = None
                message = prog.get("message", prog.get("status", ""))
                status = prog.get("status", "running")
                error = prog.get("error")
                snapshot = (percent, message, status, error)
                if snapshot != last_snapshot:
                    self.progress_updated.emit(
                        {
                            "progress": percent,
                            "message": message,
                            "status": status,
                            "error": error,
                        }
                    )
                    last_snapshot = snapshot
                time.sleep(0.1)

            if self._cancelled:
                self.progress_updated.emit(
                    {
                        "progress": 0,
                        "message": "Conversion cancelled",
                        "status": "cancelled",
                        "error": None,
                    }
                )
                worker.join(timeout=5.0)
                self.conversion_cancelled.emit(self.job_id)
                return

            worker.join(timeout=30.0)

            prog = self.shared_progress.get(self.job_id, {})
            self.progress_updated.emit(
                {
                    "progress": 100,
                    "message": prog.get("message", prog.get("status", "Done")),
                    "status": prog.get("status", "done"),
                    "error": prog.get("error"),
                }
            )

            if "error" in error_holder:
                self.error_occurred.emit(error_holder["error"])
            else:
                self.conversion_finished.emit(self.job_id, output_path)

        except Exception as e:
            self.error_occurred.emit(str(e))


class DropListWidget(QListWidget):
    # File list supporting external drops (files/folders) as well as internal
    # reordering; subclassing keeps Qt's virtual dispatch intact unlike
    # instance-level handler monkeypatching.
    files_dropped = pyqtSignal(list)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setStyleSheet(DRAG_OVER_STYLE_LIST)
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setStyleSheet("")
        if event.mimeData().hasUrls() and event.source() is not self:
            paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.toLocalFile()
            ]
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            # Preserve built-in internal-move reordering
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = Controller(locale=lang.get_system_language(), is_web=True)
        self.locale = self.controller.locale
        self._file_paths_set = set()  # Performance: O(1) duplicate checking
        self.conversion_threads = {}
        self.current_thread = None
        self._conversion_start_time = None
        self._progress_epoch = 0  # Guards stale progress-reset timers
        self.supported_formats = self.get_supported_formats()
        self.supported_extensions = {
            ext.lower()
            for formats in self.controller._supported_formats.values()
            for ext in formats.keys()
        }
        self.init_ui()
        self._setup_shortcuts()
        self.setWindowTitle(f"any_to_any.py {VERSION}")
        icon_path = APP_ROOT / "img" / "app_icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(850, 650)
        self.setAcceptDrops(True)  # Enable drag-drop on main window

    def _tr(self, key):
        return tr_key(key, self.locale)

    def _setup_shortcuts(self):
        # Keyboard shortcuts, will expand this in the future
        QShortcut(QKeySequence("Ctrl+O"), self, self.add_files)
        QShortcut(QKeySequence("Delete"), self, self.remove_selected)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.start_conversion)
        QShortcut(QKeySequence("Escape"), self, self.cancel_conversion)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, self.add_folder)

    def get_supported_formats(self):
        formats = {}
        for category, mapping in self.controller._supported_formats.items():
            cat_name = str(category).split(".")[-1].replace("_", " ").title()
            formats[cat_name] = sorted(list(mapping.keys()))
        return formats

    # ---- Drag & drop -----------------------------------------------------

    @staticmethod
    def _expand_paths(paths):
        files_to_add = []
        for path in paths:
            if not path:
                continue
            if os.path.isfile(path):
                files_to_add.append(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        files_to_add.append(os.path.join(root, file))
        return files_to_add

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.file_list.setStyleSheet(DRAG_OVER_STYLE_WINDOW)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.file_list.setStyleSheet("")
        event.accept()

    def dropEvent(self, event):
        self.file_list.setStyleSheet("")
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()
        ]
        files_to_add = self._expand_paths(paths)
        if files_to_add:
            self.add_files_batch(files_to_add)
        event.accept()

    # ---- File list management -------------------------------------------

    def add_files_batch(self, files):
        # Aggregator: adds multiple files with a single UI update, skipping
        # duplicates and extensions the backend would reject anyway.
        self.file_list.setUpdatesEnabled(False)
        try:
            for file in files:
                if file in self._file_paths_set or not os.path.isfile(file):
                    continue
                if Path(file).suffix.lstrip(".").lower() not in self.supported_extensions:
                    continue
                self._file_paths_set.add(file)
                item = QListWidgetItem(Path(file).name)
                item.setData(Qt.ItemDataRole.UserRole, file)
                item.setToolTip(file)
                self.file_list.addItem(item)
        finally:
            self.file_list.setUpdatesEnabled(True)
            self._update_file_count()
            self._update_mode_dependent_ui()

    def add_file_to_list(self, file):
        if not os.path.isfile(file):
            return
        if file in self._file_paths_set:
            return
        self._file_paths_set.add(file)
        item = QListWidgetItem(Path(file).name)
        item.setData(Qt.ItemDataRole.UserRole, file)
        item.setToolTip(file)
        self.file_list.addItem(item)
        self._update_file_count()
        self._update_mode_dependent_ui()

    def _update_file_count(self):
        count = self.file_list.count()
        self.file_count_label.setText(
            f"{count} {lang.get_translation('file(s)', self.locale)}"
        )

    def _create_folder_icon(self):
        svg = """
                <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>
                    <path d='M3 7h6l2 2h10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z' fill='#F4C542' stroke='#8A6A1D' stroke-width='1.2'/>
                    <path d='M3 9h18' stroke='#8A6A1D' stroke-width='1.2'/>
                </svg>
              """.strip()

        icon = QIcon()
        for size in (16, 20, 24, 32):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer = None
            try:
                from PyQt6.QtSvg import QSvgRenderer

                renderer = QSvgRenderer(bytearray(svg, encoding="utf-8"))
                renderer.render(painter)
            except Exception:
                # Fallback simple folder glyph if QtSvg is unavailable.
                painter.setPen(QColor("#8A6A1D"))
                painter.setBrush(QColor("#F4C542"))
                painter.drawRoundedRect(2, 7, size - 4, size - 9, 2, 2)
                painter.drawRect(2, 5, int(size * 0.45), 4)
            finally:
                painter.end()
            icon.addPixmap(pixmap)
        return icon

    def open_current_output_dir(self):
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("no_dir_exist", self.locale).replace(
                    "[dir]", output_dir or "-"
                ),
            )
            return
        self._open_file_location(output_dir)

    # ---- Resolution support ---------------------------------------------

    def _resolution_ladder_for_target(self, target_format):
        # Allowed resolutions for a movie/codec/protocol target, largest first
        supported = self.controller._supported_formats
        if target_format in self.controller._fmt_movie_keys:
            return available_resolutions(supported[Category.MOVIE], target_format)
        if target_format in self.controller._fmt_codec_keys:
            return available_resolutions(supported[Category.MOVIE_CODECS], target_format)
        if target_format in self.controller._fmt_protocol_keys:
            return available_resolutions(supported[Category.PROTOCOLS], target_format)
        return []

    def _selected_movie_ladder_intersection(self):
        # For resize-only jobs: resolutions every selected movie file permits
        ladders = []
        seen_exts = set()
        for i in range(self.file_list.count()):
            ext = Path(self.file_list.item(i).data(Qt.ItemDataRole.UserRole)).suffix.lstrip(".").lower()
            if ext in seen_exts:
                continue
            seen_exts.add(ext)
            ladder = self._resolution_ladder_for_target(ext)
            if ladder:
                ladders.append(set(ladder))
        if not ladders:
            return []
        common = set.intersection(*ladders)
        return [res for res in self.controller._STD_RES if res in common]

    def _populate_resolution_combo(self, allowed):
        # The resolution field shares its grid slot with the split field; it
        # is shown only when a ladder exists for the effective mode.
        combo = self.resolution_combo
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self._tr("resolution_original"), "")
        for res in allowed:
            combo.addItem(res, res)
        if previous and previous in allowed:
            combo.setCurrentIndex(combo.findData(previous))
        else:
            combo.setCurrentIndex(0)
        combo.setEnabled(bool(allowed))
        combo.blockSignals(False)
        visible = bool(allowed)
        combo.setVisible(visible)
        self.resolution_label.setVisible(visible)

    def _update_mode_dependent_ui(self):
        # Single source of truth for controls depending on the selected mode;
        # keeps the split and resolution fields mutually exclusive and hidden
        # whenever they cannot apply.
        merge = self.merge_check.isChecked()
        concat = self.concat_check.isChecked()
        merge_or_concat = merge or concat
        target = self.format_combo.currentData()

        # Split row: offered exclusively for PDF targets outside merge/concat
        split_visible = target == "pdf" and not merge_or_concat
        split_text = self.split_edit.text().strip()
        if not split_visible and split_text:
            self.split_edit.blockSignals(True)
            self.split_edit.clear()
            self.split_edit.blockSignals(False)
            split_text = ""
        self.split_label.setVisible(split_visible)
        self.split_edit.setVisible(split_visible)

        # A filled split pattern excludes merging/concatenating (CLI rules)
        lock_merge_concat = bool(split_text)
        self.merge_check.setEnabled(not lock_merge_concat)
        self.concat_check.setEnabled(not lock_merge_concat)

        # Resolution row: per-target ladder, intersection for resize-only
        if merge_or_concat:
            self._populate_resolution_combo([])
        elif target == "original":
            self._populate_resolution_combo(self._selected_movie_ladder_intersection())
        elif target:
            self._populate_resolution_combo(self._resolution_ladder_for_target(target))
        else:
            self._populate_resolution_combo([])

    def _on_format_changed(self):
        self._update_mode_dependent_ui()

    # ---- UI construction --------------------------------------------------

    def init_ui(self):
        self.last_dir = str(Path.home())
        self.settings = load_settings()
        if "last_dir" in self.settings:
            self.last_dir = self.settings["last_dir"]
        if "locale" in self.settings:
            self.locale = self.settings["locale"]

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Input files section
        input_group = QGroupBox(lang.get_translation("select_files", self.locale))
        input_layout = QVBoxLayout(input_group)

        # File list
        self.file_list = DropListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.file_list.setUniformItemSizes(True)
        self.file_list.files_dropped.connect(
            lambda paths: self.add_files_batch(self._expand_paths(paths))
        )
        self.file_list.setMinimumHeight(150)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_file_context_menu)
        input_layout.addWidget(self.file_list)

        # File count and buttons
        file_btn_layout = QHBoxLayout()
        self.file_count_label = QLabel(
            f"0 {lang.get_translation('file(s)', self.locale)}"
        )
        file_btn_layout.addWidget(self.file_count_label)
        file_btn_layout.addStretch()

        self.add_files_btn = QPushButton(lang.get_translation("add_files", self.locale))
        self.add_files_btn.clicked.connect(self.add_files)

        self.add_folder_btn = QPushButton(
            lang.get_translation("add_folder", self.locale)
        )
        self.add_folder_btn.clicked.connect(self.add_folder)

        self.remove_btn = QPushButton(lang.get_translation("remove", self.locale))
        self.remove_btn.clicked.connect(self.remove_selected)

        self.clear_btn = QPushButton(lang.get_translation("clear_all", self.locale))
        self.clear_btn.clicked.connect(self.clear_all_files)

        for file_btn_widget in [
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
        ]:
            file_btn_layout.addWidget(file_btn_widget)

        input_layout.addLayout(file_btn_layout)
        layout.addWidget(input_group)

        # Conversion settings group
        settings_group = QGroupBox(lang.get_translation("settings", self.locale))
        settings_layout = QGridLayout(settings_group)

        # Row 0: Format and output directory
        format_label = QLabel(lang.get_translation("convert", self.locale) + ":")
        self.format_combo = QComboBox()
        self.format_combo.addItem(lang.get_translation("resolution_original", self.locale), "original")
        for cat, fmts in self.supported_formats.items():
            self.format_combo.addItem(f"--- {cat} ---")
            idx = self.format_combo.count() - 1
            self.format_combo.model().item(idx).setEnabled(False)
            for fmt in fmts:
                self.format_combo.addItem(f"{fmt}", fmt)
                self.format_combo.setItemData(
                    self.format_combo.count() - 1, f"{cat}", Qt.ItemDataRole.ToolTipRole
                )
        self.format_combo.setCurrentIndex(1)  # Category header: force explicit choice
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        settings_layout.addWidget(format_label, 0, 0)
        settings_layout.addWidget(self.format_combo, 0, 1)

        output_dir_label = QLabel(lang.get_translation("output_dir", self.locale) + ":")
        self.output_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.output_dir_edit.setMinimumWidth(200)
        browse_btn = QPushButton(lang.get_translation("browse", self.locale))
        browse_btn.clicked.connect(self.browse_output_dir)
        self.open_output_btn = QPushButton()
        self.open_output_btn.setIcon(self._create_folder_icon())
        self.open_output_btn.setToolTip("Open target folder")
        self.open_output_btn.setFixedWidth(34)
        self.open_output_btn.clicked.connect(self.open_current_output_dir)
        settings_layout.addWidget(output_dir_label, 0, 2)
        settings_layout.addWidget(self.output_dir_edit, 0, 3)
        settings_layout.addWidget(browse_btn, 0, 4)
        settings_layout.addWidget(self.open_output_btn, 0, 5)

        framerate_label = QLabel(f"{lang.get_translation('framerate', self.locale)}:")
        self.framerate_spin = QSpinBox()
        self.framerate_spin.setRange(0, 120)
        self.framerate_spin.setValue(0)
        self.framerate_spin.setSpecialValueText("Auto")
        self.framerate_spin.setToolTip(
            lang.get_translation("framerate_help", self.locale)
        )
        settings_layout.addWidget(framerate_label, 1, 0)
        settings_layout.addWidget(self.framerate_spin, 1, 1)

        quality_label = QLabel(f"{lang.get_translation('quality', self.locale)}:")
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Default", "High", "Medium", "Low"])
        settings_layout.addWidget(quality_label, 1, 2)
        settings_layout.addWidget(self.quality_combo, 1, 3)

        workers_label = QLabel(f"{lang.get_translation('workers', self.locale)}:")
        self.workers_spin = QSpinBox()
        cpu_count = os.cpu_count() or 2
        self.workers_spin.setRange(1, max(1, min(cpu_count - 1, 32)))
        self.workers_spin.setValue(1)
        self.workers_spin.setToolTip(
            lang.get_translation("max_threads", self.locale)
        )
        settings_layout.addWidget(workers_label, 2, 0)
        settings_layout.addWidget(self.workers_spin, 2, 1)

        # Row 2 (right): Resolution and Split Pages share this slot; exactly
        # one of them can apply at a time (movies vs PDF targets), so the
        # inapplicable one stays hidden and the layout collapses cleanly.
        self.resolution_label = QLabel(
            f"{lang.get_translation('resolution_label', self.locale)}:"
        )
        self.resolution_combo = QComboBox()
        self.resolution_combo.setToolTip(
            lang.get_translation("resolution_help", self.locale)
        )
        settings_layout.addWidget(self.resolution_label, 2, 2)
        settings_layout.addWidget(self.resolution_combo, 2, 3)

        split_label = QLabel(f"{self._tr('split_pages')}:")
        self.split_label = split_label
        self.split_edit = QLineEdit()
        self.split_edit.setPlaceholderText(self._tr("split_placeholder"))
        self.split_edit.setToolTip(lang.get_translation("split_help", self.locale))
        self.split_edit.textChanged.connect(lambda _: self._update_mode_dependent_ui())
        settings_layout.addWidget(split_label, 2, 2)
        settings_layout.addWidget(self.split_edit, 2, 3)

        # Row 3: Metadata handling (single selector, details on hover)
        self.metadata_label = QLabel(f"{self._tr('metadata_label')}:")
        self.metadata_combo = QComboBox()
        self.metadata_combo.addItems(["Default", "Preserve", "Strip"])
        self.metadata_combo.setToolTip(
            f"{lang.get_translation('preserve_meta', self.locale)}\n\n"
            f"{lang.get_translation('strip_meta', self.locale)}"
        )
        settings_layout.addWidget(self.metadata_label, 3, 0)
        settings_layout.addWidget(self.metadata_combo, 3, 1, 1, 2)

        layout.addWidget(settings_group)

        # Options checkboxes
        options_layout = QHBoxLayout()
        self.merge_check = QCheckBox(lang.get_translation("merge", self.locale))
        self.concat_check = QCheckBox(lang.get_translation("concatenate", self.locale))
        self.recursive_check = QCheckBox(lang.get_translation("recursive", self.locale))
        self.delete_check = QCheckBox(
            lang.get_translation("delete source files", self.locale)
        )
        self.open_target_folder_check = QCheckBox(
            lang.get_translation("show_folder_on_completion", self.locale)
        )

        for widget in [
            self.merge_check,
            self.concat_check,
            self.recursive_check,
            self.delete_check,
            self.open_target_folder_check,
        ]:
            options_layout.addWidget(widget)

        self.merge_check.toggled.connect(lambda _: self._update_mode_dependent_ui())
        self.concat_check.toggled.connect(lambda _: self._update_mode_dependent_ui())

        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Progress section
        progress_layout = QVBoxLayout()
        progress_label = QLabel(lang.get_translation("progress", self.locale) + ":")
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        layout.addLayout(progress_layout)

        # Action buttons
        action_layout = QHBoxLayout()
        self.settings_btn = QPushButton(lang.get_translation("settings", self.locale))
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        self.help_btn = QPushButton(lang.get_translation("help", self.locale))
        self.help_btn.clicked.connect(self.open_help_dialog)

        action_layout.addWidget(self.settings_btn)
        action_layout.addWidget(self.help_btn)
        action_layout.addStretch()

        self.cancel_btn = QPushButton(lang.get_translation("cancel", self.locale))
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(STYLE_CANCEL_BTN)

        self.convert_btn = QPushButton(lang.get_translation("convert", self.locale))
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setStyleSheet(STYLE_CONVERT_BTN)

        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.convert_btn)
        layout.addLayout(action_layout)

        # Set layout margins and spacing
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Initialize dependent controls once everything exists
        self._update_mode_dependent_ui()

    # ---- File actions -----------------------------------------------------

    def clear_all_files(self):
        self.file_list.clear()
        self._file_paths_set.clear()
        self._update_file_count()
        self._update_mode_dependent_ui()

    def add_files(self):
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        files, _ = file_dialog.getOpenFileNames(
            self,
            lang.get_translation("select_files", self.locale),
            self.last_dir,
            "All Files (*.*)",
        )
        if files:
            self.last_dir = str(Path(files[0]).parent)
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            self.add_files_batch(files)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, lang.get_translation("select_folder", self.locale), self.last_dir
        )
        if folder:
            self.last_dir = folder
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            files = []
            for root, _, names in os.walk(folder):
                for name in names:
                    files.append(os.path.join(root, name))
            self.add_files_batch(files)

    def remove_selected(self):
        rows = sorted(
            {self.file_list.row(item) for item in self.file_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            item = self.file_list.item(row)
            if item is not None:
                self._file_paths_set.discard(item.data(Qt.ItemDataRole.UserRole))
                self.file_list.takeItem(row)
        self._update_file_count()
        self._update_mode_dependent_ui()

    def show_file_context_menu(self, pos):
        # Right-click context menu for file list
        menu = QMenu(self)
        selected = self.file_list.selectedItems()

        if selected:
            remove_action = menu.addAction(
                lang.get_translation("remove_selected_files", self.locale)
            )
            remove_action.triggered.connect(self.remove_selected)
            if len(selected) == 1:
                file_path = selected[0].data(Qt.ItemDataRole.UserRole)
                open_folder_action = menu.addAction(self._tr("open_containing_folder"))
                open_folder_action.triggered.connect(
                    lambda: self._open_file_location(file_path)
                )

        menu.addSeparator()

        clear_action = menu.addAction(lang.get_translation("clear_all", self.locale))
        clear_action.triggered.connect(self.clear_all_files)
        add_files_action = menu.addAction(lang.get_translation("add_files", self.locale))
        add_files_action.triggered.connect(self.add_files)
        add_folder_action = menu.addAction(
            lang.get_translation("add_folder", self.locale)
        )
        add_folder_action.triggered.connect(self.add_folder)

        menu.exec(self.file_list.mapToGlobal(pos))

    def _open_file_location(self, file_path):
        folder = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
        system = platform.system()
        openers = {
            "Linux": (
                ["xdg-open"],
                ["gio", "open"],
                ["kde-open5"],
                ["kde-open"],
                ["nautilus"],
                ["dolphin"],
                ["thunar"],
                ["nemo"],
                ["pcmanfm"],
            ),
            "Darwin": (["open"],),
            "Windows": (["explorer"],),
        }.get(system, ())
        # PyInstaller's bootloader points LD_LIBRARY_PATH (and friends) at the
        # extraction directory; GUI openers inheriting that can fail to start
        # due to mismatched bundled libraries. Hand them a clean slate.
        blocked_prefixes = ("_MEI", "_PYI")
        child_env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(blocked_prefixes)
            and key not in ("LD_LIBRARY_PATH", "LD_PRELOAD")
        }
        popen_kwargs = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_env,
        )
        if system != "Windows":
            # Windowed PyInstaller binaries may carry invalid stdio handles;
            # detaching the spawned opener from them keeps the call working.
            popen_kwargs["start_new_session"] = True
        for opener in openers:
            if shutil.which(opener[0]) is None:
                continue
            try:
                process = subprocess.Popen(opener + [folder], **popen_kwargs)
            except OSError:
                continue
            if system == "Windows":
                # explorer.exe always exits non-zero, even on success
                return
            # Openers like xdg-open exit non-zero when they could not hand
            # the folder off; give them a brief window to reveal that and
            # fall through to the next candidate on failure.
            try:
                if process.wait(timeout=1.0) == 0:
                    return
            except subprocess.TimeoutExpired:
                # Still running: the opener (e.g. a file manager) took over
                return
        QMessageBox.warning(
            self,
            lang.get_translation("error", self.locale),
            f'Could not open "{folder}".',
        )

    def browse_output_dir(self):
        # Start from current output dir if set, otherwise last used dir
        start_dir = self.output_dir_edit.text().strip()
        if not start_dir or not os.path.isdir(start_dir):
            start_dir = self.last_dir

        directory = QFileDialog.getExistingDirectory(
            self,
            lang.get_translation("select_output_dir", self.locale),
            start_dir,
        )
        if directory:
            self.last_dir = directory
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            self.output_dir_edit.setText(directory)

    def _prune_missing_sources(self):
        # Drop list entries whose source files are gone (e.g. deleted after a
        # successful conversion) so the list never offers stale inputs.
        missing_rows = []
        for i in range(self.file_list.count()):
            path = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            if not os.path.exists(path):
                missing_rows.append(i)
        for row in reversed(missing_rows):
            item = self.file_list.item(row)
            if item is not None:
                self._file_paths_set.discard(item.data(Qt.ItemDataRole.UserRole))
                self.file_list.takeItem(row)
        if missing_rows:
            self._update_file_count()
            self._update_mode_dependent_ui()

    # ---- Split helpers ----------------------------------------------------

    @staticmethod
    def _is_valid_split_pattern(pattern):
        # Mirrors the backend's page-range grammar ('1-3,8-end', 'rest', also
        # ';'-delimited), while rejecting reversed ranges up front which the
        # backend would silently drop.
        normalized = pattern.replace(";", ",")
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if not parts:
            return False
        for part in parts:
            if SPLIT_SINGLE_RE.match(part):
                continue
            match = SPLIT_RANGE_RE.match(part)
            if not match:
                return False
            end_token = match.group(2)
            if end_token.isdigit() and int(end_token) < int(match.group(1)):
                return False
        return True

    # ---- Conversion -------------------------------------------------------

    def start_conversion(self):
        if self.current_thread is not None and self.current_thread.isRunning():
            return  # Shortcut-triggered double start guard

        input_files = [
            self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.file_list.count())
        ]
        if not input_files:
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("no_files_selected", self.locale),
            )
            return

        output_dir = self.output_dir_edit.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("no_dir_exist", self.locale).replace(
                    "[dir]", output_dir or "-"
                ),
            )
            return

        merge = self.merge_check.isChecked()
        concat = self.concat_check.isChecked()
        if merge and concat:
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("merge_concat_error", self.locale),
            )
            return

        # Only fields actually offered by the current mode contribute; hidden
        # ones are inert by construction.
        split_pattern = (
            self.split_edit.text().strip() if self.split_edit.isVisibleTo(self) else ""
        )
        if split_pattern and (merge or concat):
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("split_merge_error", self.locale),
            )
            return

        quality_map = {
            "Default": None,
            "High": "high",
            "Medium": "medium",
            "Low": "low",
        }

        resolution = (
            self.resolution_combo.currentData() or None
            if self.resolution_combo.isVisibleTo(self)
            else None
        )
        run_format = self.format_combo.currentData()
        run_split = None

        if split_pattern:
            # Splitting ignores the output format and needs a PDF input
            if not self._is_valid_split_pattern(split_pattern):
                QMessageBox.warning(
                    self,
                    lang.get_translation("error", self.locale),
                    lang.get_translation("split_help", self.locale),
                )
                return
            if not any(Path(f).suffix.lower() == ".pdf" for f in input_files):
                QMessageBox.warning(
                    self,
                    lang.get_translation("error", self.locale),
                    self._tr("no_format_available_split"),
                )
                return
            run_format = None
            run_split = split_pattern
            resolution = None
        elif run_format == "original":
            # Resize-only job: keep each input's format, apply the resolution
            has_movies = any(
                self._resolution_ladder_for_target(
                    Path(f).suffix.lstrip(".").lower()
                )
                for f in input_files
            )
            if not has_movies:
                QMessageBox.warning(
                    self,
                    lang.get_translation("error", self.locale),
                    lang.get_translation("resize_only_movies_required", self.locale),
                )
                return
            if not resolution:
                QMessageBox.warning(
                    self,
                    lang.get_translation("error", self.locale),
                    lang.get_translation("resolution_required", self.locale),
                )
                return
            run_format = None
        elif run_format is None:
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("no_format_selected", self.locale),
            )
            return
        elif resolution:
            allowed = self._resolution_ladder_for_target(run_format)
            if allowed and resolution not in allowed:
                QMessageBox.warning(
                    self,
                    lang.get_translation("error", self.locale),
                    tr_key("resolution_unsupported", self.locale).format(
                        res=resolution,
                        fmt=run_format,
                        list=", ".join(allowed),
                    ),
                )
                return
        if merge or concat:
            # Merging/concatenating never applies a resolution (web parity)
            resolution = None

        # Disable UI during conversion
        self.set_ui_enabled(False)
        self.status_label.setText(
            lang.get_translation("preparing_conversion", self.locale)
        )
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("")
        self._progress_epoch += 1

        # Start conversion thread
        self._conversion_start_time = time.time()  # For ETA
        self.current_thread = ConversionThread(
            input_files,
            run_format,
            output_dir,
            merge=merge,
            concat=concat,
            framerate=self.framerate_spin.value()
            if self.framerate_spin.value() > 0
            else None,
            quality=quality_map.get(self.quality_combo.currentText()),
            recursive=self.recursive_check.isChecked(),
            delete=self.delete_check.isChecked(),
            workers=self.workers_spin.value(),
            resolution=resolution,
            split=run_split,
            preserve_meta=self.metadata_combo.currentText() == "Preserve",
            strip_meta=self.metadata_combo.currentText() == "Strip",
        )
        self.current_thread.progress_updated.connect(self.update_progress)
        self.current_thread.conversion_finished.connect(self.conversion_completed)
        self.current_thread.error_occurred.connect(self.conversion_error)
        self.current_thread.conversion_cancelled.connect(self.conversion_cancelled)
        self.conversion_threads[self.current_thread.job_id] = self.current_thread
        self.current_thread.start()

    def cancel_conversion(self):
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.cancel()
            self.status_label.setText(self._tr("cancelling"))

    def update_progress(self, progress_info):
        value = progress_info.get("progress")
        status = progress_info.get("status", "")
        error = progress_info.get("error")
        message = progress_info.get("message", "")

        if value is None or status in ("starting", "preparing", "waiting"):
            self.progress_bar.setRange(0, 0)  # Indeterminate
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))

        # Color cues
        if status == "done":
            self.progress_bar.setStyleSheet(PROGRESS_STYLE_DONE)
        elif status == "cancelled":
            self.progress_bar.setStyleSheet(PROGRESS_STYLE_CANCELLED)
        elif error or status == "error":
            self.progress_bar.setStyleSheet(PROGRESS_STYLE_ERROR)

        if error:
            self.status_label.setText(f"Error: {error}")
            return

        eta_str = None
        # Show ETA
        if (
            value is not None
            and value > 0
            and value < 100
            and self._conversion_start_time is not None
        ):
            elapsed = time.time() - self._conversion_start_time
            if elapsed > 0.5:
                try:
                    estimated_total = elapsed / (value / 100.0)
                    eta_seconds = max(0, estimated_total - elapsed)
                    if eta_seconds < 60:
                        eta_str = f"{int(eta_seconds)}s"
                    elif eta_seconds < 3600:
                        eta_str = (
                            f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                        )
                    else:
                        eta_str = f"{int(eta_seconds // 3600)}h {int((eta_seconds % 3600) // 60)}m"
                except (ValueError, ZeroDivisionError):
                    pass

        # Surface the backend's step description alongside the ETA
        label_parts = []
        if message and message.lower().strip() not in GENERIC_STATUS_TOKENS:
            label_parts.append(message)
        if eta_str:
            label_parts.append(f"ETA {eta_str}")
        self.status_label.setText("  –  ".join(label_parts))

        if status in ("done", "cancelled"):
            self.progress_bar.setValue(100 if status == "done" else 0)
            self.progress_bar.setRange(0, 100)
            self._conversion_start_time = None

    def conversion_completed(self, job_id, output_dir):
        if job_id in self.conversion_threads:
            del self.conversion_threads[job_id]
        self.current_thread = None

        self.set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            lang.get_translation("conversion_complete", self.locale)
        )

        self._schedule_progress_reset(2000)
        self._prune_missing_sources()

        QMessageBox.information(
            self,
            lang.get_translation("success", self.locale),
            f"{lang.get_translation('conversion_successful', self.locale)}",
        )

        if self.open_target_folder_check.isChecked() and output_dir:
            if os.path.isdir(output_dir):
                self._open_file_location(output_dir)

    def conversion_error(self, error_message):
        self.current_thread = None
        self.set_ui_enabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(lang.get_translation("error", self.locale))

        self._schedule_progress_reset(3000)

        QMessageBox.critical(
            self,
            lang.get_translation("error", self.locale),
            f"{lang.get_translation('conversion_failed', self.locale)}: {error_message}",
        )

    def conversion_cancelled(self, job_id):
        # Cancel is a normal outcome: release the thread and re-enable the UI
        self.conversion_threads.pop(job_id, None)
        if self.current_thread is not None and self.current_thread.job_id == job_id:
            self.current_thread = None
        self.set_ui_enabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 100)
        self._schedule_progress_reset(2000)

    def _schedule_progress_reset(self, delay_ms):
        # Epoch-guarded reset: stale timers from a previous job must never
        # clobber the bar of a conversion started in the meantime.
        epoch = self._progress_epoch
        QTimer.singleShot(delay_ms, lambda: self._reset_progress(epoch))

    def _reset_progress(self, epoch):
        if epoch != self._progress_epoch:
            return
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("")

    def set_ui_enabled(self, enabled):
        for widget in [
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
            self.format_combo,
            self.merge_check,
            self.concat_check,
            self.recursive_check,
            self.delete_check,
            self.open_target_folder_check,
            self.framerate_spin,
            self.quality_combo,
            self.workers_spin,
            self.resolution_combo,
            self.split_edit,
            self.metadata_combo,
            self.convert_btn,
        ]:
            widget.setEnabled(enabled)

        self.cancel_btn.setEnabled(not enabled)

        if not enabled:
            self.convert_btn.setText(lang.get_translation("converting", self.locale))
        else:
            self.convert_btn.setText(lang.get_translation("convert", self.locale))
            # Restore mode-dependent availability
            self._update_mode_dependent_ui()

    def closeEvent(self, event):
        converting = self.current_thread is not None and self.current_thread.isRunning()
        if converting:
            reply = QMessageBox.question(
                self,
                self.windowTitle(),
                self._tr("exit_while_converting"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.current_thread.cancel()
        for thread in list(self.conversion_threads.values()):
            if thread.isRunning():
                thread.cancel()
                thread.wait(10000)
        save_settings({"last_dir": self.last_dir, "locale": self.locale})
        event.accept()

    def open_settings_dialog(self):
        dlg = SettingsDialog(self, self.locale, list(lang.TRANSLATIONS.keys()))
        if dlg.exec():
            self.locale = dlg.selected_locale
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            # Preserve the current selection across the UI rebuild; the set
            # must be cleared too, otherwise re-adding would be deduped away
            current_files = [
                self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.file_list.count())
            ]
            self._file_paths_set.clear()
            self.init_ui()
            self.add_files_batch(current_files)

    def open_help_dialog(self):
        HelpDialog(self, self.locale).exec()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    icon_path = APP_ROOT / "img" / "app_icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    # The update check performs network I/O; running it asynchronously keeps
    # startup instant regardless of connectivity.
    window = MainWindow()
    window.show()

    update_bridge = UpdateCheckBridge()

    def prompt_update(latest):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Update Available")
        msg.setText(f"Version {latest} is available on GitHub.")
        msg.setInformativeText(
            f"You are running version {VERSION}. Would you like to visit the releases page?"
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        if msg.exec() == QMessageBox.StandardButton.Ok:
            import webbrowser

            webbrowser.open("https://github.com/MK2112/any_to_any.py/releases")

    update_bridge.update_available.connect(prompt_update)
    start_update_check(update_bridge)

    sys.exit(app.exec())


class SettingsDialog(QDialog):
    def __init__(self, parent, locale, supported_locales):
        super().__init__(parent)
        self.setWindowTitle(tr_key("settings", locale))
        self.selected_locale = locale
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr_key("language", locale)))
        self.locale_combo = QComboBox()
        for loc in supported_locales:
            self.locale_combo.addItem(loc)
            if loc == locale:
                self.locale_combo.setCurrentText(loc)
        layout.addWidget(self.locale_combo)
        btn = QPushButton("Ok")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        self.locale_combo.currentTextChanged.connect(self.set_locale)

    def set_locale(self, value):
        self.selected_locale = value


class HelpDialog(QDialog):
    def __init__(self, parent, locale):
        super().__init__(parent)
        self.setWindowTitle(tr_key("help", locale))
        self.setMinimumSize(450, 380)
        layout = QVBoxLayout(self)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText(f"""
any_to_any.py {VERSION}

https://github.com/MK2112/any_to_any.py

Features:
- Drag-and-drop files or folders into the list
- Select output format and destination directory
- Pick a target resolution (movies/codecs/protocols only)
- 'Keep original' + resolution resizes without changing formats
- Split PDFs by page ranges, e.g. '1-3,8-end'
- Set framerate (0 = auto), quality, and worker threads
- Preserve or strip metadata (ID3 tags, EXIF, document properties)
- Check merge/concatenate/recursive/delete options
- Click Convert to start, Cancel to stop

Options:
- Framerate: Set target framerate (0 = keep original)
- Quality: High/Medium/Low for audio bitrate
- Workers: Parallel conversion threads (up to CPU count - 1)
- Recursive: Include files from subfolders
- Delete: Remove original files after conversion
- Split Pages: Appears when PDF is the target; splits PDF inputs by page ranges
- Resolution: Appears for movie targets; choices adapt to the selected format
- Metadata: Default keeps output as-is, Preserve archives tags as JSON,
  Strip removes metadata for privacy

Keyboard shortcuts:
- Ctrl+O: Add Files
- Ctrl+Shift+A: Add Folder
- Delete: Remove Selected
- Ctrl+Return: Convert
- Escape: Cancel

For more info, see the project README on GitHub:
https://github.com/MK2112/any_to_any.py/blob/main/README.md
""")
        layout.addWidget(help_text)
        btn = QPushButton("OK")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    # Merge instead of clobbering so independently stored keys survive
    merged = load_settings()
    merged.update(data)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f)
    except Exception:
        pass


if __name__ == "__main__":
    main()
