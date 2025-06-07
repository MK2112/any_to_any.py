import os
import sys
from pathlib import Path
from PyQt6.QtGui import QIcon, QFont
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
    QProgressBar,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.controller import Controller
import utils.language_support as lang


class ConversionThread(QThread):
    progress_updated = pyqtSignal(int, str)
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
            # Update progress
            self.progress_updated.emit(10, "Starting conversion...")

            # Create a new controller instance for this conversion
            controller = Controller(
                job_id=self.job_id, shared_progress_dict=self.shared_progress
            )

            # Prepare output path
            if len(self.input_files) == 1:
                base_name = Path(self.input_files[0]).stem
                output_path = str(
                    Path(self.output_dir) / f"{base_name}.{self.output_format}"
                )
            else:
                output_path = str(
                    Path(self.output_dir) / f"converted.{self.output_format}"
                )

            # Run the conversion
            controller.convert_files(
                input_path_args=self.input_files,
                format=self.output_format,
                output=output_path,
                merge=self.merge,
                concat=self.concat,
            )

            # Emit completion signal
            self.conversion_finished.emit(self.job_id, output_path)

        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = Controller()
        self.locale = self.controller.locale
        self.init_ui()
        self.setWindowTitle("any_to_any.py")
        self.setMinimumSize(800, 600)
        self.conversion_threads = {}

    def init_ui(self):
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
        input_layout.addWidget(self.file_list)

        # Add/Remove files buttons
        button_layout = QHBoxLayout()

        self.add_files_btn = QPushButton(lang.get_translation("add_files", self.locale))
        self.add_files_btn.clicked.connect(self.add_files)

        self.add_folder_btn = QPushButton(
            lang.get_translation("add_folder", self.locale)
        )
        self.add_folder_btn.clicked.connect(self.add_folder)

        self.remove_btn = QPushButton(lang.get_translation("remove", self.locale))
        self.remove_btn.clicked.connect(self.remove_selected)

        button_layout.addWidget(self.add_files_btn)
        button_layout.addWidget(self.add_folder_btn)
        button_layout.addWidget(self.remove_btn)

        input_layout.addLayout(button_layout)
        layout.addLayout(input_layout)

        # Output format
        format_layout = QHBoxLayout()
        format_label = QLabel(lang.get_translation("output_format", self.locale))
        self.format_combo = QComboBox()

        # Add supported formats to combo box
        for category in self.controller.supported_formats:
            self.format_combo.addItem(category.upper(), category)

        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()

        # Output directory
        output_dir_layout = QHBoxLayout()
        output_dir_label = QLabel(lang.get_translation("output_directory", self.locale))
        self.output_dir_edit = QLabel(str(Path.home() / "Downloads"))
        self.output_dir_edit.setStyleSheet("border: 1px solid #ccc; padding: 5px;")
        self.output_dir_edit.setMinimumHeight(30)

        browse_btn = QPushButton(lang.get_translation("browse", self.locale))
        browse_btn.clicked.connect(self.browse_output_dir)

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
            str(Path.home()),
            "All Files (*.*)",
        )

        if files:
            for file in files:
                if file not in [
                    self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.file_list.count())
                ]:
                    item = QListWidgetItem(Path(file).name)
                    item.setData(Qt.ItemDataRole.UserRole, file)
                    self.file_list.addItem(item)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, lang.get_translation("select_folder", self.locale), str(Path.home())
        )

        if folder:
            # Add all files from the directory
            for root, _, files in os.walk(folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file_path not in [
                        self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                        for i in range(self.file_list.count())
                    ]:
                        item = QListWidgetItem(file_path.replace(folder + os.sep, ""))
                        item.setData(Qt.ItemDataRole.UserRole, file_path)
                        self.file_list.addItem(item)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            lang.get_translation("select_output_directory", self.locale),
            str(Path.home()),
        )

        if directory:
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

        # Get output format and directory
        output_format = self.format_combo.currentData()
        output_dir = self.output_dir_edit.text()

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Get options
        merge = self.merge_check.isChecked()
        concat = self.concat_check.isChecked()

        # Disable UI during conversion
        self.set_ui_enabled(False)
        self.status_label.setText(
            lang.get_translation("preparing_conversion", self.locale)
        )

        # Create and start conversion thread
        thread = ConversionThread(
            controller=self.controller,
            input_files=input_files,
            output_format=output_format,
            output_dir=output_dir,
            merge=merge,
            concat=concat,
        )

        # Connect signals
        thread.progress_updated.connect(self.update_progress)
        thread.conversion_finished.connect(self.conversion_completed)
        thread.error_occurred.connect(self.conversion_error)

        # Store thread reference
        self.conversion_threads[thread.job_id] = thread

        # Start thread
        thread.start()

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

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
        self.status_label.setText(lang.get_translation("error_occurred", self.locale))

        QMessageBox.critical(
            self,
            lang.get_translation("error", self.locale),
            f"{lang.get_translation('conversion_failed', self.locale)}: {error_message}",
        )

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
        event.accept()


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


if __name__ == "__main__":
    main()
