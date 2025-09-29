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
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.controller import Controller
import utils.language_support as lang


class ConversionThread(QThread):
    # Now emits a dict: {'progress': int, 'message': str, 'status': str, 'error': str or None}
    progress_updated = pyqtSignal(dict)
    conversion_finished = pyqtSignal(str, str)  # job_id, output_path
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        controller,
        input_files,
        output_format,
        output_dir,
        merge=False,
        concat=False,
    ):
        super().__init__()
        self.controller = controller
        self.input_files = input_files
        self.output_format = output_format
        self.output_dir = output_dir
        self.merge = merge
        self.concat = concat
        self.job_id = str(id(self))
        self.shared_progress = {}

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
                        framerate=None,
                        quality=None,
                        split=None,
                        merge=self.merge,
                        concat=self.concat,
                        delete=False,
                        across=False,
                        recursive=False,
                        dropzone=False,
                        language=None,
                        workers=1,
                    )
                except Exception as e:
                    error_holder["error"] = str(e)
                finally:
                    conversion_done.set()

            t = threading.Thread(target=conversion_job)
            t.start()

            last_snapshot = None
            # Poll progress every 0.25s until done
            while not conversion_done.is_set():
                prog = copy.deepcopy(self.shared_progress.get(self.job_id, {}))
                # Compose full progress dict
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
                time.sleep(0.25)

            # Final progress update after completion
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
        self.init_ui()
        self.setWindowTitle("any_to_any.py")
        self.setMinimumSize(800, 600)
        self.conversion_threads = {}

    def get_supported_formats(self):
        # Query backend Controller for supported formats
        # Return a dict of {category: [format, ...]}
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
        if file not in [
            self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.file_list.count())
        ]:
            item = QListWidgetItem(Path(file).name)
            item.setData(Qt.ItemDataRole.UserRole, file)
            item.setToolTip(file)  # Show full path on hover
            self.file_list.addItem(item)

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
        input_layout = QVBoxLayout()
        input_label = QLabel(lang.get_translation("select_files", self.locale))
        input_layout.addWidget(input_label)

        # File list
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(True)
        self.file_list.viewport().setAcceptDrops(True)
        self.file_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.file_list.dragEnterEvent = self.dragEnterEvent
        self.file_list.dropEvent = self.dropEvent
        input_layout.addWidget(self.file_list)

        # Add/Remove files buttons
        button_layout = QHBoxLayout()

        self.add_files_btn = QPushButton(lang.get_translation("add_files", self.locale))
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_files_btn.setToolTip(lang.get_translation("add_files", self.locale))

        self.add_folder_btn = QPushButton(
            lang.get_translation("add_folder", self.locale)
        )
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.add_folder_btn.setToolTip(lang.get_translation("add_folder", self.locale))

        self.remove_btn = QPushButton(lang.get_translation("remove", self.locale))
        self.remove_btn.clicked.connect(self.remove_selected)
        self.remove_btn.setToolTip(
            lang.get_translation("remove_selected_files", self.locale)
        )

        self.settings_btn = QPushButton(lang.get_translation("settings", self.locale))
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        self.settings_btn.setToolTip(lang.get_translation("settings", self.locale))
        button_layout.addWidget(self.settings_btn)

        self.help_btn = QPushButton(lang.get_translation("help", self.locale))
        self.help_btn.clicked.connect(self.open_help_dialog)
        self.help_btn.setToolTip(lang.get_translation("help_about", self.locale))
        button_layout.addWidget(self.help_btn)

        button_layout.addWidget(self.add_files_btn)
        button_layout.addWidget(self.add_folder_btn)
        button_layout.addWidget(self.remove_btn)

        input_layout.addLayout(button_layout)
        layout.addLayout(input_layout)

        # Output format
        format_layout = QHBoxLayout()

        # Dynamically populate supported formats, grouped by category
        format_label = QLabel(lang.get_translation("convert", self.locale))
        self.format_combo = QComboBox()
        self.supported_formats = self.get_supported_formats()
        for cat, fmts in self.supported_formats.items():
            self.format_combo.addItem(f"--- {cat} ---")
            idx = self.format_combo.count() - 1
            self.format_combo.model().item(idx).setEnabled(False)
            for fmt in fmts:
                self.format_combo.addItem(f"{fmt}", fmt)
                # Optionally, set tooltip for each format
                self.format_combo.setItemData(
                    self.format_combo.count() - 1, f"{cat}", Qt.ItemDataRole.ToolTipRole
                )
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()

        # Output directory
        output_dir_layout = QHBoxLayout()
        output_dir_label = QLabel(lang.get_translation("output_dir", self.locale))
        self.output_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.output_dir_edit.setStyleSheet("border: 1px solid #ccc; padding: 5px;")
        self.output_dir_edit.setMinimumHeight(30)
        self.output_dir_edit.setToolTip(lang.get_translation("output_dir", self.locale))

        browse_btn = QPushButton(lang.get_translation("browse", self.locale))
        browse_btn.clicked.connect(self.browse_output_dir)
        browse_btn.setToolTip(lang.get_translation("browse_dir", self.locale))

        output_dir_layout.addWidget(output_dir_label)
        output_dir_layout.addWidget(self.output_dir_edit, 1)
        output_dir_layout.addWidget(browse_btn)

        # Options
        options_layout = QHBoxLayout()

        self.merge_check = QCheckBox(lang.get_translation("merge", self.locale))
        self.concat_check = QCheckBox(lang.get_translation("concatenate", self.locale))

        options_layout.addWidget(self.merge_check)
        options_layout.addWidget(self.concat_check)
        options_layout.addStretch()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # Status label
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)

        # Convert button
        self.convert_btn = QPushButton(lang.get_translation("convert", self.locale))
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setToolTip(
            lang.get_translation("start_conversion", self.locale)
        )
        self.convert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        # Add all to main layout
        layout.addLayout(format_layout)
        layout.addLayout(output_dir_layout)
        layout.addLayout(options_layout)
        layout.addWidget(QLabel(lang.get_translation("progress", self.locale) + ":"))
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.convert_btn, 0, Qt.AlignmentFlag.AlignRight)

        # Set layout margins and spacing
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

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
                if os.path.isfile(file) and file not in [
                    self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.file_list.count())
                ]:
                    item = QListWidgetItem(Path(file).name)
                    item.setData(Qt.ItemDataRole.UserRole, file)
                    item.setToolTip(file)  # Full path tooltip
                    self.file_list.addItem(item)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, lang.get_translation("select_folder", self.locale), self.last_dir
        )
        if folder:
            self.last_dir = folder
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            # Add all files from the directory
            for root, _, files in os.walk(folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path) and file_path not in [
                        self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                        for i in range(self.file_list.count())
                    ]:
                        item = QListWidgetItem(file_path.replace(folder + os.sep, ""))
                        item.setData(Qt.ItemDataRole.UserRole, file_path)
                        item.setToolTip(file_path)  # Full path tooltip
                        self.file_list.addItem(item)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

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
        # Get input files
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

        merge = self.merge_check.isChecked()
        concat = self.concat_check.isChecked()

        # Disable UI during conversion
        self.set_ui_enabled(False)
        self.status_label.setText(
            lang.get_translation("starting_conversion", self.locale)
        )
        self.progress_bar.setValue(0)

        # Start conversion in a separate thread
        conversion_thread = ConversionThread(
            self.controller,
            input_files,
            output_format,
            output_dir,
            merge=merge,
            concat=concat,
        )
        conversion_thread.progress_updated.connect(self.update_progress)
        conversion_thread.conversion_finished.connect(self.conversion_completed)
        conversion_thread.error_occurred.connect(self.conversion_error)
        self.conversion_threads[conversion_thread.job_id] = conversion_thread
        conversion_thread.start()

    def update_progress(self, progress_info):
        # progress_info: {'progress': int|None, 'message': str, 'status': str, 'error': str|None}
        value = progress_info.get("progress")
        message = progress_info.get("message", "")
        status = progress_info.get("status", "")
        error = progress_info.get("error")

        # Handle indeterminate state
        if value is None or status in ("starting", "preparing", "waiting"):
            self.progress_bar.setRange(0, 0)  # Indeterminate
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))

        # Color and style cues
        if status == "done":
            self.progress_bar.setStyleSheet(
                "QProgressBar {background: #e0ffe0;} QProgressBar::chunk {background: #4CAF50;}"
            )
        elif error or status == "error":
            self.progress_bar.setStyleSheet(
                "QProgressBar {background: #ffe0e0;} QProgressBar::chunk {background: #e53935;}"
            )
        else:
            self.progress_bar.setStyleSheet("")  # Default

        # Status label
        if error:
            self.status_label.setText(self.tr("Error: ") + str(error))
        else:
            self.status_label.setText(str(message))

        # Optionally, hide progress bar when done or error (UX choice)
        if status == "done" or error:
            self.progress_bar.setValue(100)
            self.progress_bar.setRange(0, 100)

    def conversion_completed(self, job_id, output_path):
        # Remove thread reference
        if job_id in self.conversion_threads:
            del self.conversion_threads[job_id]

        # Update UI
        self.set_ui_enabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            lang.get_translation("conversion_complete", self.locale)
        )

        # Show completion message
        QMessageBox.information(
            self,
            lang.get_translation("success", self.locale),
            f"{lang.get_translation('conversion_successful', self.locale)}: {output_path}",
        )

    def conversion_error(self, error_message):
        self.set_ui_enabled(True)
        self.status_label.setText(lang.get_translation("error", self.locale))
        QMessageBox.critical(
            self,
            lang.get_translation("error", self.locale),
            f"{lang.get_translation('conversion_failed', self.locale)}: {error_message}",
        )

    def show_detailed_error(self, error_message):
        self.set_ui_enabled(True)
        self.status_label.setText(lang.get_translation("error", self.locale))
        dlg = QMessageBox(self)
        dlg.setWindowTitle(lang.get_translation("error", self.locale))
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setText(f"{lang.get_translation('conversion_failed', self.locale)}")
        dlg.setDetailedText(str(error_message))
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.exec()

    def set_ui_enabled(self, enabled):
        self.add_files_btn.setEnabled(enabled)
        self.add_folder_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.merge_check.setEnabled(enabled)
        self.concat_check.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)

        if not enabled:
            self.convert_btn.setText(lang.get_translation("converting", self.locale))
        else:
            self.convert_btn.setText(lang.get_translation("convert", self.locale))

    def closeEvent(self, event):
        # Clean up any running threads
        for thread in list(self.conversion_threads.values()):
            if thread.isRunning():
                thread.terminate()
                thread.wait()
        save_settings({"last_dir": self.last_dir, "locale": self.locale})
        event.accept()

    def open_settings_dialog(self):
        supported_locales = list(lang.TRANSLATIONS.keys())
        dlg = SettingsDialog(self, self.locale, supported_locales)
        if dlg.exec():
            self.locale = dlg.selected_locale
            save_settings({"last_dir": self.last_dir, "locale": self.locale})
            self.init_ui()  # reload UI with new locale

    def open_help_dialog(self):
        dlg = HelpDialog(self, self.locale)
        dlg.exec()


def main():
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Set application font
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


# --- Additional methods for new features ---

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
        self.setMinimumSize(400, 250)
        layout = QVBoxLayout(self)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setPlainText("""
any_to_any.py GUI

- Select files or folders to convert
- Choose output format and directory
- Set merge/concatenate options
- Click Convert
- Drag-and-drop files into the list is supported

For more info, see the project README or try the CLI/web interfaces.
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
