
import sys
import json
import time
from itertools import product
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPoint, QPointF, QSize, QEvent, QSettings, QObject, QT_VERSION_STR
from PyQt6.QtGui import (
    QActionGroup,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QFontMetricsF,
    QPainter,
    QPen,
    QPixmap,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QWidget,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QSpinBox,
    QFontComboBox,
    QFontDialog,
    QColorDialog,
    QInputDialog,
    QFileDialog,
    QWidgetAction,
    QToolButton,
    QSizePolicy,
    QListWidget,
    QDialog,
    QTabWidget,
    QKeySequenceEdit,
    QStackedWidget,
    QScrollArea,
)
import mido

from music_theory import (
    ACCIDENTAL_TO_SYMBOL,
    DETECT_NOTE_NAMES,
    NOTE_LETTER_TO_INDEX,
    NOTE_LETTER_TO_PC,
    NOTE_NAMES,
    _accidental_offset,
    _parse_root_spelling,
    midi_of_C,
    note_octave,
    spell_note_for_degree_interval,
    spell_note_for_interval,
    spelled_octave,
)

# Asegura que PyInstaller incluya el backend rtmidi (y permite correr sin él).
try:
    import mido.backends.rtmidi  # type: ignore  # noqa: F401
except Exception:
    pass

# MIDI note range for a full piano
MIN_NOTE = 21   # A0
MAX_NOTE = 108  # C8
DEFAULT_START_NOTE = 36  # C2
DEFAULT_OCTAVES = 5      # C2–C7
DEFAULT_VIEW_MODE = "single"
IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def _qt_version_tuple() -> Tuple[int, int, int]:
    parts = str(QT_VERSION_STR).split(".")
    values = []
    for part in parts[:3]:
        try:
            values.append(int(part))
        except ValueError:
            values.append(0)
    while len(values) < 3:
        values.append(0)
    return tuple(values)


IS_LEGACY_QT_MAC = IS_MAC and _qt_version_tuple() < (6, 5, 0)
UI_FONT_FAMILY = "Segoe UI" if IS_WINDOWS else "Avenir Next"
UI_FONT_STACK = (
    "'Segoe UI', 'Avenir Next', 'Helvetica Neue', Arial, sans-serif"
    if IS_WINDOWS
    else "'Avenir Next', 'Helvetica Neue', Arial, sans-serif"
)
WINDOWS_FONT_SCALE = 0.82 if IS_WINDOWS else 1.0
WINDOWS_STAFF_GLYPH_SCALE = 0.82 if IS_WINDOWS else 1.0
WINDOWS_SCALE_CIRCLE_SCALE = 0.86 if IS_WINDOWS else 1.0
LEGACY_QT_MAC_SCALE_CIRCLE_SCALE = 1.35 if IS_LEGACY_QT_MAC else 1.0
LEGACY_QT_MAC_STAFF_LEFT_PAD = 3.2 if IS_LEGACY_QT_MAC else 0.0
LEGACY_QT_MAC_NOTE_PAD = 10.0 if IS_LEGACY_QT_MAC else 0.0
LEGACY_QT_MAC_NOTE_HEAD_SCALE = 0.95 if IS_LEGACY_QT_MAC else 1.0
WINDOWS_DEFAULT_WIDTH = 1280
WINDOWS_DEFAULT_HEIGHT = 760


def ui_font(point_size: Optional[int] = None, weight: Optional[QFont.Weight] = None) -> QFont:
    font = QFont(UI_FONT_FAMILY)
    if point_size is not None:
        font.setPointSize(max(1, int(round(point_size * WINDOWS_FONT_SCALE))))
    if weight is not None:
        font.setWeight(weight)
    return font


class PersistentMenu(QMenu):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._combo_popup_open = False

    def set_combo_popup_open(self, is_open: bool) -> None:
        self._combo_popup_open = is_open

    def _is_widget_action_pos(self, pos):
        action = self.actionAt(pos)
        if isinstance(action, QWidgetAction):
            return True
        child = self.childAt(pos)
        if child is None:
            return False
        for action in self.actions():
            if isinstance(action, QWidgetAction):
                widget = action.defaultWidget()
                if widget and (child is widget or widget.isAncestorOf(child)):
                    return True
        return False

    def mouseReleaseEvent(self, event):
        if self._is_widget_action_pos(event.pos()):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        if self._is_widget_action_pos(event.pos()):
            event.accept()
            return
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self._combo_popup_open:
            event.accept()
            return
        super().focusOutEvent(event)


class ResponsiveWidthWidget(QWidget):
    """Container whose contents may reflow without imposing a window width."""

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint


class MenuComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet(
            "QListView::item:hover {"
            "  background-color: #fff7ed;"
            "  color: #1d1d1f;"
            "}"
            "QComboBox::drop-down {"
            "  border: none;"
            "  width: 0px;"
            "}"
            "QComboBox::down-arrow {"
            "  image: none;"
            "  width: 0px;"
            "  height: 0px;"
            "}"
        )
        self.activated.connect(self._close_menu_after_select)

    def showPopup(self) -> None:
        if self.count() <= 0:
            return

        menu = self._find_menu_parent()
        if isinstance(menu, PersistentMenu):
            menu.set_combo_popup_open(True)

        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Seleccionar opción")
            dialog.setModal(True)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

            layout = QVBoxLayout(dialog)
            list_widget = QListWidget(dialog)
            for idx in range(self.count()):
                list_widget.addItem(self.itemText(idx))

            current_row = self.currentIndex()
            if current_row < 0:
                current_row = 0
            if list_widget.count() > 0:
                list_widget.setCurrentRow(current_row)

            layout.addWidget(list_widget)

            buttons = QHBoxLayout()
            accept_btn = QPushButton("Aceptar", dialog)
            cancel_btn = QPushButton("Cancelar", dialog)
            buttons.addStretch()
            buttons.addWidget(accept_btn)
            buttons.addWidget(cancel_btn)
            layout.addLayout(buttons)

            accept_btn.clicked.connect(dialog.accept)
            cancel_btn.clicked.connect(dialog.reject)
            list_widget.itemDoubleClicked.connect(lambda _item: dialog.accept())

            if not _dialog_accepted(_exec_popup_dialog(dialog)):
                return

            row = list_widget.currentRow()
            if 0 <= row < self.count():
                self.setCurrentIndex(row)
                self._close_menu_after_select(row)
        finally:
            if isinstance(menu, PersistentMenu):
                menu.set_combo_popup_open(False)

    def hidePopup(self) -> None:
        menu = self._find_menu_parent()
        if isinstance(menu, PersistentMenu):
            menu.set_combo_popup_open(False)

    def _close_menu_after_select(self, _index: int) -> None:
        menu = self._find_menu_parent()
        if isinstance(menu, PersistentMenu):
            QTimer.singleShot(0, menu.close)

    def _find_menu_parent(self) -> Optional[QMenu]:
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QMenu):
            parent = parent.parentWidget()
        return parent


class WindowDragFilter(QObject):
    """Permite arrastrar ventanas sin marco desde widgets hijos no interactivos."""

    def __init__(self, target_window: QWidget):
        super().__init__(target_window)
        self._target_window = target_window
        self._drag_offset: Optional[QPoint] = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget):
            return False

        if watched.property("skip_window_drag_filter"):
            return False

        if isinstance(watched, (QPushButton, QComboBox, QSpinBox, QToolButton, QCheckBox, QFontComboBox)):
            return False

        if event.type() == QEvent.Type.MouseButtonDblClick and hasattr(event, "button"):
            if event.button() == Qt.MouseButton.LeftButton:
                on_double_click = getattr(self._target_window, "on_double_click", None)
                if callable(on_double_click):
                    on_double_click()
                    event.accept()
                    return True

        if event.type() == QEvent.Type.MouseButtonPress and hasattr(event, "button"):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self._target_window.frameGeometry().topLeft()
        elif event.type() == QEvent.Type.MouseMove and hasattr(event, "buttons"):
            if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
                self._target_window.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None

        return False


class PopupDragFilter(QObject):
    """Permite arrastrar popups con click/drag desde zonas no interactivas."""

    def __init__(self, target_window: QWidget):
        super().__init__(target_window)
        self._target_window = target_window
        self._drag_offset: Optional[QPoint] = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget):
            return False

        if isinstance(watched, (QPushButton, QComboBox, QSpinBox, QToolButton, QCheckBox, QFontComboBox, QListWidget)):
            return False

        if event.type() == QEvent.Type.MouseButtonPress and hasattr(event, "button"):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self._target_window.frameGeometry().topLeft()
        elif event.type() == QEvent.Type.MouseMove and hasattr(event, "buttons"):
            if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
                self._target_window.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_offset = None

        return False


def _install_popup_drag_support(dialog: QDialog) -> None:
    drag_filter = PopupDragFilter(dialog)
    dialog._popup_drag_filter = drag_filter  # type: ignore[attr-defined]
    dialog.installEventFilter(drag_filter)
    for child in dialog.findChildren(QWidget):
        child.installEventFilter(drag_filter)


def _prepare_popup_dialog(dialog: QDialog, draggable: bool = True) -> None:
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setStyleSheet(
        "QDialog, QInputDialog {"
        "  background-color: #f7f7f8;"
        "  color: #1d1d1f;"
        f"  font-family: {UI_FONT_STACK};"
        "  font-size: 13px;"
        "}"
        "QLabel {"
        "  color: #1d1d1f;"
        "  background-color: transparent;"
        "}"
        "QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QListWidget, "
        "QComboBox, QFontComboBox, QKeySequenceEdit {"
        "  color: #1d1d1f;"
        "  background-color: #ffffff;"
        "  border: 1px solid #b8b8bd;"
        "  border-radius: 4px;"
        "  padding: 4px 6px;"
        "  selection-background-color: #f09a00;"
        "  selection-color: #1d1d1f;"
        "}"
        "QPushButton {"
        "  color: #1d1d1f;"
        "  background-color: #ffffff;"
        "  border: 1px solid #b8b8bd;"
        "  border-radius: 6px;"
        "  padding: 6px 14px;"
        "  min-width: 72px;"
        "}"
        "QPushButton:hover {"
        "  background-color: #fff3df;"
        "  border-color: #f09a00;"
        "}"
        "QPushButton:pressed {"
        "  background-color: #f09a00;"
        "}"
        "QPushButton#PrimaryButton {"
        "  background-color: #f09a00;"
        "  border-color: #d88700;"
        "  font-weight: 600;"
        "}"
        "QPushButton#PrimaryButton:hover { background-color: #ffad1f; }"
        "QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {"
        "  color: #1d1d1f;"
        "  background-color: #ffffff;"
        "  selection-background-color: #f09a00;"
        "  selection-color: #1d1d1f;"
        "}"
        "QCheckBox { color: #1d1d1f; background-color: transparent; }"
    )
    if draggable:
        _install_popup_drag_support(dialog)


def _raise_dialog_parent(parent: Optional[QWidget]) -> None:
    if parent is None:
        return
    window = parent.window()
    if window is None:
        return
    if window.isMinimized():
        window.showNormal()
    if window.isVisible():
        window.raise_()
        window.activateWindow()


def _exec_popup_dialog(dialog: QDialog, draggable: bool = True) -> int:
    _raise_dialog_parent(dialog.parentWidget())
    _prepare_popup_dialog(dialog, draggable=draggable)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return int(dialog.exec())


def _dialog_accepted(result: int) -> bool:
    return int(result) == int(QDialog.DialogCode.Accepted)


def _get_popup_text(
    parent: Optional[QWidget],
    title: str,
    label: str,
    default_text: str = "",
) -> Tuple[str, bool]:
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setInputMode(QInputDialog.InputMode.TextInput)
    dialog.setTextValue(default_text)
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return "", False
    return str(dialog.textValue()), True


def _get_popup_int(
    parent: Optional[QWidget],
    title: str,
    label: str,
    value: int,
    minimum: int,
    maximum: int,
    step: int = 1,
) -> Tuple[int, bool]:
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setInputMode(QInputDialog.InputMode.IntInput)
    dialog.setIntRange(int(minimum), int(maximum))
    dialog.setIntStep(int(step))
    dialog.setIntValue(int(value))
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return int(value), False
    return int(dialog.intValue()), True


def _get_popup_double(
    parent: Optional[QWidget],
    title: str,
    label: str,
    value: float,
    minimum: float,
    maximum: float,
    decimals: int = 2,
) -> Tuple[float, bool]:
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setInputMode(QInputDialog.InputMode.DoubleInput)
    dialog.setDoubleRange(float(minimum), float(maximum))
    dialog.setDoubleDecimals(int(decimals))
    dialog.setDoubleValue(float(value))
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return float(value), False
    return float(dialog.doubleValue()), True


def _get_popup_item(
    parent: Optional[QWidget],
    title: str,
    label: str,
    options: List[str],
    current: int = 0,
    editable: bool = False,
) -> Tuple[str, bool]:
    if not options:
        return "", False
    current = max(0, min(int(current), len(options) - 1))
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setComboBoxItems(options)
    dialog.setComboBoxEditable(bool(editable))
    dialog.setTextValue(options[current])
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return "", False
    return str(dialog.textValue()), True


def _get_popup_color(parent: Optional[QWidget], initial: QColor, title: str) -> QColor:
    dialog = QColorDialog(initial if initial.isValid() else QColor(), parent)
    dialog.setWindowTitle(title)
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return QColor()
    return QColor(dialog.selectedColor())


def _get_popup_font(parent: Optional[QWidget], initial: QFont, title: str) -> Tuple[QFont, bool]:
    dialog = QFontDialog(initial, parent)
    dialog.setWindowTitle(title)
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return initial, False
    return dialog.currentFont(), True


def _get_popup_save_file_name(
    parent: Optional[QWidget],
    title: str,
    default_path: str,
    name_filter: str,
) -> Tuple[str, str]:
    dialog = QFileDialog(parent, title, default_path, name_filter)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return "", ""
    selected = dialog.selectedFiles()
    return (selected[0] if selected else "", dialog.selectedNameFilter())


def _get_popup_open_file_name(
    parent: Optional[QWidget],
    title: str,
    default_path: str,
    name_filter: str,
) -> Tuple[str, str]:
    dialog = QFileDialog(parent, title, default_path, name_filter)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    if not _dialog_accepted(_exec_popup_dialog(dialog, draggable=False)):
        return "", ""
    selected = dialog.selectedFiles()
    return (selected[0] if selected else "", dialog.selectedNameFilter())

INTERVAL_LABELS = {
    0: "f",
    1: "9m",
    2: "9M",
    3: "+9/3m",
    4: "3M",
    5: "4j",
    6: "4+/5b",
    7: "5j",
    8: "5+/b6",
    9: "6/7b",
    10: "7m",
    11: "7M",
}


SIMPLE_INTERVAL_LABELS = {
    0: "8j",
    1: "2m",
    2: "2M",
    3: "3m",
    4: "3M",
    5: "4j",
    6: "4+",
    7: "5j",
    8: "6m",
    9: "6M",
    10: "7m",
    11: "7M",
}


def live_note_or_interval_label(notas) -> str:
    ordered = sorted(set(int(n) for n in notas))
    if len(ordered) == 1:
        return midi_to_name(ordered[0])
    if len(ordered) == 2:
        interval = abs(ordered[1] - ordered[0]) % 12
        if interval == 0:
            return "8j"
        return SIMPLE_INTERVAL_LABELS.get(interval, "")
    return ""


def simple_interval_name(interval: int) -> str:
    interval = int(interval) % 12
    if interval == 0:
        return "8j"
    return SIMPLE_INTERVAL_LABELS.get(interval, "")


def interval_label_for_context(interval: int, present_intervals: Set[int], chord_name: str = "") -> Optional[str]:
    interval = int(interval) % 12
    present = {int(ivl) % 12 for ivl in present_intervals}
    name = chord_name or ""

    if interval == 1:
        return "9m"

    if interval == 2:
        if any(ivl in present for ivl in (3, 4, 5)) or any(token in name for token in ("9", "11", "13")):
            return "9M"
        return "sus2"

    if interval == 3:
        if "#9" in name or "♯9" in name or 4 in present:
            return "9+"
        return "3m"

    if interval == 5:
        if "11" in name:
            return "11j"
        return "4j"

    if interval == 6:
        if "b5" in name or "♭5" in name or "º" in name or "ø" in name or 3 in present:
            return "5b"
        if "#11" in name or "♯11" in name or 4 in present:
            return "11+"
        return "5b"

    if interval == 8:
        if "b13" in name or "♭13" in name or any(ivl in present for ivl in (6, 7)):
            return "13m"
        return "5+"

    if interval == 9:
        if "º7" in name or ("º" in name and "7" in name):
            return "7b"
        if "13" in name:
            return "13"
        if "6" in name:
            return "6"
        return "6"

    return INTERVAL_LABELS.get(interval)


BASE_CHORD_PATTERNS = [
    {'nombre':'', 'obligatorias':[0,4,7], 'opcionales':[]},
    {'nombre':'m', 'obligatorias':[0,3,7], 'opcionales':[]},
    {'nombre':'+', 'obligatorias':[0,4,8], 'opcionales':[]},
    {'nombre':'º', 'obligatorias':[0,3,6], 'opcionales':[]},
    {'nombre':'sus4', 'obligatorias':[0,5,7], 'opcionales':[]},
    {'nombre':'sus2', 'obligatorias':[0,2,7], 'opcionales':[]},
    {'nombre':'(b5)', 'obligatorias':[0,4,6], 'opcionales':[]},
    {'nombre':'add2', 'obligatorias':[0,2,4,7], 'opcionales':[]},
    {'nombre':'m(add2)', 'obligatorias':[0,2,3,7], 'opcionales':[]},
    {'nombre':'m(add4)', 'obligatorias':[0,3,5,7], 'opcionales':[]},
    {'nombre':'6', 'obligatorias':[0,4,7,9], 'opcionales':[]},
    {'nombre':'7', 'obligatorias':[0,4,10], 'opcionales':[]},
    {'nombre':'7', 'obligatorias':[0,4,7,10], 'opcionales':[]},
    {'nombre':'∆', 'obligatorias':[0,4,7,11], 'opcionales':[]},
    {'nombre':'m6', 'obligatorias':[0,3,7,9], 'opcionales':[]},
    {'nombre':'m7', 'obligatorias':[0,3,7,10], 'opcionales':[]},
    {'nombre':'m∆', 'obligatorias':[0,3,7,11], 'opcionales':[]},
    {'nombre':'+7', 'obligatorias':[0,4,8,10], 'opcionales':[]},
    {'nombre':'+∆', 'obligatorias':[0,4,8,11], 'opcionales':[]},
    {'nombre':'º7', 'obligatorias':[0,3,6,9], 'opcionales':[]},
    {'nombre':'m7(b5)', 'obligatorias':[0,3,6,10], 'opcionales':[]},
    {'nombre':'º∆', 'obligatorias':[0,3,6,11], 'opcionales':[]},
    {'nombre':'7sus4', 'obligatorias':[0,5,7,10], 'opcionales':[]},
    {'nombre':'7sus2', 'obligatorias':[0,2,7,10], 'opcionales':[]},
    {'nombre':'∆sus4', 'obligatorias':[0,5,7,11], 'opcionales':[]},
    {'nombre':'∆sus2', 'obligatorias':[0,2,7,11], 'opcionales':[]},
    {'nombre':'7(b5)', 'obligatorias':[0,4,6,10], 'opcionales':[]},
    {'nombre':'∆(b5)', 'obligatorias':[0,4,6,11], 'opcionales':[]},
    {'nombre':'6(9)', 'obligatorias':[0,2,4,7,9], 'opcionales':[]},
    {'nombre':'7(b9)', 'obligatorias':[0,4,7,10,1], 'opcionales':[]},
    {'nombre':'9', 'obligatorias':[0,4,10,2], 'opcionales':[7]},
    {'nombre':'7(#9)', 'obligatorias':[0,4,10,3], 'opcionales':[7]},
    {'nombre':'∆9', 'obligatorias':[0,4,11,2], 'opcionales':[7]},
    {'nombre':'∆(#9)', 'obligatorias':[0,4,11,3], 'opcionales':[7]},
    {'nombre':'m6(9)', 'obligatorias':[0,3,9,2], 'opcionales':[7]},
    {'nombre':'m9', 'obligatorias':[0,3,10,2], 'opcionales':[7]},
    {'nombre':'m∆9', 'obligatorias':[0,3,11,2], 'opcionales':[7]},
    {'nombre':'+7(b9)', 'obligatorias':[0,4,8,10,1], 'opcionales':[]},
    {'nombre':'+9', 'obligatorias':[0,4,8,10,2], 'opcionales':[]},
    {'nombre':'+7(#9)', 'obligatorias':[0,4,8,10,3], 'opcionales':[]},
    {'nombre':'+∆9', 'obligatorias':[0,4,8,11,2], 'opcionales':[]},
    {'nombre':'+∆(#9)', 'obligatorias':[0,4,8,11,3], 'opcionales':[]},
    {'nombre':'º7(9)', 'obligatorias':[0,3,6,9,2], 'opcionales':[]},
    {'nombre':'ø9', 'obligatorias':[0,3,6,10,2], 'opcionales':[]},
    {'nombre':'º∆9', 'obligatorias':[0,3,6,11,2], 'opcionales':[]},
    {'nombre':'9sus4', 'obligatorias':[0,5,7,10,2], 'opcionales':[]},
    {'nombre':'7sus4(b9)', 'obligatorias':[0,5,7,10,1], 'opcionales':[]},
    {'nombre':'sus4(addb2)', 'obligatorias':[0,5,1], 'opcionales':[7]},
    {'nombre':'7sus2(b9)', 'obligatorias':[0,2,10,1], 'opcionales':[7]},
    {'nombre':'∆9sus4', 'obligatorias':[0,5,11,2], 'opcionales':[7]},
    {'nombre':'7(b5)b9', 'obligatorias':[0,4,6,10,1], 'opcionales':[]},
    {'nombre':'9(b5)', 'obligatorias':[0,4,6,10,2], 'opcionales':[]},
    {'nombre':'7(b5)#9', 'obligatorias':[0,4,6,10,3], 'opcionales':[]},
    {'nombre':'6(9)#11', 'obligatorias':[0,4,9,2,6,7], 'opcionales':[]},
    {'nombre':'7(b9)#11', 'obligatorias':[0,4,10,1,6], 'opcionales':[7]},
    {'nombre':'9(#11)', 'obligatorias':[0,4,10,2,6], 'opcionales':[7]},
    {'nombre':'7(#9)#11', 'obligatorias':[0,4,10,3,6], 'opcionales':[7]},
    {'nombre':'∆9(#11)', 'obligatorias':[0,4,11,2,6], 'opcionales':[7]},
    {'nombre':'∆(#9)#11', 'obligatorias':[0,4,11,3,6], 'opcionales':[7]},
    {'nombre':'m11', 'obligatorias':[0,3,10,5], 'opcionales':[2,7]},
    {'nombre':'m9(#11)', 'obligatorias':[0,3,7,10,2,6], 'opcionales':[]},
    {'nombre':'m∆11', 'obligatorias':[0,3,11,5], 'opcionales':[7,2]},
    {'nombre':'m∆#11', 'obligatorias':[0,3,11,6], 'opcionales':[7,2,5]},
    {'nombre':'+7(b9)#11', 'obligatorias':[0,4,8,10,1,6], 'opcionales':[]},
    {'nombre':'+9(#11)', 'obligatorias':[0,4,8,10,2,6], 'opcionales':[]},
    {'nombre':'+7(#9)#11', 'obligatorias':[0,4,8,10,3,6], 'opcionales':[]},
    {'nombre':'+∆9(#11)', 'obligatorias':[0,4,8,11,2,6], 'opcionales':[]},
    {'nombre':'+∆(#9)#11', 'obligatorias':[0,4,8,11,3,6], 'opcionales':[]},
    {'nombre':'º7(11)', 'obligatorias':[0,3,6,9,5], 'opcionales':[2]},
    {'nombre':'ø11', 'obligatorias':[0,2,3,6,10,5], 'opcionales':[]},
    {'nombre':'º∆11', 'obligatorias':[0,3,6,11,5], 'opcionales':[2]},
    {'nombre':'13(b9)', 'obligatorias':[0,4,10,1,9], 'opcionales':[7]},
    {'nombre':'13', 'obligatorias':[0,2,4,9,10], 'opcionales':[7]},
    {'nombre':'13(#9)', 'obligatorias':[0,4,10,3,9], 'opcionales':[7]},
    {'nombre':'7(b9)b13', 'obligatorias':[0,4,10,1,8], 'opcionales':[7]},
    {'nombre':'9(b13)', 'obligatorias':[0,4,10,2,8], 'opcionales':[7]},
    {'nombre':'7(#9)b13', 'obligatorias':[0,4,10,3,8], 'opcionales':[7]},
    {'nombre':'∆13', 'obligatorias':[0,2,4,7,11,9], 'opcionales':[]},
    {'nombre':'∆13(#11)', 'obligatorias':[0,4,7,11,6,9], 'opcionales':[2]},
    {'nombre':'13(#11)', 'obligatorias':[0,4,7,10,6,9], 'opcionales':[2]},
    {'nombre':'∆13(#9)', 'obligatorias':[0,4,11,3,9], 'opcionales':[2]},
    {'nombre':'m13', 'obligatorias':[0,3,10,9], 'opcionales':[7,2,5]},
    {'nombre':'m∆13', 'obligatorias':[0,3,11,9], 'opcionales':[7,2,5]},
    {'nombre':'º7(b13)', 'obligatorias':[0,3,6,9,8], 'opcionales':[2,5]},
    {'nombre':'13sus4', 'obligatorias':[0,2,5,7,10,9], 'opcionales':[]},
    {'nombre':'13sus4(b9)', 'obligatorias':[0,5,7,10,1,9], 'opcionales':[]},
    {'nombre':'13(b5)b9', 'obligatorias':[0,4,6,10,1,9], 'opcionales':[]},
    {'nombre':'13(b5)', 'obligatorias':[0,4,6,10,9], 'opcionales':[2,7]},
    {'nombre':'13(b5)#9', 'obligatorias':[0,4,6,10,3,9], 'opcionales':[2,7]},
   ]

for _pattern in BASE_CHORD_PATTERNS:
    _pattern.setdefault("is_custom", False)

CHORD_PATTERNS = [dict(ptn) for ptn in BASE_CHORD_PATTERNS]

SCALE_PATTERNS = {
    "mayor": [2, 2, 1, 2, 2, 2, 1],
    "mayor_armonica": [2, 2, 1, 2, 1, 3, 1],
    "menor_melodica": [2, 1, 2, 2, 2, 2, 1],
    "menor_armonica": [2, 1, 2, 2, 1, 3, 1],
    "jonico": [2, 2, 1, 2, 2, 2, 1],
    "dorico": [2, 1, 2, 2, 2, 1, 2],
    "frigio": [1, 2, 2, 2, 1, 2, 2],
    "lidio": [2, 2, 2, 1, 2, 2, 1],
    "mixolidio": [2, 2, 1, 2, 2, 1, 2],
    "eolico": [2, 1, 2, 2, 1, 2, 2],
    "locrio": [1, 2, 2, 1, 2, 2, 2],
    "jonico_b6": [2, 2, 1, 2, 1, 3, 1],
    "locrio_s2s6": [2, 1, 2, 1, 3, 1, 2],
    "mixolidio_b2_s2_no4": [1, 2, 1, 3, 1, 2, 2],
    "dorico_s4_s7": [2, 1, 3, 1, 2, 2, 1],
    "mixolidio_b2": [1, 3, 1, 2, 2, 1, 2],
    "lidio_s2_s5": [3, 1, 2, 2, 1, 2, 1],
    "locrio_b7": [1, 2, 2, 1, 2, 1, 3],
    "eolico_s7": [2, 1, 2, 2, 1, 3, 1],
    "locrio_s6": [1, 2, 2, 1, 3, 1, 2],
    "jonico_aumentado": [2, 2, 1, 3, 1, 2, 1],
    "dorico_s4": [2, 1, 3, 1, 2, 1, 2],
    "mixolidio_b2b6": [1, 3, 1, 2, 1, 2, 2],
    "lidio_s2": [3, 1, 2, 1, 2, 2, 1],
    "locrio_b4b7": [1, 2, 1, 2, 2, 1, 3],
    "dorico_s7": [2, 1, 2, 2, 2, 2, 1],
    "dorico_b2": [1, 2, 2, 2, 2, 1, 2],
    "lidio_aumentado": [2, 2, 2, 2, 1, 2, 1],
    "lidio_dominante": [2, 2, 2, 1, 2, 1, 2],
    "mixolidio_b6": [2, 2, 1, 2, 1, 2, 2],
    "locrio_s2": [2, 1, 2, 1, 2, 2, 2],
    "alterado": [1, 2, 1, 2, 2, 2, 2],
    "pentatonica_mayor": [2, 2, 3, 2, 3],
    "pentatonica_dominante": [2, 2, 3, 3, 2],
    "blues": [3, 2, 1, 1, 3, 2],
    "por_tonos": [2, 2, 2, 2, 2, 2],
    "disminuida_HW": [1, 2, 1, 2, 1, 2, 1, 2],
    "disminuida_WH": [2, 1, 2, 1, 2, 1, 2, 1],
}

SPECIAL_SCALES = {
    "pentatonica_mayor",
    "pentatonica_dominante",
    "blues",
    "por_tonos",
    "disminuida_HW",
    "disminuida_WH",
}

SCALE_OPTIONS = [
    ("Mayor", "mayor"),
    ("Mayor armónica", "mayor_armonica"),
    ("Menor melódica", "menor_melodica"),
    ("Menor armónica", "menor_armonica"),
    ("Jónico", "jonico"),
    ("Dórico", "dorico"),
    ("Frigio", "frigio"),
    ("Lidio", "lidio"),
    ("Mixolidio", "mixolidio"),
    ("Eólico", "eolico"),
    ("Locrio", "locrio"),
    ("Jónico♭6", "jonico_b6"),
    ("Locrio♯2♯6", "locrio_s2s6"),
    ("Mixolidio♭2♯2 no 4", "mixolidio_b2_s2_no4"),
    ("Dórico♯4♯7", "dorico_s4_s7"),
    ("Mixolidio♭2", "mixolidio_b2"),
    ("Lidio♯2♯5", "lidio_s2_s5"),
    ("Locrio♭7", "locrio_b7"),
    ("Eólico♯7", "eolico_s7"),
    ("Locrio♯6", "locrio_s6"),
    ("Jónico aumentado", "jonico_aumentado"),
    ("Dórico♯4", "dorico_s4"),
    ("Mixolidio♭2♭6", "mixolidio_b2b6"),
    ("Lidio♯2", "lidio_s2"),
    ("Locrio♭4♭7", "locrio_b4b7"),
    ("Dórico♯7", "dorico_s7"),
    ("Dórico♭2", "dorico_b2"),
    ("Lidio aumentado", "lidio_aumentado"),
    ("Lidio dominante", "lidio_dominante"),
    ("Mixolidio♭6", "mixolidio_b6"),
    ("Locrio♯2", "locrio_s2"),
    ("Alterado", "alterado"),
    ("Pentatónica mayor", "pentatonica_mayor"),
    ("Pentatónica dominante", "pentatonica_dominante"),
    ("Escala blues", "blues"),
    ("Por tonos (Whole-tone)", "por_tonos"),
    ("Disminuida H-W", "disminuida_HW"),
    ("Disminuida W-H", "disminuida_WH"),
]


def _normalize_intervals(intervals: List[int]) -> List[int]:
    normalized = sorted({int(ivl) % 12 for ivl in intervals} | {0})
    return normalized


def _signature_from_lists(obligatorias: List[int], opcionales: List[int]) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    oblig_norm = tuple(_normalize_intervals(obligatorias))
    opc_norm = tuple(sorted({int(ivl) % 12 for ivl in opcionales}))
    return oblig_norm, opc_norm


DEFAULT_BASE_SIGNATURES = {
    _signature_from_lists(ptn.get("obligatorias", []), ptn.get("opcionales", []))
    for ptn in BASE_CHORD_PATTERNS
}


def analizar_cifrado_alternativos(notas):
    """
    notas: iterable de números MIDI.
    Devuelve dict con:
      - principal: str
      - alternativos: list[str]
    Traducción directa de analizarCifradoAlternativos de funcionalidades.js.
    """
    notas = list(notas)
    if not notas or len(notas) < 2:
        return {"principal": "", "alternativos": []}

    ordenadas = sorted(set(int(n) for n in notas))
    if len(ordenadas) < 2:
        return {"principal": "", "alternativos": []}

    bass_midi = ordenadas[0]
    bass_pc = bass_midi % 12
    pitch_classes = sorted(set(n % 12 for n in ordenadas))

    matches = []
    for root_pc in pitch_classes:
        interval_set = set((n % 12 - root_pc + 12) % 12 for n in ordenadas)
        interval_set.add(0)
        for ptn in CHORD_PATTERNS:
            oblig = ptn["obligatorias"]
            opc = ptn["opcionales"]
            if not all(ivl in interval_set for ivl in oblig):
                continue
            permitidas = set(oblig) | set(opc)
            extra_notas = [ivl for ivl in interval_set if ivl not in permitidas]
            if extra_notas:
                continue

            num_oblig = len(oblig)
            opcionales_presentes = sum(1 for ivl in opc if ivl in interval_set)

            matches.append({
                "root": root_pc,
                "nombre": ptn["nombre"],
                "numOblig": num_oblig,
                "opcionalesPresentes": opcionales_presentes,
                "esGraveFundamental": (bass_pc == root_pc),
                "obligatorias": oblig,
                "opcionales": opc,
                "is_custom": bool(ptn.get("is_custom", False)),
            })

    if not matches:
        return {"principal": "", "alternativos": []}

    def sort_key(m):
        return (
            0 if m.get("is_custom") else 1,
            0 if m["esGraveFundamental"] else 1,
            -m["numOblig"],
            -m["opcionalesPresentes"],
            m["nombre"],
        )

    def nombre_para_match(m):
        root_name = DETECT_NOTE_NAMES[m["root"]]
        nombre = root_name + m["nombre"]
        if not m["esGraveFundamental"]:
            es_solo_triada_o_sep = all(ivl not in (2, 5, 9) for ivl in m["obligatorias"]) and \
                                   all(ivl not in (2, 5, 9) for ivl in m["opcionales"])
            if es_solo_triada_o_sep:
                bass_int = (bass_pc - m["root"] + 12) % 12
                if bass_int in (3, 4, 7, 10):
                    bass_name = DETECT_NOTE_NAMES[bass_pc]
                    nombre = nombre + "/" + bass_name
        return nombre

    bass_matches = [m for m in matches if m["esGraveFundamental"]]
    ordered_bass = sorted(bass_matches, key=sort_key)
    ordered_all = sorted(matches, key=sort_key)

    principal_match = ordered_bass[0] if ordered_bass else ordered_all[0]
    principal = nombre_para_match(principal_match)

    alternativos = []
    for m in ordered_bass[1:] + [m for m in ordered_all if m is not principal_match]:
        nombre = nombre_para_match(m)
        if nombre != principal and nombre not in alternativos:
            alternativos.append(nombre)
        if len(alternativos) >= 4:
            break

    return {
        "principal": principal,
        "alternativos": alternativos,
        "principal_match": principal_match,
        "bass_pc": bass_pc,
    }



def midi_to_name(note: int) -> str:
    octave = note // 12 - 1
    name = NOTE_NAMES[note % 12]
    return f"{name}{octave}"


def is_white(note: int) -> bool:
    pc = note % 12
    return pc in (0, 2, 4, 5, 7, 9, 11)


def build_scale_pcs(root_pc: int, intervals: List[int], transpose: int = 0) -> List[int]:
    if not intervals:
        return []
    scale_pcs = [((int(root_pc) + int(transpose)) % 12)]
    for step in intervals[:-1]:
        scale_pcs.append((scale_pcs[-1] + int(step)) % 12)
    return scale_pcs


def degree_index_for_note_pc(note_pc: int, scale_pcs: List[int]) -> Optional[int]:
    try:
        return list(scale_pcs).index(int(note_pc) % 12)
    except ValueError:
        return None


