import os
import sys
import copy
import json
import time
import threading
from pathlib import Path
from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.controller import Controller
import utils.language_support as lang


class ConversionThread(QThread):
    progress_updated = pyqtSignal(dict)
    conversion_finished = pyqtSignal(str, str)  # job_id, output_path
    error_occurred = pyqtSignal(str)

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
        self.job_id = str(id(self))
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
                job_id=self.job_id, shared_progress_dict=self.shared_progress
            )

            if len(self.input_files) == 1:
                base_name = Path(self.input_files[0]).stem
                output_path = str(
                    Path(self.output_dir) / f"{base_name}.{self.output_format}"
                )
            else:
                output_path = str(
                    Path(self.output_dir) / f"converted.{self.output_format}"
                )

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
                        split=None,
                        merge=self.merge,
                        concat=self.concat,
                        delete=self.delete,
                        across=False,
                        recursive=self.recursive,
                        dropzone=False,
                        language=None,
                        workers=self.workers,
                    )
                except Exception as e:
                    error_holder["error"] = str(e)
                finally:
                    conversion_done.set()

            t = threading.Thread(target=conversion_job)
            t.start()

            last_snapshot = None
            # Poll progress every 100ms for smoother updates
            while not conversion_done.is_set() and not self._cancelled:
                prog = copy.deepcopy(self.shared_progress.get(self.job_id, {}))
                progress = prog.get("progress", None)
                total = prog.get("total", 100)
                percent = None
                if progress is not None and total:
                    try:
                        percent = int(100 * float(progress) / float(total))
                    except Exception:
                        percent = None
                message = prog.get("message", prog.get("status", ""))
                status = prog.get("status", "running")
                error = prog.get("error", None)
                snapshot = {
                    "progress": percent,
                    "message": message,
                    "status": status,
                    "error": error,
                }
                if snapshot != last_snapshot:
                    self.progress_updated.emit(snapshot)
                    last_snapshot = snapshot
                time.sleep(0.1)  # Reduced from 0.25s for smoother UI

            if self._cancelled:
                self.progress_updated.emit(
                    {
                        "progress": 0,
                        "message": "Conversion cancelled",
                        "status": "cancelled",
                        "error": None,
                    }
                )
                return

            # Wait for thread to complete
            t.join(timeout=5.0)

            # Final progress update
            prog = copy.deepcopy(self.shared_progress.get(self.job_id, {}))
            percent = 100
            message = prog.get("message", prog.get("status", "Done"))
            status = prog.get("status", "done")
            error = prog.get("error", None)
            self.progress_updated.emit(
                {
                    "progress": percent,
                    "message": message,
                    "status": status,
                    "error": error,
                }
            )

            if "error" in error_holder:
                self.error_occurred.emit(error_holder["error"])
            else:
                self.conversion_finished.emit(self.job_id, output_path)

        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = Controller(locale=lang.get_system_language())
        self.locale = self.controller.locale
        self._file_paths_set = set()  # Performance: O(1) duplicate checking
        self.conversion_threads = {}
        self.current_thread = None
        self.init_ui()
        self.setWindowTitle("any_to_any.py")
        self.setMinimumSize(850, 650)

    def get_supported_formats(self):
        formats = {}
        for category, mapping in self.controller._supported_formats.items():
            cat_name = str(category).split(".")[-1].replace("_", " ").title()
            formats[cat_name] = sorted(list(mapping.keys()))
        return formats

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.add_file_to_list(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        self.add_file_to_list(os.path.join(root, file))
        event.acceptProposedAction()

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

    def _update_file_count(self):
        count = self.file_list.count()
        self.file_count_label.setText(f"{count} file(s)")

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
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(True)
        self.file_list.viewport().setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.dragEnterEvent = self.dragEnterEvent
        self.file_list.dropEvent = self.dropEvent
        self.file_list.setMinimumHeight(150)
        input_layout.addWidget(self.file_list)

        # File count and buttons
        file_button_layout = QHBoxLayout()
        self.file_count_label = QLabel("0 file(s)")
        file_button_layout.addWidget(self.file_count_label)
        file_button_layout.addStretch()

        self.add_files_btn = QPushButton(lang.get_translation("add_files", self.locale))
        self.add_files_btn.clicked.connect(self.add_files)

        self.add_folder_btn = QPushButton(
            lang.get_translation("add_folder", self.locale)
        )
        self.add_folder_btn.clicked.connect(self.add_folder)

        self.remove_btn = QPushButton(lang.get_translation("remove", self.locale))
        self.remove_btn.clicked.connect(self.remove_selected)

        self.clear_btn = QPushButton(
            lang.get_translation("clear_all", self.locale)
            if hasattr(lang, "get_translation")
            else "Clear All"
        )
        self.clear_btn.clicked.connect(self.clear_all_files)

        file_button_layout.addWidget(self.add_files_btn)
        file_button_layout.addWidget(self.add_folder_btn)
        file_button_layout.addWidget(self.remove_btn)
        file_button_layout.addWidget(self.clear_btn)
        input_layout.addLayout(file_button_layout)
        layout.addWidget(input_group)

        # Conversion settings group
        settings_group = QGroupBox(lang.get_translation("settings", self.locale))
        settings_layout = QGridLayout(settings_group)

        # Row 0: Format and output directory
        format_label = QLabel(lang.get_translation("convert", self.locale) + ":")
        self.format_combo = QComboBox()
        self.supported_formats = self.get_supported_formats()
        for cat, fmts in self.supported_formats.items():
            self.format_combo.addItem(f"--- {cat} ---")
            idx = self.format_combo.count() - 1
            self.format_combo.model().item(idx).setEnabled(False)
            for fmt in fmts:
                self.format_combo.addItem(f"{fmt}", fmt)
                self.format_combo.setItemData(
                    self.format_combo.count() - 1, f"{cat}", Qt.ItemDataRole.ToolTipRole
                )
        settings_layout.addWidget(format_label, 0, 0)
        settings_layout.addWidget(self.format_combo, 0, 1)

        output_dir_label = QLabel(lang.get_translation("output_dir", self.locale) + ":")
        self.output_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.output_dir_edit.setMinimumWidth(200)
        browse_btn = QPushButton(lang.get_translation("browse", self.locale))
        browse_btn.clicked.connect(self.browse_output_dir)
        settings_layout.addWidget(output_dir_label, 0, 2)
        settings_layout.addWidget(self.output_dir_edit, 0, 3)
        settings_layout.addWidget(browse_btn, 0, 4)

        # Row 1: Framerate and Quality
        framerate_label = QLabel(
            lang.get_translation("framerate", self.locale)
            if "framerate" in lang.get_all_translations(self.locale)
            else "Framerate:"
        )
        self.framerate_spin = QSpinBox()
        self.framerate_spin.setRange(0, 120)
        self.framerate_spin.setValue(0)
        self.framerate_spin.setSpecialValueText("Auto")
        self.framerate_spin.setToolTip("Set framerate (0 = auto)")
        settings_layout.addWidget(framerate_label, 1, 0)
        settings_layout.addWidget(self.framerate_spin, 1, 1)

        quality_label = QLabel(
            lang.get_translation("quality", self.locale)
            if "quality" in lang.get_all_translations(self.locale)
            else "Quality:"
        )
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Default", "High", "Medium", "Low"])
        settings_layout.addWidget(quality_label, 1, 2)
        settings_layout.addWidget(self.quality_combo, 1, 3)

        # Row 2: Workers
        workers_label = QLabel("Workers:")
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 8)
        self.workers_spin.setValue(1)
        self.workers_spin.setToolTip("Number of parallel conversion threads")
        settings_layout.addWidget(workers_label, 2, 0)
        settings_layout.addWidget(self.workers_spin, 2, 1)

        layout.addWidget(settings_group)

        # Options checkboxes
        options_layout = QHBoxLayout()
        self.merge_check = QCheckBox(lang.get_translation("merge", self.locale))
        self.concat_check = QCheckBox(lang.get_translation("concatenate", self.locale))
        self.recursive_check = QCheckBox(
            lang.get_translation("recursive", self.locale)
            if "recursive" in lang.get_all_translations(self.locale)
            else "Recursive"
        )
        self.delete_check = QCheckBox(
            lang.get_translation("delete", self.locale)
            if "delete" in lang.get_all_translations(self.locale)
            else "Delete originals"
        )

        options_layout.addWidget(self.merge_check)
        options_layout.addWidget(self.concat_check)
        options_layout.addWidget(self.recursive_check)
        options_layout.addWidget(self.delete_check)
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

        self.cancel_btn = QPushButton(
            lang.get_translation("cancel", self.locale)
            if "cancel" in lang.get_all_translations(self.locale)
            else "Cancel"
        )
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        self.convert_btn = QPushButton(lang.get_translation("convert", self.locale))
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.convert_btn)
        layout.addLayout(action_layout)

        # Set layout margins and spacing
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

    def clear_all_files(self):
        self.file_list.clear()
        self._file_paths_set.clear()
        self._update_file_count()

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
            for file in files:
                self.add_file_to_list(file)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, lang.get_translation("select_folder", self.locale), self.last_dir
        )
        if folder:
            self.last_dir = folder
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            for root, _, files in os.walk(folder):
                for file in files:
                    self.add_file_to_list(os.path.join(root, file))

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            file_path = item.data(Qt.ItemDataRole.UserRole)
            self._file_paths_set.discard(file_path)
            self.file_list.takeItem(self.file_list.row(item))
        self._update_file_count()

    def browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            lang.get_translation("select_output_dir", self.locale),
            self.last_dir,
        )
        if directory:
            self.last_dir = directory
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            self.output_dir_edit.setText(directory)

    def start_conversion(self):
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
                lang.get_translation("invalid_output_dir", self.locale),
            )
            return

        output_format = self.format_combo.currentData()
        if not output_format:
            QMessageBox.warning(
                self,
                lang.get_translation("error", self.locale),
                lang.get_translation("no_format_selected", self.locale),
            )
            return

        # Get options
        merge = self.merge_check.isChecked()
        concat = self.concat_check.isChecked()
        framerate = (
            self.framerate_spin.value() if self.framerate_spin.value() > 0 else None
        )
        quality_map = {
            "Default": None,
            "High": "high",
            "Medium": "medium",
            "Low": "low",
        }
        quality = quality_map.get(self.quality_combo.currentText())
        recursive = self.recursive_check.isChecked()
        delete = self.delete_check.isChecked()
        workers = self.workers_spin.value()

        # Disable UI during conversion
        self.set_ui_enabled(False)
        self.status_label.setText(
            lang.get_translation("starting_conversion", self.locale)
        )
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("")

        # Start conversion thread
        self.current_thread = ConversionThread(
            input_files,
            output_format,
            output_dir,
            merge=merge,
            concat=concat,
            framerate=framerate,
            quality=quality,
            recursive=recursive,
            delete=delete,
            workers=workers,
        )
        self.current_thread.progress_updated.connect(self.update_progress)
        self.current_thread.conversion_finished.connect(self.conversion_completed)
        self.current_thread.error_occurred.connect(self.conversion_error)
        self.conversion_threads[self.current_thread.job_id] = self.current_thread
        self.current_thread.start()

    def cancel_conversion(self):
        if self.current_thread and self.current_thread.isRunning():
            self.current_thread.cancel()
            self.status_label.setText("Cancelling...")

    def update_progress(self, progress_info):
        value = progress_info.get("progress")
        message = progress_info.get("message", "")
        status = progress_info.get("status", "")
        error = progress_info.get("error")

        if value is None or status in ("starting", "preparing", "waiting"):
            self.progress_bar.setRange(0, 0)  # Indeterminate
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))

        # Color cues
        if status == "done":
            self.progress_bar.setStyleSheet(
                "QProgressBar {background: #e0ffe0;} QProgressBar::chunk {background: #4CAF50;}"
            )
        elif status == "cancelled":
            self.progress_bar.setStyleSheet(
                "QProgressBar {background: #fff3e0;} QProgressBar::chunk {background: #ff9800;}"
            )
        elif error or status == "error":
            self.progress_bar.setStyleSheet(
                "QProgressBar {background: #ffe0e0;} QProgressBar::chunk {background: #e53935;}"
            )

        if error:
            self.status_label.setText(f"Error: {error}")
        else:
            self.status_label.setText(str(message))

        if status in ("done", "cancelled") or error:
            self.progress_bar.setValue(100 if status == "done" else 0)
            self.progress_bar.setRange(0, 100)

    def conversion_completed(self, job_id, output_path):
        if job_id in self.conversion_threads:
            del self.conversion_threads[job_id]
        self.current_thread = None

        self.set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            lang.get_translation("conversion_complete", self.locale)
        )

        QMessageBox.information(
            self,
            lang.get_translation("success", self.locale),
            f"{lang.get_translation('conversion_successful', self.locale)}: {output_path}",
        )

    def conversion_error(self, error_message):
        self.current_thread = None
        self.set_ui_enabled(True)
        self.status_label.setText(lang.get_translation("error", self.locale))
        QMessageBox.critical(
            self,
            lang.get_translation("error", self.locale),
            f"{lang.get_translation('conversion_failed', self.locale)}: {error_message}",
        )

    def set_ui_enabled(self, enabled):
        self.add_files_btn.setEnabled(enabled)
        self.add_folder_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.merge_check.setEnabled(enabled)
        self.concat_check.setEnabled(enabled)
        self.recursive_check.setEnabled(enabled)
        self.delete_check.setEnabled(enabled)
        self.framerate_spin.setEnabled(enabled)
        self.quality_combo.setEnabled(enabled)
        self.workers_spin.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(not enabled)

        if not enabled:
            self.convert_btn.setText(lang.get_translation("converting", self.locale))
        else:
            self.convert_btn.setText(lang.get_translation("convert", self.locale))

    def closeEvent(self, event):
        for thread in list(self.conversion_threads.values()):
            if thread.isRunning():
                thread.cancel()
                thread.wait(2000)
        save_settings({"last_dir": self.last_dir, "locale": self.locale})
        event.accept()

    def open_settings_dialog(self):
        supported_locales = list(lang.TRANSLATIONS.keys())
        dlg = SettingsDialog(self, self.locale, supported_locales)
        if dlg.exec():
            self.locale = dlg.selected_locale
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            # Recreate UI with new locale
            self._file_paths_set.clear()
            for i in range(self.file_list.count()):
                self._file_paths_set.add(
                    self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                )
            self.init_ui()

    def open_help_dialog(self):
        dlg = HelpDialog(self, self.locale)
        dlg.exec()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


# --- Settings and Dialogs ---

SETTINGS_FILE = str(Path.home() / ".any_to_any_gui_settings.json")


class SettingsDialog(QDialog):
    def __init__(self, parent, locale, supported_locales):
        super().__init__(parent)
        self.setWindowTitle(lang.get_translation("settings", locale))
        self.selected_locale = locale
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(lang.get_translation("language", locale)))
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
        self.setWindowTitle(lang.get_translation("help", locale))
        self.setMinimumSize(450, 300)
        layout = QVBoxLayout(self)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText("""
any_to_any.py GUI

Features:
> Drag-and-drop files or folders into the list
> Select output format and destination directory
> Set framerate (0 = auto), quality, and worker threads
> Check merge/concatenate/recursive/delete options
> Click Convert to start, Cancel to stop

Options:
> Framerate: Set target framerate (0 = keep original)
> Quality: High/Medium/Low for audio bitrate
> Workers: Parallel conversion threads (1-8)
> Recursive: Include files from subfolders
> Delete: Remove original files after conversion

For more info, see the project README.
""")
        layout.addWidget(help_text)
        btn = QPushButton("Ok")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


if __name__ == "__main__":
    main()
