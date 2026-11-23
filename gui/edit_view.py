from __future__ import annotations

import os
import json

from pathlib import Path
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtCore import (
    QByteArray,
    QMimeData,
    Qt,
    QElapsedTimer,
    QTimer,
    QThread,
    QUrl,
    pyqtSignal,
)

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

    _HAS_MULTIMEDIA = True
except Exception:
    QAudioOutput = QMediaPlayer = None
    _HAS_MULTIMEDIA = False

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.edit_export import EditExportThread
from utils.language_support import tr_key
from gui.styles import STYLE_CANCEL_BTN, STYLE_CONVERT_BTN
from utils.category import Category
from gui.timeline import (
    CLIP_COLORS,
    MediaFile,
    MediaPoolWidget,
    TimelineClip,
    TimelineWidget,
    media_kind,
    probe_duration,
)

CLIP_MIME = "application/x-any2any-timeline-clips"


class MediaProbeWorker(QThread):
    media_ready = pyqtSignal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: list[str] = []
        self._stop = False

    def enqueue(self, paths) -> None:
        self._queue.extend(path for path in paths if path)
        if not self.isRunning() and not self._stop:
            self.start(QThread.Priority.LowestPriority)

    def stop(self) -> None:
        self._stop = True
        if self.isRunning():
            self.wait(10000)

    def run(self) -> None:
        while not self._stop and self._queue:
            path = self._queue.pop(0)
            duration = probe_duration(path)
            self.media_ready.emit(path, float(duration or 0.0))