class PianoWidget(QWidget):
    """
    Solo dibuja el teclado, sin fondo de ventana.
    La ventana que lo contiene es transparente y sin bordes.
    Mantiene proporción fija de las teclas.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_note = MIN_NOTE
        self.end_note = MAX_NOTE
        self.pressed_notes: Set[int] = set()
        self.sustained_notes: Set[int] = set()
        self.recent_released_notes: Dict[int, float] = {}
        self.note_fade_duration_ms = 120
        self._note_fade_timer = QTimer(self)
        self._note_fade_timer.setInterval(30)
        self._note_fade_timer.timeout.connect(self._advance_note_fades)
        self.live_warning_notes: Set[int] = set()
        self.live_warning_color = QColor(230, 70, 70, 180)
        self.sustain_opacity: float = 0.4  # 0.0–1.0
        self.interval_labels: Dict[int, str] = {}
        self.show_keyboard_labels = True
        self.display_chord_notes: Dict[int, QColor] = {}
        self.display_scale_notes: Dict[int, QColor] = {}
        self.display_scale_label = ""
        self.scale_circle_size_factor: float = 1.0
        self.on_scale_circle_clicked = None
        self.on_double_click = None

        # Proporción alto/ancho de una tecla blanca (alto = ancho * aspect)
        self.key_aspect_ratio = 4.5

        # Color base para notas presionadas
        self.base_color = QColor(240, 154, 0)

        self.setMinimumSize(300, 80)
        self.setProperty("skip_window_drag_filter", True)

        # Fondo transparente
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        # Para arrastrar y redimensionar la ventana desde el propio teclado
        self._drag_offset: Optional[QPoint] = None
        self._resizing = False
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_size = None
        self._resize_margin = 16  # píxeles desde la esquina inferior derecha
        self.force_full_width = False

        self.interval_label_settings = {
            "font_family": UI_FONT_FAMILY,
            "font_size": 14,
            "color_white": QColor(Qt.GlobalColor.black),
            "color_black": QColor(Qt.GlobalColor.black),
            "y_anchor_mode_white": "bottom25",
            "y_percent_white": 87.5,
            "y_anchor_mode_black": "center",
            "y_percent_black": 60.0,
            "frame_fill_color": QColor(255, 255, 255),
            "frame_fill_opacity": 0.6,
            "frame_border_color": QColor(0, 0, 0, 180),
            "frame_border_width": 1.0,
        }

    # --- configuración pública ---

    def set_range(self, start_note: int, end_note: int):
        self.start_note = max(MIN_NOTE, min(start_note, MAX_NOTE))
        self.end_note = max(self.start_note, min(end_note, MAX_NOTE))
        self.update()

    def set_range_from_start_and_octaves(self, start_note: int, octaves: int):
        """
        start_note: A0 o cualquier Cx.
        octaves: número de octavas.
        Siempre se agrega el C de la octava siguiente:
          - Si empiezas en C2 y pides 4 octavas -> C2 ... C6
          - Si empiezas en A0 y pides 1 octava -> A0 ... C2
        """
        start_note = max(MIN_NOTE, min(start_note, MAX_NOTE))
        start_oct = note_octave(start_note)
        target_oct = start_oct + octaves
        # Si el teclado inicia en A0 (u otra nota que no sea C), el conteo
        # de octavas debe empezar en C de la octava siguiente.
        if NOTE_NAMES[start_note % 12] != "C":
            target_oct += 1
        end_note = midi_of_C(target_oct)
        if end_note > MAX_NOTE:
            end_note = MAX_NOTE
        self.start_note = start_note
        self.end_note = end_note
        self.update()

    def set_pressed(self, note: int, pressed: bool):
        if pressed:
            self.pressed_notes.add(note)
            self.recent_released_notes.pop(note, None)
        else:
            if note in self.pressed_notes:
                self.recent_released_notes[note] = time.monotonic()
                if not self._note_fade_timer.isActive():
                    self._note_fade_timer.start()
            self.pressed_notes.discard(note)
        self.update()

    def clear_pressed(self):
        now = time.monotonic()
        for note in self.pressed_notes:
            self.recent_released_notes[note] = now
        if self.recent_released_notes and not self._note_fade_timer.isActive():
            self._note_fade_timer.start()
        self.pressed_notes.clear()
        self.update()

    def set_sustained(self, note: int, sustained: bool):
        if sustained:
            self.sustained_notes.add(note)
        else:
            self.sustained_notes.discard(note)
        self.update()

    def clear_sustained(self):
        self.sustained_notes.clear()
        self.update()

    def set_live_warning_notes(self, notes: Set[int], color: Optional[QColor] = None):
        self.live_warning_notes = {int(note) for note in notes if self.start_note <= int(note) <= self.end_note}
        if color is not None and color.isValid():
            self.live_warning_color = QColor(color)
        self.update()

    def set_interval_labels(self, labels: Dict[int, str]):
        self.interval_labels = labels
        self.update()

    def set_interval_label_style(self, settings: Dict):
        self.interval_label_settings = settings

    def set_keyboard_labels_visible(self, visible: bool):
        self.show_keyboard_labels = bool(visible)
        self.update()
        self.update()

    def set_display_chord_notes(self, notes: Dict[int, QColor]):
        self.display_chord_notes = dict(notes)
        self.update()

    def set_display_scale_notes(self, notes: Dict[int, QColor]):
        self.display_scale_notes = dict(notes)
        self.update()

    def set_display_scale_label(self, label: str):
        self.display_scale_label = str(label or "")
        self.update()

    def set_scale_circle_size_factor(self, factor: float) -> None:
        self.scale_circle_size_factor = max(0.5, min(2.0, float(factor)))
        self.update()

    def set_base_color(self, color: QColor):
        """Compatibilidad: permite fijar color base directamente."""
        if not isinstance(color, QColor) or not color.isValid():
            return
        self.base_color = QColor(color)
        self.update()

    def set_base_color_name(self, name: str):
        mapping = {
            "Cian": QColor(0, 200, 200),
            "Azul": QColor(80, 160, 255),
            "Verde": QColor(80, 220, 140),
            "Rojo": QColor(230, 80, 80),
            "Naranja": QColor(240, 154, 0),
            "Morado": QColor(180, 100, 220),
        }
        self.base_color = mapping.get(name, QColor("cyan"))
        self.update()

    # --- helpers internos ---

    def _advance_note_fades(self):
        now = time.monotonic()
        duration = max(1, int(self.note_fade_duration_ms)) / 1000.0
        expired = [note for note, started in self.recent_released_notes.items() if now - started >= duration]
        for note in expired:
            self.recent_released_notes.pop(note, None)
        if not self.recent_released_notes:
            self._note_fade_timer.stop()
        self.update()

    def _released_fade_color_for(self, note: int, is_black_key: bool) -> Optional[QColor]:
        started = self.recent_released_notes.get(note)
        if started is None or note in self.pressed_notes or note in self.sustained_notes:
            return None
        duration = max(1, int(self.note_fade_duration_ms)) / 1000.0
        factor = 1.0 - ((time.monotonic() - started) / duration)
        if factor <= 0:
            return None
        color = self._pressed_color_for(note, is_black_key)
        color.setAlpha(max(0, min(160, int(color.alpha() * factor * 0.65))))
        return color

    def _note_factor(self, note: int) -> float:
        """Devuelve un factor 0.6–1.0 según la posición relativa de la nota en el rango."""
        if self.end_note == self.start_note:
            return 1.0
        rel = (note - self.start_note) / float(self.end_note - self.start_note)
        return 0.6 + 0.4 * rel

    def _pressed_color_for(self, note: int, is_black_key: bool) -> QColor:
        if note in self.live_warning_notes:
            return QColor(self.live_warning_color)
        return QColor(self.base_color)


    def _sustain_color_for(self, note: int, is_black_key: bool) -> QColor:
        """Color para notas sostenidas por pedal, algo más claro (mezclado con blanco)."""
        base = self._pressed_color_for(note, is_black_key)
        factor = max(0.0, min(1.0, float(self.sustain_opacity)))
        white_r, white_g, white_b = 255, 255, 255
        r = int(white_r + (base.red() - white_r) * factor)
        g = int(white_g + (base.green() - white_g) * factor)
        b = int(white_b + (base.blue() - white_b) * factor)
        return QColor(r, g, b, 255)

    def _in_resize_zone(self, pos: QPoint) -> bool:
        """Devuelve True si el ratón está cerca de la esquina inferior derecha (zona de resize)."""
        rect = self.rect()
        return (
            pos.x() >= rect.width() - self._resize_margin
            and pos.y() >= rect.height() - self._resize_margin
        )

    def _scale_circle_hit_regions(self) -> List[Tuple[int, QPointF, float]]:
        regions: List[Tuple[int, QPointF, float]] = []
        if not self.display_scale_notes:
            return regions

        rect = self.rect()
        white_notes: List[int] = [n for n in range(self.start_note, self.end_note + 1) if is_white(n)]
        if not white_notes:
            return regions

        num_white = len(white_notes)
        key_width = rect.width() / num_white
        key_height = min(rect.height(), key_width * self.key_aspect_ratio)
        total_width = key_width * num_white
        x_offset = (rect.width() - total_width) / 2
        y_offset = (rect.height() - key_height) / 2

        note_to_white_index: Dict[int, int] = {}
        white_index = 0
        for n in range(self.start_note, self.end_note + 1):
            if is_white(n):
                note_to_white_index[n] = white_index
                white_index += 1
            else:
                note_to_white_index[n] = max(0, white_index - 1)

        scale_circle_platform_scale = WINDOWS_SCALE_CIRCLE_SCALE * LEGACY_QT_MAC_SCALE_CIRCLE_SCALE
        white_base_radius = max(3.0, min(key_width, key_height) * 0.18 * scale_circle_platform_scale)
        white_radius = white_base_radius * self.scale_circle_size_factor
        for n in white_notes:
            if n not in self.display_scale_notes:
                continue
            idx = note_to_white_index[n]
            x = x_offset + idx * key_width
            key_rect = QRectF(x, y_offset, key_width, key_height)
            center = QPointF(key_rect.center().x(), key_rect.bottom() - white_radius * 1.8)
            regions.append((n, center, white_radius))

        black_height = key_height * 0.6
        black_width = key_width * 0.6
        black_base_radius = max(2.5, min(black_width, black_height) * 0.2 * scale_circle_platform_scale)
        black_radius = black_base_radius * self.scale_circle_size_factor
        for n in range(self.start_note, self.end_note + 1):
            if is_white(n) or n not in self.display_scale_notes:
                continue
            idx = note_to_white_index[n]
            x = x_offset + idx * key_width + key_width - black_width / 2
            key_rect = QRectF(x, y_offset, black_width, black_height)
            center = QPointF(key_rect.center().x(), key_rect.bottom() - black_radius * 1.6)
            regions.append((n, center, black_radius))
        return regions

    def _scale_note_at_pos(self, pos: QPoint) -> Optional[int]:
        for note, center, radius in self._scale_circle_hit_regions():
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            if dx * dx + dy * dy <= radius * radius:
                return note
        return None

    # --- soporte para arrastrar y redimensionar ventana ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if callable(self.on_scale_circle_clicked):
                hit_note = self._scale_note_at_pos(event.pos())
                if hit_note is not None:
                    self.on_scale_circle_clicked(hit_note)
                    event.accept()
                    return
            if self._in_resize_zone(event.pos()):
                # Empezar redimensionado
                self._resizing = True
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_size = self.window().size()
                event.accept()
                return
            # Si no estamos en la zona de resize, mover la ventana
            global_pos = event.globalPosition().toPoint()
            window = self.window()
            self._drag_offset = global_pos - window.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_start_pos is not None and self._resize_start_size is not None:
            # Cambiar tamaño de la ventana
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self._resize_start_pos
            new_width = max(200, self._resize_start_size.width() + delta.x())
            new_height = max(80, self._resize_start_size.height() + delta.y())
            self.window().resize(new_width, new_height)
            event.accept()
            return

        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            global_pos = event.globalPosition().toPoint()
            new_top_left = global_pos - self._drag_offset
            self.window().move(new_top_left)
            event.accept()
            return

        # Cambiar cursor cuando está en zona de resize
        if self._in_resize_zone(event.pos()):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._resizing = False
        self._resize_start_pos = None
        self._resize_start_size = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and callable(self.on_double_click):
            self.on_double_click()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # --- dibujo ---

    def set_force_full_width(self, enabled: bool) -> None:
        self.force_full_width = bool(enabled)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()

        # Lista de teclas blancas en el rango
        white_notes: List[int] = [
            n for n in range(self.start_note, self.end_note + 1) if is_white(n)
        ]
        if not white_notes:
            return

        num_white = len(white_notes)

        # Calculamos tamaño de teclas manteniendo proporción
        # key_width debe cumplir:
        #   key_width * num_white <= rect.width
        #   key_width * aspect_ratio <= rect.height
        max_width_from_width = rect.width() / num_white
        max_width_from_height = rect.height() / self.key_aspect_ratio
        key_width = min(max_width_from_width, max_width_from_height)
        key_height = key_width * self.key_aspect_ratio

        if self.force_full_width:
            key_width = max_width_from_width
            key_height = min(rect.height(), key_width * self.key_aspect_ratio)

        total_keys_width = key_width * num_white

        # Centramos el teclado dentro del rectángulo disponible
        x_offset = rect.left() + (rect.width() - total_keys_width) / 2
        y_offset = rect.top() + (rect.height() - key_height) / 2

        # Mapeo nota -> índice de tecla blanca base
        note_to_white_index = {}
        white_index = 0
        for n in range(self.start_note, self.end_note + 1):
            if is_white(n):
                note_to_white_index[n] = white_index
                white_index += 1
            else:
                note_to_white_index[n] = max(0, white_index - 1)

        # Dibujar teclas blancas
        painter.setPen(QPen(Qt.GlobalColor.black))
        for n in white_notes:
            idx = note_to_white_index[n]
            x = x_offset + idx * key_width
            key_rect = QRectF(x, y_offset, key_width, key_height)

            if n in self.pressed_notes:
                painter.setBrush(QBrush(self._pressed_color_for(n, False)))
            elif n in self.sustained_notes:
                painter.setBrush(QBrush(self._sustain_color_for(n, False)))
            else:
                painter.setBrush(QBrush(Qt.GlobalColor.white))

            painter.drawRect(key_rect)
            fade_color = self._released_fade_color_for(n, False)
            if fade_color is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(fade_color))
                painter.drawRect(key_rect.adjusted(1.0, 1.0, -1.0, -1.0))
                painter.setPen(QPen(Qt.GlobalColor.black))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(key_rect)

        # Superposiciones de acordes y escalas (visualización) en teclas blancas
        if self.display_chord_notes or self.display_scale_notes:
            chord_notes = self.display_chord_notes
            scale_notes = self.display_scale_notes
            scale_circle_platform_scale = WINDOWS_SCALE_CIRCLE_SCALE * LEGACY_QT_MAC_SCALE_CIRCLE_SCALE
            for n in white_notes:
                idx = note_to_white_index[n]
                x = x_offset + idx * key_width
                key_rect = QRectF(x, y_offset, key_width, key_height)
                if n in chord_notes:
                    painter.setBrush(QBrush(chord_notes[n]))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(key_rect)
                if n in scale_notes:
                    color = scale_notes[n]
                    radius = (
                        max(3.0, min(key_width, key_height) * 0.18 * scale_circle_platform_scale)
                        * self.scale_circle_size_factor
                    )
                    center = QPointF(key_rect.center().x(), key_rect.bottom() - radius * 1.8)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(center, radius, radius)

        # Etiquetas para las C
        if self.show_keyboard_labels:
            label_color = QColor(Qt.GlobalColor.black)
            label_color.setAlphaF(0.65)
            painter.setPen(QPen(label_color))
            font = QFont(UI_FONT_FAMILY)
            font.setPointSize(self._keyboard_label_font_size(key_width, key_height))
            painter.setFont(font)
            metrics = painter.fontMetrics()
            for n in white_notes:
                if n % 12 == 0:  # C
                    idx = note_to_white_index[n]
                    x = x_offset + idx * key_width
                    key_rect = QRectF(x, y_offset, key_width, key_height)
                    label = midi_to_name(n)
                    text_height = metrics.height()
                    top = key_rect.bottom() - text_height - 3
                    label_rect = QRectF(
                        key_rect.left() + 1,
                        max(key_rect.top(), top),
                        max(0.0, key_rect.width() - 2),
                        text_height + 2,
                    )
                    painter.drawText(
                        label_rect,
                        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                        label,
                    )

        # Teclas negras
        black_height = key_height * 0.6
        black_width = key_width * 0.6

        for n in range(self.start_note, self.end_note + 1):
            if is_white(n):
                continue
            idx = note_to_white_index[n]
            x = x_offset + idx * key_width + key_width - black_width / 2
            key_rect = QRectF(x, y_offset, black_width, black_height)

            if n in self.pressed_notes:
                painter.setBrush(QBrush(self._pressed_color_for(n, True)))
            elif n in self.sustained_notes:
                painter.setBrush(QBrush(self._sustain_color_for(n, True)))
            else:
                painter.setBrush(QBrush(Qt.GlobalColor.black))
            painter.setPen(QPen(Qt.GlobalColor.black))
            painter.drawRect(key_rect)
            fade_color = self._released_fade_color_for(n, True)
            if fade_color is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(fade_color))
                painter.drawRect(key_rect.adjusted(1.0, 1.0, -1.0, -1.0))
                painter.setPen(QPen(Qt.GlobalColor.black))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(key_rect)

        # Superposiciones de acordes y escalas (visualización) en teclas negras
        if self.display_chord_notes or self.display_scale_notes:
            chord_notes = self.display_chord_notes
            scale_notes = self.display_scale_notes
            scale_circle_platform_scale = WINDOWS_SCALE_CIRCLE_SCALE * LEGACY_QT_MAC_SCALE_CIRCLE_SCALE

            for n in range(self.start_note, self.end_note + 1):
                if is_white(n):
                    continue
                idx = note_to_white_index[n]
                x = x_offset + idx * key_width + key_width - black_width / 2
                key_rect = QRectF(x, y_offset, black_width, black_height)
                if n in chord_notes:
                    painter.setBrush(QBrush(chord_notes[n]))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(key_rect)
                if n in scale_notes:
                    color = scale_notes[n]
                    radius = (
                        max(2.5, min(black_width, black_height) * 0.2 * scale_circle_platform_scale)
                        * self.scale_circle_size_factor
                    )
                    center = QPointF(key_rect.center().x(), key_rect.bottom() - radius * 1.6)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(center, radius, radius)

        # Etiquetas de intervalos para notas activas
        if self.show_keyboard_labels and self.interval_labels:
            settings = self.interval_label_settings or {}
            label_font = QFont(settings.get("font_family") or UI_FONT_FAMILY)
            label_font.setPointSize(self._interval_label_font_size(key_width, key_height, False))
            painter.setFont(label_font)
            metrics = painter.fontMetrics()

            # Teclas blancas
            for n in white_notes:
                label = self.interval_labels.get(n)
                if not label:
                    continue
                idx = note_to_white_index[n]
                x = x_offset + idx * key_width
                key_rect = QRectF(x, y_offset, key_width, key_height)
                text_color = self._interval_pen_color(False)
                label_zone = self._interval_label_zone(
                    key_rect, key_height, label, metrics, False
                )
                self._draw_interval_frame(painter, label_zone)
                painter.setPen(QPen(text_color))
                painter.drawText(label_zone, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)

            # Teclas negras
            label_font.setPointSize(self._interval_label_font_size(black_width, black_height, True))
            painter.setFont(label_font)
            metrics = painter.fontMetrics()
            for n in range(self.start_note, self.end_note + 1):
                if is_white(n):
                    continue
                label = self.interval_labels.get(n)
                if not label:
                    continue
                idx = note_to_white_index[n]
                x = x_offset + idx * key_width + key_width - black_width / 2
                key_rect = QRectF(x, y_offset, black_width, black_height)
                text_color = self._interval_pen_color(True)
                label_zone = self._interval_label_zone(
                    key_rect, black_height, label, metrics, True
                )
                self._draw_interval_frame(painter, label_zone)
                painter.setPen(QPen(text_color))
                painter.drawText(label_zone, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)

        self._draw_display_scale_label(painter)

    def _draw_display_scale_label(self, painter: QPainter):
        label = self.display_scale_label.strip()
        if not label:
            return

        painter.save()
        font = QFont(UI_FONT_FAMILY)
        font.setPointSize(max(14, int(max(15, min(26, int(self.height() * 0.085))) * WINDOWS_FONT_SCALE)))
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        margin = 14.0
        padding_x = 12.0
        padding_y = 7.0
        max_width = max(80.0, float(self.width()) - margin * 2)
        text_limit = max(30, int(max_width - padding_x * 2))
        visible_label = metrics.elidedText(
            label,
            Qt.TextElideMode.ElideRight,
            text_limit,
        )
        text_width = metrics.horizontalAdvance(visible_label)
        rect = QRectF(
            margin,
            margin,
            min(max_width, float(text_width) + padding_x * 2),
            float(metrics.height()) + padding_y * 2,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 190)))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(
            rect.adjusted(padding_x, 0, -padding_x, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            visible_label,
        )
        painter.restore()

    def _interval_label_zone(
        self,
        key_rect: QRectF,
        key_height: float,
        label: str,
        metrics: QFontMetrics,
        is_black_key: bool,
    ) -> QRectF:
        settings = self.interval_label_settings or {}
        zone_height = max(10.0, key_height * 0.25)
        default_mode_key = "y_anchor_mode_black" if is_black_key else "y_anchor_mode_white"
        default_percent_key = "y_percent_black" if is_black_key else "y_percent_white"
        mode = settings.get(default_mode_key, "bottom25")
        percent = float(settings.get(default_percent_key, 87.5))

        text_width = max(0.0, metrics.horizontalAdvance(label))
        zone_width = max(key_rect.width(), text_width + 6)
        zone_width = min(zone_width, float(self.width()))

        if mode == "top":
            center_y = key_rect.top() + zone_height / 2
        elif mode == "center":
            center_y = key_rect.top() + key_height / 2
        elif mode == "bottom":
            center_y = key_rect.bottom() - zone_height / 2
        elif mode == "custom":
            percent = max(0.0, min(100.0, percent))
            center_y = key_rect.top() + key_height * (percent / 100.0)
        else:  # bottom25 por defecto
            center_y = key_rect.top() + key_height * 0.875

        top = max(key_rect.top(), min(center_y - zone_height / 2, key_rect.bottom() - zone_height))

        left = key_rect.center().x() - zone_width / 2
        left = max(0.0, min(left, float(self.width()) - zone_width))

        return QRectF(left, top, zone_width, zone_height)

    def _interval_pen_color(self, is_black_key: bool) -> QColor:
        key = "color_black" if is_black_key else "color_white"
        chosen = self.interval_label_settings.get(key)
        if chosen is None:
            chosen = QColor(Qt.GlobalColor.black)
        if isinstance(chosen, str):
            chosen = QColor(chosen)
        if not isinstance(chosen, QColor) or not chosen.isValid():
            chosen = QColor(Qt.GlobalColor.black)
        return chosen

    def _keyboard_label_font_size(self, key_width: float, key_height: float) -> int:
        size = min(key_width * 0.22, key_height * 0.042)
        size *= WINDOWS_FONT_SCALE
        return max(5, int(size))

    def _interval_label_font_size(self, key_width: float, key_height: float, is_black_key: bool = False) -> int:
        settings = self.interval_label_settings or {}
        base_size = float(settings.get("font_size", 14)) * 0.88 * WINDOWS_FONT_SCALE
        black_key_scale = 0.78 if is_black_key else 1.0
        base_size *= black_key_scale
        max_size = min(key_width * (0.60 if is_black_key else 0.68), key_height * (0.18 if is_black_key else 0.21))
        size = min(base_size, max_size)
        return max(5, int(size))

    def _draw_interval_frame(self, painter: QPainter, rect: QRectF):
        settings = self.interval_label_settings or {}
        fill = settings.get("frame_fill_color", QColor(255, 255, 255))
        if isinstance(fill, str):
            fill = QColor(fill)
        if not isinstance(fill, QColor) or not fill.isValid():
            fill = QColor(255, 255, 255)

        opacity = float(settings.get("frame_fill_opacity", 0.6))
        opacity = max(0.0, min(1.0, opacity))
        fill = QColor(fill)
        fill.setAlphaF(opacity)

        border = settings.get("frame_border_color", QColor(0, 0, 0, 180))
        if isinstance(border, str):
            border = QColor(border)
        if not isinstance(border, QColor) or not border.isValid():
            border = QColor(0, 0, 0, 180)

        width = float(settings.get("frame_border_width", 1.0))
        width = max(0.0, width)

        painter.save()
        painter.setPen(QPen(border, width))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        painter.restore()


class PianoWindow(QMainWindow):
    """Ventana que muestra el teclado y puede alojar una vista combinada."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("MIDI Piano - Teclado")

        self.piano = PianoWidget()
        self.setCentralWidget(self.piano)

        self.fretboard: Optional[QWidget] = None
        self.instrument_stack: Optional[QStackedWidget] = None
        self.instrument_view = "piano"
        self._combined_container: Optional[QWidget] = None
        self._combined_background = QColor(Qt.GlobalColor.white)
        self.on_double_click = None
        self._drag_filter = WindowDragFilter(self)
        self._install_drag_support(self.piano)
        self._apply_frameless(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.resize(900, 220)

    def set_fretboard_widget(self, widget: QWidget) -> None:
        self.fretboard = widget
        self.fretboard.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_instrument_view(self, mode: str) -> None:
        if mode not in ("piano", "guitar"):
            return
        if mode == "guitar" and self.fretboard is None:
            mode = "piano"
        self.instrument_view = mode
        target = self.fretboard if mode == "guitar" else self.piano
        if target is None:
            return

        if self.instrument_stack is not None:
            self.instrument_stack.setCurrentWidget(target)
        elif self._combined_container is None and self.centralWidget() is not target:
            current = self.takeCentralWidget()
            if current is not None:
                current.setParent(None)
            self.setCentralWidget(target)

        if self._combined_container is None:
            self.setWindowTitle(
                "MIDI Piano - Diapasón" if mode == "guitar" else "MIDI Piano - Teclado"
            )

    def _release_instrument_stack(self) -> None:
        if self.instrument_stack is None:
            return
        for widget in (self.piano, self.fretboard):
            if widget is not None:
                self.instrument_stack.removeWidget(widget)
                widget.setParent(None)
        self.instrument_stack.setParent(None)
        self.instrument_stack.deleteLater()
        self.instrument_stack = None

    def _apply_frameless(self, enabled: bool) -> None:
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.FramelessWindowHint
        else:
            flags &= ~Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, enabled)
        self.setAutoFillBackground(not enabled)

        if enabled:
            self.setContentsMargins(0, 0, 0, 0)
        else:
            self.setContentsMargins(8, 8, 8, 8)

        if self.isVisible():
            self.show()

    def _install_drag_support(self, root: QWidget) -> None:
        root.installEventFilter(self._drag_filter)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self._drag_filter)

    def _remove_drag_support(self, root: QWidget) -> None:
        root.removeEventFilter(self._drag_filter)
        for child in root.findChildren(QWidget):
            child.removeEventFilter(self._drag_filter)

    def show_keyboard_only(self) -> None:
        if self.centralWidget() is self._combined_container:
            self.takeCentralWidget()
        self._release_instrument_stack()
        if self._combined_container is not None:
            self._combined_container.setParent(None)
            self._combined_container.deleteLater()
            self._combined_container = None

        target = self.fretboard if self.instrument_view == "guitar" else self.piano
        if target is None:
            target = self.piano
        if self.centralWidget() is not target:
            current = self.takeCentralWidget()
            if current is not None:
                current.setParent(None)
            self.setCentralWidget(target)

        self.setWindowTitle(
            "MIDI Piano - Diapasón" if self.instrument_view == "guitar" else "MIDI Piano - Teclado"
        )
        self._install_drag_support(target)
        self._apply_frameless(True)

    def set_combined_background_color(self, color: QColor) -> None:
        if not color.isValid():
            return
        self._combined_background = QColor(color)
        if self._combined_container is not None:
            self._combined_container.setStyleSheet(f"background: {color.name()};")

    def show_combined_view(
        self,
        chord_widget: QWidget,
        display_panel: Optional[QWidget],
        keyboard_nav_panel: Optional[QWidget] = None,
        fretboard_widget: Optional[QWidget] = None,
    ) -> None:
        if fretboard_widget is not None:
            self.set_fretboard_widget(fretboard_widget)
        if self.centralWidget() is self._combined_container:
            self.takeCentralWidget()
        self._release_instrument_stack()
        if self._combined_container is not None:
            self._combined_container.setParent(None)
            self._combined_container.deleteLater()
            self._combined_container = None

        if self.centralWidget() in (self.piano, self.fretboard):
            current = self.takeCentralWidget()
            if current is not None:
                current.setParent(None)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if display_panel is not None:
            layout.addWidget(display_panel)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        chord_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        top_layout.addWidget(chord_widget, stretch=1)

        self.piano.setMinimumHeight(220)
        if self.fretboard is not None:
            self.fretboard.setMinimumHeight(220)
        self.instrument_stack = QStackedWidget(container)
        self.instrument_stack.setObjectName("InstrumentStack")
        self.instrument_stack.addWidget(self.piano)
        if self.fretboard is not None:
            self.instrument_stack.addWidget(self.fretboard)
        layout.addLayout(top_layout, stretch=2)
        layout.addWidget(self.instrument_stack, stretch=3)
        if keyboard_nav_panel is not None:
            layout.addWidget(keyboard_nav_panel)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self._combined_container = container
        self._install_drag_support(container)
        container.setStyleSheet(f"background: {self._combined_background.name()}; border: none;")
        self.set_instrument_view(self.instrument_view)

        self.setWindowTitle("MIDI Piano — Vista única")
        self._apply_frameless(False)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and callable(self.on_double_click):
            self.on_double_click()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)




class ChordDisplayWidget(QWidget):
    """Widget reutilizable para mostrar el cifrado de acordes."""

    def __init__(self):
        super().__init__()
        self.background_color = QColor(0, 0, 0)
        self._font_family = UI_FONT_FAMILY
        self._requested_font_size = 80

        self.main_label = QLabel("")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_label.setStyleSheet("background: transparent;")
        self.main_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.main_label.setMinimumWidth(0)
        self.main_label.setTextFormat(Qt.TextFormat.PlainText)
        self.main_label.setWordWrap(False)

        self.alt_label = QLabel("")
        self.alt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alt_label.setStyleSheet("color: #ffffff; background: transparent;")
        self.alt_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.alt_label.setMinimumWidth(0)
        self.alt_label.setContentsMargins(0, 0, 0, 0)
        self.alt_label.setWordWrap(False)
        self.alt_label.setTextFormat(Qt.TextFormat.PlainText)
        self.alt_label.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 4, 24, 8)
        layout.setSpacing(0)
        layout.addWidget(self.main_label, stretch=3)
        layout.addWidget(self.alt_label, stretch=1)
        self.setLayout(layout)

        self.set_font_from_family_size(UI_FONT_FAMILY, 80)
        self.set_chord_color(QColor(Qt.GlobalColor.white))
        self.set_background_color(self.background_color)

    def set_font_from_family_size(self, family: str, size: int):
        """Actualiza la fuente del cifrado principal y alternativo."""
        self._font_family = family or UI_FONT_FAMILY
        self._requested_font_size = int(size)
        self._apply_responsive_fonts()

    def _fit_font_size(
        self,
        text: str,
        desired_size: int,
        min_size: int,
        max_width: int,
        max_height: int,
        weight: QFont.Weight,
    ) -> int:
        size = max(min_size, int(desired_size))
        lines = [line for line in (text or "G13sus4").splitlines() if line.strip()]
        if not lines:
            lines = ["G13sus4"]
        while size > min_size:
            font = QFont(self._font_family, size)
            font.setWeight(weight)
            metrics = QFontMetrics(font)
            text_width = max(metrics.horizontalAdvance(line) for line in lines)
            text_height = metrics.lineSpacing() * len(lines)
            if text_width <= max_width and text_height <= max_height:
                return size
            size -= 1
        return size

    def _apply_responsive_fonts(self):
        size = int(self._requested_font_size)
        family = self._font_family or UI_FONT_FAMILY
        chord_scale = 0.72 if IS_WINDOWS else 1.0
        available_width = max(160, self.width() - 48)
        available_height = max(70, self.height() - 12)
        has_alternatives = bool(self.alt_label.text().strip())
        main_width_limit = available_width
        alt_width_limit = available_width
        main_height_limit = int(available_height * (0.72 if has_alternatives else 0.94))
        alt_height_limit = max(28, int(available_height * 0.27))

        self.main_label.setMaximumWidth(main_width_limit)

        main_desired = min(
            int(size * 1.75 * chord_scale),
            int(available_height * (0.66 if has_alternatives else 0.82)),
        )
        main_size = self._fit_font_size(
            self.main_label.text(),
            main_desired,
            10,
            main_width_limit,
            main_height_limit,
            QFont.Weight.Medium,
        )
        main_font = QFont(family, main_size)
        main_font.setWeight(QFont.Weight.Medium)
        self.main_label.setFont(main_font)

        alt_text = self.alt_label.text()
        alt_desired = min(
            int(size * 0.50 * chord_scale),
            int(available_height * 0.22),
        )
        alt_size = self._fit_font_size(
            alt_text,
            alt_desired,
            10,
            alt_width_limit,
            alt_height_limit,
            QFont.Weight.Normal,
        )
        alt_font = QFont(family, alt_size)
        alt_font.setWeight(QFont.Weight.Normal)
        self.alt_label.setFont(alt_font)
        metrics = QFontMetrics(alt_font)
        alt_height = metrics.lineSpacing() + metrics.descent() + 6
        self.alt_label.setMinimumHeight(alt_height)
        self.alt_label.setMaximumHeight(min(alt_height_limit, max(28, alt_height)))

    def resizeEvent(self, event):
        self._apply_responsive_fonts()
        super().resizeEvent(event)

    def set_chord_color(self, color: QColor):
        if not color.isValid():
            return
        stylesheet = f"color: {color.name()};"
        self.main_label.setStyleSheet(stylesheet)
        self.alt_label.setStyleSheet(stylesheet)

    def set_background_color(self, color: QColor):
        if not color.isValid():
            return
        self.background_color = color
        self.setStyleSheet(f"background: {color.name()};")

    def update_chord(self, notas):
        info = analizar_cifrado_alternativos(notas)
        principal = info.get("principal") or ""
        alternativos = info.get("alternativos") or []

        if not principal:
            self.main_label.setText(live_note_or_interval_label(notas))
            self.alt_label.setText("")
            self.alt_label.hide()
            self._apply_responsive_fonts()
            return info

        self.main_label.setText(principal)

        if alternativos:
            self.alt_label.setText(self._format_alternative_chords(alternativos))
            self.alt_label.show()
        else:
            self.alt_label.setText("")
            self.alt_label.hide()
        self._apply_responsive_fonts()

        return info

    def _format_alternative_chords(self, alternatives: List[str]) -> str:
        cleaned = [str(item).strip() for item in alternatives if str(item).strip()]
        return "   ".join(cleaned)


class ChordWindow(QMainWindow):
    """Ventana que muestra el cifrado de acordes detectados en vivo."""

    def __init__(self):
        super().__init__()

        # Ventana sin marco
        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        self.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("background: #000000;")

        self.setWindowTitle("MIDI Piano Jaramillo — Acordes")

        self._drag_offset: Optional[QPoint] = None
        self._drag_filter = WindowDragFilter(self)

        self.display_widget = ChordDisplayWidget()
        self.setCentralWidget(self.display_widget)
        self._install_drag_support(self.display_widget)

        self.resize(740, 200)

    def _install_drag_support(self, root: QWidget) -> None:
        root.installEventFilter(self._drag_filter)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self._drag_filter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_top_left = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_top_left)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def set_font_from_family_size(self, family: str, size: int):
        self.display_widget.set_font_from_family_size(family, size)

    def set_chord_color(self, color: QColor):
        self.display_widget.set_chord_color(color)

    def set_text_color(self, color: QColor):
        """Alias de compatibilidad para código legado."""
        self.set_chord_color(color)

    def set_background_color(self, color: QColor):
        self.display_widget.set_background_color(color)

    def update_chord(self, notas):
        return self.display_widget.update_chord(notas)


