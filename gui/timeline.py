from __future__ import annotations

import sys
import uuid
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from PyQt6.QtCore import (
    Qt,
    QPointF,
    QRectF,
    QThread,
    QUrl,
    QMimeData,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QFont,
    QIcon,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

CLIP_COLORS = (
    "#2E7D6B",
    "#365A8A",
    "#7A5288",
    "#8A6430",
    "#8A4250",
    "#4C6B34",
    "#2F6E7E",
    "#6E5A2E",
    "#6E2F4C",
    "#4C346B",
)

RULER_H = 26
TRACK_H = 64
TRACK_GUTTER = 30  # px reserved for track numbers and flags
MIN_CLIP_LEN = 0.05  # seconds
MIN_PPS = 2.0
MAX_PPS = 500.0
EDGE_GRAB = 7  # px near a clip edge starts a trim instead of a move
SNAP_PX = 7
DEFAULT_IMAGE_DURATION = 5.0


def probe_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        value = float(result.stdout.strip())
        if value > 0:
            return value
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        if str(path).lower().endswith(".wav"):
            import wave

            with wave.open(path, "rb") as source:
                frames = source.getnframes()
                rate = source.getframerate()
                if rate:
                    return frames / rate
    except Exception:
        pass
    if media_kind(path) == "image":
        return DEFAULT_IMAGE_DURATION
    return None


def media_kind(path: str) -> str:
    """Return the media category using the controller's format table."""
    from gui.formats import kind_for

    return kind_for(path)


@dataclass
class MediaFile:
    path: str
    duration: float | None = None
    kind: str = ""
    name: str = ""

    def __post_init__(self):
        self.name = self.name or Path(self.path).name
        if not self.kind:
            self.kind = media_kind(self.path)


@dataclass
class TimelineClip:
    media: MediaFile
    track: int = 0
    start: float = 0.0
    in_point: float = 0.0
    out_point: float | None = None  # None means "to the end of the source"
    color: str = CLIP_COLORS[0]
    clip_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    volume: float = 1.0
    muted: bool = False
    peaks: list | None = None
    peaks_duration: float | None = None  # seconds actually covered by peaks

    @property
    def source_duration(self) -> float:
        return float(self.media.duration or 0.0)

    @property
    def out(self) -> float:
        end = self.source_duration if self.out_point is None else self.out_point
        return max(self.in_point, end)

    @property
    def length(self) -> float:
        return max(0.0, self.out - self.in_point)

    @property
    def end(self) -> float:
        return self.start + self.length

    def is_trimmed(self) -> bool:
        return self.in_point > 0.01 or (
            self.out_point is not None
            and self.source_duration > 0
            and self.out_point < self.source_duration - 0.01
        )

    def visible_peaks(self) -> list:
        if not self.peaks:
            return []
        covered = self.peaks_duration or self.source_duration
        if not covered or len(self.peaks) < 2:
            return self.peaks
        first = max(
            0, min(len(self.peaks) - 1, int(self.in_point / covered * len(self.peaks)))
        )
        last = max(
            first + 1, min(len(self.peaks), int(self.out / covered * len(self.peaks)))
        )
        return self.peaks[first:last]


class WaveformWorker(QThread):
    peaks_ready = pyqtSignal(
        str, object, float
    )  # clip_id, list[float], covered seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: list[TimelineClip] = []
        self._lock = threading.Lock()
        self._stop = False
        self._process = None
        self._cache: dict[tuple[str, float], tuple] = {}

    def request(self, clip: TimelineClip) -> None:
        if not clip.media.duration or clip.media.kind in ("other", "image"):
            return
        key = (clip.media.path, round(clip.media.duration, 3))
        cached = self._cache.get(key)
        if cached is not None:
            clip.peaks, clip.peaks_duration = cached
            return
        with self._lock:
            if any(item.media.path == clip.media.path for item in self._queue):
                return
            self._queue.append(clip)
        if not self.isRunning():
            self.start(QThread.Priority.LowestPriority)

    def stop(self) -> None:
        self._stop = True
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        if self.isRunning():
            self.wait(5000)

    def run(self) -> None:
        while not self._stop:
            with self._lock:
                clip = self._queue.pop(0) if self._queue else None
            if clip is None:
                break
            result = self._compute(clip.media.path, clip.media.duration)
            if result is not None:
                peaks, covered = result
                key = (clip.media.path, round(clip.media.duration, 3))
                self._cache[key] = (peaks, covered)
                if not self._stop:
                    self.peaks_ready.emit(clip.clip_id, peaks, covered)

    def _compute(self, path: str, duration: float | None) -> tuple | None:
        if not duration or duration <= 0:
            return None
        rate = 1000
        limit = min(float(duration), 600.0)
        self._process = None
        try:
            self._process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    path,
                    "-t",
                    f"{limit:.3f}",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(rate),
                    "-f",
                    "f32le",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            raw, _ = self._process.communicate(timeout=30)
            self._process = None
            if not raw:
                return None
            import array

            samples = array.array("f")
            samples.frombytes(raw[: len(raw) // 4 * 4])
            if sys.byteorder == "big":
                samples.byteswap()
            if not samples:
                return None
            buckets = min(480, max(32, len(samples) // 40))
            width = max(1, len(samples) // buckets)
            peaks = []
            for index in range(0, len(samples), width):
                chunk = samples[index : index + width]
                peaks.append(max(abs(sample) for sample in chunk))
            peak = max(peaks) or 1.0
            return [min(1.0, value / peak) for value in peaks], limit
        except Exception:
            return None
        finally:
            self._process = None


class MediaPoolWidget(QListWidget):
    """List of imported media that can be dragged onto the timeline."""

    media_dropped = pyqtSignal(list)
    media_activated = pyqtSignal(MediaFile)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setAcceptDrops(True)
        self.setUniformItemSizes(True)
        self.setToolTip("Drag files onto the timeline to place them.")

    def add_media(self, media: MediaFile) -> None:
        item = QListWidgetItem(f"{media.name}   [{_fmt_time(media.duration)}]")
        item.setData(Qt.ItemDataRole.UserRole, media)
        item.setToolTip(media.path)
        self.addItem(item)

    def refresh_media(self, media: MediaFile) -> None:
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.ItemDataRole.UserRole).path == media.path:
                item.setText(f"{media.name}   [{_fmt_time(media.duration)}]")
                break

    def media(self) -> list[MediaFile]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
        ]

    def selected_media(self) -> list[MediaFile]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        item = self.itemFromIndex(index)
        if item is not None:
            media = item.data(Qt.ItemDataRole.UserRole)
            self.setCurrentItem(item)
            if isinstance(media, MediaFile):
                self.media_activated.emit(media)
        super().mouseDoubleClickEvent(event)

    def startDrag(self, supportedActions):
        paths = [m.path for m in self.selected_media()]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = self.currentItem().icon() if self.currentItem() else QIcon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(24, 24))
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.source() is not self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and event.source() is not self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() and event.source() is not self:
            paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.toLocalFile()
            ]
            event.acceptProposedAction()
            if paths:
                self.media_dropped.emit(paths)
        else:
            event.ignore()


class TimelineWidget(QWidget):
    files_dropped = pyqtSignal(list, float, int)  # paths, start seconds, track
    clip_activated = pyqtSignal(object)  # TimelineClip - double-clicked clip
    selection_changed = pyqtSignal()
    playhead_changed = pyqtSignal(float)
    clips_changed = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, parent=None, locale="English"):
        super().__init__(parent)
        self.locale = locale
        self.clips: list[TimelineClip] = []
        self.track_names: list[str] = ["1"]
        self.track_states: dict[int, dict] = {}
        self.playhead = 0.0
        self.pps = 40.0
        self._scroll_x = 0.0
        self.selected_ids: set[str] = set()
        self.markers: list[float] = []
        self.snapping = True
        self.waveforms = True
        self._drag: dict | None = None
        self._ruler_drag = False
        self._drop_pos: QPointF | None = None
        self._wave_worker = WaveformWorker(self)
        self._wave_worker.peaks_ready.connect(self._on_peaks_ready)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(True)
        self.setMinimumHeight(200)

    def sizeHint(self):
        from PyQt6.QtCore import QSize

        return QSize(760, 260)

    def set_locale(self, locale: str) -> None:
        self.locale = locale

    def track_state(self, index: int) -> dict:
        state = self.track_states.get(index)
        if state is None:
            state = {"muted": False, "solo": False, "locked": False, "volume": 1.0}
            self.track_states[index] = state
        return state

    def add_media(
        self,
        media: MediaFile,
        start: float | None = None,
        track: int | None = None,
        in_point: float = 0.0,
        out_point: float | None = None,
    ) -> TimelineClip:
        duration = media.duration or 0.0
        if out_point is not None:
            length = min(out_point, duration) if duration else out_point
        else:
            length = duration
        if start is None:
            start = self.playhead if self.playhead > 0.01 else self.total_duration()
        if track is None:
            track = self._first_free_track(start, length)
        self._ensure_track(track)
        clip = TimelineClip(
            media=media,
            track=track,
            start=max(0.0, start),
            in_point=max(0.0, in_point),
            out_point=out_point,
            color=CLIP_COLORS[track % len(CLIP_COLORS)],
        )
        self.clips.append(clip)
        if self.waveforms:
            self._wave_worker.request(clip)
        self.selected_ids = {clip.clip_id}
        self.selection_changed.emit()
        self.clips_changed.emit()
        self.update()
        return clip

    def refresh_waveforms(self, media: MediaFile | None = None) -> None:
        if not self.waveforms:
            return
        for clip in self.clips:
            if media is None or clip.media is media:
                self._wave_worker.request(clip)

    def set_clips(self, clips: list[TimelineClip], track_count: int = 1) -> None:
        self.clips = list(clips)
        self.track_names = [
            str(index + 1) for index in range(max(track_count, self._needed_tracks()))
        ]
        for index in range(len(self.track_names)):
            self.track_state(index)
        self.selected_ids.clear()
        if self.waveforms:
            for clip in self.clips:
                self._wave_worker.request(clip)
        self.clips_changed.emit()
        self.update()

    def ordered_clips(self) -> list[TimelineClip]:
        return sorted(self.clips, key=lambda c: (c.start, c.track, c.clip_id))

    def total_duration(self) -> float:
        return max((clip.end for clip in self.clips), default=0.0)

    def selected_clips(self) -> list[TimelineClip]:
        return [c for c in self.clips if c.clip_id in self.selected_ids]

    def remove_selected(self) -> int:
        if not self.selected_ids:
            return 0
        before = len(self.clips)
        self.clips = [c for c in self.clips if c.clip_id not in self.selected_ids]
        self.selected_ids.clear()
        self.selection_changed.emit()
        if len(self.clips) != before:
            self.clips_changed.emit()
        self.update()
        return before - len(self.clips)

    def clear(self) -> None:
        self.clips.clear()
        self.selected_ids.clear()
        self.playhead = 0.0
        self._scroll_x = 0.0
        self.playhead_changed.emit(0.0)
        self.selection_changed.emit()
        self.clips_changed.emit()
        self.update()

    def select_all(self) -> None:
        self.selected_ids = {c.clip_id for c in self.clips}
        self.selection_changed.emit()
        self.update()

    def split_selected_at_playhead(self) -> int:
        cut = self.playhead
        additions: list[TimelineClip] = []
        for clip in list(self.clips):
            if clip.clip_id not in self.selected_ids:
                continue
            if not (clip.start + MIN_CLIP_LEN < cut < clip.end - MIN_CLIP_LEN):
                continue
            offset = cut - clip.start
            new_out = clip.out_point
            clip.out_point = clip.in_point + offset
            right = TimelineClip(
                media=clip.media,
                track=clip.track,
                start=cut,
                in_point=clip.in_point + offset,
                out_point=new_out,
                color=clip.color,
            )
            if self.waveforms:
                self._wave_worker.request(right)
            additions.append(right)
        self.clips.extend(additions)
        if additions:
            self.selected_ids = {c.clip_id for c in additions}
            self.clips_changed.emit()
            self.selection_changed.emit()
            self.update()
        return len(additions)

    def set_playhead(self, seconds: float) -> None:
        value = max(0.0, float(seconds))
        if value != self.playhead:
            self.playhead = value
            self.playhead_changed.emit(value)
            self.update()

    def set_snapping(self, enabled: bool) -> None:
        self.snapping = bool(enabled)

    def set_markers(self, markers) -> None:
        self.markers = sorted(float(value) for value in markers)
        self.update()

    def set_waveforms(self, enabled: bool) -> None:
        self.waveforms = bool(enabled)
        if self.waveforms:
            for clip in self.clips:
                self._wave_worker.request(clip)
        self.update()

    def add_track(self) -> int:
        index = len(self.track_names)
        self.track_names.append(str(index + 1))
        self.track_state(index)
        self.update()
        return index

    def clips_at_playhead(self) -> list[TimelineClip]:
        return [
            clip
            for clip in self.clips
            if clip.start + MIN_CLIP_LEN <= self.playhead <= clip.end - MIN_CLIP_LEN
        ]

    def clip_at_playhead(self) -> TimelineClip | None:
        hits = self.clips_at_playhead()
        if not hits:
            return None
        for clip in hits:
            if clip.clip_id in self.selected_ids:
                return clip
        return max(hits, key=lambda clip: clip.track)

    def zoom_in(self) -> None:
        self._set_pps(self.pps * 1.25)

    def zoom_out(self) -> None:
        self._set_pps(self.pps / 1.25)

    def zoom_fit(self) -> None:
        total = max(self.total_duration(), 5.0)
        self._set_pps(max(MIN_PPS, (self.width() - 24) / total))
        self._scroll_x = 0.0
        self.update()

    def _set_pps(self, value: float) -> None:
        self.pps = max(MIN_PPS, min(MAX_PPS, value))
        self.update()

    def shutdown(self) -> None:
        self._wave_worker.stop()

    def _time_to_x(self, seconds: float) -> float:
        return seconds * self.pps - self._scroll_x

    def _x_to_time(self, x: float) -> float:
        return max(0.0, (x + self._scroll_x) / self.pps)

    def _y_to_track(self, y: float) -> int:
        return max(0, int((y - RULER_H) // TRACK_H))

    def _needed_tracks(self) -> int:
        return max((clip.track for clip in self.clips), default=-1) + 1

    def _ensure_track(self, index: int) -> None:
        while len(self.track_names) <= index:
            self.track_names.append(str(len(self.track_names) + 1))
        self.track_state(index)

    def _first_free_track(self, start: float, length: float) -> int:
        for index in range(max(1, self._needed_tracks() + 1)):
            if self.track_state(index).get("locked"):
                continue
            if not any(
                clip.track == index
                and start < clip.end + 0.01
                and start + length > clip.start - 0.01
                for clip in self.clips
            ):
                return index
        return max(0, self._needed_tracks())

    def _clip_rect(self, clip: TimelineClip) -> QRectF:
        x = self._time_to_x(clip.start)
        y = RULER_H + clip.track * TRACK_H + 4
        return QRectF(x, y, max(2.0, clip.length * self.pps), TRACK_H - 8)

    def _clip_at(self, x: float, y: float) -> TimelineClip | None:
        if y < RULER_H:
            return None
        track = self._y_to_track(y)
        for clip in reversed(self.clips):
            if clip.track == track and self._clip_rect(clip).contains(QPointF(x, y)):
                return clip
        return None

    def _snap_time(self, value: float, exclude_id: str | None = None) -> float:
        if not self.snapping:
            return value
        candidates = [0.0, self.playhead]
        for clip in self.clips:
            if clip.clip_id == exclude_id:
                continue
            candidates.extend((clip.start, clip.end))
        threshold = SNAP_PX / self.pps
        for candidate in candidates:
            if abs(value - candidate) <= threshold:
                return candidate
        return value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1b1b1b"))
        width = self.width()
        height = self.height()

        tracks = max(len(self.track_names), self._needed_tracks(), 1)
        for index in range(tracks):
            y = RULER_H + index * TRACK_H
            color = QColor("#232323") if index % 2 == 0 else QColor("#282828")
            painter.fillRect(0, y, width, TRACK_H, color)
            painter.setPen(QColor("#333333"))
            painter.drawLine(0, y + TRACK_H, width, y + TRACK_H)
            painter.setPen(QColor("#4a4a4a"))
            painter.drawText(4, y + 14, str(index + 1))
            state = self.track_state(index)
            flags = "".join(
                flag
                for flag, key in (
                    ("M", "muted"),
                    ("S", "solo"),
                    ("L", "locked"),
                )
                if state.get(key)
            )
            if flags:
                previous_font = painter.font()
                font = QFont()
                font.setPointSize(7)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(
                    QColor("#ffb300")
                    if state.get("solo")
                    else QColor("#ff8a80")
                )
                painter.drawText(TRACK_GUTTER - 14, y + 14, flags)
                painter.setFont(previous_font)

        for clip in self.clips:
            rect = self._clip_rect(clip)
            if rect.right() < 0 or rect.left() > width:
                continue
            self._draw_clip(painter, clip, rect)

        painter.fillRect(0, 0, width, RULER_H, QColor("#2f2f2f"))
        painter.setPen(QColor("#3d3d3d"))
        painter.drawLine(0, RULER_H, width, RULER_H)
        step = self._tick_step()
        first = int(self._x_to_time(0) // step) * step
        t = first
        while self._time_to_x(t) <= width + step * self.pps:
            x = self._time_to_x(t)
            painter.setPen(QColor("#5a5a5a"))
            painter.drawLine(int(x), RULER_H - 7, int(x), RULER_H)
            painter.setPen(QColor("#bdbdbd"))
            painter.drawText(int(x) + 3, 11, _fmt_time(t))
            t += step

        if self._drop_pos is not None:
            x = self._drop_pos.x()
            track = self._y_to_track(self._drop_pos.y())
            y = RULER_H + track * TRACK_H
            painter.setPen(QPen(QColor("#8bc34a"), 2))
            painter.drawLine(int(x), y, int(x), y + TRACK_H)

        for value in self.markers:
            mx = self._time_to_x(value)
            if 0 <= mx <= width:
                painter.setPen(QPen(QColor("#ffb300"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(mx), RULER_H, int(mx), height)
                painter.setBrush(QBrush(QColor("#ffb300")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon(
                    [
                        QPointF(mx - 4, RULER_H - 7),
                        QPointF(mx + 4, RULER_H - 7),
                        QPointF(mx, RULER_H - 1),
                    ]
                )

        px = self._time_to_x(self.playhead)
        if 0 <= px <= width:
            painter.setPen(QPen(QColor("#ff5252"), 2))
            painter.drawLine(int(px), RULER_H, int(px), height)
            painter.setBrush(QBrush(QColor("#ff5252")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(
                [
                    QPointF(px - 6, 2),
                    QPointF(px + 6, 2),
                    QPointF(px, RULER_H - 2),
                ]
            )
        painter.end()

    def _tick_step(self) -> float:
        for step in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if step * self.pps >= 55:
                return step
        return 600.0

    def _draw_clip(self, painter: QPainter, clip: TimelineClip, rect: QRectF) -> None:
        selected = clip.clip_id in self.selected_ids
        base = QColor(clip.color)
        if selected:
            base = base.lighter(125)
        painter.setPen(QPen(QColor("#101010"), 1))
        painter.setBrush(QBrush(base))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setClipRect(rect)
        painter.setPen(QColor("#ffffff"))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        label = f"{clip.media.name}  {_fmt_time(clip.length)}"
        painter.drawText(
            int(rect.left() + 6),
            int(rect.top() + 14),
            int(rect.width() - 12),
            16,
            Qt.AlignmentFlag.AlignLeft,
            label,
        )

        # Waveform where only the peaks inside [in_point, out_point] are drawn
        if self.waveforms and clip.peaks and rect.height() > 20:
            body_top = rect.top() + 20
            body_height = rect.bottom() - body_top - 4
            if body_height > 2:
                shown = clip.visible_peaks()
                painter.setPen(QPen(QColor(255, 255, 255, 110)))
                step = rect.width() / len(shown)
                mid = body_top + body_height / 2
                for index, peak in enumerate(shown):
                    x = rect.left() + index * step
                    amplitude = max(1.0, peak * body_height / 2)
                    painter.drawLine(
                        int(x), int(mid - amplitude), int(x), int(mid + amplitude)
                    )

        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(
            int(rect.left() + 3),
            int(rect.top() + 4),
            int(rect.left() + 3),
            int(rect.bottom() - 4),
        )
        painter.drawLine(
            int(rect.right() - 3),
            int(rect.top() + 4),
            int(rect.right() - 3),
            int(rect.bottom() - 4),
        )
        painter.setClipping(False)

    def mousePressEvent(self, event):
        pos = event.position()
        if pos.y() < RULER_H:
            self._ruler_drag = True
            self.set_playhead(self._x_to_time(pos.x()))
            return

        if self.track_state(self._y_to_track(pos.y())).get("locked"):
            return

        clip = self._clip_at(pos.x(), pos.y())
        if clip is None:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.selected_ids.clear()
                self.selection_changed.emit()
                self.update()
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if clip.clip_id in self.selected_ids:
                self.selected_ids.discard(clip.clip_id)
            else:
                self.selected_ids.add(clip.clip_id)
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.selected_ids.add(clip.clip_id)
        elif clip.clip_id not in self.selected_ids:
            self.selected_ids = {clip.clip_id}
        self.selection_changed.emit()

        targets = self.selected_clips() or [clip]
        rect = self._clip_rect(clip)
        mode = "move"
        if abs(pos.x() - rect.left()) <= EDGE_GRAB:
            mode = "trim_left"
        elif abs(pos.x() - rect.right()) <= EDGE_GRAB:
            mode = "trim_right"
        self._drag = {
            "mode": mode,
            "press": pos,
            "clips": [
                {
                    "clip": target,
                    "start": target.start,
                    "track": target.track,
                    "in": target.in_point,
                    "out": target.out_point,
                }
                for target in targets
            ],
        }
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._ruler_drag:
            self.set_playhead(self._x_to_time(pos.x()))
            return
        if self._drag is None:
            hovered = self._clip_at(pos.x(), pos.y())
            if hovered is None:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                rect = self._clip_rect(hovered)
                if (
                    abs(pos.x() - rect.left()) <= EDGE_GRAB
                    or abs(pos.x() - rect.right()) <= EDGE_GRAB
                ):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        press = self._drag["press"]
        dt = (pos.x() - press.x()) / self.pps
        changed = False
        for state in self._drag["clips"]:
            clip: TimelineClip = state["clip"]
            if self._drag["mode"] == "move":
                new_start = max(0.0, state["start"] + dt)
                new_start = self._snap_time(new_start, clip.clip_id)
                new_track = state["track"] + round((pos.y() - press.y()) / TRACK_H)
                new_track = max(0, new_track)
                if new_start != clip.start or new_track != clip.track:
                    clip.start = new_start
                    if new_track != clip.track:
                        clip.track = new_track
                        clip.color = CLIP_COLORS[new_track % len(CLIP_COLORS)]
                    self._ensure_track(new_track)
                    changed = True
            elif self._drag["mode"] == "trim_left":
                maximum = (
                    state["out"]
                    if state["out"] is not None
                    else (clip.source_duration or float("inf"))
                )
                new_in = min(
                    max(0.0, state["in"] + dt), max(0.0, maximum - MIN_CLIP_LEN)
                )
                if new_in != clip.in_point:
                    clip.in_point = new_in
                    changed = True
            else:  # trim_right
                source = clip.source_duration
                if clip.media.kind == "image":
                    base = state["out"] if state["out"] is not None else source
                    limit = 36000.0
                else:
                    limit = source if source > 0 else (state["out"] or 0.0) + max(0.0, dt)
                    base = state["out"] if state["out"] is not None else limit
                new_out = min(limit, max(clip.in_point + MIN_CLIP_LEN, base + dt))
                if new_out != clip.out_point:
                    clip.out_point = new_out
                    changed = True
        if changed:
            self.clips_changed.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._drag is not None or self._ruler_drag:
            self._drag = None
            self._ruler_drag = False
            self.clips_changed.emit()
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = event.position()
        self._drag = None
        self._ruler_drag = False
        if pos.y() < RULER_H:
            self.set_playhead(self._x_to_time(pos.x()))
            return
        clip = self._clip_at(pos.x(), pos.y())
        if clip is not None:
            self.selected_ids = {clip.clip_id}
            self.selection_changed.emit()
            self.update()
            self.clip_activated.emit(clip)
        else:
            self.set_playhead(self._x_to_time(pos.x()))

    def wheelEvent(self, event):
        delta = event.angleDelta()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if delta.y() > 0 else 1 / 1.15
            self._set_pps(self.pps * factor)
        else:
            self._scroll_x = max(0.0, self._scroll_x - (delta.x() or delta.y()) * 0.6)
            self.update()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self.set_playhead(
                self.playhead
                - (
                    0.1
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    else 1.0
                )
            )
        elif event.key() == Qt.Key.Key_Right:
            self.set_playhead(
                self.playhead
                + (
                    0.1
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    else 1.0
                )
            )
        elif event.key() == Qt.Key.Key_Home:
            self.set_playhead(0.0)
        elif event.key() == Qt.Key.Key_End:
            self.set_playhead(self.total_duration())
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_pos = event.position()
            self.update()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_pos = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_pos = None
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()
        ]
        pos = event.position()
        start = self._snap_time(self._x_to_time(pos.x()))
        track = self._y_to_track(pos.y())
        if self.track_state(track).get("locked"):
            self.status_message.emit("Track is locked")
            event.ignore()
            return
        event.acceptProposedAction()
        if paths:
            self.files_dropped.emit(paths, start, track)
        self.update()

    def _on_peaks_ready(self, clip_id: str, peaks, covered: float) -> None:
        for clip in self.clips:
            if clip.clip_id == clip_id:
                clip.peaks = peaks
                clip.peaks_duration = covered
                self.update()
                break


def _fmt_time(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "0:00"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