class EditView(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.locale = getattr(main_window, "locale", "English")
        self.export_thread: EditExportThread | None = None
        self._probe = MediaProbeWorker(self)
        self._probe.media_ready.connect(self._on_media_ready)
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._on_play_tick)
        self._clock = QElapsedTimer()
        self._markers: list[float] = []
        self._updating_props = False
        self._voices: dict[str, tuple] = {}  # clip_id -> (QMediaPlayer, QAudioOutput)
        self._scheduled: set[str] = set()
        self._playing = False
        self._play_start = 0.0
        self._auto_switching = False
        self._mode_locked_by_user = False
        self._restoring = False
        self._build_ui()
        self._setup_shortcuts()
        self._on_mode_changed()  # marker controls only belong to Split mode
        self._mode_locked_by_user = False  # initial setup is not a user choice
        self._update_actions()
        self._update_clip_properties()

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def _tr(self, key: str) -> str:
        return tr_key(key, self.locale)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        self.add_media_btn = QPushButton(self._tr("edit_add_media"))
        self.add_media_btn.setToolTip(self._tr("edit_add_media") + "  (Ctrl+O)")
        self.add_media_btn.clicked.connect(self.add_files)
        self.add_folder_btn = QPushButton(self._tr("add_folder"))
        self.add_folder_btn.clicked.connect(self.add_folder)
        self.cut_btn = QPushButton(self._tr("edit_cut"))
        self.cut_btn.setToolTip(
            self._tr("edit_cut") + "  (S)\n" + self._tr("edit_cut_none")
        )
        self.cut_btn.clicked.connect(self.cut_at_playhead)
        self.delete_btn = QPushButton(self._tr("edit_delete"))
        self.delete_btn.setToolTip(self._tr("edit_delete") + "  (Del)")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.clear_btn = QPushButton(self._tr("edit_clear"))
        self.clear_btn.clicked.connect(self.clear_timeline)
        for widget in (
            self.add_media_btn,
            self.add_folder_btn,
            self.cut_btn,
            self.delete_btn,
            self.clear_btn,
        ):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.snap_check = QCheckBox(self._tr("edit_snap"))
        self.snap_check.setChecked(True)
        self.snap_check.setToolTip("Snap clip edges to other clips and the playhead")
        self.snap_check.toggled.connect(
            lambda checked: self.timeline.set_snapping(checked)
        )
        self.waveform_check = QCheckBox(self._tr("edit_waveforms"))
        self.waveform_check.setChecked(True)
        self.waveform_check.toggled.connect(
            lambda checked: self.timeline.set_waveforms(checked)
        )
        toolbar.addWidget(self.snap_check)
        toolbar.addWidget(self.waveform_check)
        toolbar.addStretch()
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.setToolTip(self._tr("edit_zoom_out") + "  (Ctrl+wheel)")
        self.zoom_out_btn.clicked.connect(lambda: self.timeline.zoom_out())
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.setToolTip(self._tr("edit_zoom_in") + "  (Ctrl+wheel)")
        self.zoom_in_btn.clicked.connect(lambda: self.timeline.zoom_in())
        self.zoom_fit_btn = QPushButton(self._tr("edit_zoom_fit"))
        self.zoom_fit_btn.clicked.connect(lambda: self.timeline.zoom_fit())
        toolbar.addWidget(self.zoom_out_btn)
        toolbar.addWidget(self.zoom_in_btn)
        toolbar.addWidget(self.zoom_fit_btn)
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        pool_panel = QWidget()
        pool_layout = QVBoxLayout(pool_panel)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        pool_layout.addWidget(QLabel(self._tr("edit_media_pool")))
        self.media_pool = MediaPoolWidget()
        self.media_pool.media_dropped.connect(self.add_paths)
        self.media_pool.media_activated.connect(self.place_pool_media)
        self.media_pool.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.media_pool.customContextMenuRequested.connect(self._show_pool_menu)
        pool_layout.addWidget(self.media_pool)
        pool_layout.addWidget(QLabel(self._tr("edit_pool_hint")))
        splitter.addWidget(pool_panel)

        timeline_panel = QWidget()
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel(self._tr("edit_timeline")))
        header.addStretch()
        self.add_track_btn = QPushButton(self._tr("edit_add_track"))
        self.add_track_btn.clicked.connect(self._add_track)
        header.addWidget(self.add_track_btn)
        timeline_layout.addLayout(header)
        self.timeline = TimelineWidget(self, self.locale)
        self.timeline.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.timeline.customContextMenuRequested.connect(self._show_timeline_menu)
        self.timeline.files_dropped.connect(self._on_files_dropped)
        self.timeline.clip_activated.connect(self._on_clip_activated)
        self.timeline.selection_changed.connect(self._on_selection_changed)
        self.timeline.clips_changed.connect(self._on_clips_changed)
        self.timeline.playhead_changed.connect(self._update_time_labels)
        timeline_layout.addWidget(self.timeline, 1)
        splitter.addWidget(timeline_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((250, 750))
        root.addWidget(splitter, 1)

        transport = QHBoxLayout()
        self.play_btn = QPushButton(self._tr("edit_play"))
        self.play_btn.setCheckable(True)
        self.play_btn.setToolTip(self._tr("edit_play") + "  (Space)")
        self.play_btn.clicked.connect(self.toggle_play)
        self.stop_btn = QPushButton(self._tr("edit_stop"))
        self.stop_btn.clicked.connect(self.stop_play)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(110)
        transport.addWidget(self.play_btn)
        transport.addWidget(self.stop_btn)
        transport.addWidget(self.time_label)
        transport.addStretch()

        self.marker_panel = QWidget()
        marker_layout = QHBoxLayout(self.marker_panel)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        marker_layout.addWidget(QLabel(self._tr("edit_markers") + ":"))
        self.marker_list = QListWidget()
        self.marker_list.setMaximumHeight(52)
        self.marker_list.setFixedWidth(150)
        self.marker_list.setToolTip("Double-click a marker to jump to it")
        self.marker_list.itemDoubleClicked.connect(
            lambda item: self.timeline.set_playhead(
                float(item.data(Qt.ItemDataRole.UserRole))
            )
        )
        self.add_marker_btn = QPushButton("+")
        self.add_marker_btn.setFixedWidth(28)
        self.add_marker_btn.setToolTip(self._tr("edit_add_markers") + "  (M)")
        self.add_marker_btn.clicked.connect(self.add_marker)
        self.remove_marker_btn = QPushButton("-")
        self.remove_marker_btn.setFixedWidth(28)
        self.remove_marker_btn.setToolTip(self._tr("edit_remove_marker"))
        self.remove_marker_btn.clicked.connect(self.remove_marker)
        marker_layout.addWidget(self.marker_list)
        marker_layout.addWidget(self.add_marker_btn)
        marker_layout.addWidget(self.remove_marker_btn)
        transport.addWidget(self.marker_panel)
        root.addLayout(transport)

        self.props_group = QGroupBox(self._tr("edit_clip_properties"))
        props = self.props_group
        props_layout = QHBoxLayout(props)
        props_layout.setContentsMargins(10, 12, 10, 4)
        self.clip_name_label = QLabel(self._tr("edit_nothing_selected"))
        self.clip_name_label.setMinimumWidth(170)
        props_layout.addWidget(self.clip_name_label)
        self.pos_spin = self._make_spin()
        self.in_spin = self._make_spin()
        self.out_spin = self._make_spin()
        for label, spin in (
            (self._tr("edit_position"), self.pos_spin),
            (self._tr("edit_in"), self.in_spin),
            (self._tr("edit_out"), self.out_spin),
        ):
            props_layout.addWidget(QLabel(label + ":"))
            props_layout.addWidget(spin)
        self.length_label = QLabel("")
        self.length_label.setMinimumWidth(90)
        props_layout.addWidget(QLabel(self._tr("edit_duration") + ":"))
        props_layout.addWidget(self.length_label)
        props_layout.addStretch()
        for spin in (self.pos_spin, self.in_spin, self.out_spin):
            spin.valueChanged.connect(self._on_clip_prop_changed)
        root.addWidget(props)

        export_group = QGroupBox(self._tr("edit_export_options"))
        export = QVBoxLayout(export_group)
        export.setContentsMargins(12, 8, 12, 8)
        export.setSpacing(6)

        def _label(text, width=76):
            label = QLabel(f"{text}:")
            label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if width:
                label.setMinimumWidth(width)
            return label

        self.mode_combo = QComboBox()
        for key, value in (
            ("edit_mode_stitch", "stitch"),
            ("edit_mode_timeline", "timeline"),
            ("edit_mode_trim", "trim"),
            ("edit_mode_split", "split"),
            ("edit_mode_merge", "merge"),
        ):
            self.mode_combo.addItem(self._tr(key), value)
        self.mode_combo.setToolTip(self._tr("edit_mode_tip"))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.output_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.browse_btn = QPushButton(self._tr("browse"))
        self.browse_btn.clicked.connect(self.browse_output)
        self.open_dir_btn = QPushButton(self.main._create_folder_icon(), "")
        self.open_dir_btn.setFixedWidth(32)
        self.open_dir_btn.setToolTip(self._tr("open_containing_folder"))
        self.open_dir_btn.clicked.connect(self.open_output)

        self.format_combo = QComboBox()
        self.format_combo.setEditable(True)
        self.format_combo.setPlaceholderText("mp4  or  mp4,webm")
        self.format_combo.addItem(self._tr("resolution_original"), "original")
        for cat, formats in self.main.supported_formats.items():
            self.format_combo.addItem(f"--- {cat} ---")
            index = self.format_combo.count() - 1
            self.format_combo.model().item(index).setEnabled(False)
            for fmt in formats:
                self.format_combo.addItem(fmt, fmt)
        self.format_combo.setCurrentIndex(0)
        self.format_combo.setToolTip(self._tr("edit_format_hint"))
        self.format_combo.currentTextChanged.connect(self._on_format_changed)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem(self._tr("resolution_original"), "")
        for res in self.main.controller._STD_RES:
            self.resolution_combo.addItem(res, res)

        self.framerate_spin = QSpinBox()
        self.framerate_spin.setRange(0, 120)
        self.framerate_spin.setSpecialValueText("Auto")
        self.quality_combo = QComboBox()
        for key, value in (
            ("quality_default", None),
            ("quality_high", "high"),
            ("quality_medium", "medium"),
            ("quality_low", "low"),
        ):
            self.quality_combo.addItem(self._tr(key), value)
        self.workers_spin = QSpinBox()
        cpu = os.cpu_count() or 2
        self.workers_spin.setRange(1, max(1, min(cpu - 1, 32)))
        self.burn_subs_check = QCheckBox(self._tr("edit_burn_subs"))

        self.metadata_combo = QComboBox()
        for key, value in (
            ("metadata_mode_none", "none"),
            ("metadata_mode_preserve", "preserve"),
            ("metadata_mode_strip", "strip"),
        ):
            self.metadata_combo.addItem(self._tr(key), value)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("artist:John genre:live")
        self.tags_edit.setToolTip(self._tr("edit_tags"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(5, 2)
        row = 0
        grid.addWidget(_label(self._tr("edit_mode")), row, 0)
        grid.addWidget(self.mode_combo, row, 1, 1, 5)
        row += 1
        grid.addWidget(_label(self._tr("output_dir")), row, 0)
        grid.addWidget(self.output_edit, row, 1, 1, 3)
        grid.addWidget(self.browse_btn, row, 4)
        grid.addWidget(self.open_dir_btn, row, 5)
        row += 1
        grid.addWidget(_label(self._tr("edit_format")), row, 0)
        grid.addWidget(self.format_combo, row, 1, 1, 2)
        grid.addWidget(_label(self._tr("resolution_label"), 60), row, 3)
        grid.addWidget(self.resolution_combo, row, 4, 1, 2)
        row += 1
        grid.addWidget(_label(self._tr("framerate"), 60), row, 0)
        grid.addWidget(self.framerate_spin, row, 1)
        grid.addWidget(_label(self._tr("quality"), 50), row, 2)
        grid.addWidget(self.quality_combo, row, 3)
        grid.addWidget(_label(self._tr("workers"), 50), row, 4)
        grid.addWidget(self.workers_spin, row, 5)
        row += 1
        grid.addWidget(_label(self._tr("metadata_label")), row, 0)
        grid.addWidget(self.metadata_combo, row, 1, 1, 2)
        grid.addWidget(_label(self._tr("edit_tags_label"), 50), row, 3)
        grid.addWidget(self.tags_edit, row, 4, 1, 2)
        row += 1
        grid.addWidget(QLabel(""), row, 0)
        grid.addWidget(self.burn_subs_check, row, 1, 1, 5)
        export.addLayout(grid)

        action_row = QHBoxLayout()
        self.export_btn = QPushButton(self._tr("edit_render"))
        self.export_btn.setStyleSheet(STYLE_CONVERT_BTN)
        self.export_btn.clicked.connect(self.start_export)
        self.cancel_btn = QPushButton(self._tr("cancel"))
        self.cancel_btn.setStyleSheet(STYLE_CANCEL_BTN)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_export)
        action_row.addStretch()
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.export_btn)
        export.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        export.addWidget(self.progress_bar)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        export.addWidget(self.status_label)
        self._progress_epoch = 0
        self._set_progress_visible(False)
        root.addWidget(export_group)

        self.feedback_label = QLabel(self._tr("edit_hint"))
        self.feedback_label.setWordWrap(True)
        root.addWidget(self.feedback_label)

    @staticmethod
    def _make_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 36000.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.25)
        spin.setSuffix(" s")
        spin.setFixedWidth(92)
        return spin

    def _setup_shortcuts(self) -> None:
        for sequence, slot in (
            ("Space", self.toggle_play),
            ("S", self.cut_at_playhead),
            ("M", self.add_marker),
            ("Ctrl+C", self.copy_clips),
            ("Ctrl+V", self.paste_clips),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    def _shortcut_allowed(self) -> bool:
        focus = QApplication.focusWidget()
        return not isinstance(focus, (QLineEdit, QComboBox))

    def _clipboard_allowed(self) -> bool:
        focus = QApplication.focusWidget()
        return not isinstance(focus, (QLineEdit, QComboBox, QAbstractSpinBox))

    def copy_clips(self) -> None:
        if not self._clipboard_allowed():
            return
        clips = self.timeline.selected_clips()
        if not clips:
            self.show_message(self._tr("edit_nothing_to_copy"))
            return
        payload = [
            {
                "path": clip.media.path,
                "duration": clip.media.duration,
                "kind": clip.media.kind,
                "name": clip.media.name,
                "start": clip.start,
                "track": clip.track,
                "in": clip.in_point,
                "out": clip.out_point,
            }
            for clip in clips
        ]
        mime = QMimeData()
        mime.setData(
            CLIP_MIME,
            QByteArray(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        )
        mime.setText(", ".join(clip.media.name for clip in clips))
        QApplication.clipboard().setMimeData(mime)
        self.show_message(self._tr("edit_copied").replace("[count]", str(len(clips))))

    def paste_clips(self) -> None:
        if not self._clipboard_allowed():
            return
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasFormat(CLIP_MIME):
            self.show_message(self._tr("edit_clipboard_empty"))
            return
        try:
            payload = json.loads(bytes(mime.data(CLIP_MIME)).decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            self.show_message(self._tr("edit_clipboard_empty"))
            return
        if not isinstance(payload, list) or not payload:
            return
        pool = {media.path: media for media in self.media_pool.media()}
        min_start = min(float(entry.get("start") or 0.0) for entry in payload)
        paste_at = self.timeline.playhead
        new_ids = []
        for entry in payload:
            path = entry.get("path")
            if not path or not os.path.isfile(path):
                continue
            media = pool.get(path)
            if media is None:
                media = MediaFile(
                    path=path,
                    duration=entry.get("duration"),
                    kind=entry.get("kind") or "",
                    name=entry.get("name") or "",
                )
                self.media_pool.add_media(media)
                pool[path] = media
                self._probe.enqueue([path])
            start = paste_at + (float(entry.get("start") or 0.0) - min_start)
            clip = self.timeline.add_media(
                media,
                start=start,
                track=int(entry.get("track") or 0),
                in_point=float(entry.get("in") or 0.0),
                out_point=entry.get("out"),
            )
            new_ids.append(clip.clip_id)
        if not new_ids:
            return
        self.timeline.selected_ids = set(new_ids)
        self.timeline.selection_changed.emit()
        pasted = [c for c in self.timeline.clips if c.clip_id in new_ids]
        self.timeline.set_playhead(max(clip.end for clip in pasted))
        self.show_message(self._tr("edit_pasted").replace("[count]", str(len(pasted))))

    def show_message(self, text: str) -> None:
        self.feedback_label.setText(text)

    def _set_progress_visible(self, visible: bool) -> None:
        self.progress_bar.setVisible(visible)
        self.status_label.setVisible(visible)

    def _schedule_progress_hide(self, delay_ms: int) -> None:
        epoch = self._progress_epoch
        QTimer.singleShot(delay_ms, lambda: self._hide_progress(epoch))

    def _hide_progress(self, epoch: int) -> None:
        if epoch == self._progress_epoch:
            self._set_progress_visible(False)

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._tr("select_files"),
            getattr(self.main, "last_dir", str(Path.home())),
            "All Files (*.*)",
        )
        if files:
            self.main.last_dir = str(Path(files[0]).parent)
            self.main._persist_settings()
            self.add_paths(files)

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            self._tr("select_folder"),
            getattr(self.main, "last_dir", str(Path.home())),
        )
        if not folder:
            return
        self.main.last_dir = folder
        self.main._persist_settings()
        paths = []
        for root, _, names in os.walk(folder):
            for name in names:
                paths.append(os.path.join(root, name))
        self.add_paths(paths)

    def add_paths(self, paths) -> None:
        supported = getattr(self.main, "supported_extensions", set())
        known = {media.path for media in self.media_pool.media()}
        added = []
        for path in paths:
            if not path or not os.path.isfile(path):
                continue
            if supported and Path(path).suffix.lstrip(".").lower() not in supported:
                continue
            if path in known:
                continue
            known.add(path)
            media = MediaFile(path=path, kind=media_kind(path))
            self.media_pool.add_media(media)
            added.append(path)
        if added:
            self._probe.enqueue(added)
            self.show_message(
                self._tr("edit_added_pool").replace("[count]", str(len(added)))
            )
            self._update_actions()

    def _on_media_ready(self, path: str, duration: float) -> None:
        for media in self.media_pool.media():
            if media.path == path:
                media.duration = duration or None
                self.media_pool.refresh_media(media)
                self.timeline.refresh_waveforms(media)
                break
        self._update_clip_properties()

    def _on_files_dropped(self, paths, start: float, track: int) -> None:
        self.add_paths(paths)
        existing = {media.path: media for media in self.media_pool.media()}
        for media in existing.values():
            if media.path in paths and not media.duration:
                media.duration = probe_duration(media.path) or None
                self.media_pool.refresh_media(media)
        placed = 0
        for path in paths:
            media = existing.get(path)
            if media is None or not os.path.isfile(path):
                continue
            self.timeline.add_media(media, start=start, track=track)
            start += (media.duration or 5.0) + 0.1
            placed += 1
        if placed:
            self.show_message(self._tr("edit_dropped").replace("[count]", str(placed)))
        self._update_actions()

    def place_pool_media(self, only_media=None) -> None:
        media = (
            [only_media] if only_media is not None else self.media_pool.selected_media()
        )
        media = [item for item in media if item is not None]
        if not media:
            return
        start = (
            self.timeline.playhead
            if self.timeline.playhead > 0
            else self.timeline.total_duration()
        )
        for item in media:
            self.timeline.add_media(item, start=start, track=None)
            start += (item.duration or 5.0) + 0.1
        self.show_message(self._tr("edit_dropped").replace("[count]", str(len(media))))
        self._update_actions()

    def remove_pool_media(self) -> None:
        media = self.media_pool.selected_media()
        if not media:
            return
        paths = {item.path for item in media}
        used = [c for c in self.timeline.clips if c.media.path in paths]
        if (
            used
            and QMessageBox.question(
                self,
                self._tr("edit_remove_pool"),
                self._tr("edit_pool_remove_confirm").replace("[count]", str(len(used))),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.timeline.clips = [
            c for c in self.timeline.clips if c.media.path not in paths
        ]
        self.timeline.selected_ids.clear()
        for item in self.media_pool.selectedItems():
            self.media_pool.takeItem(self.media_pool.row(item))
        self.show_message(
            self._tr("edit_pool_removed").replace(
                "[name]", ", ".join(m.name for m in media)
            )
        )
        self.timeline.clips_changed.emit()
        self.timeline.selection_changed.emit()
        self.timeline.update()

    def _show_pool_menu(self, pos) -> None:
        if not self.media_pool.selectedItems():
            return
        menu = QMenu(self)
        menu.addAction(self._tr("edit_place_here"), self.place_pool_media)
        menu.addAction(self._tr("edit_remove_pool"), self.remove_pool_media)
        menu.exec(self.media_pool.mapToGlobal(pos))

    def _show_timeline_menu(self, pos) -> None:
        clip = self.timeline._clip_at(pos.x(), pos.y())
        if clip is not None and clip.clip_id not in self.timeline.selected_ids:
            self.timeline.selected_ids = {clip.clip_id}
            self.timeline.selection_changed.emit()
            self.timeline.update()
        menu = QMenu(self)
        menu.addAction(self._tr("edit_copy"), self.copy_clips)
        paste_action = menu.addAction(self._tr("edit_paste"), self.paste_clips)
        mime = QApplication.clipboard().mimeData()
        paste_action.setEnabled(mime is not None and mime.hasFormat(CLIP_MIME))
        menu.addSeparator()
        menu.addAction(self._tr("edit_cut"), self.cut_at_playhead)
        if clip is not None:
            menu.addAction(self._tr("edit_delete"), self.delete_selected)
        if self.mode_combo.currentData() == "split":
            menu.addAction(self._tr("edit_add_markers"), self.add_marker)
        menu.exec(self.timeline.mapToGlobal(pos))

    def browse_output(self) -> None:
        start = self.output_edit.text().strip()
        if not start or not os.path.isdir(start):
            start = getattr(self.main, "last_dir", str(Path.home()))
        directory = QFileDialog.getExistingDirectory(
            self, self._tr("select_output_dir"), start
        )
        if directory:
            self.output_edit.setText(directory)
            self.main.last_dir = directory
            self.main._persist_settings()

    def open_output(self) -> None:
        directory = self.output_edit.text().strip()
        if directory and os.path.isdir(directory):
            self.main._open_file_location(directory)
        else:
            QMessageBox.warning(
                self,
                self._tr("error"),
                self._tr("no_dir_exist").replace("[dir]", directory or "-"),
            )

    def _add_track(self) -> None:
        index = self.timeline.add_track()
        self.show_message(f"{self._tr('edit_track')} {index + 1}")

    def cut_at_playhead(self) -> None:
        if not self._shortcut_allowed():
            return
        playhead = self.timeline.playhead
        targets = [
            c for c in self.timeline.selected_clips() if c.start < playhead < c.end
        ]
        if not targets:
            targets = self.timeline.clips_at_playhead()
        if not targets:
            self.show_message(self._tr("edit_cut_none"))
            return
        self.timeline.selected_ids = {c.clip_id for c in targets}
        count = self.timeline.split_selected_at_playhead()
        if count:
            self.show_message(
                self._tr("edit_cut_done")
                .replace("[count]", str(count))
                .replace("[time]", _fmt(playhead))
            )
        else:
            self.show_message(self._tr("edit_cut_none"))
        self._update_actions()

    def delete_selected(self) -> None:
        count = self.timeline.remove_selected()
        if count:
            self.show_message(f"{self._tr('edit_delete')}: {count}")
            self._update_clip_properties()

    def clear_timeline(self) -> None:
        self.timeline.clear()
        self._markers.clear()
        self._refresh_markers()
        self.show_message(self._tr("edit_clear"))
        self._update_clip_properties()

    def _is_playing(self) -> bool:
        return self._playing

    def toggle_play(self) -> None:
        if not self._shortcut_allowed():
            return
        if self._playing:
            self.stop_play()
        else:
            self._start_playback()

    def _start_playback(self) -> None:
        total = self.timeline.total_duration()
        if not total:
            return
        start = self.timeline.playhead
        if start >= total - 0.01:
            self.timeline.set_playhead(0.0)
            start = 0.0
        self._play_start = start
        self._scheduled.clear()
        self._playing = True
        self._clock.start()
        self._play_timer.start()
        self.play_btn.setChecked(True)
        self.play_btn.setText(self._tr("edit_pause"))
        self.show_message(self._tr("edit_play"))
        self._tick_scheduler()

    def _start_voice(self, clip, now: float):
        # Create and start one media player for a clip at timeline time
        if not _HAS_MULTIMEDIA:
            return None
        try:
            output = QAudioOutput(self)
            output.setVolume(0.85 if len(self.timeline.clips) > 1 else 1.0)
            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.setSource(QUrl.fromLocalFile(clip.media.path))
            offset_ms = int(max(0.0, clip.in_point + (now - clip.start)) * 1000)
            player.setPosition(offset_ms)

            def on_status(status):
                if status == QMediaPlayer.MediaStatus.LoadedMedia:
                    player.setPosition(offset_ms)
                    try:
                        player.mediaStatusChanged.disconnect(on_status)
                    except Exception:
                        pass

            player.mediaStatusChanged.connect(on_status)
            player.play()
            self._voices[clip.clip_id] = (player, output)
            return player
        except Exception:
            return None

    def _stop_voice(self, clip_id: str) -> None:
        voice = self._voices.pop(clip_id, None)
        if voice is None:
            return
        player, output = voice
        try:
            player.stop()
        except Exception:
            pass

    def _tick_scheduler(self) -> None:
        if not self._playing:
            return
        now = self._play_start + self._clock.elapsed() / 1000.0
        total = self.timeline.total_duration()
        if total and now >= total:
            self.stop_play()
            return
        for clip in list(self.timeline.clips):
            clip_id = clip.clip_id
            if clip.start <= now < clip.end:
                if clip_id not in self._scheduled:
                    self._scheduled.add(clip_id)
                    self._start_voice(clip, now)
            elif clip_id in self._voices:
                self._stop_voice(clip_id)
        self.timeline.set_playhead(now)

    def stop_play(self) -> None:
        self._playing = False
        self._play_timer.stop()
        for clip_id in list(self._voices):
            self._stop_voice(clip_id)
        self._scheduled.clear()
        self.play_btn.setChecked(False)
        self.play_btn.setText(self._tr("edit_play"))
        self.timeline.set_playhead(self._play_start)

    def _on_play_tick(self) -> None:
        self._tick_scheduler()

    def add_marker(self) -> None:
        if not self._shortcut_allowed():
            return
        value = round(self.timeline.playhead, 3)
        if value > 0 and value not in self._markers:
            self._markers.append(value)
            self._markers.sort()
            self._refresh_markers()

    def remove_marker(self) -> None:
        if not self._markers:
            return
        closest = min(self._markers, key=lambda m: abs(m - self.timeline.playhead))
        self._markers.remove(closest)
        self._refresh_markers()

    def _refresh_markers(self) -> None:
        self.marker_list.clear()
        for value in self._markers:
            minutes, seconds = divmod(value, 60)
            item = QListWidgetItem(f"{int(minutes)}:{seconds:06.3f}")
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.marker_list.addItem(item)
        self.timeline.set_markers(
            self._markers if self.mode_combo.currentData() == "split" else []
        )

    def _update_time_labels(self, value: float) -> None:
        total = self.timeline.total_duration()
        self.time_label.setText(f"{_fmt(value)} / {_fmt(total)}")

    def _on_clip_activated(self, clip) -> None:
        self.timeline.selected_ids = {clip.clip_id}
        self.timeline.selection_changed.emit()
        self._update_clip_properties()
        self.props_group.setTitle(
            f"{self._tr('edit_clip_properties')}  -  {clip.media.name}"
        )
        self.props_group.setStyleSheet("QGroupBox { border: 2px solid #4CAF50; }")
        QTimer.singleShot(900, self._clear_props_highlight)
        if self.pos_spin.isEnabled():
            self.pos_spin.setFocus()
            self.pos_spin.selectAll()
        self.show_message(
            f"{clip.media.name}: {self._tr('edit_position')} / "
            f"{self._tr('edit_in')} / {self._tr('edit_out')}"
        )

    def _clear_props_highlight(self) -> None:
        self.props_group.setStyleSheet("")

    def _on_selection_changed(self) -> None:
        self._update_actions()
        self._update_clip_properties()

    def _on_clips_changed(self) -> None:
        self._update_actions()
        self._update_clip_properties()
        self._maybe_auto_mode()

    @staticmethod
    def _has_overlap(clips) -> bool:
        ordered = sorted(clips, key=lambda clip: clip.start)
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                if first.start < second.end - 0.01 and second.start < first.end - 0.01:
                    return True
        return False

    def _maybe_auto_mode(self) -> None:
        if self._restoring or self.is_busy():
            return
        if not self._has_overlap(self.timeline.clips):
            self._mode_locked_by_user = False
            return
        if self.mode_combo.currentData() == "timeline" or self._mode_locked_by_user:
            return
        index = self.mode_combo.findData("timeline")
        if index < 0:
            return
        self._auto_switching = True
        try:
            self.mode_combo.setCurrentIndex(index)
        finally:
            self._auto_switching = False
        self.show_message(self._tr("edit_overlap_mode_hint"))

    def _update_clip_properties(self) -> None:
        if self._updating_props:
            return
        selected = self.timeline.selected_clips()
        clip = selected[0] if len(selected) == 1 else None
        self._updating_props = True
        try:
            for spin in (self.pos_spin, self.in_spin, self.out_spin):
                spin.blockSignals(True)
            if clip is None:
                self.props_group.setTitle(self._tr("edit_clip_properties"))
                self.clip_name_label.setText(
                    self._tr("edit_nothing_selected")
                    if not selected
                    else f"{len(selected)} clips selected"
                )
                self.pos_spin.setValue(0)
                self.in_spin.setValue(0)
                self.out_spin.setValue(0)
                self.length_label.setText("")
                for spin in (self.pos_spin, self.in_spin, self.out_spin):
                    spin.setEnabled(False)
            else:
                source = clip.source_duration or 36000.0
                for spin in (self.in_spin, self.out_spin):
                    spin.setMaximum(max(0.01, source))
                self.clip_name_label.setText(clip.media.name)
                self.pos_spin.setValue(round(clip.start, 2))
                self.in_spin.setValue(round(clip.in_point, 2))
                self.out_spin.setValue(round(clip.out, 2))
                for spin in (self.pos_spin, self.in_spin, self.out_spin):
                    spin.setEnabled(not self.is_busy())
                self.length_label.setText(_fmt(clip.length))
        finally:
            for spin in (self.pos_spin, self.in_spin, self.out_spin):
                spin.blockSignals(False)
            self._updating_props = False

    def _on_clip_prop_changed(self) -> None:
        if self._updating_props:
            return
        selected = self.timeline.selected_clips()
        if len(selected) != 1:
            return
        clip = selected[0]
        source = clip.source_duration
        clip.start = max(0.0, self.pos_spin.value())
        clip.in_point = max(0.0, self.in_spin.value())
        out = self.out_spin.value()
        if source > 0:
            out = min(out, source)
        clip.out_point = out if out > clip.in_point + 0.01 else clip.in_point + 0.01
        self.length_label.setText(_fmt(clip.length))
        self.timeline.update()
        self.timeline.clips_changed.emit()

    def _update_actions(self, *_) -> None:
        has_clips = bool(self.timeline.clips)
        self.cut_btn.setEnabled(has_clips and not self.is_busy())
        self.delete_btn.setEnabled(
            bool(self.timeline.selected_ids) and not self.is_busy()
        )
        self.clear_btn.setEnabled(has_clips and not self.is_busy())
        self.play_btn.setEnabled(has_clips and not self.is_busy())
        self.stop_btn.setEnabled(has_clips and not self.is_busy())
        self.add_track_btn.setEnabled(not self.is_busy())
        self.export_btn.setEnabled(has_clips and not self.is_busy())
        self._update_time_labels(self.timeline.playhead)

    def _on_mode_changed(self) -> None:
        if not self._auto_switching and not self._restoring:
            # Explicit user choice: keep it, even while overlaps exist.
            self._mode_locked_by_user = True
        split_mode = self.mode_combo.currentData() == "split"
        self.marker_panel.setVisible(split_mode)
        self.timeline.set_markers(self._markers if split_mode else [])

    def _on_format_changed(self) -> None:
        text = self.format_combo.currentText().strip()
        data = self.format_combo.currentData()
        chosen = data if data else (text.split(",")[0].strip() if text else "")
        if chosen in (None, "", "original") or chosen.startswith("---"):
            allowed = self.main.controller._STD_RES
        else:
            allowed = self.main._resolution_ladder_for_target(chosen)
        current = self.resolution_combo.currentData()
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.clear()
        self.resolution_combo.addItem(self._tr("resolution_original"), "")
        for res in allowed:
            self.resolution_combo.addItem(res, res)
        index = self.resolution_combo.findData(current)
        self.resolution_combo.setCurrentIndex(max(0, index))
        self.resolution_combo.blockSignals(False)

    def is_busy(self) -> bool:
        return self.export_thread is not None and self.export_thread.isRunning()

    def set_export_enabled(self, enabled: bool) -> None:
        if not enabled or not self.is_busy():
            self.export_btn.setEnabled(enabled and bool(self.timeline.clips))
            for widget in (
                self.add_media_btn,
                self.add_folder_btn,
                self.cut_btn,
                self.delete_btn,
                self.clear_btn,
                self.add_track_btn,
                self.play_btn,
                self.stop_btn,
                self.media_pool,
                self.snap_check,
                self.waveform_check,
                self.zoom_in_btn,
                self.zoom_out_btn,
                self.zoom_fit_btn,
                self.add_marker_btn,
                self.remove_marker_btn,
            ):
                widget.setEnabled(enabled)
            self.timeline.setEnabled(enabled)
            self._update_actions()
            self._update_clip_properties()

    def set_enabled(self, enabled: bool) -> None:
        self.set_export_enabled(enabled)

    def start_export(self) -> None:
        if self.is_busy() or getattr(self.main, "current_thread", None) is not None:
            QMessageBox.warning(
                self, self._tr("error"), self._tr("edit_render_started")
            )
            return
        clips = self.timeline.ordered_clips()
        if not clips:
            QMessageBox.warning(self, self._tr("error"), self._tr("edit_no_clips"))
            return
        output_dir = self.output_edit.text().strip()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(self, self._tr("error"), self._tr("edit_no_output_dir"))
            return

        mode = self.mode_combo.currentData()
        formats = self._parse_formats()
        if formats is False:
            QMessageBox.warning(self, self._tr("error"), self._tr("edit_no_format"))
            return

        job = {
            "mode": mode,
            "clips": [
                {
                    "path": clip.media.path,
                    "start": clip.start,
                    "in": clip.in_point,
                    "out": clip.out_point,
                    "duration": clip.media.duration or 0.0,
                    "name": clip.media.name,
                    "track": clip.track,
                }
                for clip in clips
            ],
            "format": formats,
            "output_dir": output_dir,
            "framerate": self.framerate_spin.value() or None,
            "quality": self.quality_combo.currentData(),
            "resolution": self.resolution_combo.currentData() or None,
            "burn_subs": self.burn_subs_check.isChecked(),
            "preserve_meta": self.metadata_combo.currentData() == "preserve",
            "strip_meta": self.metadata_combo.currentData() == "strip",
            "add_tag": [tag for tag in self.tags_edit.text().split() if tag],
            "workers": self.workers_spin.value(),
        }

        if mode == "timeline":
            has_video = any(media_kind(c["path"]) == "movie" for c in job["clips"])
            movie_formats = self.main.controller._supported_formats.get(
                Category.MOVIE, {}
            )
            audio_formats = self.main.controller._supported_formats.get(
                Category.AUDIO, {}
            )
            candidates = formats or []
            if has_video:
                ext = next((f for f in candidates if f in movie_formats), "mp4")
            else:
                ext = next((f for f in candidates if f in audio_formats), "mp3")
            job["output_ext"] = ext
            job["has_video"] = has_video
            job["video_codec"] = (
                movie_formats[ext][0] if has_video and ext in movie_formats else None
            )
            job["audio_codec"] = (
                audio_formats[ext] if not has_video and ext in audio_formats else None
            )
        elif mode == "split":
            if not self._markers:
                QMessageBox.warning(
                    self, self._tr("error"), self._tr("edit_add_markers")
                )
                return
            job["source_path"] = job["clips"][0]["path"]
            job["split_points"] = list(self._markers)
        elif mode == "merge":
            paths = [clip["path"] for clip in job["clips"]]
            movies = [p for p in paths if media_kind(p) == "movie"]
            audios = [p for p in paths if media_kind(p) == "audio"]
            if not movies or not audios:
                QMessageBox.warning(self, self._tr("error"), self._tr("merge_advice"))
                return
            job["inputs"] = [movies[0], audios[0]]
        elif job["resolution"] and not any(
            media_kind(c["path"]) == "movie" for c in job["clips"]
        ):
            job["resolution"] = None

        self.export_thread = EditExportThread(job)
        self.export_thread.progress_updated.connect(self._on_export_progress)
        self.export_thread.edit_finished.connect(self._on_export_finished)
        self.export_thread.error_occurred.connect(self._on_export_error)
        self.export_thread.edit_cancelled.connect(self._on_export_cancelled)
        self.export_thread.start()
        self.set_export_enabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("")
        self._progress_epoch += 1
        self._set_progress_visible(True)
        self.status_label.setText(self._tr("edit_render_started"))
        self.show_message(self._tr("edit_render_started"))
        self.main.set_edit_export_busy(True)

    def _parse_formats(self):
        text = self.format_combo.currentText().strip()
        if not text or text == self._tr("resolution_original"):
            return None
        tokens = [token.strip().lower() for token in text.split(",") if token.strip()]
        if not tokens or any(token.startswith("---") for token in tokens):
            return False
        supported = getattr(self.main, "supported_extensions", set())
        if supported and any(token not in supported for token in tokens):
            return False
        return tokens

    def cancel_export(self) -> None:
        if self.is_busy():
            self.export_thread.cancel()
            self.status_label.setText(self._tr("cancelling"))

    def _release_export_ui(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.main.set_edit_export_busy(False)
        self.set_export_enabled(True)
        self._update_clip_properties()

    def _on_export_progress(self, info: dict) -> None:
        value = info.get("progress")
        status = info.get("status", "")
        if value is None or status in ("starting", "preparing", "waiting"):
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(value))
        message = info.get("message", "")
        if info.get("error"):
            self.status_label.setText(f"Error: {info['error']}")
        elif message:
            self.status_label.setText(message)

    def _on_export_finished(self, job_id, output_dir, produced: bool) -> None:
        self.export_thread = None
        self.progress_bar.setValue(100)
        message = (
            self._tr("edit_render_done")
            if produced
            else self._tr("edit_render_no_output")
        )
        self.status_label.setText(message)
        self.show_message(message)
        self._release_export_ui()
        self._schedule_progress_hide(2000)
        if produced:
            QMessageBox.information(self, self._tr("success"), message)
        else:
            QMessageBox.warning(self, self._tr("edit_render_no_output"), message)
        if self.main.open_target_folder_check.isChecked() and os.path.isdir(output_dir):
            self.main._open_file_location(output_dir)

    def _on_export_error(self, message: str) -> None:
        self.export_thread = None
        self.progress_bar.setValue(0)
        self.status_label.setText(self._tr("edit_render_failed"))
        self.show_message(f"{self._tr('edit_render_failed')}: {message}")
        self._release_export_ui()
        self._schedule_progress_hide(3000)
        QMessageBox.critical(
            self, self._tr("error"), f"{self._tr('edit_render_failed')}: {message}"
        )

    def _on_export_cancelled(self, job_id) -> None:
        self.export_thread = None
        self.progress_bar.setValue(0)
        self.status_label.setText(self._tr("edit_render_cancelled"))
        self.show_message(self._tr("edit_render_cancelled"))
        self._release_export_ui()
        self._schedule_progress_hide(1500)

    def snapshot(self) -> dict:
        return {
            "pool": [
                {"path": media.path, "duration": media.duration, "kind": media.kind}
                for media in self.media_pool.media()
            ],
            "clips": [
                {
                    "path": clip.media.path,
                    "track": clip.track,
                    "start": clip.start,
                    "in": clip.in_point,
                    "out": clip.out_point,
                    "color": clip.color,
                }
                for clip in self.timeline.clips
            ],
            "tracks": len(self.timeline.track_names),
            "markers": list(self._markers),
            "mode": self.mode_combo.currentData(),
            "output": self.output_edit.text(),
            "format": self.format_combo.currentText(),
            # Store the *meaning*, not the translated display text: rebuilding
            # the UI for a new locale retranslates the items, so a saved
            # "Original behalten" would otherwise linger in the edit field.
            "format_original": (
                self.format_combo.currentData() == "original"
                and "," not in self.format_combo.currentText()
                and self.format_combo.currentText().strip()
                not in getattr(self.main, "supported_extensions", set())
            ),
            "resolution": self.resolution_combo.currentData(),
        }

    def restore(self, state: dict) -> None:
        if not state:
            return
        media_by_path = {}
        for entry in state.get("pool", []):
            media = MediaFile(
                path=entry["path"],
                duration=entry.get("duration"),
                kind=entry.get("kind", ""),
            )
            media_by_path[media.path] = media
            self.media_pool.add_media(media)
        clips = []
        for entry in state.get("clips", []):
            media = media_by_path.get(entry["path"])
            if media is None:
                continue
            clips.append(
                TimelineClip(
                    media=media,
                    track=entry.get("track", 0),
                    start=entry.get("start", 0.0),
                    in_point=entry.get("in", 0.0),
                    out_point=entry.get("out"),
                    color=entry.get("color") or CLIP_COLORS[0],
                )
            )
        self._restoring = True
        try:
            self.timeline.set_clips(clips, state.get("tracks", 1))
            self._markers = list(state.get("markers", []))
            self._refresh_markers()
            if state.get("mode") in [
                self.mode_combo.itemData(i) for i in range(self.mode_combo.count())
            ]:
                self.mode_combo.setCurrentIndex(self.mode_combo.findData(state["mode"]))
        finally:
            self._restoring = False
        # A restored non-timeline mode is an explicit choice: keep it.
        self._mode_locked_by_user = self.mode_combo.currentData() != "timeline"
        if state.get("output"):
            self.output_edit.setText(state["output"])
        if state.get("format_original"):
            self.format_combo.setCurrentIndex(0)  # shows this locale's wording
        elif state.get("format"):
            self.format_combo.setEditText(state["format"])
        if state.get("resolution"):
            index = self.resolution_combo.findData(state["resolution"])
            if index >= 0:
                self.resolution_combo.setCurrentIndex(index)
        self._update_actions()
        self._update_clip_properties()

    def shutdown(self) -> None:
        self._play_timer.stop()
        for clip_id in list(self._voices):
            self._stop_voice(clip_id)
        if self.is_busy():
            self.export_thread.cancel()
            self.export_thread.wait(10000)
        self._probe.stop()
        self.timeline.shutdown()


def _fmt(value: float) -> str:
    total = max(0, int(value or 0))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