class FretboardWidget(QWidget):
    """Diapasón de guitarra que refleja las alturas MIDI activas."""

    IMAGE_WIDTH = 1672.0
    IMAGE_HEIGHT = 941.0
    EMBEDDED_SOURCE_TOP = 270.0
    EMBEDDED_SOURCE_HEIGHT = 410.0
    STRING_Y = (352.0, 397.0, 444.0, 493.0, 543.0, 586.0)
    OPEN_STRING_X = 42.0
    FRET_EDGES = (
        88.0,
        256.0,
        405.0,
        537.0,
        657.0,
        765.0,
        867.0,
        962.0,
        1050.0,
        1136.0,
        1217.0,
        1294.0,
        1368.0,
        1438.0,
        1505.0,
        1570.0,
        1630.0,
    )
    # Orden visual de arriba a abajo: E4, B3, G3, D3, A2, E2.
    OPEN_STRING_MIDI = (64, 59, 55, 50, 45, 40)
    NOTE_COLOR = QColor(240, 154, 0)
    ROOT_COLOR = QColor(52, 199, 89)
    MIN_POSITION = 1
    MAX_POSITION = 13

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notes: Set[int] = set()
        self.chord_info: Dict[str, object] = {}
        self.note_order: List[int] = []
        self.display_chord_notes: Dict[int, QColor] = {}
        self.display_scale_notes: Dict[int, QColor] = {}
        self.display_interval_labels: Dict[int, str] = {}
        self.display_root_pc: Optional[int] = None
        self.display_root_label = ""
        self.embedded_mode = False
        self.current_position = self.MIN_POSITION
        self.display_assignment: List[Tuple[int, int, int, float, float, bool]] = []
        self.partial_assignment = False
        self._position_initialized = False
        self._register_anchor: Optional[float] = None
        image_path = Path(__file__).resolve().parent / "assets" / "fretboard-background.png"
        self.background = QPixmap(str(image_path))
        self.setMinimumSize(640, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #050505;")

    def set_embedded_mode(self, enabled: bool) -> None:
        self.embedded_mode = bool(enabled)
        self.update()

    @classmethod
    def fret_center(cls, fret: int) -> float:
        if fret <= 0:
            return cls.OPEN_STRING_X
        if fret >= len(cls.FRET_EDGES):
            fret = len(cls.FRET_EDGES) - 1
        return (cls.FRET_EDGES[fret - 1] + cls.FRET_EDGES[fret]) / 2.0

    @classmethod
    def positions_for_notes(cls, notes: Set[int]) -> List[Tuple[int, int, int, float, float]]:
        positions: List[Tuple[int, int, int, float, float]] = []
        max_fret = len(cls.FRET_EDGES) - 1
        for note in sorted({int(value) for value in notes}):
            for string_index, open_note in enumerate(cls.OPEN_STRING_MIDI):
                fret = note - open_note
                if 0 <= fret <= max_fret:
                    positions.append(
                        (note, string_index, fret, cls.fret_center(fret), cls.STRING_Y[string_index])
                    )
        return positions

    @classmethod
    def _candidates_for_note(
        cls,
        note: int,
        position: int,
    ) -> List[Tuple[int, int, float, float]]:
        playable = [
            (string_index, fret, x, y)
            for candidate_note, string_index, fret, x, y in cls.positions_for_notes({note})
            if candidate_note == note
        ]
        lower_fret = max(0, int(position) - 1)
        upper_fret = min(len(cls.FRET_EDGES) - 1, int(position) + 4)
        in_window = [
            candidate
            for candidate in playable
            if lower_fret <= candidate[1] <= upper_fret
        ]
        if in_window:
            return in_window

        # Una cuerda al aire sigue disponible en posiciones altas cuando esa
        # altura no existe dentro de la ventana activa.
        return [candidate for candidate in playable if candidate[1] == 0]

    @classmethod
    def _pitch_class_candidates_for_position(
        cls,
        pitch_class: int,
        position: int,
    ) -> List[Tuple[int, int, int, float, float]]:
        lower_fret = max(0, int(position) - 1)
        upper_fret = min(len(cls.FRET_EDGES) - 1, int(position) + 4)
        candidates: List[Tuple[int, int, int, float, float]] = []
        open_candidates: List[Tuple[int, int, int, float, float]] = []
        for string_index, open_note in enumerate(cls.OPEN_STRING_MIDI):
            for fret in range(0, len(cls.FRET_EDGES)):
                note = open_note + fret
                if note % 12 != int(pitch_class) % 12:
                    continue
                candidate = (
                    note,
                    string_index,
                    fret,
                    cls.fret_center(fret),
                    cls.STRING_Y[string_index],
                )
                if lower_fret <= fret <= upper_fret:
                    candidates.append(candidate)
                elif fret == 0:
                    open_candidates.append(candidate)
        return candidates or open_candidates

    @staticmethod
    def _string_continuity_penalties(string_indexes: Set[int]) -> Tuple[int, int]:
        string_numbers = sorted({int(index) + 1 for index in string_indexes})
        high_string_skip = 0
        gap_penalty = 0
        for first, second in zip(string_numbers, string_numbers[1:]):
            gap = second - first - 1
            if gap <= 0:
                continue
            if (first, second) == (4, 6):
                continue
            if (first, second) == (1, 3):
                high_string_skip += 1
            gap_penalty += gap
        return high_string_skip, gap_penalty

    @classmethod
    def guitar_scale_notes(cls, root_pc: int, steps: List[int]) -> List[int]:
        if not steps:
            return []
        scale_span = sum(int(step) for step in steps[:-1])
        highest_playable = max(cls.OPEN_STRING_MIDI) + len(cls.FRET_EDGES) - 1
        lowest_playable = min(cls.OPEN_STRING_MIDI)
        best_notes: List[int] = []
        best_score: Optional[Tuple[int, int, int]] = None

        for root_note in range(
            lowest_playable,
            highest_playable - scale_span + 1,
        ):
            if root_note % 12 != int(root_pc) % 12:
                continue
            notes = [root_note]
            for step in steps[:-1]:
                notes.append(notes[-1] + int(step))
            assignment = cls.guitar_scale_assignment(set(notes))
            if len(assignment["placements"]) != len(notes):
                continue
            score = (
                int(assignment["fret_span"]),
                int(assignment["position"]),
                root_note,
            )
            if best_score is None or score < best_score:
                best_score = score
                best_notes = notes

        return best_notes

    @classmethod
    def guitar_scale_assignment(cls, notes: Set[int]) -> Dict[str, object]:
        ordered_notes = sorted({int(note) for note in notes})
        if not ordered_notes:
            return {
                "placements": [],
                "position": cls.MIN_POSITION,
                "fret_span": 0,
            }

        candidates_by_note = []
        for note in ordered_notes:
            candidates = [
                (candidate_note, string_index, fret, x, y)
                for candidate_note, string_index, fret, x, y in cls.positions_for_notes({note})
            ]
            if not candidates:
                return {
                    "placements": [],
                    "position": cls.MIN_POSITION,
                    "fret_span": 0,
                }
            candidates_by_note.append(candidates)

        best_score: Optional[Tuple[int, int, int, int, int]] = None
        best_placements: List[Tuple[int, int, int, float, float]] = []
        for placements in product(*candidates_by_note):
            frets = [placement[2] for placement in placements]
            fret_span = max(frets) - min(frets) + 1
            reversals = sum(
                1
                for current, following in zip(placements, placements[1:])
                if following[1] > current[1]
            )
            string_jumps = sum(
                max(0, abs(following[1] - current[1]) - 1)
                for current, following in zip(placements, placements[1:])
            )
            score = (
                fret_span,
                reversals,
                string_jumps,
                min(frets),
                sum(frets),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_placements = list(placements)

        occupied_strings: Set[int] = set()
        display_placements: List[Tuple[int, int, int, float, float, bool]] = []
        for note, string_index, fret, x, y in best_placements:
            secondary = string_index in occupied_strings
            occupied_strings.add(string_index)
            display_placements.append((note, string_index, fret, x, y, secondary))

        frets = [placement[2] for placement in best_placements]
        first_fret = min(frets) if frets else cls.MIN_POSITION
        position = max(cls.MIN_POSITION, min(cls.MAX_POSITION, first_fret or 1))
        return {
            "placements": display_placements,
            "position": position,
            "fret_span": (max(frets) - min(frets) + 1) if frets else 0,
        }

    @classmethod
    def guitar_voicing_for_pitch_classes(
        cls,
        root_pc: int,
        pitch_classes: Set[int],
        pitch_order_constraints: Optional[List[Tuple[int, int]]] = None,
    ) -> Dict[str, object]:
        pcs = {int(pc) % 12 for pc in pitch_classes}
        pcs.add(int(root_pc) % 12)
        if not pcs or len(pcs) > len(cls.OPEN_STRING_MIDI):
            return {"notes": set(), "position": cls.MIN_POSITION, "placements": []}

        order_constraints = [
            (int(upper_pc) % 12, int(lower_pc) % 12)
            for upper_pc, lower_pc in (pitch_order_constraints or [])
            if int(upper_pc) % 12 != int(lower_pc) % 12
        ]

        best_result: Optional[
            Tuple[
                Tuple[float, ...],
                int,
                List[Tuple[int, int, int, float, float]],
            ]
        ] = None
        root_pc = int(root_pc) % 12

        for position in range(cls.MIN_POSITION, cls.MAX_POSITION + 1):
            candidates_by_pc = {
                pc: cls._pitch_class_candidates_for_position(pc, position)
                for pc in pcs
            }
            if any(not candidates for candidates in candidates_by_pc.values()):
                continue

            ordered_pcs = sorted(
                pcs,
                key=lambda pc: (
                    len(candidates_by_pc[pc]),
                    0 if pc == root_pc else 1,
                    pc,
                ),
            )
            best_for_position: Optional[
                Tuple[
                    Tuple[float, ...],
                    List[Tuple[int, int, int, float, float]],
                ]
            ] = None

            def visit(
                index: int,
                used_strings: Set[int],
                placements: List[Tuple[int, int, int, float, float]],
            ) -> None:
                nonlocal best_for_position
                if index >= len(ordered_pcs):
                    note_by_pitch_class = {
                        candidate[0] % 12: candidate[0]
                        for candidate in placements
                    }
                    if any(
                        upper_pc in note_by_pitch_class
                        and lower_pc in note_by_pitch_class
                        and note_by_pitch_class[upper_pc] <= note_by_pitch_class[lower_pc]
                        for upper_pc, lower_pc in order_constraints
                    ):
                        return
                    lowest_note = min(candidate[0] for candidate in placements)
                    bass_penalty = 0 if lowest_note % 12 == root_pc else 1
                    high_string_skip, gap_penalty = cls._string_continuity_penalties(
                        {candidate[1] for candidate in placements}
                    )
                    crossings = 0
                    for left_index, left in enumerate(placements):
                        for right in placements[left_index + 1:]:
                            if left[1] < right[1] and left[0] < right[0]:
                                crossings += 1
                            elif right[1] < left[1] and right[0] < left[0]:
                                crossings += 1
                    frets = [candidate[2] for candidate in placements]
                    extension_count = sum(
                        1
                        for fret in frets
                        if not position <= fret <= position + 3
                    )
                    fret_span = max(frets) - min(frets)
                    center = float(position) + 1.5
                    center_distance = sum(abs(float(fret) - center) for fret in frets)
                    total_midi = sum(candidate[0] for candidate in placements)
                    score = (
                        bass_penalty,
                        high_string_skip,
                        gap_penalty,
                        crossings,
                        extension_count,
                        center_distance,
                        fret_span,
                        total_midi,
                    )
                    if best_for_position is None or score < best_for_position[0]:
                        best_for_position = (score, list(placements))
                    return

                pitch_class = ordered_pcs[index]
                candidates = sorted(
                    candidates_by_pc[pitch_class],
                    key=lambda candidate: (
                        0 if position <= candidate[2] <= position + 3 else 1,
                        abs(float(candidate[2]) - (float(position) + 1.5)),
                        candidate[0],
                    ),
                )
                for candidate in candidates:
                    string_index = candidate[1]
                    if string_index in used_strings:
                        continue
                    used_strings.add(string_index)
                    placements.append(candidate)
                    visit(index + 1, used_strings, placements)
                    placements.pop()
                    used_strings.remove(string_index)

            visit(0, set(), [])
            if best_for_position is None:
                continue

            position_score, placements = best_for_position
            global_score = (
                position_score[0],
                position_score[1],
                position_score[2],
                position_score[3],
                position_score[4],
                position,
                position_score[5],
                position_score[6],
                position_score[7],
            )
            if best_result is None or global_score < best_result[0]:
                best_result = (global_score, position, placements)

        if best_result is None:
            return {"notes": set(), "position": cls.MIN_POSITION, "placements": []}

        _score, position, placements = best_result
        return {
            "notes": {candidate[0] for candidate in placements},
            "position": position,
            "placements": placements,
        }

    def _priority_notes(self, notes: Set[int], note_order: List[int]) -> List[int]:
        ordered_notes = sorted({int(note) for note in notes})
        if not ordered_notes:
            return []

        root_pc = self._root_pc()
        bass = ordered_notes[0]
        melody = ordered_notes[-1]
        recency = {int(note): index for index, note in enumerate(note_order)}

        def priority(note: int) -> Tuple[int, int, int]:
            interval = (note - root_pc) % 12 if root_pc is not None else None
            role_score = 0
            if note == bass:
                role_score += 10000
            if root_pc is not None and note % 12 == root_pc:
                role_score += 9000
            if note == melody:
                role_score += 8000
            if interval in (3, 4):
                role_score += 7000
            elif interval in (10, 11):
                role_score += 6500
            elif interval == 7:
                role_score += 6000
            elif interval in (1, 2, 5, 6, 8, 9):
                role_score += 5500
            return role_score, recency.get(note, -1), -note

        return sorted(ordered_notes, key=priority, reverse=True)

    def _assignment_for_position(
        self,
        notes: Set[int],
        position: int,
        note_order: List[int],
    ) -> Dict[str, object]:
        priority_notes = self._priority_notes(notes, note_order)
        candidates = {
            note: self._candidates_for_note(note, position)
            for note in priority_notes
        }
        playable_notes = [note for note in priority_notes if candidates[note]]
        missing_notes = {note for note in priority_notes if not candidates[note]}

        # El estado solo necesita recordar qué cuerdas ya tienen una nota
        # principal. Así se maximizan cuerdas distintas sin perder alturas.
        states: Dict[
            int,
            Tuple[Tuple[int, int, float, int], List[Tuple[int, int, int, float, float]]],
        ] = {0: ((0, 0, 0.0, 0), [])}
        core_center = float(position) + 1.5
        for note in playable_notes:
            next_states: Dict[
                int,
                Tuple[Tuple[int, int, float, int], List[Tuple[int, int, int, float, float]]],
            ] = {}
            for used_strings, (cost, placements) in states.items():
                for string_index, fret, x, y in candidates[note]:
                    string_mask = 1 << string_index
                    duplicate = 1 if used_strings & string_mask else 0
                    extension = 0 if position <= fret <= position + 3 else 1
                    distance = abs(float(fret) - core_center)
                    next_cost = (
                        cost[0] + duplicate,
                        cost[1] + extension,
                        cost[2] + distance,
                        cost[3] + fret,
                    )
                    next_mask = used_strings | string_mask
                    next_placements = placements + [(note, string_index, fret, x, y)]
                    previous = next_states.get(next_mask)
                    if previous is None or next_cost < previous[0]:
                        next_states[next_mask] = (next_cost, next_placements)
            states = next_states

        if not states:
            best_cost: Tuple[int, int, float, int] = (0, 0, 0.0, 0)
            raw_placements: List[Tuple[int, int, int, float, float]] = []
        else:
            best_cost, raw_placements = min(
                states.values(),
                key=lambda value: (
                    value[0][0],
                    *self._string_continuity_penalties(
                        {placement[1] for placement in value[1]}
                    ),
                    value[0][1],
                    value[0][2],
                    value[0][3],
                ),
            )

        high_string_skip, gap_penalty = self._string_continuity_penalties(
            {placement[1] for placement in raw_placements}
        )

        occupied_strings: Set[int] = set()
        placements: List[Tuple[int, int, int, float, float, bool]] = []
        for note, string_index, fret, x, y in raw_placements:
            secondary = string_index in occupied_strings
            occupied_strings.add(string_index)
            placements.append((note, string_index, fret, x, y, secondary))

        return {
            "position": position,
            "placements": placements,
            "assigned_count": len(placements),
            "duplicate_count": best_cost[0],
            "high_string_skip": high_string_skip,
            "gap_penalty": gap_penalty,
            "extension_count": best_cost[1],
            "missing_notes": missing_notes,
        }

    def _choose_position(self, notes: Set[int], note_order: List[int]) -> Dict[str, object]:
        results = {
            position: self._assignment_for_position(notes, position, note_order)
            for position in range(self.MIN_POSITION, self.MAX_POSITION + 1)
        }
        best_assigned = max(int(result["assigned_count"]) for result in results.values())
        best_duplicates = min(
            int(result["duplicate_count"])
            for result in results.values()
            if int(result["assigned_count"]) == best_assigned
        )
        best_high_string_skip = min(
            int(result["high_string_skip"])
            for result in results.values()
            if int(result["assigned_count"]) == best_assigned
            and int(result["duplicate_count"]) == best_duplicates
        )
        best_gap_penalty = min(
            int(result["gap_penalty"])
            for result in results.values()
            if int(result["assigned_count"]) == best_assigned
            and int(result["duplicate_count"]) == best_duplicates
            and int(result["high_string_skip"]) == best_high_string_skip
        )
        eligible = [
            position
            for position, result in results.items()
            if int(result["assigned_count"]) == best_assigned
            and int(result["duplicate_count"]) == best_duplicates
            and int(result["high_string_skip"]) == best_high_string_skip
            and int(result["gap_penalty"]) == best_gap_penalty
        ]

        if self._position_initialized and self.current_position in eligible:
            chosen_position = self.current_position
        elif not self._position_initialized:
            chosen_position = min(eligible)
        else:
            register = sum(notes) / max(1, len(notes))
            anchor = self._register_anchor if self._register_anchor is not None else register
            if register > anchor:
                higher = [position for position in eligible if position > self.current_position]
                chosen_position = min(higher) if higher else min(
                    eligible,
                    key=lambda position: (abs(position - self.current_position), position),
                )
            elif register < anchor:
                lower = [position for position in eligible if position < self.current_position]
                chosen_position = max(lower) if lower else min(
                    eligible,
                    key=lambda position: (abs(position - self.current_position), position),
                )
            else:
                chosen_position = min(
                    eligible,
                    key=lambda position: (abs(position - self.current_position), position),
                )

        self.current_position = chosen_position
        self._position_initialized = True
        self._register_anchor = sum(notes) / max(1, len(notes))
        return results[chosen_position]

    def set_notes(
        self,
        notes: Set[int],
        chord_info: Optional[Dict[str, object]] = None,
        note_order: Optional[List[int]] = None,
    ) -> None:
        self.notes = {int(note) for note in notes}
        self.chord_info = dict(chord_info or {})
        self.note_order = [
            int(note)
            for note in (note_order or [])
            if int(note) in self.notes
        ]
        for note in sorted(self.notes):
            if note not in self.note_order:
                self.note_order.append(note)

        if not self.notes:
            self._reset_position()
        self._refresh_assignment()
        self.update()

    def set_display_overlays(
        self,
        chord_notes: Dict[int, QColor],
        scale_notes: Dict[int, QColor],
        interval_labels: Optional[Dict[int, str]] = None,
        root_pc: Optional[int] = None,
        root_label: str = "",
    ) -> None:
        self.display_chord_notes = {
            int(note): QColor(color) for note, color in chord_notes.items()
        }
        self.display_scale_notes = {
            int(note): QColor(color) for note, color in scale_notes.items()
        }
        self.display_interval_labels = {
            int(note): str(label)
            for note, label in (interval_labels or {}).items()
            if str(label).strip()
        }
        self.display_root_pc = int(root_pc) % 12 if root_pc is not None else None
        self.display_root_label = str(root_label or "").strip()
        self._reset_position()
        self._refresh_assignment()
        self.update()

    def _visual_notes(self) -> Set[int]:
        return (
            set(self.notes)
            | set(self.display_chord_notes)
            | set(self.display_scale_notes)
        )

    def _reset_position(self) -> None:
        self.current_position = self.MIN_POSITION
        self._position_initialized = False
        self._register_anchor = None

    def _refresh_assignment(self) -> None:
        visual_notes = self._visual_notes()
        if not visual_notes:
            self.display_assignment = []
            self.partial_assignment = False
            return

        if (
            self.display_scale_notes
            and not self.notes
            and not self.display_chord_notes
        ):
            scale_assignment = self.guitar_scale_assignment(
                set(self.display_scale_notes)
            )
            self.display_assignment = list(scale_assignment["placements"])
            self.current_position = int(scale_assignment["position"])
            self._position_initialized = True
            self.partial_assignment = len(self.display_assignment) < len(visual_notes)
            return

        visual_order = list(self.note_order)
        for note in sorted(visual_notes):
            if note not in visual_order:
                visual_order.append(note)
        assignment = self._choose_position(visual_notes, visual_order)
        self.display_assignment = list(assignment["placements"])
        self.partial_assignment = len(self.display_assignment) < len(visual_notes)

    def _root_pc(self) -> Optional[int]:
        principal_match = self.chord_info.get("principal_match")
        if isinstance(principal_match, dict) and isinstance(principal_match.get("root"), int):
            return int(principal_match["root"]) % 12
        if self.notes:
            return min(self.notes) % 12
        if self.display_root_pc is not None:
            return self.display_root_pc
        return None

    def _note_label(self, note: int) -> str:
        pitch_class = int(note) % 12
        custom_map = self.chord_info.get("custom_spelling_map")
        if isinstance(custom_map, dict):
            custom_label = custom_map.get(pitch_class)
            if isinstance(custom_label, str) and custom_label.strip():
                return self._display_accidentals(custom_label.strip())

        principal = str(self.chord_info.get("principal") or "")
        principal_match = self.chord_info.get("principal_match")
        if isinstance(principal_match, dict):
            root_pc = principal_match.get("root")
            chord_name = str(principal_match.get("nombre") or "")
            root_letter, _accidental = _parse_root_spelling(principal)
            if root_letter is not None and isinstance(root_pc, int):
                interval = (pitch_class - int(root_pc)) % 12
                return self._display_accidentals(
                    spell_note_for_interval(root_letter, int(root_pc), chord_name, interval)
                )

        return self._display_accidentals(DETECT_NOTE_NAMES[pitch_class])

    def _marker_label(self, note: int) -> str:
        if note in self.notes:
            return self._note_label(note)
        interval_label = self.display_interval_labels.get(note)
        if interval_label:
            return self._display_accidentals(interval_label)
        return self._display_accidentals(DETECT_NOTE_NAMES[int(note) % 12])

    def _marker_color(self, note: int, root_pc: Optional[int]) -> QColor:
        if note in self.notes:
            if root_pc is not None and note % 12 == root_pc:
                return QColor(self.ROOT_COLOR)
            return QColor(self.NOTE_COLOR)
        if note in self.display_chord_notes:
            return QColor(self.display_chord_notes[note])
        if note in self.display_scale_notes:
            return QColor(self.display_scale_notes[note])
        return QColor(self.NOTE_COLOR)

    def _marker_opacity(self, note: int, secondary: bool) -> float:
        if not secondary or note in self.display_scale_notes:
            return 1.0
        return 0.24

    @staticmethod
    def _display_accidentals(label: str) -> str:
        return str(label).replace("#", "♯").replace("b", "♭")

    def _chord_texts(self) -> Tuple[str, str]:
        principal = str(self.chord_info.get("principal") or "")
        if not principal:
            principal = live_note_or_interval_label(self.notes)

        alternatives = [
            str(value).strip()
            for value in (self.chord_info.get("alternativos") or [])
            if str(value).strip()
        ]
        if len(alternatives) <= 2:
            alternate_text = " ".join(alternatives)
        else:
            midpoint = (len(alternatives) + 1) // 2
            alternate_text = " ".join(alternatives[:midpoint]) + "\n" + " ".join(alternatives[midpoint:])
        return principal, alternate_text

    @staticmethod
    def _fit_pixel_font(
        text: str,
        family: str,
        maximum: int,
        minimum: int,
        max_width: float,
        max_height: float,
        weight: QFont.Weight,
    ) -> QFont:
        lines = [line for line in str(text).splitlines() if line] or [" "]
        for pixel_size in range(maximum, minimum - 1, -1):
            font = QFont(family)
            font.setPixelSize(pixel_size)
            font.setWeight(weight)
            metrics = QFontMetricsF(font)
            width = max(metrics.horizontalAdvance(line) for line in lines)
            height = metrics.lineSpacing() * len(lines)
            if width <= max_width and height <= max_height:
                return font
        font = QFont(family)
        font.setPixelSize(minimum)
        font.setWeight(weight)
        return font

    def _embedded_map_point(self, x: float, y: float) -> QPointF:
        x_scale = max(1.0, float(self.width())) / self.IMAGE_WIDTH
        y_scale = max(1.0, float(self.height())) / self.EMBEDDED_SOURCE_HEIGHT
        return QPointF(
            float(x) * x_scale,
            (float(y) - self.EMBEDDED_SOURCE_TOP) * y_scale,
        )

    def _embedded_map_rect(self, rect: QRectF) -> QRectF:
        top_left = self._embedded_map_point(rect.left(), rect.top())
        bottom_right = self._embedded_map_point(rect.right(), rect.bottom())
        return QRectF(top_left, bottom_right).normalized()

    def _embedded_marker_radius(self) -> float:
        string_positions = [
            self._embedded_map_point(0.0, string_y).y()
            for string_y in self.STRING_Y
        ]
        minimum_spacing = min(
            abs(second - first)
            for first, second in zip(string_positions, string_positions[1:])
        )
        return max(6.0, minimum_spacing / 2.0)

    @staticmethod
    def _marker_radius_for_note(_note: int, string_radius: float) -> float:
        return float(string_radius)

    def _paint_embedded_fretboard(self, painter: QPainter) -> None:
        target_rect = QRectF(self.rect())
        source_rect = QRectF(
            0.0,
            self.EMBEDDED_SOURCE_TOP,
            self.IMAGE_WIDTH,
            self.EMBEDDED_SOURCE_HEIGHT,
        )
        if not self.background.isNull():
            painter.drawPixmap(target_rect, self.background, source_rect)

        fret_font = QFont(UI_FONT_FAMILY)
        fret_font.setPixelSize(max(10, min(18, int(self.height() * 0.065))))
        fret_font.setWeight(QFont.Weight.Medium)
        painter.setFont(fret_font)
        painter.setPen(QColor(244, 239, 231, 190))
        for fret in range(len(self.FRET_EDGES)):
            label_rect = self._embedded_map_rect(
                QRectF(self.fret_center(fret) - 30.0, 292.0, 60.0, 42.0)
            )
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, str(fret))

        meta_font = QFont(UI_FONT_FAMILY)
        meta_font.setPixelSize(max(10, min(17, int(self.height() * 0.06))))
        meta_font.setWeight(QFont.Weight.Medium)
        painter.setFont(meta_font)
        painter.setPen(QColor(244, 239, 231, 185))
        painter.drawText(
            self._embedded_map_rect(QRectF(1260.0, 632.0, 330.0, 34.0)),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Posición {self.current_position}",
        )

        if self.partial_assignment:
            painter.setPen(QColor(240, 154, 0, 220))
            painter.drawText(
                self._embedded_map_rect(QRectF(70.0, 632.0, 410.0, 30.0)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Fuera del diapasón",
            )

        root_pc = self._root_pc()
        marker_radius = self._embedded_marker_radius()
        for note, _string_index, _fret, x, y, secondary in self.display_assignment:
            painter.save()
            painter.setOpacity(self._marker_opacity(note, secondary))
            note_radius = self._marker_radius_for_note(note, marker_radius)

            center = self._embedded_map_point(x, y)
            fill = self._marker_color(note, root_pc)
            painter.setBrush(QBrush(fill))
            outline = QColor(255, 255, 255, 225)
            outline_width = 2.0
            if note in self.display_chord_notes and note in self.display_scale_notes:
                outline = QColor(self.display_scale_notes[note])
                outline.setAlpha(245)
                outline_width = 4.0
            outline_pen = QPen(outline, outline_width)
            outline_pen.setCosmetic(True)
            painter.setPen(outline_pen)
            painter.drawEllipse(center, note_radius, note_radius)

            label = self._marker_label(note)
            label_font = self._fit_pixel_font(
                label,
                UI_FONT_FAMILY,
                max(8, min(24, int(note_radius * 1.05))),
                7,
                note_radius * 1.55,
                note_radius * 1.45,
                QFont.Weight.DemiBold,
            )
            painter.setFont(label_font)
            painter.setPen(QColor(24, 20, 14))
            painter.drawText(
                QRectF(
                    center.x() - note_radius,
                    center.y() - note_radius,
                    note_radius * 2.0,
                    note_radius * 2.0,
                ),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )
            painter.restore()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(5, 5, 5))

        if self.embedded_mode:
            self._paint_embedded_fretboard(painter)
            painter.end()
            return

        source_top = 0.0
        source_height = self.IMAGE_HEIGHT
        scale = min(self.width() / self.IMAGE_WIDTH, self.height() / source_height)
        drawn_width = self.IMAGE_WIDTH * scale
        drawn_height = source_height * scale
        offset_x = (self.width() - drawn_width) / 2.0
        offset_y = (self.height() - drawn_height) / 2.0 - source_top * scale

        painter.save()
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)
        if not self.background.isNull():
            painter.drawPixmap(
                QRectF(0.0, 0.0, self.IMAGE_WIDTH, self.IMAGE_HEIGHT),
                self.background,
                QRectF(self.background.rect()),
            )

        fret_font = QFont(UI_FONT_FAMILY)
        fret_font.setPixelSize(20)
        fret_font.setWeight(QFont.Weight.Medium)
        painter.setFont(fret_font)
        painter.setPen(QColor(244, 239, 231, 185))
        for fret in range(len(self.FRET_EDGES)):
            label_rect = QRectF(self.fret_center(fret) - 30.0, 292.0, 60.0, 42.0)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, str(fret))

        principal, alternatives = self._chord_texts()
        if principal and not self.embedded_mode:
            if alternatives:
                principal_rect = QRectF(82.0, 54.0, 800.0, 190.0)
                principal_alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            else:
                principal_rect = QRectF(82.0, 54.0, 1508.0, 190.0)
                principal_alignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            principal_font = self._fit_pixel_font(
                principal,
                UI_FONT_FAMILY,
                86,
                34,
                principal_rect.width(),
                principal_rect.height(),
                QFont.Weight.Medium,
            )
            painter.setFont(principal_font)
            painter.setPen(QColor(250, 250, 250))
            painter.drawText(principal_rect, principal_alignment, principal)

        if alternatives and not self.embedded_mode:
            alternate_rect = QRectF(930.0, 60.0, 660.0, 180.0)
            alternate_font = self._fit_pixel_font(
                alternatives,
                UI_FONT_FAMILY,
                34,
                22,
                alternate_rect.width(),
                alternate_rect.height(),
                QFont.Weight.Normal,
            )
            painter.setFont(alternate_font)
            painter.setPen(QColor(245, 245, 245, 225))
            painter.drawText(
                alternate_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                alternatives,
            )

        position_font = QFont(UI_FONT_FAMILY)
        position_font.setPixelSize(20)
        position_font.setWeight(QFont.Weight.Medium)
        painter.setFont(position_font)
        painter.setPen(QColor(244, 239, 231, 175))
        position_rect = (
            QRectF(1280.0, 632.0, 310.0, 32.0)
            if self.embedded_mode
            else QRectF(1260.0, 18.0, 330.0, 34.0)
        )
        painter.drawText(
            position_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"Posición {self.current_position}",
        )

        if self.partial_assignment:
            warning_font = QFont(UI_FONT_FAMILY)
            warning_font.setPixelSize(18)
            warning_font.setWeight(QFont.Weight.Medium)
            painter.setFont(warning_font)
            painter.setPen(QColor(240, 154, 0, 210))
            warning_rect = (
                QRectF(70.0, 632.0, 410.0, 30.0)
                if self.embedded_mode
                else QRectF(1180.0, 250.0, 410.0, 30.0)
            )
            painter.drawText(
                warning_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "Fuera del diapasón",
            )

        root_pc = self._root_pc()
        marker_radius = min(
            abs(second - first)
            for first, second in zip(self.STRING_Y, self.STRING_Y[1:])
        ) / 2.0
        for note, _string_index, _fret, x, y, secondary in self.display_assignment:
            painter.save()
            painter.setOpacity(self._marker_opacity(note, secondary))
            note_radius = self._marker_radius_for_note(note, marker_radius)
            fill = self._marker_color(note, root_pc)
            painter.setBrush(QBrush(fill))
            outline = QColor(255, 255, 255, 225)
            outline_width = 3.0
            if note in self.display_chord_notes and note in self.display_scale_notes:
                outline = QColor(self.display_scale_notes[note])
                outline.setAlpha(245)
                outline_width = 6.0
            painter.setPen(QPen(outline, outline_width))
            painter.drawEllipse(QPointF(x, y), note_radius, note_radius)

            label = self._marker_label(note)
            label_font = self._fit_pixel_font(
                label,
                UI_FONT_FAMILY,
                24,
                11,
                note_radius * 1.55,
                note_radius * 1.45,
                QFont.Weight.DemiBold,
            )
            painter.setFont(label_font)
            painter.setPen(QColor(24, 20, 14))
            painter.drawText(
                QRectF(
                    x - note_radius,
                    y - note_radius,
                    note_radius * 2.0,
                    note_radius * 2.0,
                ),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )
            painter.restore()

        painter.restore()
        painter.end()


class StaffWidget(QWidget):
    """Dibuja un endecagrama de piano con notas en tiempo real."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notes: Set[int] = set()
        self.chord_info: Dict[str, object] = {}
        self.setMinimumSize(520, 240)
        self.staff_settings = self.default_staff_settings()
        self.staff_font_family = self._load_staff_font()

    @staticmethod
    def default_staff_settings() -> Dict[str, object]:
        return {
            "background_color": "#000000",
            "staff_line_color": "#ffffff",
            "ledger_line_color": "#ffffff",
            "clef_color": "#ffffff",
            "note_head_color": "#ffffff",
            "accidental_color": "#ffffff",
            "label_color": "#ffffff",
            "content_x_offset": 0.0,
            "clef_scale": 1.0,
            "clef_x_offset": 0.0,
            "treble_clef_scale": 1.0,
            "bass_clef_scale": 1.0,
            "treble_clef_x_offset": 0.0,
            "bass_clef_x_offset": 0.0,
            "treble_clef_y_offset": 0.0,
            "bass_clef_y_offset": 0.0,
            "label_font_scale": 1.0,
            "label_font_family": "",
            "label_x_offset": 0.0,
            "label_y_offset": 0.0,
            "note_head_scale": 1.0,
            "note_x_offset": 0.0,
            "note_y_offset": 0.0,
            "accidental_scale": 1.0,
            "accidental_x_offset": 0.0,
            "accidental_y_offset": 0.0,
            "accidental_collision_x_offset": 0.0,
            "accidental_stack_offset": 0.25,
            "collision_y_offset_steps": 0.0,
            "collision_x_offset_scale": 1.0,
            "staff_line_length_scale": 1.0,
            "staff_line_extra": 0.0,
            "ledger_x_offset": 0.0,
            "ledger_y_offset": 0.0,
            "middle_c_ledger_x_offset": 0.0,
            "label_collision_x_offset": 0.6,
        }

    def _load_staff_font(self) -> str:
        font_path = Path(__file__).resolve().parent / "assets" / "fonts" / "MTF-ImprovisoLighter.otf"
        if font_path.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    return families[0]
        return "Times New Roman"

    def apply_staff_settings(self, settings: Dict[str, object]):
        self.staff_settings.update(settings)
        self.update()

    def _staff_float(
        self,
        key: str,
        default: float,
        *,
        min_value: Optional[float] = None,
        platform_scale: float = 1.0,
    ) -> float:
        try:
            value = float(self.staff_settings.get(key, default))
        except Exception:
            value = default
        value *= platform_scale
        if min_value is not None:
            value = max(min_value, value)
        return value

    def set_notes(self, notes: Set[int], chord_info: Optional[Dict[str, object]] = None):
        self.notes = {n for n in notes if MIN_NOTE <= n <= MAX_NOTE}
        if chord_info is not None:
            self.chord_info = chord_info
        self.update()

    def _relative_step(self, note: int, letter: str, accidental: str) -> int:
        """Posición relativa (en pasos de línea/espacio) respecto a C4."""

        octave = spelled_octave(note, letter, accidental)
        letter_index = NOTE_LETTER_TO_INDEX.get(letter, 0)
        step = octave * 7 + letter_index
        reference = 4 * 7  # C4
        return step - reference

    def _clef_rect(self, clef_type: str, staff_top_y: float, staff_spacing: float, x: float) -> QRectF:
        base_scale = self._staff_float("clef_scale", 1.0, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE)
        if clef_type == "treble":
            clef_scale = self._staff_float(
                "treble_clef_scale",
                base_scale,
                min_value=0.4,
                platform_scale=WINDOWS_STAFF_GLYPH_SCALE,
            )
        else:
            clef_scale = self._staff_float(
                "bass_clef_scale",
                base_scale,
                min_value=0.4,
                platform_scale=WINDOWS_STAFF_GLYPH_SCALE,
            )

        if clef_type == "treble":
            line_index = 3  # Segunda línea desde abajo (G4)
            y_offset = float(self.staff_settings.get("treble_clef_y_offset", 0.0)) * staff_spacing
            y = staff_top_y + line_index * staff_spacing + y_offset
        else:
            line_index = 1  # Los puntos abrazan la cuarta línea (F3)
            y_offset = float(self.staff_settings.get("bass_clef_y_offset", 0.0)) * staff_spacing
            y = staff_top_y + line_index * staff_spacing + y_offset
        if IS_LEGACY_QT_MAC:
            y -= staff_spacing

        rect_height_factor = 4.8 if IS_LEGACY_QT_MAC else 4.2
        rect_width_factor = 4.4 if IS_LEGACY_QT_MAC else 3.2
        rect_x_pad = staff_spacing * 0.6 * clef_scale if IS_LEGACY_QT_MAC else 0.0
        rect_height = staff_spacing * rect_height_factor * clef_scale
        rect_width = staff_spacing * rect_width_factor * clef_scale
        return QRectF(
            x - rect_x_pad,
            y - rect_height / 2,
            rect_width,
            rect_height,
        )

    @staticmethod
    def _rects_intersect(rect: QRectF, others: List[QRectF]) -> bool:
        return any(rect.intersects(other) for other in others)

    def _resolve_horizontal_collision(
        self,
        rect: QRectF,
        occupied: List[QRectF],
        step: float,
        max_attempts: int = 12,
        prefer_left: bool = True,
        allow_right: bool = True,
    ) -> QRectF:
        if not self._rects_intersect(rect, occupied):
            return rect

        if allow_right:
            directions = (-1, 1) if prefer_left else (1, -1)
        else:
            directions = (-1,) if prefer_left else (1,)
        for offset_index in range(1, max_attempts + 1):
            for direction in directions:
                candidate = QRectF(rect)
                candidate.translate(direction * step * offset_index, 0)
                if not self._rects_intersect(candidate, occupied):
                    return candidate
        return rect

    def _color_from_setting(self, key: str, default: QColor) -> QColor:
        value = self.staff_settings.get(key, default)
        if isinstance(value, QColor):
            return value if value.isValid() else default
        if isinstance(value, str):
            color = QColor(value)
            return color if color.isValid() else default
        return default

    # --- Layout helpers -------------------------------------------------
    def computeLayout(self, rect: QRect) -> Dict[str, float]:
        """Calcula márgenes, anchos y posiciones básicas a partir del rectángulo."""

        staff_spacing = max(7.0, min(16.0 if IS_WINDOWS else 18.0, rect.height() / 18.0))
        margin = staff_spacing * (1.2 + LEGACY_QT_MAC_STAFF_LEFT_PAD)
        label_width = 0.0
        base_clef_scale = self._staff_float(
            "clef_scale", 1.0, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        treble_scale = self._staff_float(
            "treble_clef_scale", base_clef_scale, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        bass_scale = self._staff_float(
            "bass_clef_scale", base_clef_scale, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        clef_scale = max(treble_scale, bass_scale)
        clef_width = staff_spacing * 3.0 * clef_scale

        if IS_LEGACY_QT_MAC:
            line_x_start = margin + label_width + staff_spacing * 0.4
            usable_width = max(rect.width() - line_x_start - margin, staff_spacing * 10)
        else:
            line_x_start = margin + label_width + clef_width
            usable_width = max(rect.width() - 2 * margin - label_width - clef_width, staff_spacing * 10)
        min_staff_width = staff_spacing * 10
        center_y = rect.center().y()

        return {
            "staffSpacing": staff_spacing,
            "margin": margin,
            "labelWidth": label_width,
            "clefWidth": clef_width,
            "usableWidth": usable_width,
            "lineStart": line_x_start,
            "minStaffWidth": min_staff_width,
            "centerY": center_y,
        }

    def computeNoteXOffsetsForCollisions(
        self, notes: List[int], note_head_width: float, note_steps: Dict[int, int]
    ) -> Dict[int, float]:
        """Desplazamientos en X para segundas que colisionan (intervalo de 1 paso)."""

        offsets: Dict[int, float] = {n: 0.0 for n in notes}
        if not notes:
            return offsets

        collision_scale = float(self.staff_settings.get("collision_x_offset_scale", 1.0))
        second_contact_dx = note_head_width * 0.42
        dx = second_contact_dx * collision_scale
        unison_dx = note_head_width * 0.9 * collision_scale

        step_map: Dict[int, List[int]] = {}
        for note in notes:
            step_map.setdefault(note_steps.get(note, 0), []).append(note)

        unique_steps = sorted(step_map.keys())
        index = 0
        while index < len(unique_steps):
            run_steps = [unique_steps[index]]
            while (
                index + 1 < len(unique_steps)
                and unique_steps[index + 1] - unique_steps[index] == 1
            ):
                index += 1
                run_steps.append(unique_steps[index])

            if len(run_steps) > 1:
                for run_index, step in enumerate(run_steps):
                    base_offset = -dx if run_index % 2 == 0 else dx
                    for note in step_map[step]:
                        offsets[note] += base_offset
            index += 1

        for _step, notes_in_step in step_map.items():
            if len(notes_in_step) <= 1:
                continue
            notes_in_step.sort()
            start = -unison_dx * (len(notes_in_step) - 1) / 2.0
            for note_index, note in enumerate(notes_in_step):
                offsets[note] += start + note_index * unison_dx

        return offsets

    # --- Dibujo modular -------------------------------------------------
    def drawStaff(self, painter: QPainter, y_top: float, staff_spacing: float, x_start: float, x_end: float):
        """Dibuja un pentagrama de 5 líneas desde y_top (de arriba a abajo)."""

        for i in range(5):
            y = y_top + i * staff_spacing
            painter.drawLine(QPointF(x_start, y), QPointF(x_end, y))

    def drawClef(self, painter: QPainter, clef_type: str, staff_top_y: float, staff_spacing: float, x: float):
        """Dibuja la clave indicada, escalada al espaciado del pentagrama."""

        base_scale = self._staff_float("clef_scale", 1.0, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE)
        if clef_type == "treble":
            clef_scale = self._staff_float(
                "treble_clef_scale",
                base_scale,
                min_value=0.4,
                platform_scale=WINDOWS_STAFF_GLYPH_SCALE,
            )
        else:
            clef_scale = self._staff_float(
                "bass_clef_scale",
                base_scale,
                min_value=0.4,
                platform_scale=WINDOWS_STAFF_GLYPH_SCALE,
            )
        font_size = staff_spacing * 3.2 * clef_scale
        clef_font = QFont(self.staff_font_family, int(font_size))
        painter.setFont(clef_font)

        if clef_type == "treble":
            line_index = 3  # Segunda línea desde abajo (G4)
            symbol = "𝄞"
            y_offset = float(self.staff_settings.get("treble_clef_y_offset", 0.0)) * staff_spacing
            y = staff_top_y + line_index * staff_spacing + y_offset
        else:
            line_index = 1  # Los puntos abrazan la cuarta línea (F3)
            symbol = "𝄢"
            y_offset = float(self.staff_settings.get("bass_clef_y_offset", 0.0)) * staff_spacing
            y = staff_top_y + line_index * staff_spacing + y_offset
        if IS_LEGACY_QT_MAC:
            y -= staff_spacing

        rect_height_factor = 4.8 if IS_LEGACY_QT_MAC else 4.2
        rect_width_factor = 4.4 if IS_LEGACY_QT_MAC else 3.2
        rect_x_pad = staff_spacing * 0.6 if IS_LEGACY_QT_MAC else 0.0
        rect_height = staff_spacing * rect_height_factor
        rect = QRectF(
            x - rect_x_pad,
            y - rect_height / 2,
            staff_spacing * rect_width_factor,
            rect_height,
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)

    def drawNoteHead(self, painter: QPainter, center_x: float, center_y: float, staff_spacing: float):
        """Dibuja una cabeza de nota ovalada inclinada hacia la izquierda."""

        note_scale = self._staff_float(
            "note_head_scale", 1.0, min_value=0.5, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        if IS_LEGACY_QT_MAC:
            width = staff_spacing * 1.32 * LEGACY_QT_MAC_NOTE_HEAD_SCALE * note_scale
            height = staff_spacing * LEGACY_QT_MAC_NOTE_HEAD_SCALE * note_scale
            painter.save()
            painter.translate(center_x, center_y)
            painter.rotate(-10)
            painter.setBrush(QBrush(self._color_from_setting("note_head_color", QColor(Qt.GlobalColor.black))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(-width / 2.0, -height / 2.0, width, height))
            painter.restore()
            return

        font_size = staff_spacing * 2.4 * note_scale
        font = QFont(self.staff_font_family, int(font_size))
        painter.setFont(font)
        rect_factor = 2.8 if IS_WINDOWS else 2.2
        rect = QRectF(
            center_x - staff_spacing * rect_factor * note_scale / 2.0,
            center_y - staff_spacing * rect_factor * note_scale / 2.0,
            staff_spacing * rect_factor * note_scale,
            staff_spacing * rect_factor * note_scale,
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "𝅝")

    def _accidental_symbol(self, accidental: str, show_natural: bool = False) -> str:
        if accidental:
            return ACCIDENTAL_TO_SYMBOL.get(accidental, "")
        return "♮" if show_natural else ""

    def _note_spellings_for_notes(self, notes: Set[int]) -> Dict[int, str]:
        if not notes:
            return {}
        chord_info = self.chord_info or {}
        custom_map = chord_info.get("custom_spelling_map")
        if isinstance(custom_map, dict) and custom_map:
            spellings: Dict[int, str] = {}
            for note in notes:
                pc = note % 12
                spelling = custom_map.get(pc)
                if spelling:
                    spellings[note] = spelling
                else:
                    spellings[note] = NOTE_NAMES[pc]
            return spellings
        principal = str(chord_info.get("principal") or "")
        principal_match = chord_info.get("principal_match") or {}
        root_pc = principal_match.get("root")
        chord_name = str(principal_match.get("nombre") or "")
        root_letter, _accidental = _parse_root_spelling(principal)
        if root_letter is None or root_pc is None:
            return {note: NOTE_NAMES[note % 12] for note in notes}

        spellings: Dict[int, str] = {}
        root_pc = int(root_pc)
        for note in notes:
            interval = (note - root_pc) % 12
            spellings[note] = spell_note_for_interval(root_letter, root_pc, chord_name, interval)
        return spellings

    def drawAccidental(
        self,
        painter: QPainter,
        accidental: str,
        column_x: float,
        note_y: float,
        staff_spacing: float,
        note_head_width: float,
    ):
        """Dibuja una alteración a la izquierda de la cabeza de nota."""

        accidental_scale = self._staff_float(
            "accidental_scale", 1.0, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        font = QFont(self.staff_font_family, int(staff_spacing * 1.4 * accidental_scale))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        _rect, origin = self._accidental_text_layout(
            accidental, column_x, note_y, staff_spacing, note_head_width, metrics
        )
        painter.drawText(origin, accidental)

    def _accidental_text_layout(
        self,
        accidental: str,
        column_x: float,
        note_y: float,
        staff_spacing: float,
        note_head_width: float,
        metrics: QFontMetricsF,
    ) -> Tuple[QRectF, QPointF]:
        """Devuelve el rectángulo real y punto de baseline para centrar la alteración en la nota."""

        accidental_x_offset = float(self.staff_settings.get("accidental_x_offset", 0.0)) * staff_spacing
        accidental_y_offset = float(self.staff_settings.get("accidental_y_offset", 0.0)) * staff_spacing
        accidental_x = column_x - note_head_width * 1.2 + accidental_x_offset
        center_x = accidental_x + (note_head_width * 1.2) / 2.0

        if IS_LEGACY_QT_MAC:
            bounds = metrics.tightBoundingRect(accidental)
            if bounds.isNull() or bounds.width() <= 0 or bounds.height() <= 0:
                bounds = metrics.boundingRect(accidental)
            origin = QPointF(
                center_x - bounds.center().x(),
                note_y + accidental_y_offset - bounds.center().y(),
            )
            padding_x = staff_spacing * 0.08
            padding_y = staff_spacing * 0.05
            rect = QRectF(bounds).translated(origin).adjusted(
                -padding_x, -padding_y, padding_x, padding_y
            )
            return rect, origin

        text_width = metrics.horizontalAdvance(accidental)
        text_height = metrics.height()
        baseline_y = note_y - text_height / 2.0 + metrics.ascent() + accidental_y_offset
        origin = QPointF(center_x - text_width / 2.0, baseline_y)
        rect = QRectF(
            origin.x(),
            baseline_y - metrics.ascent(),
            text_width,
            text_height,
        )
        return rect, origin

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        background_color = self._color_from_setting("background_color", QColor(Qt.GlobalColor.white))
        painter.fillRect(rect, QBrush(background_color))

        layout = self.computeLayout(rect)
        staff_spacing = layout["staffSpacing"]
        step_height = staff_spacing / 2.0
        center_y = layout["centerY"]
        line_start = layout["lineStart"]
        staff_line_color = self._color_from_setting("staff_line_color", QColor(40, 40, 40))
        pen = QPen(staff_line_color)
        pen.setWidthF(max(1.2, staff_spacing * 0.12))
        painter.setPen(pen)

        treble_top = center_y - 10 * step_height
        bass_top = center_y + 2 * step_height

        content_x_offset = float(self.staff_settings.get("content_x_offset", 0.0)) * staff_spacing
        note_x_offset = float(self.staff_settings.get("note_x_offset", 0.0)) * staff_spacing
        note_y_offset = float(self.staff_settings.get("note_y_offset", 0.0)) * staff_spacing
        note_x_base = (
            line_start
            + staff_spacing * (1.2 + LEGACY_QT_MAC_NOTE_PAD)
            + note_x_offset
            + content_x_offset
        )
        note_head_scale = self._staff_float(
            "note_head_scale", 1.0, min_value=0.5, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        note_head_width = (
            staff_spacing
            * (1.32 * LEGACY_QT_MAC_NOTE_HEAD_SCALE if IS_LEGACY_QT_MAC else 1.2)
            * note_head_scale
        )
        note_head_size = (
            staff_spacing
            * (1.32 * LEGACY_QT_MAC_NOTE_HEAD_SCALE if IS_LEGACY_QT_MAC else 2.2)
            * note_head_scale
        )
        ledger_length = note_head_width * 1.4
        collision_y_offset = float(self.staff_settings.get("collision_y_offset_steps", 0.0)) * step_height

        clef_x = layout["margin"] + layout["labelWidth"]
        clef_x += float(self.staff_settings.get("clef_x_offset", 0.0)) * staff_spacing
        treble_clef_x = clef_x + float(self.staff_settings.get("treble_clef_x_offset", 0.0)) * staff_spacing
        bass_clef_x = clef_x + float(self.staff_settings.get("bass_clef_x_offset", 0.0)) * staff_spacing
        clef_rects = [
            self._clef_rect("treble", treble_top, staff_spacing, treble_clef_x),
            self._clef_rect("bass", bass_top, staff_spacing, bass_clef_x),
        ]

        note_spellings = self._note_spellings_for_notes(self.notes)
        note_steps: Dict[int, int] = {}
        note_accidentals: Dict[int, str] = {}
        for note in self.notes:
            spelling = note_spellings.get(note, NOTE_NAMES[note % 12])
            letter = spelling[0]
            accidental = spelling[1:]
            note_steps[note] = self._relative_step(note, letter, accidental)
            note_accidentals[note] = accidental

        offsets = self.computeNoteXOffsetsForCollisions(sorted(self.notes), note_head_width, note_steps)

        note_positions: List[float] = []
        accidental_info: List[Tuple[str, float, float, float]] = []
        note_rows: List[Tuple[int, float, List[int], float]] = []
        note_head_rects: List[QRectF] = []

        step_groups: Dict[int, Dict[str, bool]] = {}
        for note, rel_step in note_steps.items():
            info = step_groups.setdefault(rel_step, {"natural": False, "altered": False})
            if note_accidentals.get(note):
                info["altered"] = True
            else:
                info["natural"] = True

        for note in sorted(self.notes):
            rel_step = note_steps[note]
            y = center_y - rel_step * step_height + note_y_offset
            if offsets.get(note, 0.0) != 0.0:
                y += collision_y_offset

            ledger_steps: List[int] = []
            if rel_step > 10:
                ledger_steps = list(range(12, rel_step + 1, 2))
            elif rel_step < -10:
                ledger_steps = list(range(-12, rel_step - 1, -2))
            elif -2 < rel_step < 2 and rel_step % 2 == 0:
                ledger_steps = [0]

            note_x = note_x_base + offsets.get(note, 0.0)
            note_positions.append(note_x)
            note_rows.append((note, y, ledger_steps, note_x))
            note_head_rects.append(
                QRectF(
                    note_x - note_head_size / 2.0,
                    y - note_head_size / 2.0,
                    note_head_size,
                    note_head_size,
                )
            )

            group_info = step_groups.get(rel_step, {})
            show_natural = not note_accidentals.get(note) and bool(group_info.get("altered"))
            accidental = self._accidental_symbol(note_accidentals.get(note, ""), show_natural)
            if accidental:
                accidental_column_x = note_x
                if offsets.get(note, 0.0) != 0.0:
                    accidental_column_x += float(
                        self.staff_settings.get("accidental_collision_x_offset", 0.0)
                    ) * staff_spacing
                accidental_info.append((accidental, accidental_column_x, y, note_head_width))

        accidental_info.sort(key=lambda item: item[2])
        accidental_scale = self._staff_float(
            "accidental_scale", 1.0, min_value=0.4, platform_scale=WINDOWS_STAFF_GLYPH_SCALE
        )
        accidental_font = QFont(self.staff_font_family, int(staff_spacing * 1.4 * accidental_scale))
        metrics = QFontMetricsF(accidental_font)
        accidental_min_left = max(rect.right() for rect in clef_rects) + staff_spacing * 0.35
        if accidental_info:
            min_left = None
            for symbol, column_x, y, head_width in accidental_info:
                rect, _origin = self._accidental_text_layout(
                    symbol, column_x, y, staff_spacing, head_width, metrics
                )
                min_left = rect.left() if min_left is None else min(min_left, rect.left())
            if min_left is not None and min_left < accidental_min_left:
                shift_x = accidental_min_left - min_left
                note_positions = [x + shift_x for x in note_positions]
                note_rows = [
                    (note, y, ledger_steps, note_x + shift_x)
                    for note, y, ledger_steps, note_x in note_rows
                ]
                note_head_rects = [QRectF(rect).translated(shift_x, 0) for rect in note_head_rects]
                accidental_info = [
                    (symbol, column_x + shift_x, y, head_width)
                    for symbol, column_x, y, head_width in accidental_info
                ]
        staff_width = layout["usableWidth"]

        line_length_scale = max(0.3, float(self.staff_settings.get("staff_line_length_scale", 1.0)))
        line_extra = float(self.staff_settings.get("staff_line_extra", 0.0)) * staff_spacing

        line_end = line_start + staff_width * line_length_scale + line_extra
        self.drawStaff(painter, treble_top, staff_spacing, line_start, line_end)
        self.drawStaff(painter, bass_top, staff_spacing, line_start, line_end)

        clef_color = self._color_from_setting("clef_color", QColor(Qt.GlobalColor.black))
        painter.setPen(QPen(clef_color))
        self.drawClef(painter, "treble", treble_top, staff_spacing, treble_clef_x)
        painter.setPen(QPen(clef_color))
        self.drawClef(painter, "bass", bass_top, staff_spacing, bass_clef_x)

        base_occupied_rects = note_head_rects + clef_rects

        for note, y, ledger_steps, note_x in note_rows:
            ledger_color = self._color_from_setting("ledger_line_color", staff_line_color)
            ledger_pen = QPen(ledger_color)
            ledger_pen.setWidthF(max(1.2, staff_spacing * 0.12))
            painter.setPen(ledger_pen)
            ledger_global_x = float(self.staff_settings.get("ledger_x_offset", 0.0)) * staff_spacing
            ledger_global_y = float(self.staff_settings.get("ledger_y_offset", 0.0)) * staff_spacing
            for ls in ledger_steps:
                ly = center_y - ls * step_height + note_y_offset + ledger_global_y
                ledger_x_offset = ledger_global_x
                if ls == 0:
                    ledger_x_offset += float(self.staff_settings.get("middle_c_ledger_x_offset", 0.0)) * staff_spacing
                painter.drawLine(
                    QPointF(note_x - ledger_length / 2 + ledger_x_offset, ly),
                    QPointF(note_x + ledger_length / 2 + ledger_x_offset, ly),
                )

            note_color = self._color_from_setting("note_head_color", QColor(Qt.GlobalColor.black))
            painter.setPen(QPen(note_color))
            self.drawNoteHead(painter, note_x, y, staff_spacing)

        accidental_rects: List[QRectF] = []
        for symbol, column_x, y, head_width in accidental_info:
            stack_offset = float(self.staff_settings.get("accidental_stack_offset", 0.25))
            if IS_LEGACY_QT_MAC:
                step = max(staff_spacing * 0.9, head_width * 0.8)
            else:
                step = max(staff_spacing * 0.35, head_width * stack_offset)
            accidental_color = self._color_from_setting("accidental_color", QColor(Qt.GlobalColor.black))
            painter.setPen(QPen(accidental_color))
            painter.setFont(accidental_font)

            def accidental_rect(x_pos: float) -> Tuple[QRectF, float, float]:
                rect, origin = self._accidental_text_layout(
                    symbol, x_pos, y, staff_spacing, head_width, metrics
                )
                return rect, rect.left(), origin.y()

            column_offsets = (
                [0.0, -step, -2 * step, -3 * step, -4 * step, -5 * step]
                if IS_LEGACY_QT_MAC
                else [0.0, -step, -2 * step]
            )
            placed = False
            for offset in column_offsets:
                candidate_x = column_x + offset
                rect, center_x, _baseline_y = accidental_rect(candidate_x)
                if (
                    rect.left() >= accidental_min_left
                    and not self._rects_intersect(rect, base_occupied_rects + accidental_rects)
                ):
                    column_x = candidate_x
                    accidental_rects.append(QRectF(rect))
                    placed = True
                    break

            if not placed:
                rect, center_x, _baseline_y = accidental_rect(column_x)
                rect = self._resolve_horizontal_collision(
                    rect,
                    base_occupied_rects + accidental_rects,
                    step,
                    max_attempts=14,
                    prefer_left=True,
                    allow_right=False,
                )
                if rect.left() < accidental_min_left:
                    rect.translate(accidental_min_left - rect.left(), 0)
                column_x += rect.left() - center_x
                accidental_rects.append(QRectF(rect))

            self.drawAccidental(
                painter,
                symbol,
                column_x,
                y,
                staff_spacing,
                head_width,
            )


class StaffWindow(QMainWindow):
    """Ventana flotante con notación de endecagrama."""

    def __init__(self):
        super().__init__()

        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)

        self.setWindowTitle("MIDI Piano — Partitura")
        self._drag_offset: Optional[QPoint] = None
        self._drag_filter = WindowDragFilter(self)

        self.widget = StaffWidget()
        self.setCentralWidget(self.widget)
        self._install_drag_support(self.widget)
        self.resize(760, 320)

    def _install_drag_support(self, root: QWidget) -> None:
        root.installEventFilter(self._drag_filter)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self._drag_filter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def set_notes(self, notes: Set[int], chord_info: Optional[Dict[str, object]] = None):
        self.widget.set_notes(notes, chord_info)

class ControlWindow(ResponsiveWidthWidget):
    """
    Panel de controles (se aloja en el menú superior):
    - Selección de dispositivo MIDI
    - Nota inicial (solo A0 o Cs)
    - Número de octavas
    - Color base
    - Siempre al frente (para la ventana del teclado)
    - Guardar preferencias de forma persistente al cerrar la app
    """

    CONFIG_PATH = Path.home() / ".midi_piano_prefs.json"
    APPEARANCE_CONFIG_PATH = Path.home() / ".midi_piano_appearance_default.json"

    def __init__(
        self,
        piano_window: PianoWindow,
        chord_window: ChordWindow,
        staff_window: StaffWindow,
        fretboard_widget: FretboardWidget,
    ):
        super().__init__()
        self.setObjectName("ControlWindow")
        self.setWindowTitle("Controles - MIDI Piano Jaramillo")

        self.settings = QSettings("MIDI-Piano-Jaramillo", "MIDI-Piano")

        self.menu_bar = piano_window.menuBar()
        self.piano_window = piano_window
        self.piano = piano_window.piano
        self.chord_window = chord_window
        self.staff_window = staff_window
        self.fretboard_widget = fretboard_widget
        self.instrument_view = "piano"
        self.fretboard_widget.set_embedded_mode(True)
        self.piano_window.set_fretboard_widget(self.fretboard_widget)
        self.active_notes: Set[int] = set()
        self.sustained_notes: Set[int] = set()
        self._held_note_sources: Dict[int, Set[Tuple[int, int]]] = {}
        self._sustain_sources: Set[Tuple[int, int]] = set()
        self.note_activation_order: List[int] = []
        self.sustain_on: bool = False
        self._midi_backend_error_shown: bool = False
        self.custom_chords: List[Dict] = []
        self.additional_base_chords: List[Dict] = []
        self._additional_base_signatures: Set[Tuple[Tuple[int, ...], Tuple[int, ...]]] = set()
        self.learning_chord: bool = False
        self.learning_waiting_first_note: bool = False
        self.learning_capture_notes: Set[int] = set()
        self.midi_learn_help_dialog: Optional[QDialog] = None
        self.capture_window_ms: int = 500
        self._learn_button_default_text = "Midi learn: nuevo cifrado"
        self.chord_text_color = QColor(Qt.GlobalColor.white)
        self.chord_bg_color = QColor(0, 0, 0)
        self.single_window_bg_color = QColor(0, 0, 0)
        self.interval_label_settings = self._default_interval_label_settings()
        self.custom_chord_spellings: Dict[Tuple[int, ...], Dict[int, str]] = {}
        self.custom_chord_quality_spellings: Dict[str, Dict[int, Dict[str, object]]] = {}
        self.display_chord_color = QColor(0, 122, 255, 190)
        self.display_chord_root_color = QColor(52, 199, 89, 190)
        self.display_chord_warning_color = QColor(230, 70, 70, 180)
        self.display_chord_interval_labels: Dict[int, str] = {}
        self.display_scale_colors = {
            "green": QColor(60, 200, 120, 200),
            "blue": QColor(60, 120, 240, 200),
            "orange": QColor(240, 160, 60, 200),
            "red": QColor(230, 80, 80, 200),
        }
        self.display_scale_circle_size_percent = 100
        self.scale_edit_mode_enabled = False
        self.scale_role_overrides: Dict[str, Dict[int, str]] = {}
        self._scale_color_to_role = {
            "green": "root",
            "blue": "stable",
            "orange": "tension",
            "red": "critical",
        }
        self._role_to_scale_color = {
            "root": "green",
            "stable": "blue",
            "tension": "orange",
            "critical": "red",
        }
        self._scale_role_labels = {
            "root": "Fundamental",
            "stable": "Estructural",
            "tension": "Tensión disponible",
            "critical": "Nota evitada",
        }
        self._scale_palette_buttons: List[Tuple[str, QPushButton]] = []
        self._visual_save_state = "Guardado"
        self._last_status_message = ""
        self._status_message_timer = QTimer(self)
        self._status_message_timer.setSingleShot(True)
        self._status_message_timer.timeout.connect(self._clear_transient_status_message)
        self._presentation_mode_enabled = False
        self._presentation_previous_mode = DEFAULT_VIEW_MODE
        self._presentation_previous_fullscreen = False
        self._shortcut_objects: List[QShortcut] = []
        self._shortcut_overrides: Dict[str, str] = {}
        self.jazzscope_chords = self._load_jazzscope_chord_library()
        self.capture_timer = QTimer()
        self.capture_timer.setSingleShot(True)
        self.capture_timer.timeout.connect(self._finish_capture_window)
        self._menu_panel_widgets: List[QWidget] = []
        self._visual_state_tracking_enabled = False
        self._is_closing = False
        self._visual_state_save_timer = QTimer(self)
        self._visual_state_save_timer.setSingleShot(True)
        self._visual_state_save_timer.timeout.connect(self._persist_visual_state)
        self.piano.on_scale_circle_clicked = self._handle_scale_circle_clicked
        self.piano.on_double_click = self._toggle_single_fullscreen_from_double_click
        self.piano_window.on_double_click = self._toggle_single_fullscreen_from_double_click

        # Widgets
        self.input_combo = MenuComboBox()
        self.refresh_button = QPushButton("Actualizar dispositivos")

        self.start_combo = MenuComboBox()
        self.octaves_spin = QSpinBox()
        self.octaves_spin.setRange(1, 7)
        self.octaves_spin.setValue(3)

        # Selector de color del sistema
        self.color_button = QPushButton("Elegir color…")

        # Color de cifrado
        self.chord_color_button = QPushButton("Color cifrado…")

        # Color de fondo para la ventana de acordes
        self.chord_bg_button = QPushButton("Fondo acordes…")

        # Fuente y tamaño para la ventana de acordes
        self.font_combo = QFontComboBox()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(10, 160)
        self.font_size_spin.setValue(80)

        try:
            self.font_combo.setCurrentFont(QFont(UI_FONT_FAMILY))
        except Exception:
            pass

        self.always_on_top = QPushButton("Teclado siempre al frente")
        self.always_on_top.setCheckable(True)

        self.export_button = QPushButton("Exportar diccionario…")

        # Rellenar combo de nota inicial:
        #  - A0
        #  - Todos los Cx dentro de A0–C8
        for n in range(MIN_NOTE, MAX_NOTE + 1):
            if n == MIN_NOTE or NOTE_NAMES[n % 12] == "C":
                label = f"{midi_to_name(n)} ({n})"
                self.start_combo.addItem(label, n)

        # Por defecto: teclado completo (A0–C8)
        default_start = DEFAULT_START_NOTE
        self._select_combo_value(self.start_combo, default_start)
        self.octaves_spin.setValue(DEFAULT_OCTAVES)
        self.piano.set_range_from_start_and_octaves(default_start, self.octaves_spin.value())

        # Layout
        top_layout = QVBoxLayout()
        self.main_status_strip = self._build_compact_status_label()
        top_layout.addWidget(self.main_status_strip)
        self.primary_controls_tabs = QTabWidget()
        midi_tab = QWidget()
        midi_tab.setObjectName("ControlTabPage")
        midi_layout = QVBoxLayout()
        midi_layout.setContentsMargins(6, 6, 6, 6)
        keyboard_tab = QWidget()
        keyboard_tab.setObjectName("ControlTabPage")
        keyboard_layout = QVBoxLayout()
        keyboard_layout.setContentsMargins(6, 6, 6, 6)
        appearance_tab = QWidget()
        appearance_tab.setObjectName("ControlTabPage")
        appearance_layout = QVBoxLayout()
        appearance_layout.setContentsMargins(6, 6, 6, 6)
        learn_tab = QWidget()
        learn_tab.setObjectName("ControlTabPage")
        learn_layout = QVBoxLayout()
        learn_layout.setContentsMargins(6, 6, 6, 6)

        # Fila 1: MIDI
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("MIDI In:"))
        row1.addWidget(self.input_combo)
        row1.addWidget(self.refresh_button)
        midi_layout.addLayout(row1)

        # Fila 2: rango por octavas
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Nota inicial:"))
        row2.addWidget(self.start_combo)
        row2.addWidget(QLabel("Octavas:"))
        row2.addWidget(self.octaves_spin)
        keyboard_layout.addLayout(row2)

        # Fila 3: color
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Color base notas:"))
        row3.addWidget(self.color_button)
        appearance_layout.addLayout(row3)

        # Fila 4: color de cifrado
        row3b = QHBoxLayout()
        row3b.addWidget(QLabel("Color del cifrado:"))
        row3b.addWidget(self.chord_color_button)
        appearance_layout.addLayout(row3b)

        row3c = QHBoxLayout()
        row3c.addWidget(QLabel("Fondo de acordes:"))
        row3c.addWidget(self.chord_bg_button)
        appearance_layout.addLayout(row3c)

        # Fila 4: fuente acordes
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Fuente acordes:"))
        row4.addWidget(self.font_combo)
        row4.addWidget(QLabel("Tamaño:"))
        row4.addWidget(self.font_size_spin)
        appearance_layout.addLayout(row4)

        # Fila 5: botones de ventana
        row5 = QHBoxLayout()
        row5.addWidget(self.export_button)
        row5.addStretch()
        appearance_layout.addLayout(row5)

        # Fila 6: Midi learn
        self.learn_button = QPushButton("Midi learn: nuevo cifrado")
        row6 = QHBoxLayout()
        row6.addWidget(self.learn_button)
        row6.addStretch()
        learn_layout.addLayout(row6)

        # Fila 7: duración ventana de captura para Midi learn
        capture_row = QHBoxLayout()
        capture_row.addWidget(QLabel("Ventana captura (ms):"))
        self.capture_window_spin = QSpinBox()
        self.capture_window_spin.setRange(100, 5000)
        self.capture_window_spin.setSingleStep(50)
        self.capture_window_spin.setValue(self.capture_window_ms)
        capture_row.addWidget(self.capture_window_spin)
        capture_row.addStretch()
        learn_layout.addLayout(capture_row)

        # Visualización de acordes y escalas (pregrabados) se configura en el menú superior
        self.display_chord_checkbox = QCheckBox("Mostrar acorde")
        self.display_root_combo = QComboBox()
        self.display_root_combo.setFixedWidth(92)
        self.display_chord_combo = QComboBox()
        self.display_chord_combo.setMinimumWidth(230)
        self.display_chord_combo.setMinimumContentsLength(18)
        self.display_inversion_spin = QSpinBox()
        self.display_inversion_spin.setRange(-4, 4)
        self.display_inversion_spin.setValue(0)
        self.display_inversion_spin.setFixedWidth(58)
        self.display_drop_combo = QComboBox()
        self.display_drop_combo.setFixedWidth(112)
        self.display_drop_combo.addItem("No Drop", "none")
        self.display_drop_combo.addItem("Drop 2", "drop2")
        self.display_drop_combo.addItem("Drop 3", "drop3")
        self.display_drop_combo.addItem("Drop 2-4", "drop2-4")
        self.display_transpose_spin = QSpinBox()
        self.display_transpose_spin.setRange(-24, 24)
        self.display_transpose_spin.setValue(0)
        self.display_scale_checkbox = QCheckBox("Mostrar escala")
        self.display_scale_combo = QComboBox()
        self.display_scale_combo.setMinimumWidth(300)
        self.display_scale_combo.setMinimumContentsLength(26)
        self.view_mode = "separate"
        self._syncing_display_panel = False

        self._setup_window_menu()
        self.display_panel_widget = self._build_display_panel()
        self.keyboard_nav_panel = self._build_keyboard_navigation_panel()
        self._set_instrument_view("piano", persist=False, show_status=False)

        self._load_external_chord_dictionary()

        # Lista de acordes aprendidos
        learn_layout.addWidget(QLabel("Acordes aprendidos:"))
        self.learned_chords_container = QWidget()
        self.learned_chords_layout = QVBoxLayout()
        self.learned_chords_layout.setContentsMargins(0, 0, 0, 0)
        self.learned_chords_layout.setSpacing(6)
        self.learned_chords_container.setLayout(self.learned_chords_layout)
        self.learned_chords_scroll = QScrollArea()
        self.learned_chords_scroll.setObjectName("LearnedChordsScroll")
        self.learned_chords_scroll.setWidgetResizable(True)
        self.learned_chords_scroll.setWidget(self.learned_chords_container)
        learn_layout.addWidget(self.learned_chords_scroll)

        midi_layout.addStretch()
        keyboard_layout.addStretch()
        appearance_layout.addStretch()
        learn_layout.addStretch()
        midi_tab.setLayout(midi_layout)
        keyboard_tab.setLayout(keyboard_layout)
        appearance_tab.setLayout(appearance_layout)
        learn_tab.setLayout(learn_layout)
        self.primary_controls_tabs.addTab(midi_tab, "MIDI")
        self.primary_controls_tabs.addTab(keyboard_tab, "Teclado")
        self.primary_controls_tabs.addTab(appearance_tab, "Apariencia")
        self.primary_controls_tabs.addTab(learn_tab, "Aprender")
        top_layout.addWidget(self.primary_controls_tabs)

        self.setLayout(top_layout)

        # MIDI
        self.midi_in = None
        self.midi_inputs: List[object] = []
        self._all_inputs_value = "__all_midi_inputs__"

        # Conexiones (con validación de handlers para evitar fallos por métodos faltantes)
        self._connect_signal_handler(self.refresh_button.clicked, "refresh_inputs", self.refresh_button, "Actualizar entradas MIDI")
        self._connect_signal_handler(self.input_combo.currentIndexChanged, "change_input", self.input_combo, "Entrada MIDI")
        self._connect_signal_handler(self.start_combo.currentIndexChanged, "range_changed", self.start_combo, "Nota inicial")
        self._connect_signal_handler(self.octaves_spin.valueChanged, "range_changed", self.octaves_spin, "Número de octavas")
        self._connect_signal_handler(self.color_button.clicked, "choose_color", self.color_button, "Color del teclado")
        self._connect_signal_handler(self.chord_color_button.clicked, "choose_chord_color", self.chord_color_button, "Color del cifrado")
        self._connect_signal_handler(self.chord_bg_button.clicked, "choose_chord_background", self.chord_bg_button, "Fondo de acordes")
        self._connect_signal_handler(self.font_combo.currentFontChanged, "font_changed", self.font_combo, "Fuente")
        self._connect_signal_handler(self.font_size_spin.valueChanged, "font_size_changed", self.font_size_spin, "Tamaño de fuente")
        self._connect_signal_handler(self.export_button.clicked, "export_chord_dictionary", self.export_button, "Exportar diccionario")
        self._connect_signal_handler(self.learn_button.clicked, "start_learning_mode", self.learn_button, "Midi learn")
        self._connect_signal_handler(self.display_chord_checkbox.toggled, "_update_display_overlays", self.display_chord_checkbox, "Mostrar acorde")
        self._connect_signal_handler(self.display_scale_checkbox.toggled, "_update_display_overlays", self.display_scale_checkbox, "Mostrar escala")
        self._connect_signal_handler(self.display_root_combo.currentIndexChanged, "_update_display_overlays", self.display_root_combo, "Raíz del acorde")
        self._connect_signal_handler(self.display_chord_combo.currentIndexChanged, "_update_display_overlays", self.display_chord_combo, "Tipo de acorde")
        self._connect_signal_handler(self.display_scale_combo.currentIndexChanged, "_update_display_overlays", self.display_scale_combo, "Escala")
        self._connect_signal_handler(self.display_chord_combo.currentIndexChanged, "_sync_selector_button_labels", self.display_chord_combo, "Sincronizar selector de acordes")
        self._connect_signal_handler(self.display_scale_combo.currentIndexChanged, "_sync_selector_button_labels", self.display_scale_combo, "Sincronizar selector de escalas")
        self.display_chord_combo.currentIndexChanged.connect(lambda _idx: self._set_display_enabled_from_selection("chord"))
        self.display_scale_combo.currentIndexChanged.connect(lambda _idx: self._set_display_enabled_from_selection("scale"))
        self._connect_signal_handler(self.display_inversion_spin.valueChanged, "_update_display_overlays", self.display_inversion_spin, "Inversión")
        self._connect_signal_handler(self.display_drop_combo.currentIndexChanged, "_update_display_overlays", self.display_drop_combo, "Drop")
        self._connect_signal_handler(self.display_transpose_spin.valueChanged, "_update_display_overlays", self.display_transpose_spin, "Transposición")
        self._connect_display_panel_signals()
        self._connect_keyboard_navigation_signals()

        # Timer para leer MIDI

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.poll_midi)
        self.timer.start(10)

        # Inicializar dispositivos y preferencias
        self._load_interval_settings()
        self._load_staff_settings()
        self._install_visual_state_tracking()
        self.refresh_inputs()
        self._populate_display_controls()
        self._apply_startup_defaults()
        self.load_preferences()
        self._load_default_appearance()
        self._install_shortcuts()
        self.range_changed(fit_window=False)
        self._apply_chord_font()
        self._refresh_learned_chords_ui()
        self._update_display_overlays(show_status=False)
        self._visual_state_tracking_enabled = True
        QTimer.singleShot(0, self._ensure_startup_window_visible)

    def _connect_signal_handler(self, signal, handler_name: str, widget: Optional[QWidget] = None, control_label: str = "control") -> None:
        handler = getattr(self, handler_name, None)
        if callable(handler):
            signal.connect(handler)
            return

        warning = f"[ControlWindow] Handler faltante '{handler_name}' en '{control_label}'. Control deshabilitado."
        print(warning)
        self._show_status_message(warning, timeout_ms=10000)
        if widget is not None:
            widget.setEnabled(False)
            widget.setToolTip(f"Deshabilitado: falta handler '{handler_name}'.")

    def _build_compact_status_label(self) -> QLabel:
        label = QLabel()
        label.setWordWrap(False)
        label.setMinimumHeight(26)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet(
            "QLabel {"
            f"  font-family: {UI_FONT_STACK};"
            "  font-size: 13px;"
            "  color: #1d1d1f;"
            "  background-color: rgba(248, 250, 252, 232);"
            "  border: 1px solid #cbd5e1;"
            "  border-radius: 5px;"
            "  padding: 4px 10px;"
            "}"
        )
        return label

    def _current_keyboard_range_text(self) -> str:
        return f"{midi_to_name(self.piano.start_note)}-{midi_to_name(self.piano.end_note)}"

    def _current_display_status_text(self) -> str:
        root = str(self.display_root_combo.currentText() or "-").strip() or "-"
        chord = str(self.display_chord_combo.currentText() or "-").strip() or "-"
        scale = str(self.display_scale_combo.currentText() or "-").strip() or "-"
        mode_parts = []
        if self.display_chord_checkbox.isChecked() and chord != "-":
            mode_parts.append(f"Acorde {root} {chord}")
        if self.display_scale_checkbox.isChecked() and scale != "-":
            mode_parts.append(f"Escala {root} {scale}")
        mode = " + ".join(mode_parts) if mode_parts else "MIDI en vivo"
        return (
            f"Midi Piano Jaramillo   |   {mode}   |   "
            f"Inv {int(self.display_inversion_spin.value())}   |   "
            f"{self.display_drop_combo.currentText()}   |   "
            f"{int(self.octaves_spin.value())} oct. {self._current_keyboard_range_text()}   |   "
            f"{self._visual_save_state}"
        )

    def _update_status_strip(self) -> None:
        text = self._current_display_status_text()
        if self._last_status_message:
            text = f"{text}   |   {self._last_status_message}"
        for attr in ("main_status_strip", "display_panel_status_strip"):
            label = getattr(self, attr, None)
            if isinstance(label, QLabel):
                label.setText(text)
                label.setToolTip(text)

    def _clear_transient_status_message(self) -> None:
        self._last_status_message = ""
        self._update_status_strip()
        toast = getattr(self, "_status_toast", None)
        if isinstance(toast, QLabel):
            toast.hide()

    def _show_status_toast(self, text: str) -> None:
        parent = self.piano_window
        toast = getattr(self, "_status_toast", None)
        if not isinstance(toast, QLabel):
            toast = QLabel(parent)
            toast.setObjectName("StatusToast")
            toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
            toast.setWordWrap(True)
            toast.setStyleSheet(
                "QLabel#StatusToast {"
                f"  font-family: {UI_FONT_STACK};"
                "  font-size: 12px;"
                "  color: #1d1d1f;"
                "  background-color: rgba(247, 247, 248, 242);"
                "  border: 1px solid #f09a00;"
                "  border-radius: 6px;"
                "  padding: 7px 12px;"
                "}"
            )
            self._status_toast = toast

        toast.setText(str(text))
        toast.setMaximumWidth(max(260, min(560, parent.width() - 32)))
        toast.adjustSize()
        x = max(16, int((parent.width() - toast.width()) / 2))
        y = max(parent.menuBar().height() + 10, 10)
        toast.move(x, y)
        toast.show()
        toast.raise_()

    def _show_status_message(self, text: str, timeout_ms: int = 6000) -> None:
        self._last_status_message = str(text)
        self._status_message_timer.start(max(250, int(timeout_ms)))
        self._update_status_strip()
        if self.piano_window.isVisible():
            self._show_status_toast(str(text))
        window = self.window()
        status_bar = None
        if hasattr(window, "statusBar"):
            try:
                status_bar = window.statusBar()
            except Exception:
                status_bar = None
        if status_bar is not None:
            status_bar.showMessage(str(text), max(0, int(timeout_ms)))
        else:
            print(str(text))

    def _ensure_startup_window_visible(self) -> None:
        if self.view_mode != "single":
            self.show_all_windows()
            return

        screen = self.piano_window.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            geometry = self.piano_window.frameGeometry()
            too_large = geometry.width() > int(area.width() * 0.94) or geometry.height() > int(area.height() * 0.92)
            if not geometry.isValid() or not area.intersects(geometry) or (IS_WINDOWS and too_large):
                if IS_WINDOWS:
                    width = min(WINDOWS_DEFAULT_WIDTH, int(area.width() * 0.92))
                    height = min(WINDOWS_DEFAULT_HEIGHT, int(area.height() * 0.88))
                    width = min(area.width(), max(1040, width))
                    height = min(area.height(), max(680, height))
                else:
                    width = min(max(900, int(area.width() * 0.86)), area.width())
                    height = min(max(640, int(area.height() * 0.86)), area.height())
                x = area.x() + max(0, int((area.width() - width) / 2))
                y = area.y() + max(0, int((area.height() - height) / 2))
                self.piano_window.setGeometry(x, y, width, height)

        self._bring_to_front(self.piano_window)

    def _confirm_action(self, title: str, message: str) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(title or "Confirmar")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        message_label = QLabel(str(message), dialog)
        message_label.setWordWrap(True)
        message_label.setMinimumWidth(380)
        layout.addWidget(message_label)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancelar", dialog)
        confirm_button = QPushButton("Continuar", dialog)
        confirm_button.setObjectName("PrimaryButton")
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(confirm_button)
        layout.addLayout(button_row)

        cancel_button.clicked.connect(dialog.reject)
        confirm_button.clicked.connect(dialog.accept)
        return _dialog_accepted(_exec_popup_dialog(dialog))

    def _prompt_text_foreground(self, title: str, label: str, default_text: str = "") -> Tuple[str, bool]:
        parent = self.window() if isinstance(self.window(), QWidget) else self
        try:
            text, ok = _get_popup_text(parent, title, label, default_text)
        except Exception as exc:
            self._show_status_message(f"Midi learn: no se pudo abrir el diálogo ({exc}).")
            return "", False
        return str(text), bool(ok)

    def _shortcut_definitions(self) -> Dict[str, Tuple[str, str, object]]:
        return {
            "presentation": ("Modo presentación", "Ctrl+Shift+P", self._toggle_presentation_shortcut),
            "rearrange": ("Reacomodar ventanas", "Ctrl+0", self.rearrange_windows),
            "fullscreen": ("Pantalla completa vista única", "F11", self._toggle_single_fullscreen_shortcut),
            "octave_down": ("Teclado una octava abajo", "Ctrl+Left", lambda: self._shift_visible_keyboard_octave(-1)),
            "octave_up": ("Teclado una octava arriba", "Ctrl+Right", lambda: self._shift_visible_keyboard_octave(1)),
            "add_octave": ("Agregar octava visible", "Ctrl+Up", lambda: self._change_visible_octaves(1)),
            "remove_octave": ("Quitar octava visible", "Ctrl+Down", lambda: self._change_visible_octaves(-1)),
            "toggle_scale": ("Mostrar/ocultar escala", "Ctrl+Shift+S", self._toggle_scale_display_shortcut),
            "toggle_chord": ("Mostrar/ocultar acorde", "Ctrl+Shift+C", self._toggle_chord_display_shortcut),
            "keyboard_labels": ("Etiquetas del teclado", "Ctrl+L", self._toggle_keyboard_labels_shortcut),
        }

    def _shortcut_sequence_for(self, key: str) -> str:
        definitions = self._shortcut_definitions()
        default = definitions.get(key, ("", "", None))[1]
        value = str(self._shortcut_overrides.get(key) or default).strip()
        return value

    def _install_shortcuts(self) -> None:
        for shortcut in self._shortcut_objects:
            shortcut.setParent(None)
        self._shortcut_objects = []
        for key, (_label, _default, callback) in self._shortcut_definitions().items():
            sequence = self._shortcut_sequence_for(key)
            if not sequence:
                continue
            try:
                shortcut = QShortcut(QKeySequence(sequence), self.piano_window)
            except Exception:
                continue
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(callback)
            self._shortcut_objects.append(shortcut)
        self._sync_shortcut_action_labels()

    def _shortcut_hint(self, key: str) -> str:
        sequence = self._shortcut_sequence_for(key)
        return f" ({sequence})" if sequence else ""

    def _sync_shortcut_action_labels(self) -> None:
        if hasattr(self, "rearrange_action"):
            self.rearrange_action.setText(f"Reacomodar ventanas{self._shortcut_hint('rearrange')}")
        if hasattr(self, "single_fullscreen_action"):
            self.single_fullscreen_action.setText(
                f"Pantalla completa (vista única){self._shortcut_hint('fullscreen')}"
            )
        if hasattr(self, "presentation_action"):
            self.presentation_action.setText(f"Modo presentación{self._shortcut_hint('presentation')}")
        if hasattr(self, "keyboard_labels_action"):
            self.keyboard_labels_action.setText(f"Etiquetas del teclado{self._shortcut_hint('keyboard_labels')}")
        if hasattr(self, "display_scale_checkbox"):
            self.display_scale_checkbox.setToolTip(f"Atajo: {self._shortcut_sequence_for('toggle_scale')}")
        if hasattr(self, "display_chord_checkbox"):
            self.display_chord_checkbox.setToolTip(f"Atajo: {self._shortcut_sequence_for('toggle_chord')}")

    def _toggle_presentation_shortcut(self) -> None:
        self.presentation_action.setChecked(not self.presentation_action.isChecked())

    def _toggle_single_fullscreen_shortcut(self) -> None:
        if self.view_mode != "single":
            self.set_view_mode("single")
        self.single_fullscreen_action.setChecked(not self.piano_window.isFullScreen())

    def _toggle_scale_display_shortcut(self) -> None:
        self.display_scale_checkbox.setChecked(not self.display_scale_checkbox.isChecked())

    def _toggle_chord_display_shortcut(self) -> None:
        self.display_chord_checkbox.setChecked(not self.display_chord_checkbox.isChecked())

    def _toggle_keyboard_labels_shortcut(self) -> None:
        self.keyboard_labels_action.setChecked(not self.keyboard_labels_action.isChecked())

    def _open_shortcuts_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Atajos de teclado")
        layout = QVBoxLayout(dialog)
        editors: Dict[str, QKeySequenceEdit] = {}

        for key, (label_text, _default, _callback) in self._shortcut_definitions().items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            editor = QKeySequenceEdit(QKeySequence(self._shortcut_sequence_for(key)), dialog)
            editors[key] = editor
            row.addWidget(editor)
            layout.addLayout(row)

        button_row = QHBoxLayout()
        reset_button = QPushButton("Restaurar")
        save_button = QPushButton("Guardar")
        cancel_button = QPushButton("Cancelar")
        button_row.addStretch()
        button_row.addWidget(reset_button)
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        reset_button.clicked.connect(lambda: self._reset_shortcut_editors(editors))
        save_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)

        if not _dialog_accepted(_exec_popup_dialog(dialog)):
            return

        self._shortcut_overrides = {
            key: editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            for key, editor in editors.items()
            if editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        }
        self._install_shortcuts()
        self._schedule_visual_state_save()
        self._show_status_message("Atajos de teclado actualizados.")

    def _reset_shortcut_editors(self, editors: Dict[str, QKeySequenceEdit]) -> None:
        for key, (_label, default, _callback) in self._shortcut_definitions().items():
            editor = editors.get(key)
            if editor is not None:
                editor.setKeySequence(QKeySequence(default))

    def _apply_startup_defaults(self) -> None:
        self._select_combo_value(self.start_combo, DEFAULT_START_NOTE)
        self.octaves_spin.setValue(DEFAULT_OCTAVES)
        self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)
        self.range_changed(fit_window=False)
        self._update_window_actions()

    def _install_visual_state_tracking(self) -> None:
        """Guarda estado visual automáticamente al cerrar/reubicar/redimensionar ventanas."""
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._persist_preferences_on_close)

        for window in (
            self.piano_window,
            self.chord_window,
        ):
            window.installEventFilter(self)

    def _schedule_visual_state_save(self) -> None:
        if not self._visual_state_tracking_enabled or self._is_closing:
            return
        self._visual_save_state = "Guardando..."
        self._update_status_strip()
        if self._visual_state_save_timer.isActive():
            self._visual_state_save_timer.stop()
        self._visual_state_save_timer.start(200)

    def _persist_preferences_on_close(self) -> None:
        self._is_closing = True
        self._persist_visual_state(force=True)

    def _persist_visual_state(self, force: bool = False) -> None:
        if not force and (not self._visual_state_tracking_enabled or self._is_closing):
            return
        if self._visual_state_save_timer.isActive():
            self._visual_state_save_timer.stop()
        self._write_preferences(False)
        self._visual_save_state = "Guardado"
        self._update_status_strip()

    # --- menú de ventanas ---

    def _setup_window_menu(self):
        self.window_menu = self.menu_bar.addMenu("Ventana")

        self.keyboard_action = self.window_menu.addAction("Ocultar Teclado")
        self.keyboard_action.setCheckable(True)
        self.keyboard_action.setChecked(True)
        self.keyboard_action.triggered.connect(
            lambda checked: self._toggle_window_visibility(self.piano_window, checked)
        )

        self.chord_action = self.window_menu.addAction("Ocultar Acordes")
        self.chord_action.setCheckable(True)
        self.chord_action.setChecked(True)
        self.chord_action.triggered.connect(
            lambda checked: self._toggle_window_visibility(self.chord_window, checked)
        )

        self.fretboard_action = self.window_menu.addAction("Vista de guitarra")
        self.fretboard_action.setCheckable(True)
        self.fretboard_action.setChecked(False)
        self.fretboard_action.triggered.connect(
            lambda checked: self._set_instrument_view(
                "guitar" if checked else "piano"
            )
        )

        self.window_menu.addSeparator()
        show_all = self.window_menu.addAction("Mostrar todas")
        show_all.triggered.connect(self.show_all_windows)
        self.rearrange_action = self.window_menu.addAction("Reacomodar ventanas")
        self.rearrange_action.triggered.connect(self.rearrange_windows)

        self.dictionary_menu = self.menu_bar.addMenu("Diccionario")
        learn_chord = self.dictionary_menu.addAction("Aprender nuevo cifrado…")
        learn_chord.triggered.connect(self.start_learning_mode)
        show_learn_panel = self.dictionary_menu.addAction("Ver cifrados aprendidos…")
        show_learn_panel.triggered.connect(lambda: self._show_controls_tab("Aprender"))
        self.dictionary_menu.addSeparator()
        load_dict = self.dictionary_menu.addAction("Cargar diccionario…")
        load_dict.triggered.connect(self.load_chord_dictionary_from_dialog)
        export_dict = self.dictionary_menu.addAction("Exportar diccionario…")
        export_dict.triggered.connect(self.export_chord_dictionary)

        self._setup_view_menu()
        self._setup_display_menus()
        self._setup_controls_menu()
        self._setup_interval_menu()

        QTimer.singleShot(0, self._update_window_actions)

    def _setup_view_menu(self):
        self.visualization_menu = self.menu_bar.addMenu("Visualización")
        self.view_mode_group = QActionGroup(self)
        self.view_mode_group.setExclusive(True)

        self.view_single_action = self.visualization_menu.addAction("Una sola ventana")
        self.view_single_action.setCheckable(True)
        self.view_single_action.setData("single")
        self.view_mode_group.addAction(self.view_single_action)

        self.view_separate_action = self.visualization_menu.addAction("Ventanas separadas")
        self.view_separate_action.setCheckable(True)
        self.view_separate_action.setData("separate")
        self.view_mode_group.addAction(self.view_separate_action)

        self.view_separate_action.setChecked(True)

        self.single_fullscreen_action = self.visualization_menu.addAction("Pantalla completa (vista única)")
        self.single_fullscreen_action.setCheckable(True)
        self.single_fullscreen_action.toggled.connect(self._toggle_single_fullscreen)

        self.presentation_action = self.visualization_menu.addAction("Modo presentación")
        self.presentation_action.setCheckable(True)
        self.presentation_action.toggled.connect(self._toggle_presentation_mode)

        self.view_mode_group.triggered.connect(
            lambda action: self.set_view_mode(str(action.data()))
        )

    def _toggle_single_fullscreen(self, enabled: bool) -> None:
        if self.view_mode != "single":
            self.single_fullscreen_action.blockSignals(True)
            self.single_fullscreen_action.setChecked(False)
            self.single_fullscreen_action.blockSignals(False)
            return

        if enabled:
            self.piano_window.showFullScreen()
        else:
            self.piano_window.showNormal()

    def _toggle_single_fullscreen_from_double_click(self) -> None:
        if self.view_mode != "single":
            return
        self.single_fullscreen_action.setChecked(not self.piano_window.isFullScreen())

    def _toggle_presentation_mode(self, enabled: bool) -> None:
        self._presentation_mode_enabled = bool(enabled)
        if enabled:
            self._presentation_previous_mode = self.view_mode
            self._presentation_previous_fullscreen = self.piano_window.isFullScreen()
            self.set_view_mode("single", persist=False)
            self.display_panel_widget.hide()
            self.keyboard_nav_panel.hide()
            self.menu_bar.hide()
            self.piano_window.showFullScreen()
            self._show_status_message("Modo presentación activado.")
            return

        self.menu_bar.show()
        self.display_panel_widget.show()
        self.keyboard_nav_panel.setVisible(self.instrument_view == "piano")
        if self._presentation_previous_mode == "separate":
            self.set_view_mode("separate", persist=False)
        elif not self._presentation_previous_fullscreen:
            self.piano_window.showNormal()
        self._show_status_message("Modo presentación desactivado.")

    def _window_is_visible(self, window: QMainWindow) -> bool:
        if not window.isVisible():
            return False
        return not bool(window.windowState() & Qt.WindowState.WindowMinimized)

    def _bring_to_front(self, window: QMainWindow):
        window.show()
        window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.raise_()
        window.activateWindow()

    def _toggle_window_visibility(self, window: QMainWindow, checked: bool):
        if checked:
            self._bring_to_front(window)
        else:
            window.hide()
        self._update_window_actions()

    def show_all_windows(self):
        for win in (
            self.piano_window,
            self.chord_window,
        ):
            self._bring_to_front(win)
        self._update_window_actions()

    def rearrange_windows(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.show_all_windows()
            return
        area = screen.availableGeometry()
        margin = 24
        if self.view_mode == "single":
            self._bring_to_front(self.piano_window)
        else:
            top_height = max(260, int(area.height() * 0.42))
            bottom_height = max(180, int(area.height() * 0.24))
            self.chord_window.setGeometry(
                area.x() + margin,
                area.y() + margin,
                max(900, area.width() - margin * 2),
                top_height,
            )
            self.piano_window.setGeometry(
                area.x() + margin,
                area.y() + margin * 2 + top_height,
                max(900, area.width() - margin * 2),
                bottom_height,
            )
            self.show_all_windows()
        self._schedule_visual_state_save()
        self._show_status_message("Ventanas reacomodadas.")

    def _update_window_actions(self):
        keyboard_visible = self._window_is_visible(self.piano_window)
        chords_visible = self._window_is_visible(self.chord_window)
        single_view = self.view_mode == "single"
        instrument_label = "Guitarra" if self.instrument_view == "guitar" else "Teclado"

        self.keyboard_action.blockSignals(True)
        self.keyboard_action.setChecked(keyboard_visible or single_view)
        self.keyboard_action.setText(
            f"{instrument_label} (vista única)"
            if single_view
            else (
                f"Ocultar {instrument_label}"
                if keyboard_visible
                else f"Mostrar {instrument_label}"
            )
        )
        self.keyboard_action.setEnabled(not single_view)
        self.keyboard_action.blockSignals(False)

        self.chord_action.blockSignals(True)
        self.chord_action.setChecked(chords_visible or single_view)
        self.chord_action.setText(
            "Cifrado (vista única)"
            if single_view
            else ("Ocultar Acordes" if chords_visible else "Mostrar Acordes")
        )
        self.chord_action.setEnabled(not single_view)
        self.chord_action.blockSignals(False)

        self.fretboard_action.blockSignals(True)
        self.fretboard_action.setChecked(self.instrument_view == "guitar")
        self.fretboard_action.setText("Vista de guitarra")
        self.fretboard_action.blockSignals(False)

    def _take_window_widget(self, window: QMainWindow) -> Optional[QWidget]:
        widget = window.takeCentralWidget()
        if widget is not None:
            widget.setParent(None)
        return widget

    def _restore_window_widget(self, window: QMainWindow, widget: Optional[QWidget]) -> None:
        if widget is None:
            return
        if window.centralWidget() is None:
            window.setCentralWidget(widget)
        else:
            widget.setParent(window)

    def set_view_mode(self, mode: str, persist: bool = True) -> None:
        if mode not in ("single", "separate"):
            return
        if mode == self.view_mode:
            return

        if mode == "single":
            chord_widget = self._take_window_widget(self.chord_window) or self.chord_window.display_widget
            self.piano_window.piano.set_force_full_width(True)
            self.piano_window.show_combined_view(
                chord_widget,
                self.display_panel_widget,
                self.keyboard_nav_panel,
                self.fretboard_widget,
            )
            self.piano_window.set_combined_background_color(self.single_window_bg_color)
            self.piano_window.set_instrument_view(self.instrument_view)
            self.keyboard_nav_panel.setVisible(self.instrument_view == "piano")
            self._sync_single_window_keyboard_controls()
            self.staff_window.hide()
            self.chord_window.hide()
            self._bring_to_front(self.piano_window)
        else:
            self.piano_window.piano.set_force_full_width(False)
            self._restore_window_widget(self.chord_window, self.chord_window.display_widget)
            self.piano_window._remove_drag_support(self.chord_window.display_widget)
            self.display_panel_widget.setParent(None)
            self.keyboard_nav_panel.setParent(None)
            self.piano_window.show_keyboard_only()
            self.piano_window.set_instrument_view(self.instrument_view)
            self.staff_window.hide()
            self.chord_window.show()
            self._bring_to_front(self.piano_window)

        self.view_mode = mode
        if mode == "single":
            self.view_single_action.setChecked(True)
        else:
            self.view_separate_action.setChecked(True)
            if self.single_fullscreen_action.isChecked():
                self.single_fullscreen_action.blockSignals(True)
                self.single_fullscreen_action.setChecked(False)
                self.single_fullscreen_action.blockSignals(False)
                self.piano_window.showNormal()
        self._apply_single_view_styles(mode == "single")
        if mode != "single":
            self._fit_keyboard_window_to_available_width()
        self._update_window_actions()
        if persist:
            self._write_preferences(False)

    def _apply_single_view_styles(self, enabled: bool) -> None:
        if enabled:
            menu_style = (
                "QMenuBar {"
                "  font-family: 'Avenir Next', 'Helvetica Neue', Arial, sans-serif;"
                "  font-size: 13px;"
                "  background: #f6f6f7;"
                "  color: #1d1d1f;"
                "  border: 1px solid #d8d8dc;"
                "  border-left: none;"
                "  border-right: none;"
                "}"
                "QMenuBar::item {"
                "  background: transparent;"
                "  color: #1d1d1f;"
                "  padding: 5px 11px;"
                "  border-radius: 5px;"
                "  margin: 2px 2px;"
                "}"
                "QMenuBar::item:selected { background: rgba(240, 154, 0, 48); }"
                "QMenuBar::item:pressed { background: #f09a00; color: #1d1d1f; }"
                "QMenu {"
                "  font-family: 'Avenir Next', 'Helvetica Neue', Arial, sans-serif;"
                "  font-size: 13px;"
                "  background-color: #f7f7f8;"
                "  color: #1d1d1f;"
                "  border: 1px solid #c7c7cc;"
                "  padding: 6px;"
                "}"
                "QMenu::item { color: #1d1d1f; padding: 7px 24px 7px 20px; border-radius: 5px; }"
                "QMenu::item:selected { background-color: #f09a00; color: #1d1d1f; }"
                "QMenu::item:disabled { color: #8e8e93; background-color: transparent; }"
                "QMenu::separator { height: 1px; background: #d1d1d6; margin: 5px 8px; }"
            )
            control_style = (
                "QWidget {"
                "  font-family: 'Avenir Next', 'Helvetica Neue', Arial, sans-serif;"
                "  font-size: 13px;"
                "  color: #f5f5f7;"
                "  background-color: transparent;"
                "}"
                "QLabel, QCheckBox { color: #f5f5f7; background-color: transparent; }"
                "QCheckBox { spacing: 7px; }"
                "QCheckBox::indicator {"
                "  width: 16px;"
                "  height: 16px;"
                "  border-radius: 4px;"
                "  border: 1px solid #d0d0d4;"
                "  background-color: #ffffff;"
                "}"
                "QCheckBox::indicator:hover { border-color: #f09a00; }"
                "QCheckBox::indicator:checked {"
                "  background-color: #f09a00;"
                "  border-color: #f09a00;"
                "}"
                "QPushButton, QToolButton, QComboBox, QSpinBox {"
                "  color: #f7f3ed;"
                "  background-color: rgba(255, 255, 255, 34);"
                "  border: 1px solid rgba(255, 255, 255, 70);"
                "  border-radius: 6px;"
                "  padding: 5px 10px;"
                "  min-height: 20px;"
                "}"
                "QPushButton:hover, QToolButton:hover, QComboBox:hover, QSpinBox:hover {"
                "  background-color: rgba(255, 255, 255, 58);"
                "  border-color: #f09a00;"
                "}"
                "QPushButton:pressed, QToolButton:pressed { background-color: rgba(240, 154, 0, 130); }"
                "QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled {"
                "  color: #8a8780;"
                "  background-color: rgba(255, 255, 255, 24);"
                "  border-color: rgba(255, 255, 255, 42);"
                "}"
                "QWidget#DisplayPanel {"
                "  background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #201a14, stop:0.55 #12100d, stop:1 #050505);"
                "  border-bottom: 1px solid rgba(255, 255, 255, 40);"
                "}"
                "QStackedWidget#DisplayPanelStack {"
                "  background-color: transparent;"
                "  border: none;"
                "}"
                "QWidget#PanelPage {"
                "  background-color: rgba(255, 255, 255, 18);"
                "  border: 1px solid rgba(255, 255, 255, 42);"
                "  border-radius: 7px;"
                "}"
                "QLabel#PanelTitle {"
                "  color: #ffffff;"
                "  font-size: 16px;"
                "  font-weight: 700;"
                "  letter-spacing: 0;"
                "}"
                "QLabel#PanelCaption {"
                "  color: #c7c7cc;"
                "  font-size: 12px;"
                "}"
                "QLabel#PanelSectionTitle {"
                "  color: #f09a00;"
                "  font-weight: 700;"
                "  padding-right: 4px;"
                "}"
                "QLabel#ScaleRoleText {"
                "  color: #f5f5f7;"
                "  font-size: 12px;"
                "}"
                "QPushButton#GlassSegmentButton {"
                "  color: #fff7ed;"
                "  background-color: rgba(240, 154, 0, 70);"
                "  border: 1px solid rgba(240, 154, 0, 155);"
                "  border-radius: 5px;"
                "  padding: 7px 18px;"
                "  font-size: 11px;"
                "  font-weight: 700;"
                "}"
                "QPushButton#GlassSegmentButton:hover {"
                "  background-color: rgba(240, 154, 0, 120);"
                "  border-color: #f09a00;"
                "}"
                "QPushButton#GlassSegmentButton:checked {"
                "  color: #1d1d1f;"
                "  background-color: rgba(240, 154, 0, 232);"
                "  border-color: #f09a00;"
                "}"
                "QPushButton#InstrumentSegmentButton {"
                "  color: #f7f3ed;"
                "  background-color: rgba(255, 255, 255, 24);"
                "  border: 1px solid rgba(255, 255, 255, 62);"
                "  border-radius: 5px;"
                "  padding: 5px 13px;"
                "  font-size: 10px;"
                "  font-weight: 700;"
                "}"
                "QPushButton#InstrumentSegmentButton:hover {"
                "  background-color: rgba(240, 154, 0, 90);"
                "  border-color: #f09a00;"
                "}"
                "QPushButton#InstrumentSegmentButton:checked {"
                "  color: #1d1d1f;"
                "  background-color: #f09a00;"
                "  border-color: #f09a00;"
                "}"
                "QToolButton#MenuButton {"
                "  color: #1d1d1f;"
                "  background-color: #fbfbfc;"
                "  border: 1px solid #d0d0d4;"
                "  border-radius: 6px;"
                "  padding: 5px 10px;"
                "}"
                "QToolButton::menu-indicator { image: none; width: 0px; }"
                "QToolButton#MenuButton:hover {"
                "  background-color: #fff7ed;"
                "  border-color: #f09a00;"
                "}"
                "QTabWidget::pane {"
                "  border: 1px solid #d0d0d4;"
                "  border-radius: 7px;"
                "  top: -1px;"
                "}"
                "QTabBar::tab {"
                "  color: #3a3a3c;"
                "  background-color: #eeeeef;"
                "  border: 1px solid #d0d0d4;"
                "  border-bottom: none;"
                "  border-top-left-radius: 7px;"
                "  border-top-right-radius: 7px;"
                "  padding: 7px 20px;"
                "  margin-right: 2px;"
                "}"
                "QTabBar::tab:selected {"
                "  color: #1d1d1f;"
                "  background-color: #f09a00;"
                "  border-color: #f09a00;"
                "}"
                "QTabBar::tab:hover:!selected { background-color: #fff7ed; color: #1d1d1f; }"
                "QComboBox QAbstractItemView {"
                "  background-color: #17130f;"
                "  color: #f7f3ed;"
                "  selection-background-color: #f09a00;"
                "  selection-color: #1d1d1f;"
                "  border: 1px solid rgba(255, 255, 255, 64);"
                "}"
            )
            menu_panel_style = (
                "QWidget {"
                "  font-family: 'Avenir Next', 'Helvetica Neue', Arial, sans-serif;"
                "  font-size: 13px;"
                "  color: #1d1d1f;"
                "  background-color: #f7f7f8;"
                "}"
                "QWidget#ControlWindow { background-color: #f2f2f4; }"
                "QWidget#ControlTabPage, QScrollArea#LearnedChordsScroll, "
                "QScrollArea#LearnedChordsScroll > QWidget > QWidget { background-color: #fbfbfc; }"
                "QLabel, QCheckBox { color: #1d1d1f; background-color: transparent; }"
                "QTabWidget::pane {"
                "  background-color: #fbfbfc;"
                "  border: 1px solid #c7c7cc;"
                "  border-radius: 7px;"
                "  top: -1px;"
                "}"
                "QTabBar::tab {"
                "  color: #3a3a3c;"
                "  background-color: #e8e8eb;"
                "  border: 1px solid #c7c7cc;"
                "  border-bottom: none;"
                "  border-top-left-radius: 7px;"
                "  border-top-right-radius: 7px;"
                "  padding: 7px 20px;"
                "  margin-right: 2px;"
                "}"
                "QTabBar::tab:selected {"
                "  color: #1d1d1f;"
                "  background-color: #f09a00;"
                "  border-color: #d88700;"
                "}"
                "QTabBar::tab:hover:!selected { background-color: #fff3df; color: #1d1d1f; }"
                "QCheckBox::indicator {"
                "  width: 16px;"
                "  height: 16px;"
                "  border-radius: 4px;"
                "  border: 1px solid #8e8e93;"
                "  background-color: #ffffff;"
                "}"
                "QCheckBox::indicator:checked {"
                "  background-color: #f09a00;"
                "  border-color: #b87300;"
                "}"
                "QPushButton, QComboBox, QSpinBox, QFontComboBox, QKeySequenceEdit {"
                "  color: #1d1d1f;"
                "  background-color: #ffffff;"
                "  border: 1px solid #c7c7cc;"
                "  border-radius: 6px;"
                "  padding: 5px 10px;"
                "  min-height: 20px;"
                "}"
                "QPushButton:hover, QComboBox:hover, QSpinBox:hover, QFontComboBox:hover, QKeySequenceEdit:hover {"
                "  background-color: #fff7cc;"
                "  border-color: #f09a00;"
                "}"
                "QPushButton#PrimaryButton { background-color: #f09a00; border-color: #d88700; font-weight: 600; }"
                "QPushButton#PrimaryButton:hover { background-color: #ffad1f; }"
                "QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled {"
                "  color: #8e8e93; background-color: #ececef; border-color: #d1d1d6;"
                "}"
                "QComboBox QAbstractItemView {"
                "  background-color: #ffffff;"
                "  color: #1d1d1f;"
                "  selection-background-color: #f09a00;"
                "  selection-color: #1d1d1f;"
                "}"
            )
            menu_style = menu_style.replace(
                "'Avenir Next', 'Helvetica Neue', Arial, sans-serif", UI_FONT_STACK
            )
            control_style = control_style.replace(
                "'Avenir Next', 'Helvetica Neue', Arial, sans-serif", UI_FONT_STACK
            )
            menu_panel_style = menu_panel_style.replace(
                "'Avenir Next', 'Helvetica Neue', Arial, sans-serif", UI_FONT_STACK
            )
            self.menu_bar.setStyleSheet(menu_style)
            self.setStyleSheet(menu_panel_style)
            self.display_panel_widget.setStyleSheet(control_style)
            self.keyboard_nav_panel.setStyleSheet(control_style)
            for widget in self._menu_panel_widgets:
                widget.setStyleSheet(menu_panel_style)
        else:
            self.menu_bar.setStyleSheet("")
            self.setStyleSheet("")
            self.display_panel_widget.setStyleSheet("")
            self.keyboard_nav_panel.setStyleSheet("")
            for widget in self._menu_panel_widgets:
                widget.setStyleSheet("")

    def _set_absolute_black_backgrounds(self, persist: bool) -> None:
        black = QColor(0, 0, 0)
        self.chord_bg_color = black
        self.chord_window.set_background_color(black)
        self.single_window_bg_color = black
        self.piano_window.set_combined_background_color(black)
        if persist:
            self._write_preferences(False)

    def _setup_interval_menu(self):
        self.interval_menu = self.menu_bar.addMenu("Ver")
        intervals_menu = self.interval_menu.addMenu("Intervalos en teclas")

        font_action = intervals_menu.addAction("Fuente…")
        font_action.triggered.connect(self._choose_interval_font)

        size_action = intervals_menu.addAction("Tamaño…")
        size_action.triggered.connect(self._choose_interval_size)

        color_white_action = intervals_menu.addAction("Color teclas blancas…")
        color_white_action.triggered.connect(lambda: self._choose_interval_color(False))

        color_black_action = intervals_menu.addAction("Color teclas negras…")
        color_black_action.triggered.connect(lambda: self._choose_interval_color(True))

        position_menu = intervals_menu.addMenu("Posición")
        self.interval_position_group_white = QActionGroup(self)
        self.interval_position_group_white.setExclusive(True)
        self.interval_position_actions_white = {}
        self.interval_position_group_black = QActionGroup(self)
        self.interval_position_group_black.setExclusive(True)
        self.interval_position_actions_black = {}
        for text, mode in (
            ("Arriba", "top"),
            ("Centro", "center"),
            ("Abajo", "bottom"),
            ("Abajo 25%", "bottom25"),
        ):
            action_w = position_menu.addAction(f"{text} (blancas)")
            action_w.setCheckable(True)
            action_w.setData((mode, False))
            self.interval_position_group_white.addAction(action_w)
            self.interval_position_actions_white[mode] = action_w

            action_b = position_menu.addAction(f"{text} (negras)")
            action_b.setCheckable(True)
            action_b.setData((mode, True))
            self.interval_position_group_black.addAction(action_b)
            self.interval_position_actions_black[mode] = action_b

        custom_action = position_menu.addAction("Personalizado… (blancas)")
        custom_action.setCheckable(True)
        custom_action.setData(("custom", False))
        self.interval_position_group_white.addAction(custom_action)
        self.interval_position_actions_white["custom"] = custom_action

        custom_action_b = position_menu.addAction("Personalizado… (negras)")
        custom_action_b.setCheckable(True)
        custom_action_b.setData(("custom", True))
        self.interval_position_group_black.addAction(custom_action_b)
        self.interval_position_actions_black["custom"] = custom_action_b

        self.interval_position_group_white.triggered.connect(self._interval_position_selected)
        self.interval_position_group_black.triggered.connect(self._interval_position_selected)

        frame_menu = intervals_menu.addMenu("Marco de etiquetas")
        frame_fill_action = frame_menu.addAction("Color de relleno…")
        frame_fill_action.triggered.connect(self._choose_interval_frame_fill)

        frame_opacity_action = frame_menu.addAction("Opacidad del relleno…")
        frame_opacity_action.triggered.connect(self._choose_interval_frame_opacity)

        frame_border_color_action = frame_menu.addAction("Color del borde…")
        frame_border_color_action.triggered.connect(self._choose_interval_frame_border_color)

        frame_border_width_action = frame_menu.addAction("Grosor del borde…")
        frame_border_width_action.triggered.connect(self._choose_interval_frame_border_width)

    def _build_single_window_menu_strip(self) -> QWidget:
        container = QWidget()
        container.setObjectName("MenuStrip")
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for label, menu in (
            ("Ventana", self.window_menu),
            ("Diccionario", self.dictionary_menu),
            ("Visualización", self.visualization_menu),
            ("Acordes", self.chord_menu),
            ("Escalas", self.scale_menu),
            ("Controles", self.controls_menu),
            ("Ver", self.interval_menu),
        ):
            button = QToolButton()
            button.setObjectName("MenuButton")
            button.setText(label)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setMenu(menu)
            layout.addWidget(button)

        layout.addStretch()
        container.setLayout(layout)
        return container

    def _color_to_stylesheet(self, color: QColor) -> str:
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"

    def _build_scale_role_palette(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout() if IS_WINDOWS else QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for index, role in enumerate(("root", "stable", "tension", "critical")):
            item = QWidget()
            item_layout = QHBoxLayout()
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)

            label_text = self._scale_role_labels.get(role, role)
            button = QPushButton("")
            button.setObjectName("ScaleRoleCircle")
            button.setFixedSize(24, 24)
            button.setToolTip(f"{label_text}: cambiar color")
            button.clicked.connect(lambda _checked=False, selected_role=role: self._choose_scale_role_color(selected_role))
            text_label = QLabel(label_text)
            text_label.setObjectName("ScaleRoleText")
            text_label.setToolTip(label_text)
            self._scale_palette_buttons.append((role, button))
            item_layout.addWidget(button)
            item_layout.addWidget(text_label)
            item.setLayout(item_layout)
            if IS_WINDOWS:
                layout.addWidget(item, index // 2, index % 2)
            else:
                layout.addWidget(item)
        if IS_WINDOWS:
            layout.setColumnStretch(2, 1)
        else:
            layout.addStretch()
        panel.setLayout(layout)
        self._sync_scale_palette_buttons()
        return panel

    def _sync_scale_palette_buttons(self) -> None:
        for role, button in self._scale_palette_buttons:
            color_key = self._role_to_scale_color.get(role, "blue")
            color = QColor(self.display_scale_colors.get(color_key, QColor(60, 120, 240, 200)))
            text_color = "#111827" if color.lightness() > 145 else "#ffffff"
            button.setStyleSheet(
                "QPushButton {"
                f"  background-color: {self._color_to_stylesheet(color)};"
                f"  color: {text_color};"
                "  border: 1px solid rgba(255, 255, 255, 160);"
                "  border-radius: 12px;"
                "  min-width: 24px;"
                "  max-width: 24px;"
                "  min-height: 24px;"
                "  max-height: 24px;"
                "  padding: 0;"
                "}"
                "QPushButton:hover {"
                "  border: 2px solid #f09a00;"
                "}"
            )

    def _choose_scale_role_color(self, role: str) -> None:
        color_key = self._role_to_scale_color.get(role)
        if color_key is None:
            return
        current = QColor(self.display_scale_colors.get(color_key, QColor(60, 120, 240, 200)))
        color = _get_popup_color(self, current, f"Color categoría {self._scale_role_labels.get(role, role)}")
        if not color.isValid():
            return
        color.setAlpha(max(120, color.alpha()))
        self.display_scale_colors[color_key] = QColor(color)
        self._sync_scale_palette_buttons()
        self._update_display_overlays()
        self._schedule_visual_state_save()
        self._show_status_message(f"Color de escala actualizado: {self._scale_role_labels.get(role, role)}.")

    def _build_panel_section_button(self, text: str, index: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("GlassSegmentButton")
        button.setCheckable(True)
        button.setMinimumWidth(126)
        button.clicked.connect(lambda _checked=False, selected_index=index: self._set_display_panel_section(selected_index))
        return button

    def _set_display_panel_section(self, index: int) -> None:
        stack = getattr(self, "display_panel_section_stack", None)
        buttons = getattr(self, "display_panel_section_buttons", [])
        if not isinstance(stack, QStackedWidget):
            return
        index = max(0, min(int(index), stack.count() - 1))
        stack.setCurrentIndex(index)
        for button_index, button in enumerate(buttons):
            if isinstance(button, QPushButton):
                button.blockSignals(True)
                button.setChecked(button_index == index)
                button.blockSignals(False)

    def _build_instrument_view_button(self, text: str, mode: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("InstrumentSegmentButton")
        button.setCheckable(True)
        button.setMinimumWidth(92)
        button.setToolTip(
            "Mostrar teclado" if mode == "piano" else "Mostrar diapasón"
        )
        button.clicked.connect(
            lambda _checked=False, selected_mode=mode: self._set_instrument_view(selected_mode)
        )
        return button

    def _set_instrument_view(
        self,
        mode: str,
        persist: bool = True,
        show_status: bool = True,
    ) -> None:
        if mode not in ("piano", "guitar"):
            return
        self.instrument_view = mode
        self.piano_window.set_instrument_view(mode)

        for button_mode, button in getattr(self, "instrument_view_buttons", []):
            button.blockSignals(True)
            button.setChecked(button_mode == mode)
            button.blockSignals(False)

        nav_panel = getattr(self, "keyboard_nav_panel", None)
        if isinstance(nav_panel, QWidget):
            nav_panel.setVisible(
                mode == "piano"
                and self.view_mode == "single"
                and not self._presentation_mode_enabled
            )

        if hasattr(self, "fretboard_action"):
            self.fretboard_action.blockSignals(True)
            self.fretboard_action.setChecked(mode == "guitar")
            self.fretboard_action.blockSignals(False)

        if persist and self._visual_state_tracking_enabled:
            self._schedule_visual_state_save()
        if show_status:
            self._show_status_message(
                "Vista de guitarra activada."
                if mode == "guitar"
                else "Vista de piano activada.",
                timeout_ms=2200,
            )

    def _build_display_panel(self) -> QWidget:
        panel = ResponsiveWidthWidget()
        panel.setObjectName("DisplayPanel")
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel("Midi Piano Jaramillo")
        title.setObjectName("PanelTitle")
        subtitle = QLabel("consola de visualización")
        subtitle.setObjectName("PanelCaption")
        header_row.addWidget(title)
        header_row.addWidget(subtitle)
        header_row.addStretch()
        self.instrument_view_buttons = [
            ("piano", self._build_instrument_view_button("PIANO", "piano")),
            ("guitar", self._build_instrument_view_button("GUITARRA", "guitar")),
        ]
        for _mode, button in self.instrument_view_buttons:
            header_row.addWidget(button)
        layout.addLayout(header_row)

        self.display_panel_status_strip = self._build_compact_status_label()
        self.display_panel_status_strip.hide()

        section_row = QHBoxLayout()
        section_row.setContentsMargins(0, 2, 0, 2)
        section_row.setSpacing(8)
        section_row.addStretch()
        self.display_panel_section_buttons = [
            self._build_panel_section_button("ACORDES", 0),
            self._build_panel_section_button("ESCALAS", 1),
        ]
        for button in self.display_panel_section_buttons:
            section_row.addWidget(button)
        section_row.addStretch()
        layout.addLayout(section_row)

        self.display_panel_section_stack = QStackedWidget(panel)
        self.display_panel_section_stack.setObjectName("DisplayPanelStack")

        chord_page = QWidget(panel)
        chord_page.setObjectName("PanelPage")
        chord_page_layout = QVBoxLayout()
        chord_page_layout.setContentsMargins(14, 10, 14, 10)
        chord_page_layout.setSpacing(7)
        chord_primary_row = QHBoxLayout()
        chord_primary_row.setSpacing(9)
        self.display_panel_chord_checkbox = QCheckBox("Mostrar acorde")
        self.display_panel_root_combo = QComboBox()
        self.display_panel_root_combo.setFixedWidth(86)
        self.display_panel_chord_combo = QComboBox(panel)
        self.display_panel_chord_combo.setMinimumWidth(230)
        self.display_panel_chord_combo.setMinimumContentsLength(18)
        self.display_panel_chord_combo.setMaxVisibleItems(18)
        self.display_panel_chord_combo.setToolTip("Seleccionar y activar un acorde pregrabado")
        self.display_panel_inversion_spin = QSpinBox()
        self.display_panel_inversion_spin.setRange(-4, 4)
        self.display_panel_inversion_spin.setFixedWidth(58)
        self.display_panel_drop_combo = QComboBox()
        self.display_panel_drop_combo.setFixedWidth(112)
        self.display_panel_drop_combo.addItem("No Drop", "none")
        self.display_panel_drop_combo.addItem("Drop 2", "drop2")
        self.display_panel_drop_combo.addItem("Drop 3", "drop3")
        self.display_panel_drop_combo.addItem("Drop 2-4", "drop2-4")
        chord_primary_row.addWidget(self.display_panel_chord_checkbox)
        chord_primary_row.addSpacing(10)
        chord_primary_row.addWidget(QLabel("Fundamental"))
        chord_primary_row.addWidget(self.display_panel_root_combo)
        chord_primary_row.addWidget(QLabel("Acorde"))
        chord_primary_row.addWidget(self.display_panel_chord_combo)
        chord_primary_row.addStretch()
        chord_page_layout.addLayout(chord_primary_row)

        chord_secondary_row = QHBoxLayout()
        chord_secondary_row.setSpacing(9)
        chord_secondary_row.addWidget(QLabel("Inversión"))
        chord_secondary_row.addWidget(self.display_panel_inversion_spin)
        chord_secondary_row.addWidget(QLabel("Drop"))
        chord_secondary_row.addWidget(self.display_panel_drop_combo)
        chord_secondary_row.addStretch()
        chord_page_layout.addLayout(chord_secondary_row)
        chord_page.setLayout(chord_page_layout)

        scale_page = QWidget(panel)
        scale_page.setObjectName("PanelPage")
        scale_page_layout = QVBoxLayout()
        scale_page_layout.setContentsMargins(14, 10, 14, 10)
        scale_page_layout.setSpacing(7)
        scale_primary_row = QHBoxLayout()
        scale_primary_row.setSpacing(9)
        self.display_panel_scale_checkbox = QCheckBox("Mostrar escala")
        self.display_panel_scale_root_combo = QComboBox()
        self.display_panel_scale_root_combo.setFixedWidth(86)
        self.display_panel_scale_combo = QComboBox(panel)
        self.display_panel_scale_combo.setMinimumWidth(300)
        self.display_panel_scale_combo.setMinimumContentsLength(26)
        self.display_panel_scale_combo.setMaxVisibleItems(18)
        self.display_panel_scale_combo.setToolTip("Seleccionar y activar una escala pregrabada")
        scale_primary_row.addWidget(self.display_panel_scale_checkbox)
        scale_primary_row.addSpacing(10)
        scale_primary_row.addWidget(QLabel("Fundamental"))
        scale_primary_row.addWidget(self.display_panel_scale_root_combo)
        scale_primary_row.addWidget(QLabel("Escala"))
        scale_primary_row.addWidget(self.display_panel_scale_combo)
        scale_primary_row.addStretch()
        scale_page_layout.addLayout(scale_primary_row)
        scale_page_layout.addWidget(self._build_scale_role_palette())
        scale_page.setLayout(scale_page_layout)

        self.display_panel_section_stack.addWidget(chord_page)
        self.display_panel_section_stack.addWidget(scale_page)
        layout.addWidget(self.display_panel_section_stack)
        self._set_display_panel_section(0)

        panel.setLayout(layout)
        self._update_status_strip()
        return panel

    def _build_keyboard_navigation_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("KeyboardNavigationPanel")
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)

        self.single_octave_down_button = QPushButton("←")
        self.single_octave_down_button.setFixedWidth(54)
        self.single_octave_down_button.setToolTip("Desplazar teclado una octava hacia abajo")

        self.single_octaves_minus_button = QPushButton("-")
        self.single_octaves_minus_button.setFixedWidth(42)
        self.single_octaves_minus_button.setToolTip("Quitar una octava visible")

        self.single_octaves_button = QPushButton("")
        self.single_octaves_button.setMinimumWidth(120)
        self.single_octaves_button.setEnabled(False)
        self.single_octaves_button.setToolTip("Cantidad de octavas visibles")

        self.single_octaves_plus_button = QPushButton("+")
        self.single_octaves_plus_button.setFixedWidth(42)
        self.single_octaves_plus_button.setToolTip("Agregar una octava visible")

        self.single_octave_up_button = QPushButton("→")
        self.single_octave_up_button.setFixedWidth(54)
        self.single_octave_up_button.setToolTip("Desplazar teclado una octava hacia arriba")

        layout.addWidget(self.single_octave_down_button)
        layout.addStretch()
        layout.addWidget(self.single_octaves_minus_button)
        layout.addWidget(self.single_octaves_button)
        layout.addWidget(self.single_octaves_plus_button)
        layout.addStretch()
        layout.addWidget(self.single_octave_up_button)

        panel.setLayout(layout)
        self._sync_single_window_keyboard_controls()
        return panel

    def _connect_keyboard_navigation_signals(self) -> None:
        self.single_octave_down_button.clicked.connect(lambda: self._shift_visible_keyboard_octave(-1))
        self.single_octave_up_button.clicked.connect(lambda: self._shift_visible_keyboard_octave(1))
        self.single_octaves_minus_button.clicked.connect(lambda: self._change_visible_octaves(-1))
        self.single_octaves_plus_button.clicked.connect(lambda: self._change_visible_octaves(1))

    def _start_note_fits_octaves(self, start_note: int, octaves: int) -> bool:
        target_octave = note_octave(start_note) + int(octaves)
        if NOTE_NAMES[start_note % 12] != "C":
            target_octave += 1
        return midi_of_C(target_octave) <= MAX_NOTE

    def _single_window_start_notes(self, octaves: Optional[int] = None) -> List[int]:
        starts = [MIN_NOTE] + [midi_of_C(octave) for octave in range(2, 8)]
        if octaves is None:
            return starts
        valid = [note for note in starts if self._start_note_fits_octaves(note, int(octaves))]
        return valid or [MIN_NOTE]

    def _coerce_start_for_visible_octaves(self, octaves: int) -> None:
        starts = self._single_window_start_notes(octaves)
        current = int(self.start_combo.currentData() or DEFAULT_START_NOTE)
        if current in starts:
            return
        lower = [note for note in starts if note <= current]
        next_start = lower[-1] if lower else starts[0]
        self._select_combo_value(self.start_combo, next_start)

    def _shift_visible_keyboard_octave(self, direction: int) -> None:
        starts = self._single_window_start_notes(int(self.octaves_spin.value()))
        current = int(self.start_combo.currentData() or DEFAULT_START_NOTE)
        if current in starts:
            idx = starts.index(current)
            next_idx = idx + (1 if direction > 0 else -1)
        elif direction > 0:
            higher = [idx for idx, note in enumerate(starts) if note > current]
            next_idx = higher[0] if higher else len(starts) - 1
        else:
            lower = [idx for idx, note in enumerate(starts) if note < current]
            next_idx = lower[-1] if lower else 0

        next_idx = max(0, min(len(starts) - 1, next_idx))
        next_start = starts[next_idx]
        if next_start == current:
            self._sync_single_window_keyboard_controls()
            return

        self._select_combo_value(self.start_combo, next_start)
        self.range_changed()
        self._sync_single_window_keyboard_controls()
        self._schedule_visual_state_save()

    def _change_visible_octaves(self, delta: int) -> None:
        current = int(self.octaves_spin.value())
        next_value = max(1, min(7, current + int(delta)))
        if next_value == current:
            self._sync_single_window_keyboard_controls()
            return
        self.octaves_spin.blockSignals(True)
        self.octaves_spin.setValue(next_value)
        self.octaves_spin.blockSignals(False)
        self._coerce_start_for_visible_octaves(next_value)
        self.range_changed()
        self._sync_single_window_keyboard_controls()
        self._schedule_visual_state_save()

    def _cycle_visible_octaves(self) -> None:
        self._change_visible_octaves(1)

    def _sync_single_window_keyboard_controls(self) -> None:
        if not hasattr(self, "single_octaves_button"):
            return
        octave_count = int(self.octaves_spin.value())
        starts = self._single_window_start_notes(octave_count)
        current = int(self.start_combo.currentData() or DEFAULT_START_NOTE)
        suffix = "octava" if octave_count == 1 else "octavas"
        self.single_octaves_button.setText(f"{octave_count} {suffix}")
        self.single_octaves_minus_button.setEnabled(octave_count > 1)
        self.single_octaves_plus_button.setEnabled(octave_count < 7)
        self.single_octave_down_button.setEnabled(any(note < current for note in starts))
        self.single_octave_up_button.setEnabled(any(note > current for note in starts))

    def _connect_display_panel_signals(self) -> None:
        self.display_panel_chord_checkbox.toggled.connect(self._mirror_panel_to_primary)
        self.display_panel_root_combo.currentIndexChanged.connect(self._handle_panel_root_selection_changed)
        self.display_panel_chord_combo.currentIndexChanged.connect(self._handle_panel_chord_selection_changed)
        self.display_panel_inversion_spin.valueChanged.connect(self._mirror_panel_to_primary)
        self.display_panel_drop_combo.currentIndexChanged.connect(self._mirror_panel_to_primary)
        self.display_panel_scale_checkbox.toggled.connect(self._mirror_panel_to_primary)
        self.display_panel_scale_root_combo.currentIndexChanged.connect(self._handle_panel_scale_root_selection_changed)
        self.display_panel_scale_combo.currentIndexChanged.connect(self._handle_panel_scale_selection_changed)

    def _handle_panel_root_selection_changed(self, *_args) -> None:
        self._mirror_panel_to_primary(root_combo=self.display_panel_root_combo)

    def _handle_panel_scale_root_selection_changed(self, *_args) -> None:
        self._mirror_panel_to_primary(root_combo=self.display_panel_scale_root_combo)

    def _handle_panel_chord_selection_changed(self, *_args) -> None:
        self._mirror_panel_to_primary()
        self._set_display_enabled_from_selection("chord")

    def _handle_panel_scale_selection_changed(self, *_args) -> None:
        self._mirror_panel_to_primary()
        self._set_display_enabled_from_selection("scale")

    def _mirror_panel_to_primary(self, *_args, root_combo: Optional[QComboBox] = None) -> None:
        if self._syncing_display_panel:
            return
        self._syncing_display_panel = True
        try:
            selected_root_combo = root_combo or self.display_panel_root_combo
            self.display_chord_checkbox.blockSignals(True)
            self.display_chord_checkbox.setChecked(self.display_panel_chord_checkbox.isChecked())
            self.display_chord_checkbox.blockSignals(False)

            self._select_combo_value(
                self.display_root_combo,
                int(selected_root_combo.currentData() or 0),
            )
            self._select_combo_value(
                self.display_chord_combo,
                str(self.display_panel_chord_combo.currentData() or ""),
            )

            self.display_inversion_spin.blockSignals(True)
            self.display_inversion_spin.setValue(int(self.display_panel_inversion_spin.value()))
            self.display_inversion_spin.blockSignals(False)

            self.display_drop_combo.blockSignals(True)
            self.display_drop_combo.setCurrentIndex(self.display_panel_drop_combo.currentIndex())
            self.display_drop_combo.blockSignals(False)

            self.display_scale_checkbox.blockSignals(True)
            self.display_scale_checkbox.setChecked(self.display_panel_scale_checkbox.isChecked())
            self.display_scale_checkbox.blockSignals(False)

            self.display_scale_combo.blockSignals(True)
            self.display_scale_combo.setCurrentIndex(self.display_panel_scale_combo.currentIndex())
            self.display_scale_combo.blockSignals(False)

        finally:
            self._syncing_display_panel = False

        self._update_display_overlays()

    def _sync_panel_from_primary(self) -> None:
        if self._syncing_display_panel:
            return
        self._syncing_display_panel = True
        try:
            self.display_panel_chord_checkbox.blockSignals(True)
            self.display_panel_chord_checkbox.setChecked(self.display_chord_checkbox.isChecked())
            self.display_panel_chord_checkbox.blockSignals(False)

            self.display_panel_root_combo.blockSignals(True)
            self.display_panel_root_combo.setCurrentIndex(self.display_root_combo.currentIndex())
            self.display_panel_root_combo.blockSignals(False)

            self.display_panel_scale_root_combo.blockSignals(True)
            self.display_panel_scale_root_combo.setCurrentIndex(self.display_root_combo.currentIndex())
            self.display_panel_scale_root_combo.blockSignals(False)

            self.display_panel_chord_combo.blockSignals(True)
            self.display_panel_chord_combo.setCurrentIndex(self.display_chord_combo.currentIndex())
            self.display_panel_chord_combo.blockSignals(False)

            self.display_panel_inversion_spin.blockSignals(True)
            self.display_panel_inversion_spin.setValue(int(self.display_inversion_spin.value()))
            self.display_panel_inversion_spin.blockSignals(False)

            self.display_panel_drop_combo.blockSignals(True)
            self.display_panel_drop_combo.setCurrentIndex(self.display_drop_combo.currentIndex())
            self.display_panel_drop_combo.blockSignals(False)

            self.display_panel_scale_checkbox.blockSignals(True)
            self.display_panel_scale_checkbox.setChecked(self.display_scale_checkbox.isChecked())
            self.display_panel_scale_checkbox.blockSignals(False)

            self.display_panel_scale_combo.blockSignals(True)
            self.display_panel_scale_combo.setCurrentIndex(self.display_scale_combo.currentIndex())
            self.display_panel_scale_combo.blockSignals(False)

            self._sync_selector_button_labels()
        finally:
            self._syncing_display_panel = False

    def _setup_display_menus(self):
        self.chord_menu = PersistentMenu("Acordes", self.menu_bar)
        self.menu_bar.addMenu(self.chord_menu)
        chord_widget = QWidget()
        chord_layout = QVBoxLayout()
        chord_layout.setContentsMargins(8, 6, 8, 6)
        chord_layout.setSpacing(6)

        chord_row1 = QHBoxLayout()
        chord_row1.addWidget(self.display_chord_checkbox)
        chord_row1.addWidget(QLabel("Fundamental:"))
        chord_row1.addWidget(self.display_root_combo)
        chord_row1.addWidget(QLabel("Acorde:"))
        chord_row1.addWidget(self.display_chord_combo)
        chord_row1.addStretch()
        chord_layout.addLayout(chord_row1)

        chord_row2 = QHBoxLayout()
        chord_row2.addWidget(QLabel("Inversión:"))
        chord_row2.addWidget(self.display_inversion_spin)
        chord_row2.addWidget(QLabel("Drops:"))
        chord_row2.addWidget(self.display_drop_combo)
        chord_row2.addStretch()
        chord_layout.addLayout(chord_row2)

        chord_widget.setLayout(chord_layout)
        chord_widget.setMinimumWidth(650)
        self.chord_menu.setMinimumWidth(666)
        chord_action = QWidgetAction(self.chord_menu)
        chord_action.setDefaultWidget(chord_widget)
        self.chord_menu.addAction(chord_action)
        self._menu_panel_widgets.append(chord_widget)

        self.scale_menu = PersistentMenu("Escalas", self.menu_bar)
        self.menu_bar.addMenu(self.scale_menu)
        scale_widget = QWidget()
        scale_layout = QVBoxLayout()
        scale_layout.setContentsMargins(8, 6, 8, 6)
        scale_layout.setSpacing(6)

        scale_row = QHBoxLayout()
        scale_row.addWidget(self.display_scale_checkbox)
        scale_row.addWidget(QLabel("Escala:"))
        scale_row.addWidget(self.display_scale_combo)
        scale_row.addStretch()
        scale_layout.addLayout(scale_row)

        scale_mode_row = QHBoxLayout()
        self.scale_edit_mode_button = QPushButton("Modo edición de categorías: OFF")
        self.scale_edit_mode_button.setCheckable(True)
        self.scale_edit_mode_button.setChecked(False)
        self.scale_edit_mode_button.toggled.connect(self._toggle_scale_edit_mode)
        scale_mode_row.addWidget(self.scale_edit_mode_button)
        scale_mode_row.addStretch()
        scale_layout.addLayout(scale_mode_row)
        scale_layout.addWidget(self._build_scale_role_palette())

        scale_widget.setLayout(scale_layout)
        scale_widget.setMinimumWidth(610)
        self.scale_menu.setMinimumWidth(626)
        scale_action = QWidgetAction(self.scale_menu)
        scale_action.setDefaultWidget(scale_widget)
        self.scale_menu.addAction(scale_action)
        self._menu_panel_widgets.append(scale_widget)

    def _setup_controls_menu(self):
        self.controls_menu = self.menu_bar.addMenu("Controles")
        midi_tab_link = self.controls_menu.addAction("Panel MIDI…")
        midi_tab_link.triggered.connect(lambda: self._show_controls_tab("MIDI"))
        keyboard_tab_link = self.controls_menu.addAction("Panel Teclado…")
        keyboard_tab_link.triggered.connect(lambda: self._show_controls_tab("Teclado"))
        appearance_tab_link = self.controls_menu.addAction("Panel Apariencia…")
        appearance_tab_link.triggered.connect(lambda: self._show_controls_tab("Apariencia"))
        learn_tab_link = self.controls_menu.addAction("Panel Aprender…")
        learn_tab_link.triggered.connect(lambda: self._show_controls_tab("Aprender"))
        self.controls_menu.addSeparator()
        edit_chords_action = self.controls_menu.addAction("Editar etiquetas de acordes…")
        edit_chords_action.triggered.connect(self._edit_chord_labels)
        learn_chord_action = self.controls_menu.addAction("Midi learn: nuevo cifrado…")
        learn_chord_action.triggered.connect(self.start_learning_mode)
        self.keyboard_labels_action = self.controls_menu.addAction("Etiquetas del teclado")
        self.keyboard_labels_action.setCheckable(True)
        self.keyboard_labels_action.setChecked(True)
        self.keyboard_labels_action.toggled.connect(self._toggle_keyboard_labels)
        self.single_window_bg_action = self.controls_menu.addAction("Fondo vista única…")
        self.single_window_bg_action.triggered.connect(self.choose_single_window_background)
        scale_circle_size_action = self.controls_menu.addAction("Tamaño fijo de círculos de escala…")
        scale_circle_size_action.triggered.connect(self._choose_scale_circle_size)
        shortcuts_action = self.controls_menu.addAction("Atajos de teclado…")
        shortcuts_action.triggered.connect(self._open_shortcuts_dialog)
        save_appearance_action = self.controls_menu.addAction("Guardar apariencia actual como predeterminada")
        save_appearance_action.triggered.connect(self.save_default_appearance)

    def _show_controls_tab(self, tab_name: str) -> None:
        tabs = getattr(self, "primary_controls_tabs", None)
        if isinstance(tabs, QTabWidget):
            for index in range(tabs.count()):
                if tabs.tabText(index) == tab_name:
                    tabs.setCurrentIndex(index)
                    break
        self.show()
        self.raise_()
        self.activateWindow()

    def _default_interval_label_settings(self) -> Dict:
        return {
            "font_family": "",
            "font_size": 14,
            "color_white": QColor(Qt.GlobalColor.black),
            "color_black": QColor(Qt.GlobalColor.black),
            "y_anchor_mode_white": "bottom25",
            "y_percent_white": 87.5,
            "y_anchor_mode_black": "center",
            "y_percent_black": 60.0,
            "frame_fill_color": QColor(255, 255, 255),
            "frame_fill_opacity": 0.6,
            "frame_border_color": QColor(0, 0, 0, 180),
            "frame_border_width": 1.0,
        }

    def _load_interval_settings(self):
        settings = self._default_interval_label_settings()
        font_family = self.settings.value("intervals/font_family", "", type=str)
        if font_family:
            settings["font_family"] = font_family

        font_size = self.settings.value("intervals/font_size")
        if isinstance(font_size, (int, float)) and 6 <= int(font_size) <= 300:
            settings["font_size"] = int(font_size)

        color_name_white = self.settings.value("intervals/color_white", "", type=str)
        color_white = QColor(color_name_white)
        if color_white.isValid():
            settings["color_white"] = color_white
        else:
            legacy_color = self.settings.value("intervals/color", "", type=str)
            legacy_qc = QColor(legacy_color)
            if legacy_qc.isValid():
                settings["color_white"] = legacy_qc

        color_name_black = self.settings.value("intervals/color_black", "", type=str)
        color_black = QColor(color_name_black)
        if color_black.isValid():
            settings["color_black"] = color_black
        if IS_LEGACY_QT_MAC and settings["color_black"].lightness() > 190:
            settings["color_black"] = QColor(Qt.GlobalColor.black)

        position_mode_white = self.settings.value("intervals/position_mode_white", "bottom25", type=str)
        settings["y_anchor_mode_white"] = position_mode_white or "bottom25"

        position_mode_black = self.settings.value("intervals/position_mode_black", "center", type=str)
        settings["y_anchor_mode_black"] = position_mode_black or "center"

        y_percent_white = self.settings.value(
            "intervals/y_percent_white", settings.get("y_percent_white", 87.5), type=float
        )
        try:
            settings["y_percent_white"] = float(y_percent_white)
        except Exception:
            pass

        y_percent_black = self.settings.value(
            "intervals/y_percent_black", settings.get("y_percent_black", 60.0), type=float
        )
        try:
            settings["y_percent_black"] = float(y_percent_black)
        except Exception:
            pass

        frame_fill = self.settings.value("intervals/frame_fill_color", "", type=str)
        fill_color = QColor(frame_fill)
        if fill_color.isValid():
            settings["frame_fill_color"] = fill_color

        fill_opacity = self.settings.value(
            "intervals/frame_fill_opacity", settings.get("frame_fill_opacity", 0.6), type=float
        )
        try:
            settings["frame_fill_opacity"] = float(fill_opacity)
        except Exception:
            pass

        border_color_name = self.settings.value("intervals/frame_border_color", "", type=str)
        border_color = QColor(border_color_name)
        if border_color.isValid():
            settings["frame_border_color"] = border_color

        border_width = self.settings.value(
            "intervals/frame_border_width", settings.get("frame_border_width", 1.0), type=float
        )
        try:
            settings["frame_border_width"] = float(border_width)
        except Exception:
            pass

        self.interval_label_settings = settings
        self._apply_interval_settings_to_piano()
        self._sync_interval_position_actions()

    def _default_staff_settings(self) -> Dict[str, object]:
        return StaffWidget.default_staff_settings()

    def _load_staff_settings(self):
        settings = self._default_staff_settings()
        for key, default_value in list(settings.items()):
            value = self.settings.value(f"staff/{key}")
            if value is None:
                continue
            if isinstance(default_value, (int, float)):
                try:
                    settings[key] = float(value)
                except Exception:
                    continue
            else:
                settings[key] = str(value)

        self.staff_settings = settings
        self._apply_staff_settings()

    def _save_staff_settings(self):
        for key, value in self.staff_settings.items():
            if isinstance(value, (int, float)):
                self.settings.setValue(f"staff/{key}", float(value))
            else:
                self.settings.setValue(f"staff/{key}", str(value))

    def _apply_staff_settings(self):
        self.staff_window.widget.apply_staff_settings(self.staff_settings)

    def _prompt_staff_setting(
        self,
        key: str,
        title: str,
        label: str,
        min_value: float,
        max_value: float,
    ):
        current = float(self.staff_settings.get(key, 0.0))
        value, ok = _get_popup_double(
            self,
            title,
            label,
            current,
            min_value,
            max_value,
            2,
        )
        if not ok:
            return
        self.staff_settings[key] = float(value)
        self._apply_staff_settings()
        self._save_staff_settings()

    def _choose_staff_color(self, key: str, title: str):
        current_value = self.staff_settings.get(key, "#000000")
        if isinstance(current_value, QColor):
            current_color = current_value
        else:
            current_color = QColor(str(current_value))
        color = _get_popup_color(self, current_color, title)
        if not color.isValid():
            return
        self.staff_settings[key] = color.name(QColor.NameFormat.HexArgb)
        self._apply_staff_settings()
        self._save_staff_settings()

    def _choose_staff_label_font(self):
        current_family = str(self.staff_settings.get("label_font_family", "")).strip() or "Arial"
        current_font = QFont(current_family)
        font, ok = _get_popup_font(self, current_font, "Fuente etiquetas")
        if not ok:
            return
        self.staff_settings["label_font_family"] = font.family()
        self._apply_staff_settings()
        self._save_staff_settings()

    def _save_interval_settings(self):
        self.settings.setValue("intervals/font_family", self.interval_label_settings.get("font_family", ""))
        self.settings.setValue("intervals/font_size", int(self.interval_label_settings.get("font_size", 14)))
        color_white = self.interval_label_settings.get("color_white", QColor(Qt.GlobalColor.black))
        if isinstance(color_white, str):
            color_white = QColor(color_white)
        color_white_name = (
            color_white.name(QColor.NameFormat.HexArgb)
            if isinstance(color_white, QColor) and color_white.isValid()
            else QColor(Qt.GlobalColor.black).name(QColor.NameFormat.HexArgb)
        )

        color_black = self.interval_label_settings.get("color_black", QColor(Qt.GlobalColor.white))
        if isinstance(color_black, str):
            color_black = QColor(color_black)
        color_black_name = (
            color_black.name(QColor.NameFormat.HexArgb)
            if isinstance(color_black, QColor) and color_black.isValid()
            else QColor(Qt.GlobalColor.white).name(QColor.NameFormat.HexArgb)
        )

        self.settings.setValue("intervals/color_white", color_white_name)
        self.settings.setValue("intervals/color_black", color_black_name)
        self.settings.setValue(
            "intervals/position_mode_white", self.interval_label_settings.get("y_anchor_mode_white", "bottom25")
        )
        self.settings.setValue(
            "intervals/position_mode_black", self.interval_label_settings.get("y_anchor_mode_black", "center")
        )
        self.settings.setValue(
            "intervals/y_percent_white", float(self.interval_label_settings.get("y_percent_white", 87.5))
        )
        self.settings.setValue(
            "intervals/y_percent_black", float(self.interval_label_settings.get("y_percent_black", 60.0))
        )

        frame_fill = self.interval_label_settings.get("frame_fill_color", QColor(255, 255, 255))
        if isinstance(frame_fill, str):
            frame_fill = QColor(frame_fill)
        frame_fill_name = (
            frame_fill.name() if isinstance(frame_fill, QColor) and frame_fill.isValid() else "#ffffff"
        )
        self.settings.setValue("intervals/frame_fill_color", frame_fill_name)

        frame_opacity = float(self.interval_label_settings.get("frame_fill_opacity", 0.6))
        self.settings.setValue("intervals/frame_fill_opacity", frame_opacity)

        border_color = self.interval_label_settings.get("frame_border_color", QColor(0, 0, 0, 180))
        if isinstance(border_color, str):
            border_color = QColor(border_color)
        border_color_name = (
            border_color.name()
            if isinstance(border_color, QColor) and border_color.isValid()
            else "#000000"
        )
        self.settings.setValue("intervals/frame_border_color", border_color_name)

        border_width = float(self.interval_label_settings.get("frame_border_width", 1.0))
        self.settings.setValue("intervals/frame_border_width", border_width)
        self.settings.sync()

    def _apply_interval_settings_to_piano(self):
        self.piano.set_interval_label_style(dict(self.interval_label_settings))

    def _sync_interval_position_actions(self):
        mode_white = self.interval_label_settings.get("y_anchor_mode_white", "bottom25")
        actions_white = getattr(self, "interval_position_actions_white", {})
        for key, action in actions_white.items():
            action.blockSignals(True)
            action.setChecked(key == mode_white)
            action.blockSignals(False)

        mode_black = self.interval_label_settings.get("y_anchor_mode_black", "center")
        actions_black = getattr(self, "interval_position_actions_black", {})
        for key, action in actions_black.items():
            action.blockSignals(True)
            action.setChecked(key == mode_black)
            action.blockSignals(False)

    def _choose_interval_font(self):
        current_family = self.interval_label_settings.get("font_family", "")
        current_font = QFont(current_family) if current_family else QFont()
        font, ok = _get_popup_font(self, current_font, "Fuente para intervalos")
        if not ok:
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["font_family"] = font.family()
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_size(self):
        current_size = int(self.interval_label_settings.get("font_size", 14))
        size, ok = _get_popup_int(
            self,
            "Tamaño de intervalos",
            "Tamaño en puntos:",
            current_size,
            6,
            300,
        )
        if not ok:
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["font_size"] = int(size)
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_color(self, is_black: bool):
        key = "color_black" if is_black else "color_white"
        title = "Color intervalos en teclas negras" if is_black else "Color intervalos en teclas blancas"
        current_color = self.interval_label_settings.get(
            key, QColor(Qt.GlobalColor.white if is_black else Qt.GlobalColor.black)
        )
        if isinstance(current_color, str):
            current_color = QColor(current_color)
        color = _get_popup_color(self, current_color, title)
        if not color.isValid():
            self._sync_interval_position_actions()
            return
        self.interval_label_settings[key] = color
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_fill(self):
        current_fill = self.interval_label_settings.get("frame_fill_color", QColor(255, 255, 255))
        if isinstance(current_fill, str):
            current_fill = QColor(current_fill)
        color = _get_popup_color(self, current_fill, "Color de relleno de etiqueta")
        if not color.isValid():
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_fill_color"] = color
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_opacity(self):
        current_opacity = float(self.interval_label_settings.get("frame_fill_opacity", 0.6))
        opacity, ok = _get_popup_double(
            self,
            "Opacidad de relleno",
            "Valor entre 0 (transparente) y 1 (opaco):",
            current_opacity,
            0.0,
            1.0,
            2,
        )
        if not ok:
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_fill_opacity"] = opacity
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_border_color(self):
        current_color = self.interval_label_settings.get("frame_border_color", QColor(0, 0, 0, 180))
        if isinstance(current_color, str):
            current_color = QColor(current_color)
        color = _get_popup_color(self, current_color, "Color del borde de etiqueta")
        if not color.isValid():
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_border_color"] = color
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_border_width(self):
        current_width = float(self.interval_label_settings.get("frame_border_width", 1.0))
        width, ok = _get_popup_double(
            self,
            "Grosor del borde",
            "Espesor en píxeles:",
            current_width,
            0.0,
            10.0,
            1,
        )
        if not ok:
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_border_width"] = width
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _interval_position_selected(self, action):
        mode, is_black = action.data()
        anchor_key = "y_anchor_mode_black" if is_black else "y_anchor_mode_white"
        percent_key = "y_percent_black" if is_black else "y_percent_white"
        if mode == "custom":
            current_percent = int(self.interval_label_settings.get(percent_key, 87.5))
            percent, ok = _get_popup_int(
                self,
                "Posición personalizada",
                "Porcentaje vertical (0=arriba, 100=abajo):",
                current_percent,
                0,
                100,
            )
            if not ok:
                self._sync_interval_position_actions()
                return
            self.interval_label_settings[anchor_key] = "custom"
            self.interval_label_settings[percent_key] = percent
        else:
            self.interval_label_settings[anchor_key] = mode
            if mode == "bottom25":
                self.interval_label_settings[percent_key] = 87.5
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()
        self._sync_interval_position_actions()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in {
            self.piano_window,
            self.chord_window,
        }:
            if event.type() in {
                QEvent.Type.Move,
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.Hide,
                QEvent.Type.Close,
                QEvent.Type.WindowStateChange,
            }:
                self._schedule_visual_state_save()

            if event.type() in {
                QEvent.Type.WindowStateChange,
                QEvent.Type.Hide,
                QEvent.Type.Show,
            }:
                QTimer.singleShot(0, self._update_window_actions)
        return super().eventFilter(watched, event)

    # --- helpers ---

    def _pattern_signature(self, pattern: Dict) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
        oblig = pattern.get("obligatorias", []) if isinstance(pattern, dict) else []
        opc = pattern.get("opcionales", []) if isinstance(pattern, dict) else []
        return _signature_from_lists(list(oblig), list(opc))

    def _find_pattern_by_signature(
        self, signature: Tuple[Tuple[int, ...], Tuple[int, ...]], include_custom: bool = True
    ) -> Optional[Dict]:
        for ptn in CHORD_PATTERNS:
            if not include_custom and ptn.get("is_custom"):
                continue
            if self._pattern_signature(ptn) == signature:
                return ptn
        return None

    def _remember_additional_base(self, name: str, obligatorias: List[int], opcionales: List[int]):
        signature = _signature_from_lists(obligatorias, opcionales)
        payload = {
            "nombre": name,
            "obligatorias": list(_normalize_intervals(obligatorias)),
            "opcionales": list(sorted({int(ivl) % 12 for ivl in opcionales})),
        }
        if signature in self._additional_base_signatures:
            for stored in self.additional_base_chords:
                if self._pattern_signature(stored) == signature:
                    stored.update(payload)
                    break
        else:
            self._additional_base_signatures.add(signature)
            self.additional_base_chords.append(payload)

    def _add_base_chord(
        self,
        name: str,
        obligatorias: List[int],
        opcionales: Optional[List[int]] = None,
        *,
        source: str = "",
        allow_overwrite: bool = False,
        prompt_on_conflict: bool = False,
        record_extra: bool = False,
    ) -> Optional[Dict]:
        opcionales = opcionales or []
        oblig_norm = _normalize_intervals(obligatorias)
        opc_norm = sorted({int(ivl) % 12 for ivl in opcionales})
        signature = _signature_from_lists(oblig_norm, opc_norm)

        existing_base = self._find_pattern_by_signature(signature, include_custom=False)
        if existing_base is not None:
            if allow_overwrite:
                if prompt_on_conflict:
                    if not self._confirm_action(
                        "Duplicado",
                        (
                            "Ya existe un acorde con esos intervalos en la base. "
                            f"Actual: «{existing_base.get('nombre', '(sin nombre)')}». "
                            f"Nuevo: «{name}». Se sobrescribirá."
                        ),
                    ):
                        return None
                existing_base.update(
                    {
                        "nombre": name,
                        "obligatorias": oblig_norm,
                        "opcionales": opc_norm,
                        "is_custom": False,
                    }
                )
                if record_extra:
                    self._remember_additional_base(name, oblig_norm, opc_norm)
                return existing_base
            if source:
                print(f"Acorde duplicado ignorado desde {source}: {name} {signature}")
            return existing_base

        pattern = {
            "nombre": name,
            "obligatorias": oblig_norm,
            "opcionales": opc_norm,
            "is_custom": False,
        }
        CHORD_PATTERNS.append(pattern)
        if record_extra:
            self._remember_additional_base(name, oblig_norm, opc_norm)
        return pattern

    def _import_dictionary_from_path(
        self, path: Path, record_extra: bool = False, allow_overwrite: bool = False
    ) -> int:
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"No se pudo leer {path}: {e}")
            return 0

        chords = data.get("chords") if isinstance(data, dict) else None
        if not isinstance(chords, list):
            return 0

        added = 0

        for chord in chords:
            if not isinstance(chord, dict):
                continue
            name = chord.get("nombre") or ""
            oblig = chord.get("obligatorias") or []
            opc = chord.get("opcionales") or []
            try:
                if not oblig:
                    continue
                pattern = self._add_base_chord(
                    name,
                    [int(ivl) for ivl in oblig],
                    [int(ivl) for ivl in opc],
                    source=str(path),
                    allow_overwrite=allow_overwrite,
                    record_extra=record_extra,
                )
                if pattern is not None:
                    added += 1
            except Exception:
                continue

        return added

    def _load_external_chord_dictionary(self):
        project_dict = Path(__file__).resolve().parent / "diccionario_acordes.json"
        config_dict = Path.home() / "diccionario_acordes.json"

        # Preferir el diccionario de la carpeta de configuración (editable por el usuario).
        self._import_dictionary_from_path(config_dict, record_extra=True)
        self._import_dictionary_from_path(project_dict, record_extra=False)

    def _select_combo_value(self, combo: QComboBox, value: object):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _load_jazzscope_chord_library(self) -> Dict[str, List[int]]:
        library_path = Path(__file__).resolve().parent / "assets" / "jazzscope_chords.json"
        if not library_path.exists():
            return {}
        try:
            data = json.loads(library_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        cleaned: Dict[str, List[int]] = {}
        for name, intervals in data.items():
            if not isinstance(name, str) or not isinstance(intervals, list):
                continue
            try:
                cleaned[name] = [int(ivl) for ivl in intervals]
            except Exception:
                continue
        return cleaned

    def _populate_display_controls(self):
        def fill_root(combo: QComboBox) -> None:
            if combo.count() == 0:
                for idx, name in enumerate(DETECT_NOTE_NAMES):
                    combo.addItem(name, idx)

        def fill_chords(combo: QComboBox) -> None:
            combo.setMaxVisibleItems(18)
            if combo.count() == 0:
                combo.addItem("-", "")
                for name in sorted(self.jazzscope_chords.keys()):
                    label = name.replace("_", " ")
                    combo.addItem(label, name)

        def fill_scales(combo: QComboBox) -> None:
            combo.setMaxVisibleItems(18)
            if combo.count() == 0:
                combo.addItem("-", "")
                for label, key in SCALE_OPTIONS:
                    combo.addItem(label, key)

        fill_root(self.display_root_combo)
        fill_chords(self.display_chord_combo)
        fill_scales(self.display_scale_combo)

        fill_root(self.display_panel_root_combo)
        fill_root(self.display_panel_scale_root_combo)
        fill_chords(self.display_panel_chord_combo)
        fill_scales(self.display_panel_scale_combo)

        self._sync_selector_button_labels()
        self._sync_panel_from_primary()

    def _sync_selector_button_labels(self, *_args) -> None:
        chord_label = str(self.display_chord_combo.currentText() or "-")
        scale_label = str(self.display_scale_combo.currentText() or "-")
        chord_tip = "Sin acorde seleccionado" if chord_label == "-" else f"Acorde seleccionado: {chord_label}"
        scale_tip = "Sin escala seleccionada" if scale_label == "-" else f"Escala seleccionada: {scale_label}"
        self.display_chord_combo.setToolTip(chord_tip)
        self.display_scale_combo.setToolTip(scale_tip)
        if isinstance(getattr(self, "display_panel_chord_combo", None), QComboBox):
            self.display_panel_chord_combo.setToolTip(chord_tip)
        if isinstance(getattr(self, "display_panel_scale_combo", None), QComboBox):
            self.display_panel_scale_combo.setToolTip(scale_tip)

    def _set_display_enabled_from_selection(self, kind: str) -> None:
        if self._syncing_display_panel:
            return
        if kind == "chord":
            enabled = bool(self.display_chord_combo.currentData())
            self.display_chord_checkbox.setChecked(enabled)
            self._sync_panel_from_primary()
            if enabled:
                self._show_status_message(f"Acorde activado: {self.display_chord_combo.currentText()}.")
            return
        if kind == "scale":
            enabled = bool(self.display_scale_combo.currentData())
            self.display_scale_checkbox.setChecked(enabled)
            self._sync_panel_from_primary()
            if enabled:
                root = str(self.display_root_combo.currentText() or "").strip()
                self._show_status_message(f"Escala activada: {root} {self.display_scale_combo.currentText()}.")

    def _toggle_scale_edit_mode(self, enabled: bool) -> None:
        self.scale_edit_mode_enabled = bool(enabled)
        if hasattr(self, "scale_edit_mode_button"):
            label = "ON" if self.scale_edit_mode_enabled else "OFF"
            self.scale_edit_mode_button.setText(f"Modo edición de categorías: {label}")
        status = "activado" if self.scale_edit_mode_enabled else "desactivado"
        self._show_status_message(f"Modo edición de categorías {status}.")
        if not self.scale_edit_mode_enabled:
            self._schedule_visual_state_save()

    def _choose_scale_circle_size(self) -> None:
        value, ok = _get_popup_int(
            self,
            "Tamaño de círculos de escala",
            "Tamaño fijo (%):",
            int(self.display_scale_circle_size_percent),
            50,
            200,
            5,
        )
        if not ok:
            return
        self.display_scale_circle_size_percent = int(value)
        self.piano.set_scale_circle_size_factor(self.display_scale_circle_size_percent / 100.0)
        self._show_status_message(f"Tamaño de círculos de escala: {self.display_scale_circle_size_percent}%")
        self._schedule_visual_state_save()

    def _next_scale_role(self, role: str) -> str:
        order = ["stable", "tension", "critical"]
        if role not in order:
            return "stable"
        idx = order.index(role)
        return order[(idx + 1) % len(order)]

    def _handle_scale_circle_clicked(self, note: int) -> None:
        if not self.scale_edit_mode_enabled:
            return
        if not self.display_scale_checkbox.isChecked():
            self._show_status_message("Activa 'Mostrar escala' para editar categorías.")
            return
        scale_key = self.display_scale_combo.currentData()
        if not isinstance(scale_key, str) or not scale_key:
            self._show_status_message("Selecciona una escala antes de editar categorías.")
            return
        root_pc = self.display_root_combo.currentData()
        if root_pc is None:
            self._show_status_message("Selecciona una tónica para editar categorías.")
            return
        intervals = SCALE_PATTERNS.get(scale_key)
        if not intervals:
            return
        transpose = int(self.display_transpose_spin.value())
        scale_pcs = build_scale_pcs(root_pc, intervals, transpose)
        degree_idx = degree_index_for_note_pc(note % 12, scale_pcs)
        if degree_idx is None:
            return
        if int(degree_idx) == 0:
            self._show_status_message("La fundamental mantiene siempre su categoría.")
            return
        if note not in self.piano.display_scale_notes:
            return

        current_color = self.piano.display_scale_notes[note]
        current_role = "stable"
        for color_key, color in self.display_scale_colors.items():
            if QColor(color) == QColor(current_color):
                current_role = self._scale_color_to_role.get(color_key, "stable")
                break

        next_role = self._next_scale_role(current_role)
        role_overrides = self.scale_role_overrides.setdefault(scale_key, {})
        role_overrides[int(degree_idx)] = next_role
        self._update_display_overlays()
        self._show_status_message(f"Escala '{self.display_scale_combo.currentText()}': {midi_to_name(note)} -> {next_role}")

    def _category_role_for_scale_note(self, scale_key: str, idx: int, pc: int, scale_pcs: List[int]) -> str:
        if idx == 0:
            return "root"

        overrides = self.scale_role_overrides.get(scale_key, {})
        role_override = overrides.get(idx)
        if role_override not in self._role_to_scale_color:
            role_override = overrides.get(pc)
        if role_override in self._role_to_scale_color:
            return str(role_override)

        if scale_key in SPECIAL_SCALES:
            if idx == 0:
                return "root"
            return "stable"
        if idx in (2, 4, 6):
            return "stable"
        prev_pc = scale_pcs[idx - 1]
        is_semitone = ((pc - prev_pc + 12) % 12) == 1
        if idx in (1, 3, 5) and is_semitone:
            return "critical"
        return "tension"

    def _apply_inversion(self, notes: List[int], inversion: int) -> List[int]:
        result = list(sorted(notes))
        if inversion > 0:
            for _ in range(inversion):
                if not result:
                    break
                note = result.pop(0)
                result.append(note + 12)
        elif inversion < 0:
            for _ in range(-inversion):
                if not result:
                    break
                note = result.pop()
                result.insert(0, note - 12)
        return sorted(result)

    def _apply_drop(self, notes: List[int], drop_type: str) -> List[int]:
        result = list(sorted(notes))
        if drop_type == "none":
            return result
        if drop_type == "drop2" and len(result) >= 3:
            result[-2] -= 12
        elif drop_type == "drop3" and len(result) >= 4:
            result[-3] -= 12
        elif drop_type == "drop2-4" and len(result) >= 4:
            result[-2] -= 12
            result[-4] -= 12
        return sorted(result)

    def _find_minor_ninth_warnings(self, notes: List[int], chord_info: Optional[Dict] = None) -> Set[int]:
        principal_match = chord_info.get("principal_match") if chord_info else None
        if isinstance(principal_match, dict):
            root_pc = principal_match.get("root")
            if root_pc is not None:
                intervals = {((int(note) % 12) - int(root_pc)) % 12 for note in notes}
                if 4 in intervals and 10 in intervals:
                    return set()

        warnings: Set[int] = set()
        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                distance = abs(notes[i] - notes[j])
                if distance >= 13 and distance % 12 == 1:
                    warnings.add(notes[i])
                    warnings.add(notes[j])
        return warnings

    def _update_live_minor_ninth_warnings(self, notes: Set[int], chord_info: Optional[Dict] = None) -> None:
        warnings = self._find_minor_ninth_warnings(sorted(int(note) for note in notes), chord_info)
        self.piano.set_live_warning_notes(warnings, self.display_chord_warning_color)

    @staticmethod
    def _normalized_guitar_chord_name(name: str) -> str:
        normalized = str(name or "").replace(" ", "")
        if "_ó_" in normalized:
            left, right = normalized.split("_ó_", 1)
            normalized = right if left.startswith("phryg.") else left
        aliases = {
            "M": "",
            "maj7": "∆",
            "ø": "m7(b5)",
            "6/9": "6(9)",
            "m∆(9)": "m∆9",
            "º∆(9)": "º∆9",
            "∆9(sus4)": "∆9sus4",
            "∆(9)#11": "∆9(#11)",
            "m∆(9)11": "m∆11",
            "m∆(9)#11": "m∆#11",
            "º∆(9)11": "º∆11",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _guitar_interval_priority(interval: int, present: Set[int]) -> int:
        interval = int(interval) % 12
        if interval == 0:
            return 100
        if interval in (3, 4):
            return 96
        if interval in (10, 11):
            return 95
        if interval in (1, 6, 8):
            return 93
        if interval == 5:
            return 92 if not ({3, 4} & present) else 86
        if interval == 2:
            return 92 if not ({3, 4, 5} & present) else 87
        if interval == 9:
            return 90
        if interval == 7:
            return 70
        return 80

    @classmethod
    def _guitar_chord_required_intervals(
        cls,
        chord_key: str,
        intervals: List[int],
    ) -> List[int]:
        target = {0} | {int(interval) % 12 for interval in intervals}
        normalized_name = cls._normalized_guitar_chord_name(chord_key)
        name_matches = [
            pattern
            for pattern in BASE_CHORD_PATTERNS
            if cls._normalized_guitar_chord_name(str(pattern.get("nombre", "")))
            == normalized_name
        ]
        signature_matches = []
        for pattern in BASE_CHORD_PATTERNS:
            mandatory = {int(value) % 12 for value in pattern.get("obligatorias", [])}
            optional = {int(value) % 12 for value in pattern.get("opcionales", [])}
            if mandatory | optional == target:
                signature_matches.append(pattern)
        matches = name_matches or signature_matches
        if normalized_name.lower().startswith("penta"):
            matches = []

        optional_intervals: Set[int] = set()
        if matches:
            mandatory_sets = [
                {int(value) % 12 for value in pattern.get("obligatorias", [])} & target
                for pattern in matches
            ]
            mandatory = set.intersection(*mandatory_sets) if mandatory_sets else set(target)
            optional_intervals.update(target - mandatory)
            for pattern in matches:
                optional_intervals.update(
                    int(value) % 12
                    for value in pattern.get("opcionales", [])
                    if int(value) % 12 in target
                )

        required = set(target) - optional_intervals
        required.add(0)

        # Antes de usar las seis cuerdas, se prefieren voicings de cuatro o
        # cinco voces. La quinta justa puede omitirse; con tritono, puede
        # omitirse la tercera que el cifrado reconoce como tal.
        if len(required) > 5 and 7 in required:
            required.remove(7)
        if len(required) > 5 and 6 in required:
            labels = {
                interval: interval_label_for_context(
                    interval,
                    required,
                    normalized_name,
                )
                for interval in required
            }
            thirds = [
                interval
                for interval, label in labels.items()
                if label in {"3m", "3M"}
            ]
            if thirds:
                required.remove(thirds[0])

        if len(required) > len(FretboardWidget.OPEN_STRING_MIDI):
            required = set(
                sorted(
                    required,
                    key=lambda interval: (
                        cls._guitar_interval_priority(interval, target),
                        -interval,
                    ),
                    reverse=True,
                )[: len(FretboardWidget.OPEN_STRING_MIDI)]
            )
            required.add(0)
            while len(required) > len(FretboardWidget.OPEN_STRING_MIDI):
                removable = min(
                    (interval for interval in required if interval != 0),
                    key=lambda interval: cls._guitar_interval_priority(interval, target),
                )
                required.remove(removable)
        return sorted(required)

    @classmethod
    def _guitar_chord_voicing(
        cls,
        root_pc: int,
        chord_key: str,
        intervals: List[int],
    ) -> Dict[str, object]:
        required = cls._guitar_chord_required_intervals(chord_key, intervals)
        present = set(required)
        normalized_name = cls._normalized_guitar_chord_name(chord_key)

        if normalized_name.lower().startswith("penta"):
            ordered_intervals: List[int] = []
            for interval in intervals:
                normalized_interval = int(interval) % 12
                if (
                    normalized_interval in required
                    and normalized_interval not in ordered_intervals
                ):
                    ordered_intervals.append(normalized_interval)
            for interval in required:
                if interval not in ordered_intervals:
                    ordered_intervals.append(interval)

            relative_order = [
                (ordered_intervals[index], ordered_intervals[index - 1])
                for index in range(1, len(ordered_intervals))
            ]
            pitch_classes = {
                (int(root_pc) + interval) % 12
                for interval in required
            }
            order_constraints = [
                (
                    (int(root_pc) + upper_interval) % 12,
                    (int(root_pc) + lower_interval) % 12,
                )
                for upper_interval, lower_interval in relative_order
            ]
            result = FretboardWidget.guitar_voicing_for_pitch_classes(
                root_pc,
                pitch_classes,
                order_constraints,
            )
            result["intervals"] = set(required)
            result["voice_order"] = list(ordered_intervals)
            return result

        while required:
            pitch_classes = {(int(root_pc) + interval) % 12 for interval in required}
            labels = {
                interval: interval_label_for_context(
                    interval,
                    set(required),
                    normalized_name,
                )
                for interval in required
            }
            relative_constraints: Set[Tuple[int, int]] = set()

            ninths = [
                interval
                for interval, label in labels.items()
                if label in {"9m", "9M", "9+"}
            ]
            thirds = [
                interval
                for interval, label in labels.items()
                if label in {"3m", "3M"}
            ]
            relative_constraints.update((ninth, 0) for ninth in ninths)
            relative_constraints.update(
                (ninth, third)
                for ninth in ninths
                for third in thirds
                if ninth != third
            )

            elevenths = [
                interval
                for interval, label in labels.items()
                if label in {"11j", "11+"}
            ]
            fifths = [
                interval
                for interval, label in labels.items()
                if label in {"5b", "5j", "5+"}
            ]
            relative_constraints.update(
                (eleventh, fifth)
                for eleventh in elevenths
                for fifth in fifths
                if eleventh != fifth
            )

            thirteenths = [
                interval
                for interval, label in labels.items()
                if label in {"13m", "13"}
            ]
            sevenths = [
                interval
                for interval, label in labels.items()
                if label in {"7b", "7m", "7M"}
            ]
            if (
                "º" in normalized_name
                and ("b13" in normalized_name or "♭13" in normalized_name)
                and 8 in required
                and 9 in required
            ):
                sevenths.append(9)
            relative_constraints.update(
                (thirteenth, seventh)
                for thirteenth in thirteenths
                for seventh in sevenths
                if thirteenth != seventh
            )

            order_constraints = [
                (
                    (int(root_pc) + upper_interval) % 12,
                    (int(root_pc) + lower_interval) % 12,
                )
                for upper_interval, lower_interval in sorted(relative_constraints)
            ]
            result = FretboardWidget.guitar_voicing_for_pitch_classes(
                root_pc,
                pitch_classes,
                order_constraints,
            )
            if result.get("notes"):
                result["intervals"] = set(required)
                return result
            removable = [interval for interval in required if interval != 0]
            if not removable:
                break
            remove_interval = min(
                removable,
                key=lambda interval: cls._guitar_interval_priority(interval, present),
            )
            required.remove(remove_interval)

        return {
            "notes": set(),
            "position": FretboardWidget.MIN_POSITION,
            "placements": [],
            "intervals": set(),
        }

    def _update_display_overlays(self, *_args, show_status: bool = True):
        chord_overlays: Dict[int, QColor] = {}
        chord_interval_labels: Dict[int, str] = {}
        guitar_chord_overlays: Dict[int, QColor] = {}
        guitar_chord_interval_labels: Dict[int, str] = {}
        scale_overlays: Dict[int, QColor] = {}
        guitar_scale_overlays: Dict[int, QColor] = {}
        display_label_parts: List[str] = []
        should_persist = self._visual_state_tracking_enabled and not self._syncing_display_panel

        root_pc = self.display_root_combo.currentData()
        if root_pc is None:
            self.piano.set_display_chord_notes({})
            self.piano.set_display_scale_notes({})
            self.piano.set_display_scale_label("")
            self.fretboard_widget.set_display_overlays({}, {}, {}, None, "")
            self._sync_panel_from_primary()
            self._update_status_strip()
            return

        root_pc = int(root_pc)
        transpose = int(self.display_transpose_spin.value())
        root_label = str(self.display_root_combo.currentText() or "").strip()
        guitar_root_pc = (root_pc + transpose) % 12

        if self.display_chord_checkbox.isChecked():
            chord_key = self.display_chord_combo.currentData()
            intervals = self.jazzscope_chords.get(chord_key, [])
            if intervals:
                chord_name = str(self.display_chord_combo.currentText() or "").strip()
                if chord_name and chord_name != "-":
                    display_label_parts.append(f"{root_label} {chord_name}".strip())
                start_oct = note_octave(self.piano.start_note)
                end_oct = note_octave(self.piano.end_note)
                base_oct = (start_oct + end_oct) // 2
                base_midi = midi_of_C(base_oct) + root_pc
                if base_midi < self.piano.start_note:
                    base_midi += 12 * ((self.piano.start_note - base_midi) // 12 + 1)
                if base_midi > self.piano.end_note:
                    base_midi -= 12 * ((base_midi - self.piano.end_note) // 12 + 1)
                notes = [base_midi + ivl for ivl in intervals]
                notes = self._apply_inversion(notes, int(self.display_inversion_spin.value()))
                drop_type = str(self.display_drop_combo.currentData() or "none")
                notes = self._apply_drop(notes, drop_type)
                notes = [note + transpose for note in notes]
                bass_note = base_midi - 12 + transpose
                if bass_note not in notes:
                    notes.append(bass_note)
                warnings = self._find_minor_ninth_warnings(notes)
                root_candidates = sorted(note for note in notes if note % 12 == root_pc)
                root_note_for_labels = root_candidates[0] if root_candidates else base_midi
                present_intervals = {(note - root_note_for_labels) % 12 for note in notes}
                for note in notes:
                    if self.piano.start_note <= note <= self.piano.end_note:
                        if note in warnings:
                            chord_overlays[note] = QColor(self.display_chord_warning_color)
                        elif note % 12 == root_pc:
                            chord_overlays[note] = QColor(self.display_chord_root_color)
                        else:
                            chord_overlays[note] = QColor(self.display_chord_color)
                        label = interval_label_for_context(
                            (note - root_note_for_labels) % 12,
                            present_intervals,
                            str(chord_key or ""),
                        )
                        if label:
                            chord_interval_labels[note] = label

                guitar_voicing = self._guitar_chord_voicing(
                    guitar_root_pc,
                    str(chord_key or ""),
                    list(intervals),
                )
                guitar_notes = sorted(
                    int(note) for note in guitar_voicing.get("notes", set())
                )
                guitar_present_intervals = {
                    int(interval) % 12
                    for interval in guitar_voicing.get("intervals", set())
                }
                guitar_warnings = self._find_minor_ninth_warnings(guitar_notes)
                for note in guitar_notes:
                    interval = (note - guitar_root_pc) % 12
                    if note in guitar_warnings:
                        guitar_chord_overlays[note] = QColor(
                            self.display_chord_warning_color
                        )
                    elif interval == 0:
                        guitar_chord_overlays[note] = QColor(
                            self.display_chord_root_color
                        )
                    else:
                        guitar_chord_overlays[note] = QColor(self.display_chord_color)
                    label = interval_label_for_context(
                        interval,
                        guitar_present_intervals,
                        str(chord_key or ""),
                    )
                    if label:
                        guitar_chord_interval_labels[note] = label

        if self.display_scale_checkbox.isChecked():
            scale_key = self.display_scale_combo.currentData()
            intervals = SCALE_PATTERNS.get(scale_key or "")
            if intervals:
                scale_name = str(self.display_scale_combo.currentText() or "").strip()
                if scale_name and scale_name != "-":
                    display_label_parts.append(f"{root_label} {scale_name}".strip())
                scale_pcs = build_scale_pcs(root_pc, intervals, transpose)
                scale_notes_with_colors: List[Tuple[int, QColor]] = []
                for idx, pc in enumerate(scale_pcs):
                    role = self._category_role_for_scale_note(str(scale_key), idx, pc, scale_pcs)
                    color_key = self._role_to_scale_color.get(role, "blue")
                    color = self.display_scale_colors[color_key]
                    scale_notes_with_colors.append((idx, QColor(color)))

                octave4_start = midi_of_C(4)
                overlay_start = max(self.piano.start_note, octave4_start)
                first_root_note = overlay_start + ((scale_pcs[0] - (overlay_start % 12)) % 12)

                scale_notes: List[int] = [first_root_note]
                for step in intervals[:-1]:
                    scale_notes.append(scale_notes[-1] + int(step))

                for idx, note in enumerate(scale_notes):
                    if self.piano.start_note <= note <= self.piano.end_note:
                        scale_overlays[note] = QColor(scale_notes_with_colors[idx][1])

                guitar_scale_notes = FretboardWidget.guitar_scale_notes(
                    scale_pcs[0],
                    list(intervals),
                )
                for idx, note in enumerate(guitar_scale_notes):
                    guitar_scale_overlays[note] = QColor(
                        scale_notes_with_colors[idx][1]
                    )

        self.piano.set_display_chord_notes(chord_overlays)
        self.piano.set_display_scale_notes(scale_overlays)
        self.fretboard_widget.set_display_overlays(
            guitar_chord_overlays,
            guitar_scale_overlays,
            guitar_chord_interval_labels,
            guitar_root_pc,
            root_label,
        )
        self.display_chord_interval_labels = chord_interval_labels
        if not self.active_notes and not self.sustained_notes:
            self.piano.set_interval_labels(dict(self.display_chord_interval_labels))
        self.piano.set_display_scale_label("  ·  ".join(display_label_parts))
        self._sync_panel_from_primary()
        self._update_status_strip()
        if should_persist:
            if show_status:
                self._show_status_message("Visualización actualizada.", timeout_ms=2500)
            self._schedule_visual_state_save()

    def _announce_keyboard_range(self) -> None:
        self._show_status_message(
            f"Teclado: {self._current_keyboard_range_text()} ({int(self.octaves_spin.value())} octavas).",
            timeout_ms=3000,
        )

    def _update_display_overlays_with_keyboard_status(self) -> None:
        self._update_display_overlays(show_status=False)
        if self._visual_state_tracking_enabled:
            self._announce_keyboard_range()
            self._schedule_visual_state_save()

    # --- preferencias persistentes ---

    def _appearance_payload(self) -> Dict[str, object]:
        return {
            "base_color_rgba": [
                int(self.piano.base_color.red()),
                int(self.piano.base_color.green()),
                int(self.piano.base_color.blue()),
                int(self.piano.base_color.alpha()),
            ],
            "chord_color_rgba": [
                int(self.chord_text_color.red()),
                int(self.chord_text_color.green()),
                int(self.chord_text_color.blue()),
                int(self.chord_text_color.alpha()),
            ],
            "font_family": self.font_combo.currentFont().family(),
            "font_size": int(self.font_size_spin.value()),
            "keyboard_labels_visible": bool(self.keyboard_labels_action.isChecked()),
            "chord_text_color": self.chord_text_color.name(),
            "chord_background": self.chord_bg_color.name(),
            "single_window_background": self.single_window_bg_color.name(),
            "display_chord_enabled": bool(self.display_chord_checkbox.isChecked()),
            "display_scale_enabled": bool(self.display_scale_checkbox.isChecked()),
            "display_root_pc": int(self.display_root_combo.currentData() or 0),
            "display_chord_type": str(self.display_chord_combo.currentData() or ""),
            "display_scale_type": str(self.display_scale_combo.currentData() or ""),
            "display_scale_circle_size_percent": int(self.display_scale_circle_size_percent),
            "display_scale_colors": {
                str(key): QColor(color).name(QColor.NameFormat.HexArgb)
                for key, color in self.display_scale_colors.items()
            },
            "scale_edit_mode_enabled": bool(self.scale_edit_mode_enabled),
            "scale_role_overrides": {
                str(scale): {str(pc): str(role) for pc, role in overrides.items()}
                for scale, overrides in self.scale_role_overrides.items()
            },
            "display_inversion": int(self.display_inversion_spin.value()),
            "display_drop": str(self.display_drop_combo.currentData() or "none"),
            "display_transpose": 0,
            "view_mode": str(self.view_mode),
            "instrument_view": str(self.instrument_view),
            "start_note": int(self.start_combo.currentData() or DEFAULT_START_NOTE),
            "octaves": int(self.octaves_spin.value()),
            "interval_label_settings": self._serialize_interval_settings(self.interval_label_settings),
            "staff_settings": self._serialize_staff_settings(self.staff_settings),
            "shortcut_overrides": dict(self._shortcut_overrides),
        }

    def save_default_appearance(self) -> None:
        try:
            self.APPEARANCE_CONFIG_PATH.write_text(
                json.dumps(self._appearance_payload(), indent=2), encoding="utf-8"
            )
        except Exception as e:
            self._show_status_message(f"Error: No se pudo guardar la apariencia predeterminada: {e}")
            return

        self._show_status_message(
            "Apariencia guardada: la apariencia actual se usará como estado predeterminado al abrir la app."
        )

    def _load_default_appearance(self) -> None:
        if not self.APPEARANCE_CONFIG_PATH.exists():
            return
        try:
            payload = json.loads(self.APPEARANCE_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        self._apply_appearance_payload(payload)

    def _apply_appearance_payload(self, prefs: Dict[str, object]) -> None:
        self.piano.set_base_color(QColor(240, 154, 0))

        chord_rgba = prefs.get("chord_color_rgba")
        if isinstance(chord_rgba, list) and len(chord_rgba) == 4 and all(isinstance(x, int) for x in chord_rgba):
            self.chord_text_color = QColor(*chord_rgba)
            self.chord_window.set_text_color(self.chord_text_color)

        font_family = prefs.get("font_family")
        if isinstance(font_family, str) and font_family:
            self.font_combo.setCurrentFont(QFont(font_family))

        font_size = prefs.get("font_size")
        if isinstance(font_size, int):
            self.font_size_spin.setValue(max(10, min(160, font_size)))

        chord_text = prefs.get("chord_text_color")
        if isinstance(chord_text, str):
            text_color = QColor(chord_text)
            if text_color.isValid():
                self.chord_text_color = text_color
                self.chord_window.set_text_color(text_color)

        chord_bg = prefs.get("chord_background")
        if isinstance(chord_bg, str):
            bg_color = QColor(chord_bg)
            if bg_color.isValid():
                self.chord_bg_color = bg_color
                self.chord_window.set_background_color(bg_color)

        single_bg = prefs.get("single_window_background")
        if isinstance(single_bg, str):
            bg_color = QColor(single_bg)
            if bg_color.isValid():
                self.single_window_bg_color = bg_color
                self.piano_window.set_combined_background_color(bg_color)

        start_note = prefs.get("start_note")
        if isinstance(start_note, int):
            self._select_combo_value(self.start_combo, max(MIN_NOTE, min(MAX_NOTE, start_note)))

        octaves = prefs.get("octaves")
        if isinstance(octaves, int):
            self.octaves_spin.setValue(max(1, min(7, octaves)))

        display_root = prefs.get("display_root_pc")
        if isinstance(display_root, int):
            self._select_combo_value(self.display_root_combo, display_root % 12)

        display_chord = prefs.get("display_chord_type")
        if isinstance(display_chord, str):
            idx = self.display_chord_combo.findData(display_chord)
            if idx >= 0:
                self.display_chord_combo.setCurrentIndex(idx)

        display_scale = prefs.get("display_scale_type")
        if isinstance(display_scale, str):
            idx = self.display_scale_combo.findData(display_scale)
            if idx >= 0:
                self.display_scale_combo.setCurrentIndex(idx)

        size_percent = prefs.get("display_scale_circle_size_percent")
        if isinstance(size_percent, int):
            self.display_scale_circle_size_percent = max(50, min(200, size_percent))
            self.piano.set_scale_circle_size_factor(self.display_scale_circle_size_percent / 100.0)

        scale_colors = prefs.get("display_scale_colors")
        if isinstance(scale_colors, dict):
            for color_key, value in scale_colors.items():
                if str(color_key) not in self.display_scale_colors or not isinstance(value, str):
                    continue
                color = QColor(value)
                if color.isValid():
                    self.display_scale_colors[str(color_key)] = color
            self._sync_scale_palette_buttons()

        role_overrides = prefs.get("scale_role_overrides")
        if isinstance(role_overrides, dict):
            cleaned_overrides: Dict[str, Dict[int, str]] = {}
            valid_roles = set(self._role_to_scale_color.keys())
            for scale_key, mapping in role_overrides.items():
                if not isinstance(scale_key, str) or not isinstance(mapping, dict):
                    continue
                parsed: Dict[int, str] = {}
                for pc_key, role in mapping.items():
                    try:
                        pc = int(pc_key) % 12
                    except Exception:
                        continue
                    if isinstance(role, str) and role in valid_roles:
                        parsed[pc] = role
                if parsed:
                    cleaned_overrides[scale_key] = parsed
            self.scale_role_overrides = cleaned_overrides

        edit_mode_enabled = prefs.get("scale_edit_mode_enabled")
        if isinstance(edit_mode_enabled, bool):
            self.scale_edit_mode_enabled = edit_mode_enabled
            if hasattr(self, "scale_edit_mode_button"):
                self.scale_edit_mode_button.blockSignals(True)
                self.scale_edit_mode_button.setChecked(edit_mode_enabled)
                self.scale_edit_mode_button.blockSignals(False)
                self._toggle_scale_edit_mode(edit_mode_enabled)

        display_inversion = prefs.get("display_inversion")
        if isinstance(display_inversion, int):
            self.display_inversion_spin.setValue(max(-4, min(4, display_inversion)))

        display_drop = prefs.get("display_drop")
        if isinstance(display_drop, str):
            idx = self.display_drop_combo.findData(display_drop)
            if idx >= 0:
                self.display_drop_combo.setCurrentIndex(idx)

        self.display_transpose_spin.setValue(0)

        display_chord_enabled = prefs.get("display_chord_enabled")
        if isinstance(display_chord_enabled, bool):
            self.display_chord_checkbox.setChecked(display_chord_enabled)

        display_scale_enabled = prefs.get("display_scale_enabled")
        if isinstance(display_scale_enabled, bool):
            self.display_scale_checkbox.setChecked(display_scale_enabled)

        shortcuts = prefs.get("shortcut_overrides")
        if isinstance(shortcuts, dict):
            self._shortcut_overrides = {
                str(key): str(value)
                for key, value in shortcuts.items()
                if isinstance(key, str) and isinstance(value, str)
            }

        interval_settings = prefs.get("interval_label_settings")
        if isinstance(interval_settings, dict):
            self._apply_interval_settings_payload(interval_settings)

        staff_settings = prefs.get("staff_settings")
        if isinstance(staff_settings, dict):
            self.staff_settings = dict(self._default_staff_settings())
            self.staff_settings.update({str(k): v for k, v in staff_settings.items()})
            self._apply_staff_settings()

        self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)
        saved_instrument_view = prefs.get("instrument_view")
        if saved_instrument_view in ("piano", "guitar"):
            self._set_instrument_view(
                str(saved_instrument_view),
                persist=False,
                show_status=False,
            )

        keyboard_labels = prefs.get("keyboard_labels_visible")
        if isinstance(keyboard_labels, bool):
            self.keyboard_labels_action.setChecked(keyboard_labels)
            self.piano.set_keyboard_labels_visible(keyboard_labels)

        self._update_display_overlays()

    def _preferences_payload(self):
        return {
            "midi_in_name": self.input_combo.currentData() or "",
            "start_note": int(self.start_combo.currentData() or DEFAULT_START_NOTE),
            "octaves": int(self.octaves_spin.value()),
            "base_color_rgba": [
                int(self.piano.base_color.red()),
                int(self.piano.base_color.green()),
                int(self.piano.base_color.blue()),
                int(self.piano.base_color.alpha()),
            ],
            "chord_color_rgba": [
                int(self.chord_text_color.red()),
                int(self.chord_text_color.green()),
                int(self.chord_text_color.blue()),
                int(self.chord_text_color.alpha()),
            ],
            "capture_window_ms": int(self.capture_window_spin.value()),
            "font_family": self.font_combo.currentFont().family(),
            "font_size": int(self.font_size_spin.value()),
            "always_on_top": False,
            "keyboard_labels_visible": bool(self.keyboard_labels_action.isChecked()),
            "chord_text_color": self.chord_text_color.name(),
            "chord_background": self.chord_bg_color.name(),
            "single_window_background": self.single_window_bg_color.name(),
            "base_chords": [
                {
                    "nombre": c.get("nombre", ""),
                    "obligatorias": list(_normalize_intervals(c.get("obligatorias", []))),
                    "opcionales": list(sorted({int(ivl) % 12 for ivl in c.get("opcionales", [])})),
                }
                for c in self.additional_base_chords
            ],
            "custom_chords": [
                {
                    "nombre": c.get("nombre", ""),
                    "intervalos": list(c.get("obligatorias", [])),
                }
                for c in self.custom_chords
            ],
            "custom_chord_spellings": [
                {
                    "pcs": list(signature),
                    "labels": [spellings.get(pc, NOTE_NAMES[pc]) for pc in signature],
                }
                for signature, spellings in sorted(self.custom_chord_spellings.items())
            ],
            "custom_chord_quality_spellings": [
                {
                    "quality": quality,
                    "intervals": [
                        {
                            "interval": int(interval),
                            "degree": int(data.get("degree", 1)),
                            "accidental": str(data.get("accidental", "")),
                        }
                        for interval, data in sorted(intervals.items())
                    ],
                }
                for quality, intervals in sorted(self.custom_chord_quality_spellings.items())
            ],
            "display_chord_enabled": bool(self.display_chord_checkbox.isChecked()),
            "display_scale_enabled": bool(self.display_scale_checkbox.isChecked()),
            "display_root_pc": int(self.display_root_combo.currentData() or 0),
            "display_chord_type": str(self.display_chord_combo.currentData() or ""),
            "display_scale_type": str(self.display_scale_combo.currentData() or ""),
            "display_scale_circle_size_percent": int(self.display_scale_circle_size_percent),
            "display_scale_colors": {
                str(key): QColor(color).name(QColor.NameFormat.HexArgb)
                for key, color in self.display_scale_colors.items()
            },
            "scale_edit_mode_enabled": bool(self.scale_edit_mode_enabled),
            "scale_role_overrides": {
                str(scale): {str(pc): str(role) for pc, role in overrides.items()}
                for scale, overrides in self.scale_role_overrides.items()
            },
            "display_inversion": int(self.display_inversion_spin.value()),
            "display_drop": str(self.display_drop_combo.currentData() or "none"),
            "display_transpose": 0,
            "view_mode": str(self.view_mode),
            "instrument_view": str(self.instrument_view),
            "window_visibility": {
                "keyboard": bool(self.piano_window.isVisible()),
                "chords": bool(self.chord_window.isVisible()),
            },
            "interval_label_settings": self._serialize_interval_settings(self.interval_label_settings),
            "staff_settings": self._serialize_staff_settings(self.staff_window.widget.staff_settings),
            "window_geometries": {
                "keyboard": self._geometry_payload_for(self.piano_window),
                "chords": self._geometry_payload_for(self.chord_window),
            },
            "shortcut_overrides": dict(self._shortcut_overrides),
        }

    def _serialize_interval_settings(self, settings: Dict) -> Dict:
        serialized: Dict[str, object] = {}
        for key, value in (settings or {}).items():
            if isinstance(value, QColor):
                serialized[key] = value.name(QColor.NameFormat.HexArgb)
            else:
                serialized[key] = value
        return serialized

    def _serialize_staff_settings(self, settings: Dict) -> Dict:
        return {str(k): v for k, v in (settings or {}).items()}

    def _geometry_payload_for(self, window: QMainWindow) -> Dict[str, int]:
        rect = window.geometry()
        return {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "w": int(rect.width()),
            "h": int(rect.height()),
        }

    def _write_preferences(self, show_message: bool):
        try:
            self.CONFIG_PATH.write_text(
                json.dumps(self._preferences_payload(), indent=2), encoding="utf-8"
            )
        except Exception as e:
            if show_message:
                self._show_status_message(f"Error: No se pudieron guardar las preferencias: {e}")
        else:
            if show_message:
                self._show_status_message("OK: preferencias guardadas correctamente.")

    def export_chord_dictionary(self):
        default_path = str(Path.home() / "diccionario_acordes.json")
        file_path, _ = _get_popup_save_file_name(
            self,
            "Exportar diccionario de acordes",
            default_path,
            "JSON (*.json)",
        )
        if not file_path:
            return

        payload = []
        for ptn in CHORD_PATTERNS:
            oblig = [int(ivl) for ivl in ptn.get("obligatorias", [])]
            opcionales = [int(ivl) for ivl in ptn.get("opcionales", [])]
            payload.append(
                {
                    "nombre": ptn.get("nombre", ""),
                    "root_pc": 0,
                    "root_name": DETECT_NOTE_NAMES[0],
                    "obligatorias": oblig,
                    "opcionales": opcionales,
                    "fuente": "aprendido" if ptn.get("is_custom") else "base",
                }
            )

        try:
            Path(file_path).write_text(
                json.dumps({"chords": payload}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            self._show_status_message(f"Error: no se pudo exportar el diccionario: {e}")
        else:
            self._show_status_message(f"Exportación lista: diccionario exportado en {file_path}")

    def load_chord_dictionary_from_dialog(self):
        file_path, _ = _get_popup_open_file_name(
            self,
            "Cargar diccionario de acordes",
            str(Path.home()),
            "JSON (*.json)",
        )
        if not file_path:
            return

        added = self._import_dictionary_from_path(
            Path(file_path), record_extra=True, allow_overwrite=True
        )
        if added:
            self._write_preferences(False)
        self._show_status_message(
            f"Diccionario cargado en memoria. Acordes agregados o actualizados: {added}."
        )

    def load_preferences(self):
        if not self.CONFIG_PATH.exists():
            self._select_combo_value(self.start_combo, DEFAULT_START_NOTE)
            self.octaves_spin.setValue(DEFAULT_OCTAVES)
            self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)
            self._update_window_actions()
            return
        try:
            prefs = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self._select_combo_value(self.start_combo, DEFAULT_START_NOTE)
        self.octaves_spin.setValue(DEFAULT_OCTAVES)

        start_note = prefs.get("start_note")
        if isinstance(start_note, int):
            self._select_combo_value(self.start_combo, max(MIN_NOTE, min(MAX_NOTE, start_note)))

        octaves = prefs.get("octaves")
        if isinstance(octaves, int):
            self.octaves_spin.setValue(max(1, min(7, octaves)))

        self.piano.set_base_color(QColor(240, 154, 0))

        chord_rgba = prefs.get("chord_color_rgba")
        if (
            isinstance(chord_rgba, list)
            and len(chord_rgba) == 4
            and all(isinstance(x, int) for x in chord_rgba)
        ):
            try:
                self.chord_text_color = QColor(
                    chord_rgba[0], chord_rgba[1], chord_rgba[2], chord_rgba[3]
                )
                self.chord_window.set_chord_color(self.chord_text_color)
            except Exception:
                pass

        font_family = prefs.get("font_family")
        if isinstance(font_family, str) and font_family:
            try:
                self.font_combo.setCurrentFont(QFont(font_family))
            except Exception:
                pass

        font_size = prefs.get("font_size")
        if isinstance(font_size, int) and 10 <= font_size <= 160:
            self.font_size_spin.setValue(int(font_size))

        chord_text = prefs.get("chord_text_color")
        if isinstance(chord_text, str):
            try:
                color = QColor(chord_text)
                if color.isValid():
                    self.chord_text_color = color
                    self.chord_window.set_chord_color(color)
            except Exception:
                pass

        chord_bg = prefs.get("chord_background")
        if isinstance(chord_bg, str):
            bg_color = QColor(chord_bg)
            if bg_color.isValid():
                self.chord_bg_color = bg_color
                self.chord_window.set_background_color(bg_color)

        single_bg = prefs.get("single_window_background")
        if isinstance(single_bg, str):
            bg_color = QColor(single_bg)
            if bg_color.isValid():
                self.single_window_bg_color = bg_color
                self.piano_window.set_combined_background_color(bg_color)

        display_root = prefs.get("display_root_pc")
        if isinstance(display_root, int):
            self._select_combo_value(self.display_root_combo, display_root % 12)

        display_chord = prefs.get("display_chord_type")
        if isinstance(display_chord, str):
            idx = self.display_chord_combo.findData(display_chord)
            if idx >= 0:
                self.display_chord_combo.setCurrentIndex(idx)

        display_scale = prefs.get("display_scale_type")
        if isinstance(display_scale, str):
            idx = self.display_scale_combo.findData(display_scale)
            if idx >= 0:
                self.display_scale_combo.setCurrentIndex(idx)

        size_percent = prefs.get("display_scale_circle_size_percent")
        if isinstance(size_percent, int):
            self.display_scale_circle_size_percent = max(50, min(200, size_percent))
            self.piano.set_scale_circle_size_factor(self.display_scale_circle_size_percent / 100.0)

        role_overrides = prefs.get("scale_role_overrides")
        if isinstance(role_overrides, dict):
            cleaned_overrides: Dict[str, Dict[int, str]] = {}
            valid_roles = set(self._role_to_scale_color.keys())
            for scale_key, mapping in role_overrides.items():
                if not isinstance(scale_key, str) or not isinstance(mapping, dict):
                    continue
                parsed: Dict[int, str] = {}
                for pc_key, role in mapping.items():
                    try:
                        pc = int(pc_key) % 12
                    except Exception:
                        continue
                    if isinstance(role, str) and role in valid_roles:
                        parsed[pc] = role
                if parsed:
                    cleaned_overrides[scale_key] = parsed
            self.scale_role_overrides = cleaned_overrides

        edit_mode_enabled = prefs.get("scale_edit_mode_enabled")
        if isinstance(edit_mode_enabled, bool):
            self.scale_edit_mode_enabled = edit_mode_enabled
            if hasattr(self, "scale_edit_mode_button"):
                self.scale_edit_mode_button.blockSignals(True)
                self.scale_edit_mode_button.setChecked(edit_mode_enabled)
                self.scale_edit_mode_button.blockSignals(False)
                self._toggle_scale_edit_mode(edit_mode_enabled)

        display_inversion = prefs.get("display_inversion")
        if isinstance(display_inversion, int):
            self.display_inversion_spin.setValue(max(-4, min(4, display_inversion)))

        display_drop = prefs.get("display_drop")
        if isinstance(display_drop, str):
            idx = self.display_drop_combo.findData(display_drop)
            if idx >= 0:
                self.display_drop_combo.setCurrentIndex(idx)

        self.display_transpose_spin.setValue(0)

        display_chord_enabled = prefs.get("display_chord_enabled")
        if isinstance(display_chord_enabled, bool):
            self.display_chord_checkbox.setChecked(display_chord_enabled)

        display_scale_enabled = prefs.get("display_scale_enabled")
        if isinstance(display_scale_enabled, bool):
            self.display_scale_checkbox.setChecked(display_scale_enabled)

        self._update_display_overlays()

        interval_settings = prefs.get("interval_label_settings")
        if isinstance(interval_settings, dict):
            self._apply_interval_settings_payload(interval_settings)

        staff_settings = prefs.get("staff_settings")
        if isinstance(staff_settings, dict):
            self.staff_settings = dict(self._default_staff_settings())
            self.staff_settings.update({str(k): v for k, v in staff_settings.items()})
            self._apply_staff_settings()

        self.set_view_mode(DEFAULT_VIEW_MODE, persist=False)
        saved_instrument_view = prefs.get("instrument_view")
        if saved_instrument_view in ("piano", "guitar"):
            self._set_instrument_view(
                str(saved_instrument_view),
                persist=False,
                show_status=False,
            )

        self._restore_window_geometries(prefs)

        visibility = prefs.get("window_visibility")
        if isinstance(visibility, dict):
            if self.view_mode == "separate":
                if not bool(visibility.get("keyboard", True)):
                    self.piano_window.hide()
                if not bool(visibility.get("chords", True)):
                    self.chord_window.hide()
            self._update_window_actions()


        capture_window_ms = prefs.get("capture_window_ms")
        if isinstance(capture_window_ms, int) and 50 <= capture_window_ms <= 10000:
            self.capture_window_ms = capture_window_ms
            self.capture_window_spin.setValue(capture_window_ms)

        self.always_on_top.setChecked(False)

        keyboard_labels = prefs.get("keyboard_labels_visible", True)
        self.keyboard_labels_action.setChecked(bool(keyboard_labels))
        self.piano.set_keyboard_labels_visible(bool(keyboard_labels))

        base_chords = prefs.get("base_chords")
        if isinstance(base_chords, list):
            for item in base_chords:
                name = item.get("nombre") if isinstance(item, dict) else None
                oblig = item.get("obligatorias") if isinstance(item, dict) else None
                opc = item.get("opcionales") if isinstance(item, dict) else []
                if (
                    isinstance(name, str)
                    and name is not None
                    and isinstance(oblig, list)
                    and all(isinstance(x, int) for x in oblig)
                ):
                    self._add_base_chord(
                        name,
                        [int(x) for x in oblig],
                        [int(x) for x in opc] if isinstance(opc, list) else [],
                        allow_overwrite=True,
                        record_extra=True,
                    )

        midi_name = prefs.get("midi_in_name") or ""
        if midi_name:
            idx = self.input_combo.findData(midi_name)
            if idx >= 0:
                self.input_combo.setCurrentIndex(idx)

        custom = prefs.get("custom_chords")
        if isinstance(custom, list):
            for item in custom:
                name = item.get("nombre") if isinstance(item, dict) else None
                intervals = item.get("intervalos") if isinstance(item, dict) else None
                if (
                    isinstance(name, str)
                    and name
                    and isinstance(intervals, list)
                    and all(isinstance(x, int) for x in intervals)
                ):
                    self._register_custom_chord(name, intervals, persist=False)

        custom_spellings = prefs.get("custom_chord_spellings")
        if isinstance(custom_spellings, list):
            for entry in custom_spellings:
                if not isinstance(entry, dict):
                    continue
                pcs = entry.get("pcs")
                labels = entry.get("labels")
                if not (
                    isinstance(pcs, list)
                    and isinstance(labels, list)
                    and all(isinstance(pc, int) for pc in pcs)
                    and all(isinstance(label, str) for label in labels)
                ):
                    continue
                signature = tuple(sorted({int(pc) % 12 for pc in pcs}))
                if len(signature) != len(labels):
                    continue
                spellings = {pc: label for pc, label in zip(signature, labels)}
                self.custom_chord_spellings[signature] = spellings

        quality_spellings = prefs.get("custom_chord_quality_spellings")
        if isinstance(quality_spellings, list):
            for entry in quality_spellings:
                if not isinstance(entry, dict):
                    continue
                quality = entry.get("quality")
                intervals = entry.get("intervals")
                if not isinstance(quality, str) or not isinstance(intervals, list):
                    continue
                interval_map: Dict[int, Dict[str, object]] = {}
                for item in intervals:
                    if not isinstance(item, dict):
                        continue
                    interval = item.get("interval")
                    degree = item.get("degree")
                    if (
                        isinstance(interval, int)
                        and isinstance(degree, int)
                    ):
                        interval_map[int(interval) % 12] = {
                            "degree": int(degree),
                            "accidental": str(item.get("accidental", "")),
                        }
                if interval_map:
                    self.custom_chord_quality_spellings[str(quality)] = interval_map

        # Aplicar rango con las preferencias cargadas
        self.range_changed(fit_window=False)

    def _apply_interval_settings_payload(self, payload: Dict) -> None:
        merged = dict(self._default_interval_label_settings())
        for key, value in payload.items():
            if key in {"color_white", "color_black", "frame_fill_color", "frame_border_color"}:
                color = QColor(value) if isinstance(value, str) else value
                if isinstance(color, QColor) and color.isValid():
                    merged[key] = color
            elif key in {"font_size"}:
                if isinstance(value, int):
                    merged[key] = max(6, min(96, value))
            elif key in {"frame_fill_opacity"}:
                if isinstance(value, (int, float)):
                    merged[key] = max(0.0, min(1.0, float(value)))
            elif key in {"frame_border_width"}:
                if isinstance(value, (int, float)):
                    merged[key] = max(0.0, float(value))
            elif key in {
                "font_family",
                "y_anchor_mode_white",
                "y_anchor_mode_black",
                "y_percent_white",
                "y_percent_black",
            }:
                merged[key] = value
        self.interval_label_settings = merged
        self._apply_interval_settings_to_piano()
        self._sync_interval_position_actions()

    def _toggle_keyboard_labels(self, checked: bool):
        self.piano.set_keyboard_labels_visible(checked)
        self._update_status_strip()
        self._write_preferences(False)

    def _restore_window_geometries(self, prefs: Dict):
        geoms = prefs.get("window_geometries") if isinstance(prefs, dict) else None
        if not isinstance(geoms, dict):
            return

        def rect_from_payload(payload: Dict) -> Optional[QRect]:
            if not isinstance(payload, dict):
                return None
            try:
                x = int(payload.get("x"))
                y = int(payload.get("y"))
                w = int(payload.get("w"))
                h = int(payload.get("h"))
            except Exception:
                return None
            if w <= 0 or h <= 0:
                return None
            return QRect(x, y, w, h)

        self._apply_geometry_if_valid(self.piano_window, rect_from_payload(geoms.get("keyboard")))
        self._apply_geometry_if_valid(self.chord_window, rect_from_payload(geoms.get("chords")))

    def _apply_geometry_if_valid(self, window: QMainWindow, rect: Optional[QRect]):
        if rect is None:
            return

        adjusted = self._clamp_rect_to_visible_area(rect)
        window.setGeometry(adjusted)

    def _clamp_rect_to_visible_area(self, rect: QRect) -> QRect:
        screens = QApplication.screens() or []
        available_rects = [s.availableGeometry() for s in screens if s is not None]
        if not available_rects:
            return rect

        def intersection_area(a: QRect, b: QRect) -> int:
            inter = a.intersected(b)
            return max(0, inter.width()) * max(0, inter.height())

        best_rect = available_rects[0]
        best_area = intersection_area(rect, best_rect)
        for avail in available_rects[1:]:
            area = intersection_area(rect, avail)
            if area > best_area:
                best_area = area
                best_rect = avail

        target = best_rect
        width = min(rect.width(), target.width())
        height = min(rect.height(), target.height())
        max_x = target.left() + target.width() - width
        max_y = target.top() + target.height() - height

        x = max(target.left(), min(rect.x(), max_x))
        y = max(target.top(), min(rect.y(), max_y))

        return QRect(x, y, width, height)

    # --- callbacks UI ---

    def refresh_inputs(self):
        current_name = self.input_combo.currentData()
        self.input_combo.blockSignals(True)
        self.input_combo.clear()
        try:
            # Preferir backend rtmidi si está disponible (especialmente al empaquetar).
            try:
                mido.set_backend("mido.backends.rtmidi")
            except Exception:
                pass
            names = mido.get_input_names()
        except ModuleNotFoundError:
            if not self._midi_backend_error_shown:
                self._midi_backend_error_shown = True
                self._show_status_message(
                    "MIDI no disponible: no se pudo cargar el backend MIDI (python-rtmidi). "
                    "Si corres desde terminal, instala python-rtmidi en tu venv. "
                    "Si es la app empaquetada, recompílala incluyendo mido.backends.rtmidi."
                )
            names = []
        except Exception as e:
            if not self._midi_backend_error_shown:
                self._midi_backend_error_shown = True
                self._show_status_message(f"Error MIDI: no se pudieron listar los dispositivos MIDI: {e}")
            names = []

        if not names:
            self.input_combo.addItem("No hay dispositivos MIDI", None)
        else:
            self.input_combo.addItem("Todos los dispositivos MIDI", self._all_inputs_value)
            for n in names:
                self.input_combo.addItem(n, n)
        self.input_combo.blockSignals(False)

        if current_name:
            idx = self.input_combo.findData(current_name)
            if idx >= 0:
                self.input_combo.setCurrentIndex(idx)
                return

        idx_all = self.input_combo.findData(self._all_inputs_value)
        if idx_all >= 0:
            self.input_combo.setCurrentIndex(idx_all)

        self.change_input()

    def _clear_live_midi_state(self) -> None:
        had_notes = bool(self.active_notes or self.sustained_notes)
        self.active_notes.clear()
        self.sustained_notes.clear()
        self._held_note_sources.clear()
        self._sustain_sources.clear()
        self.note_activation_order.clear()
        self.sustain_on = False
        self.piano.clear_pressed()
        self.piano.clear_sustained()
        if had_notes:
            self._refresh_staff_for_current_notes()

    def _close_midi_inputs(self) -> None:
        ports = []
        if self.midi_in is not None:
            ports.append(self.midi_in)
        ports.extend(port for port in self.midi_inputs if port is not None)

        seen = set()
        for port in ports:
            port_id = id(port)
            if port_id in seen:
                continue
            seen.add(port_id)
            try:
                port.close()
            except Exception:
                pass

        self.midi_in = None
        self.midi_inputs = []
        self._clear_live_midi_state()

    def change_input(self):
        self._close_midi_inputs()

        selected = self.input_combo.currentData()
        if not selected:
            return
        try:
            if selected == self._all_inputs_value:
                names = mido.get_input_names()
                opened = []
                for name in names:
                    try:
                        opened.append(mido.open_input(name))
                    except Exception:
                        continue
                self.midi_inputs = opened
                self.midi_in = opened[0] if opened else None
            else:
                self.midi_in = mido.open_input(selected)
                self.midi_inputs = [self.midi_in]
        except Exception:
            self.midi_in = None
            self.midi_inputs = []

    def range_changed(self, *_args, fit_window: bool = False):
        start = self.start_combo.currentData()
        octaves = self.octaves_spin.value()
        if start is None:
            return
        self.piano.set_range_from_start_and_octaves(int(start), int(octaves))
        self._sync_single_window_keyboard_controls()
        if fit_window:
            self._fit_keyboard_window_to_available_width()
        self._update_display_overlays_with_keyboard_status()

    def _fit_keyboard_window_to_available_width(self):
        if self.view_mode == "single":
            return

        screen = self.piano_window.screen() or QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        current = self.piano_window.geometry()

        keyboard_height = max(120, int(current.height()))
        if self.view_mode == "single":
            keyboard_height = max(120, int(self.piano_window.piano.height()))

        white_notes = [n for n in range(self.piano.start_note, self.piano.end_note + 1) if is_white(n)]
        if white_notes:
            key_width = available.width() / max(1, len(white_notes))
            ideal_keyboard_height = int(key_width * self.piano.key_aspect_ratio)
            keyboard_height = max(120, ideal_keyboard_height)

        if self.view_mode == "single":
            top_min_height = max(
                self.staff_window.widget.minimumSizeHint().height(),
                self.chord_window.display_widget.minimumSizeHint().height(),
            )
            margins = 16
            spacing = 6
            target_height = max(220, top_min_height + keyboard_height + margins + spacing)
        else:
            target_height = keyboard_height

        if self.view_mode == "single":
            target_width = max(720, int(current.width()))
        else:
            target_width = max(720, available.width())
        self.piano_window.resize(target_width, target_height)

    def choose_color(self):
        color = _get_popup_color(self, self.piano.base_color, "Seleccionar color de notas")
        if color.isValid():
            self.piano.base_color = color
            self.piano.update()
            self._write_preferences(False)

    def choose_chord_color(self):
        color = _get_popup_color(self, self.chord_text_color, "Seleccionar color del cifrado")
        if color.isValid():
            self.chord_text_color = color
            self.chord_window.set_chord_color(color)
            self._write_preferences(False)

    def choose_chord_background(self):
        color = _get_popup_color(
            self,
            self.chord_bg_color,
            "Seleccionar fondo de acordes",
        )
        if color.isValid():
            self.chord_bg_color = QColor(color)
            self.chord_window.set_background_color(color)
            self._write_preferences(False)

    def choose_single_window_background(self):
        color = _get_popup_color(
            self,
            self.single_window_bg_color,
            "Seleccionar fondo de la vista única",
        )
        if color.isValid():
            self.single_window_bg_color = QColor(color)
            self.piano_window.set_combined_background_color(color)
            self._write_preferences(False)

    def _apply_chord_font(self):
        family = self.font_combo.currentFont().family()
        size = int(self.font_size_spin.value())
        self.chord_window.set_font_from_family_size(family, size)

    def font_changed(self, qfont):
        self._apply_chord_font()

    def font_size_changed(self, value: int):
        self._apply_chord_font()

    def _apply_on_top_to_window(self, window: QMainWindow, on: bool):
        flags = window.windowFlags()
        if on:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        window.setWindowFlags(flags)

        if on:
            # Restaurar y llevar al frente incluso si estaba minimizada u oculta.
            self._bring_to_front(window)
        elif window.isVisible():
            # setWindowFlags requiere volver a mostrar la ventana para aplicar cambios.
            window.show()

    def toggle_on_top(self, on: bool):
        for win in (self.piano_window, self.chord_window):
            self._apply_on_top_to_window(win, on)

    def _refresh_learned_chords_ui(self):
        while self.learned_chords_layout.count():
            item = self.learned_chords_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.custom_chords:
            label = QLabel("No hay acordes aprendidos.")
            self.learned_chords_layout.addWidget(label)
            return

        for idx, chord in enumerate(self.custom_chords):
            row = QHBoxLayout()
            name = chord.get("nombre", "")
            intervals = chord.get("obligatorias", [])
            label = QLabel(f"{name} — intervalos: {intervals}")
            edit_btn = QPushButton("Editar")
            edit_btn.clicked.connect(lambda _=False, i=idx: self._edit_custom_chord_name(i))
            move_btn = QPushButton("Mover a base")
            move_btn.clicked.connect(lambda _=False, i=idx: self._move_custom_to_base(i))
            delete_btn = QPushButton("Eliminar")
            delete_btn.clicked.connect(lambda _=False, i=idx: self._delete_custom_chord(i))
            row.addWidget(label)
            row.addStretch()
            row.addWidget(edit_btn)
            row.addWidget(move_btn)
            row.addWidget(delete_btn)

            container = QWidget()
            container.setLayout(row)
            self.learned_chords_layout.addWidget(container)

    def _edit_chord_labels(self):
        notes = set(self.active_notes) | set(self.sustained_notes)
        if not notes:
            self._show_status_message("Editar etiquetas: toca un acorde para definir su enarmonía.")
            return

        signature = tuple(sorted({n % 12 for n in notes}))
        chord_info = analizar_cifrado_alternativos(notes)
        principal_match = chord_info.get("principal_match") if chord_info else None
        quality = principal_match.get("nombre") if isinstance(principal_match, dict) else None
        custom_map = self._custom_spelling_for_notes(notes, chord_info)
        if custom_map:
            default_text = " ".join(custom_map.get(pc, NOTE_NAMES[pc]) for pc in signature)
        else:
            default_text = " ".join(NOTE_NAMES[pc] for pc in signature)

        text, ok = _get_popup_text(
            self,
            "Editar etiquetas",
            "Escribe la enarmonía deseada (ej: E Bb D F# A):",
            default_text,
        )
        if not ok:
            return

        raw = str(text).strip()
        if not raw:
            if quality:
                self.custom_chord_quality_spellings.pop(str(quality), None)
            if signature in self.custom_chord_spellings:
                self.custom_chord_spellings.pop(signature, None)
                self._write_preferences(False)
                self._refresh_staff_for_current_notes()
            return

        parsed = self._parse_note_labels(raw)
        if parsed is None:
            self._show_status_message("Etiqueta inválida: usa letras A-G con b/#.")
            return

        pcs = tuple(sorted(parsed.keys()))
        if pcs != signature:
            self._show_status_message("Etiqueta inválida: las notas no coinciden con el acorde tocado.")
            return

        if quality:
            principal = str(chord_info.get("principal") or "")
            root_letter, _accidental = _parse_root_spelling(principal)
            root_pc = principal_match.get("root") if isinstance(principal_match, dict) else None
            if root_letter is not None and root_pc is not None:
                root_index = NOTE_LETTER_TO_INDEX[root_letter]
                interval_spellings: Dict[int, Dict[str, object]] = {}
                for pc, label in parsed.items():
                    letter = label[0].upper()
                    interval = (pc - int(root_pc)) % 12
                    degree = (NOTE_LETTER_TO_INDEX[letter] - root_index + 7) % 7 + 1
                    interval_spellings[interval] = {
                        "degree": degree,
                    }
                self.custom_chord_quality_spellings[str(quality)] = interval_spellings
            else:
                self.custom_chord_spellings[signature] = parsed
        else:
            self.custom_chord_spellings[signature] = parsed
        self._write_preferences(False)
        self._refresh_staff_for_current_notes()

    def _refresh_staff_for_current_notes(self):
        notes = set(self.active_notes) | set(self.sustained_notes)
        self._sync_note_activation_order(notes)
        chord_info = self.chord_window.update_chord(notes)
        if chord_info is not None:
            chord_info["custom_spelling_map"] = self._custom_spelling_for_notes(notes, chord_info)
        self._update_live_minor_ninth_warnings(notes, chord_info)
        self.staff_window.set_notes(notes, chord_info)
        self.fretboard_widget.set_notes(notes, chord_info, self.note_activation_order)
        self._update_interval_labels(notes, chord_info)

    def _sync_note_activation_order(self, notes: Set[int]) -> None:
        active = {int(note) for note in notes}
        self.note_activation_order = [
            note for note in self.note_activation_order if note in active
        ]
        known = set(self.note_activation_order)
        for note in sorted(active):
            if note not in known:
                self.note_activation_order.append(note)
                known.add(note)

    def _parse_note_labels(self, text: str) -> Optional[Dict[int, str]]:
        tokens = [
            token.strip()
            for token in text.replace(",", " ").split()
            if token.strip()
        ]
        if not tokens:
            return None

        parsed: Dict[int, str] = {}
        for token in tokens:
            letter = token[0].upper()
            if letter not in NOTE_LETTER_TO_PC:
                return None
            accidental = token[1:].replace("♯", "#").replace("♭", "b")
            if any(ch not in ("b", "#") for ch in accidental):
                return None
            if len(accidental) > 2:
                return None
            pc = (NOTE_LETTER_TO_PC[letter] + _accidental_offset(accidental)) % 12
            if pc in parsed:
                return None
            parsed[pc] = f"{letter}{accidental}"
        return parsed

    def _custom_spelling_for_notes(
        self,
        notes: Set[int],
        chord_info: Optional[Dict[str, object]] = None,
    ) -> Optional[Dict[int, str]]:
        if not notes:
            return None
        chord_info = chord_info or analizar_cifrado_alternativos(notes)
        principal_match = chord_info.get("principal_match") if chord_info else None
        quality = principal_match.get("nombre") if isinstance(principal_match, dict) else None
        if quality:
            principal = str(chord_info.get("principal") or "")
            root_letter, _accidental = _parse_root_spelling(principal)
            root_pc = principal_match.get("root") if isinstance(principal_match, dict) else None
            interval_spellings = self.custom_chord_quality_spellings.get(str(quality))
            if root_letter is not None and root_pc is not None and interval_spellings:
                root_pc = int(root_pc)
                spellings: Dict[int, str] = {}
                for note in notes:
                    interval = (note - root_pc) % 12
                    custom = interval_spellings.get(interval)
                    if custom:
                        degree = int(custom.get("degree", 1))
                        spellings[note % 12] = spell_note_for_degree_interval(
                            root_letter,
                            root_pc,
                            degree,
                            interval,
                        )
                    else:
                        spellings[note % 12] = spell_note_for_interval(
                            root_letter,
                            root_pc,
                            str(quality),
                            interval,
                        )
                if spellings:
                    return spellings
        signature = tuple(sorted({n % 12 for n in notes}))
        return self.custom_chord_spellings.get(signature)

    def _edit_custom_chord_name(self, index: int):
        if index < 0 or index >= len(self.custom_chords):
            return
        pattern = self.custom_chords[index]
        current_name = pattern.get("nombre", "")
        new_name, ok = _get_popup_text(
            self,
            "Editar cifrado",
            "Nuevo nombre para el acorde:",
            current_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            self._show_status_message("Editar cifrado: el nombre no puede estar vacío.")
            return
        if new_name == current_name:
            return
        pattern["nombre"] = new_name
        self._refresh_learned_chords_ui()
        self._write_preferences(False)

    def _register_custom_chord(self, name: str, intervals: List[int], persist: bool = True):
        unique_intervals = sorted({int(ivl) % 12 for ivl in intervals} | {0})
        pattern = {"nombre": name, "obligatorias": unique_intervals, "opcionales": [], "is_custom": True}
        existing_idx = next(
            (i for i, p in enumerate(self.custom_chords) if sorted(p.get("obligatorias", [])) == unique_intervals),
            None,
        )
        if existing_idx is not None:
            old_name = self.custom_chords[existing_idx].get("nombre", "(sin nombre)")
            if persist and not self._confirm_action(
                "Midi learn",
                f"Ya existe un acorde aprendido con esos intervalos: «{old_name}». "
                f"Se reemplazará por «{name}».",
            ):
                return
            existing_pattern = self.custom_chords[existing_idx]
            existing_pattern.update(pattern)
        else:
            CHORD_PATTERNS.append(pattern)
            self.custom_chords.append(pattern)
        self._refresh_learned_chords_ui()
        if persist:
            self._write_preferences(False)

    def _move_custom_to_base(self, index: int):
        if index < 0 or index >= len(self.custom_chords):
            return
        pattern = self.custom_chords[index]
        oblig = pattern.get("obligatorias", [])
        opc = pattern.get("opcionales", [])
        signature = _signature_from_lists(oblig, opc)
        existing_base = self._find_pattern_by_signature(signature, include_custom=False)

        if existing_base is not None and existing_base is not pattern:
            if not self._confirm_action(
                "Duplicado",
                (
                    "Ya existe un acorde en la base con esos intervalos. "
                    f"Actual: «{existing_base.get('nombre', '(sin nombre)')}». "
                    f"Nuevo: «{pattern.get('nombre', '(sin nombre)')}». Se sobrescribirá."
                ),
            ):
                return
            existing_base.update(
                {
                    "nombre": pattern.get("nombre", ""),
                    "obligatorias": _normalize_intervals(oblig),
                    "opcionales": sorted({int(ivl) % 12 for ivl in opc}),
                    "is_custom": False,
                }
            )
            try:
                CHORD_PATTERNS.remove(pattern)
            except ValueError:
                pass
        else:
            pattern["is_custom"] = False
            if pattern not in CHORD_PATTERNS:
                CHORD_PATTERNS.append(pattern)
        self._remember_additional_base(
            pattern.get("nombre", ""),
            pattern.get("obligatorias", []),
            pattern.get("opcionales", []),
        )
        try:
            self.custom_chords.pop(index)
        except IndexError:
            return
        self._refresh_learned_chords_ui()
        self._write_preferences(False)

    def _delete_custom_chord(self, index: int):
        if index < 0 or index >= len(self.custom_chords):
            return
        pattern = self.custom_chords[index]
        if not self._confirm_action(
            "Eliminar cifrado",
            f"Se eliminará «{pattern.get('nombre', '(sin nombre)')}» del diccionario aprendido.",
        ):
            return
        self.custom_chords.pop(index)
        try:
            CHORD_PATTERNS.remove(pattern)
        except ValueError:
            pass
        self._refresh_learned_chords_ui()
        self._write_preferences(False)

    def _update_interval_labels(self, notas: Set[int], chord_info: Optional[Dict]):
        if not notas:
            self.piano.set_interval_labels(dict(self.display_chord_interval_labels))
            return

        principal_match = chord_info.get("principal_match") if chord_info else None
        if not principal_match:
            self.piano.set_interval_labels({})
            return

        root_pc = principal_match.get("root")
        if root_pc is None:
            self.piano.set_interval_labels({})
            return

        root_candidates = sorted(n for n in notas if n % 12 == root_pc)
        if not root_candidates:
            self.piano.set_interval_labels({})
            return

        root_note = root_candidates[0]
        chord_name = str(principal_match.get("nombre") or "")
        present_intervals = {(int(note) - root_note) % 12 for note in notas}
        labels: Dict[int, str] = {}
        for note in notas:
            interval = (note - root_note) % 12
            label = interval_label_for_context(interval, present_intervals, chord_name)
            if label:
                labels[note] = label

        self.piano.set_interval_labels(labels)

    def start_learning_mode(self):
        if self.learning_chord:
            self._reset_learning_state()
            self._show_status_message("Midi learn: modo aprendizaje cancelado.")
            return

        current_notes = set(self.active_notes) | set(self.sustained_notes)
        if current_notes:
            self.learning_chord = True
            self._set_learn_button_text("Midi learn: capturando acorde…")
            self._complete_learning_with_notes(current_notes)
            return

        self.learning_chord = True
        self.learning_waiting_first_note = True
        self._set_learn_button_text("Midi learn: esperando acorde…")
        self._show_midi_learn_start_dialog()
        self._show_status_message(
            "Midi learn: toca y sostén el acorde en tu teclado MIDI. Al capturarlo, escribe el cifrado en la ventana."
        )

    def _show_midi_learn_start_dialog(self) -> None:
        existing = getattr(self, "midi_learn_help_dialog", None)
        if isinstance(existing, QDialog) and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        parent = self.window() if isinstance(self.window(), QWidget) else self
        dialog = QDialog(parent)
        dialog.setWindowTitle("Midi learn: esperando acorde")
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        dialog.setStyleSheet(
            "QDialog {"
            "  background-color: #f7f7f8;"
            "  color: #1d1d1f;"
            f"  font-family: {UI_FONT_STACK};"
            "  font-size: 13px;"
            "}"
            "QLabel { color: #1d1d1f; background-color: transparent; }"
            "QPushButton {"
            "  color: #1d1d1f;"
            "  background-color: #ffffff;"
            "  border: 1px solid #b8b8bd;"
            "  border-radius: 6px;"
            "  padding: 6px 14px;"
            "  min-width: 72px;"
            "}"
            "QPushButton:hover { background-color: #fff3df; border-color: #f09a00; }"
            "QPushButton:pressed { background-color: #f09a00; }"
        )

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Midi learn está activo", dialog)
        title_font = ui_font(16, QFont.Weight.DemiBold)
        title.setFont(title_font)
        layout.addWidget(title)

        instructions = QLabel(
            "1. Toca y sostén el acorde que quieres aprender.\n"
            "2. La app capturará las notas desde el primer NOTE ON.\n"
            "3. Luego se abrirá otra ventana para escribir el cifrado.\n\n"
            "Si ya estabas tocando un acorde antes de activar Midi learn, vuelve a presionar el botón para capturarlo directamente.",
            dialog,
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        button_row = QHBoxLayout()
        close_button = QPushButton("Entendido", dialog)
        cancel_button = QPushButton("Cancelar aprendizaje", dialog)
        close_button.clicked.connect(dialog.close)
        cancel_button.clicked.connect(lambda: (self._reset_learning_state(), dialog.close()))
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        dialog.resize(460, dialog.sizeHint().height())
        self.midi_learn_help_dialog = dialog
        _raise_dialog_parent(parent)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _close_midi_learn_start_dialog(self) -> None:
        dialog = getattr(self, "midi_learn_help_dialog", None)
        if isinstance(dialog, QDialog):
            dialog.close()
        self.midi_learn_help_dialog = None

    def _complete_learning_with_notes(self, notas):
        self._reset_learning_state()
        if not notas:
            self._show_status_message("Midi learn: no se detectaron notas para aprender.")
            return

        ordenadas = sorted(set(int(n) for n in notas))
        if len(ordenadas) < 2:
            self._show_status_message("Midi learn: el cifrado necesita al menos dos notas del acorde.")
            return

        root_note = ordenadas[0]
        intervals = [(n - root_note) % 12 for n in ordenadas]
        note_names = ", ".join(midi_to_name(note) for note in ordenadas)
        interval_names = ", ".join(
            "fundamental" if interval == 0 else simple_interval_name(interval)
            for interval in intervals
        )
        prompt = (
            "MIDI learn capturó este acorde.\n\n"
            f"Notas capturadas: {note_names}\n"
            f"Fundamental asumida: {midi_to_name(root_note)}\n"
            f"Intervalos que se guardarán: {interval_names}\n\n"
            "Escribe abajo el cifrado que quieres guardar para este grupo de notas.\n"
            "Ejemplos: 7, m7(b5), 13(b9), add2."
        )

        name, ok = self._prompt_text_foreground(
            "Midi learn: nuevo cifrado",
            prompt,
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            self._show_status_message("Midi learn: el nombre del cifrado no puede estar vacío.")
            return

        self._register_custom_chord(name, intervals, persist=True)

    def _reset_learning_state(self):
        self._close_midi_learn_start_dialog()
        self.learning_chord = False
        self.learning_waiting_first_note = False
        self.learning_capture_notes.clear()
        if self.capture_timer.isActive():
            self.capture_timer.stop()
        self._set_learn_button_text(self._learn_button_default_text)

    def _set_learn_button_text(self, text: str) -> None:
        self._set_button_text_safe(getattr(self, "learn_button", None), text)
        self._set_button_text_safe(getattr(self, "display_panel_midi_learn", None), text)

    def _set_button_text_safe(self, button: Optional[QPushButton], text: str) -> None:
        if button is None:
            return
        try:
            button.setText(text)
        except RuntimeError:
            # El botón puede haber sido destruido al reconstruir el panel de visualización.
            return

    def _begin_capture_window(self, notas_actuales: Set[int]):
        self.learning_waiting_first_note = False
        self.learning_capture_notes = set(notas_actuales)
        self._set_learn_button_text("Midi learn: capturando acorde…")
        self.capture_timer.start(int(self.capture_window_spin.value()))

    def _absorb_capture_notes(self, notas_actuales: Set[int]):
        self.learning_capture_notes.update(notas_actuales)

    def _finish_capture_window(self):
        notas = set(self.learning_capture_notes)
        try:
            self._complete_learning_with_notes(notas)
        except Exception as exc:
            self._reset_learning_state()
            self._show_status_message(f"Midi learn: error durante captura ({exc}).")

    # --- MIDI polling ---

    
    def poll_midi(self):
        inputs = [port for port in self.midi_inputs if port is not None]
        if not inputs and self.midi_in is not None:
            inputs = [self.midi_in]
        if not inputs:
            return
        try:
            changed = False
            new_note_on = False
            for midi_input in inputs:
                for msg in midi_input.iter_pending():
                    source = (
                        id(midi_input),
                        int(getattr(msg, "channel", 0) or 0),
                    )
                    # Pedal de sustain (CC 64)
                    if msg.type == "control_change" and getattr(msg, "control", None) == 64:
                        sustain_was_on = self.sustain_on
                        if msg.value >= 64:
                            self._sustain_sources.add(source)
                        else:
                            self._sustain_sources.discard(source)
                        self.sustain_on = bool(self._sustain_sources)
                        if sustain_was_on and not self.sustain_on:
                            if self.sustained_notes:
                                for n in list(self.sustained_notes):
                                    self.piano.set_sustained(n, False)
                                self.sustained_notes.clear()
                                changed = True
                    elif msg.type in ("note_on", "note_off"):
                        note = msg.note
                        if msg.type == "note_on" and msg.velocity > 0:
                            note_sources = self._held_note_sources.setdefault(note, set())
                            was_held = bool(note_sources)
                            note_sources.add(source)
                            if not was_held:
                                self.piano.set_pressed(note, True)
                            self.active_notes.add(note)
                            if note in self.note_activation_order:
                                self.note_activation_order.remove(note)
                            self.note_activation_order.append(note)
                            # Si estaba en sustain, lo quitamos de ahí
                            if note in self.sustained_notes:
                                self.sustained_notes.discard(note)
                                self.piano.set_sustained(note, False)
                            new_note_on = True
                        else:
                            note_sources = self._held_note_sources.get(note, set())
                            note_sources.discard(source)
                            if note_sources:
                                continue
                            self._held_note_sources.pop(note, None)
                            self.piano.set_pressed(note, False)
                            if self.sustain_on:
                                self.active_notes.discard(note)
                                self.sustained_notes.add(note)
                                self.piano.set_sustained(note, True)
                            else:
                                self.active_notes.discard(note)
                                self.sustained_notes.discard(note)
                                self.piano.set_sustained(note, False)
                        changed = True
            if changed:
                notas_para_acorde = set(self.active_notes) | set(self.sustained_notes)
                self._refresh_staff_for_current_notes()
                if self.learning_chord:
                    if self.learning_waiting_first_note and new_note_on and notas_para_acorde:
                        self._begin_capture_window(notas_para_acorde)
                    elif self.capture_timer.isActive():
                        self._absorb_capture_notes(notas_para_acorde)
        except Exception:
            # no queremos que un error de MIDI tumbe la interfaz
            pass




def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setFont(ui_font(10 if IS_WINDOWS else 13))
    app.setQuitOnLastWindowClosed(False)

    piano_window = PianoWindow()
    chord_window = ChordWindow()
    staff_window = StaffWindow()
    fretboard_widget = FretboardWidget()
    app.piano_window = piano_window
    app.chord_window = chord_window
    app.staff_window = staff_window
    app.fretboard_widget = fretboard_widget
    piano_window.show()
    chord_window.show()
    staff_window.hide()

    control_window = ControlWindow(
        piano_window,
        chord_window,
        staff_window,
        fretboard_widget,
    )
    app.control_window = control_window  # mantiene vivos los controles y atajos durante toda la sesión

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
