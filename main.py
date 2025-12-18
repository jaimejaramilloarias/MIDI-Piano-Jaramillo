
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPoint, QEvent, QSettings
from PyQt6.QtGui import (
    QActionGroup,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSpinBox,
    QMessageBox,
    QFontComboBox,
    QFontDialog,
    QColorDialog,
    QInputDialog,
    QFileDialog,
)
import mido

# Asegura que PyInstaller incluya el backend rtmidi (y permite correr sin él).
try:
    import mido.backends.rtmidi  # type: ignore  # noqa: F401
except Exception:
    pass

# MIDI note range for a full piano
MIN_NOTE = 21   # A0
MAX_NOTE = 108  # C8

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

INTERVAL_LABELS = {
    0: "f",
    1: "2m",
    2: "2M",
    3: "+2/3m",
    4: "3M",
    5: "4j",
    6: "4+/5b",
    7: "5j",
    8: "5+/b6",
    9: "6",
    10: "b6/7m",
    11: "7M",
}

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

DETECT_NOTE_NAMES = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']


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


def note_octave(note: int) -> int:
    """Devuelve la octava según la convención MIDI típica."""
    return note // 12 - 1


def midi_of_C(octave: int) -> int:
    """Devuelve el número de nota MIDI de C<octave>."""
    return (octave + 1) * 12


def is_white(note: int) -> bool:
    pc = note % 12
    return pc in (0, 2, 4, 5, 7, 9, 11)


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
        self.sustain_opacity: float = 0.4  # 0.0–1.0
        self.interval_labels: Dict[int, str] = {}

        # Proporción alto/ancho de una tecla blanca (alto = ancho * aspect)
        self.key_aspect_ratio = 4.5

        # Color base para notas presionadas
        self.base_color = QColor("cyan")

        self.setMinimumSize(300, 80)

        # Fondo transparente
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        # Para arrastrar y redimensionar la ventana desde el propio teclado
        self._drag_offset: Optional[QPoint] = None
        self._resizing = False
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_size = None
        self._resize_margin = 16  # píxeles desde la esquina inferior derecha

        self.interval_label_settings = {
            "font_family": "",
            "font_size": 14,
            "color_white": QColor(Qt.GlobalColor.black),
            "color_black": QColor(Qt.GlobalColor.white),
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
        end_note = midi_of_C(target_oct)
        if end_note > MAX_NOTE:
            end_note = MAX_NOTE
        self.start_note = start_note
        self.end_note = end_note
        self.update()

    def set_pressed(self, note: int, pressed: bool):
        if note < self.start_note or note > self.end_note:
            return
        if pressed:
            self.pressed_notes.add(note)
        else:
            self.pressed_notes.discard(note)
        self.update()

    def clear_pressed(self):
        self.pressed_notes.clear()
        self.update()

    def set_sustained(self, note: int, sustained: bool):
        if note < self.start_note or note > self.end_note:
            return
        if sustained:
            self.sustained_notes.add(note)
        else:
            self.sustained_notes.discard(note)
        self.update()

    def clear_sustained(self):
        self.sustained_notes.clear()
        self.update()

    def set_interval_labels(self, labels: Dict[int, str]):
        self.interval_labels = labels
        self.update()

    def set_interval_label_style(self, settings: Dict):
        self.interval_label_settings = settings
        self.update()

    def set_base_color_name(self, name: str):
        mapping = {
            "Cian": QColor(0, 200, 200),
            "Azul": QColor(80, 160, 255),
            "Verde": QColor(80, 220, 140),
            "Rojo": QColor(230, 80, 80),
            "Naranja": QColor(240, 160, 60),
            "Morado": QColor(180, 100, 220),
        }
        self.base_color = mapping.get(name, QColor("cyan"))
        self.update()

    # --- helpers internos ---

    def _note_factor(self, note: int) -> float:
        """Devuelve un factor 0.6–1.0 según la posición relativa de la nota en el rango."""
        if self.end_note == self.start_note:
            return 1.0
        rel = (note - self.start_note) / float(self.end_note - self.start_note)
        return 0.6 + 0.4 * rel

    def _pressed_color_for(self, note: int, is_black_key: bool) -> QColor:
        base = self.base_color
        h, s, v, a = base.getHsv()
        factor = self._note_factor(note)
        if is_black_key:
            factor *= 0.8
        new_v = max(50, min(int(v * factor), 255))
        return QColor.fromHsv(h, s, new_v, a)


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

    # --- soporte para arrastrar y redimensionar ventana ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
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

    # --- dibujo ---

    def paintEvent(self, event):
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

        # Etiquetas para las C
        painter.setPen(QPen(Qt.GlobalColor.black))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        for n in white_notes:
            if n % 12 == 0:  # C
                idx = note_to_white_index[n]
                x = x_offset + idx * key_width
                key_rect = QRectF(x, y_offset, key_width, key_height)
                label = midi_to_name(n)
                painter.drawText(
                    key_rect.adjusted(2, key_height - 20, -2, -2),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
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

        # Etiquetas de intervalos para notas activas
        if self.interval_labels:
            settings = self.interval_label_settings or {}
            label_font = QFont(settings.get("font_family") or "")
            label_font.setPointSize(int(settings.get("font_size", 14)))
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
            chosen = QColor(Qt.GlobalColor.black if not is_black_key else Qt.GlobalColor.white)
        if isinstance(chosen, str):
            chosen = QColor(chosen)
        if not isinstance(chosen, QColor) or not chosen.isValid():
            chosen = QColor(Qt.GlobalColor.black if not is_black_key else Qt.GlobalColor.white)
        return chosen

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
    """Ventana que SOLO muestra el teclado, sin bordes ni barra de título."""

    def __init__(self):
        super().__init__()

        # Ventana sin marco / botones
        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)

        # Fondo transparente
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self.setWindowTitle("MIDI Piano - Teclado")

        self.piano = PianoWidget()
        self.setCentralWidget(self.piano)

        # Sin márgenes extra
        self.setContentsMargins(0, 0, 0, 0)

        self.resize(900, 220)




class ChordWindow(QMainWindow):
    """Ventana que muestra el cifrado de acordes detectados en vivo."""

    def __init__(self):
        super().__init__()

        # Ventana sin marco
        flags = self.windowFlags()
        flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)

        self.setWindowTitle("MIDI Piano Jaramillo — Acordes")

        self._drag_offset: Optional[QPoint] = None

        # Contenedor blanco puro
        self.background_color = QColor(Qt.GlobalColor.white)
        self.central = QWidget()
        self.setCentralWidget(self.central)

        self.main_label = QLabel("")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.alt_label = QLabel("")
        self.alt_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.alt_label.setStyleSheet("color: #000000;")

        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(self.main_label, stretch=0)
        layout.addWidget(self.alt_label, stretch=0)
        self.central.setLayout(layout)

        # Fuente por defecto
        self.set_font_from_family_size("Avenir Next", 80)

        # Color por defecto
        self.set_chord_color(QColor(Qt.GlobalColor.black))

        self.resize(740, 200)

        self.set_background_color(self.background_color)

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
        """Actualiza la fuente del cifrado principal y alternativo."""
        size = int(size)

        main_font = QFont(family, size)
        main_font.setWeight(QFont.Weight.Medium)
        self.main_label.setFont(main_font)

        alt_size = max(10, int(size * 0.35))
        alt_font = QFont(family, alt_size)
        alt_font.setWeight(QFont.Weight.Normal)
        self.alt_label.setFont(alt_font)

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
        self.central.setStyleSheet(f"background: {color.name()};")

    def update_chord(self, notas):
        info = analizar_cifrado_alternativos(notas)
        principal = info.get("principal") or ""
        alternativos = info.get("alternativos") or []

        if not principal:
            self.main_label.setText("")
            self.alt_label.setText("")
            return info

        self.main_label.setText(principal)

        # Alternativos a la derecha, pegados al principal
        if alternativos:
            self.alt_label.setText("  ·  ".join(alternativos))
        else:
            self.alt_label.setText("")

        return info

class ControlWindow(QMainWindow):
    """
    Ventana de controles:
    - Selección de dispositivo MIDI
    - Nota inicial (solo A0 o Cs)
    - Número de octavas
    - Color base
    - Siempre al frente (para la ventana del teclado)
    - Guardar preferencias de forma persistente
    """

    CONFIG_PATH = Path.home() / ".midi_piano_prefs.json"

    def __init__(self, piano_window: PianoWindow, chord_window: ChordWindow):
        super().__init__()
        self.setWindowTitle("MIDI Piano - Controles")

        self.settings = QSettings("MIDI-Piano-Jaramillo", "MIDI-Piano")

        self.piano_window = piano_window
        self.piano = piano_window.piano
        self.chord_window = chord_window
        self.active_notes: Set[int] = set()
        self.sustained_notes: Set[int] = set()
        self.sustain_on: bool = False
        self._midi_backend_error_shown: bool = False
        self.custom_chords: List[Dict] = []
        self.additional_base_chords: List[Dict] = []
        self._additional_base_signatures: Set[Tuple[Tuple[int, ...], Tuple[int, ...]]] = set()
        self.learning_chord: bool = False
        self.learning_waiting_first_note: bool = False
        self.learning_capture_notes: Set[int] = set()
        self.capture_window_ms: int = 500
        self._learn_button_default_text = "Midi learn: nuevo cifrado"
        self.chord_text_color = QColor(Qt.GlobalColor.black)
        self.chord_bg_color = QColor(Qt.GlobalColor.white)
        self.interval_label_settings = self._default_interval_label_settings()
        self.capture_timer = QTimer()
        self.capture_timer.setSingleShot(True)
        self.capture_timer.timeout.connect(self._finish_capture_window)

        self._setup_window_menu()

        self._load_external_chord_dictionary()

        # Widgets
        self.input_combo = QComboBox()
        self.refresh_button = QPushButton("Actualizar dispositivos")

        self.start_combo = QComboBox()
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
            self.font_combo.setCurrentFont(QFont("Avenir Next"))
        except Exception:
            pass

        self.always_on_top = QPushButton("Teclado siempre al frente")
        self.always_on_top.setCheckable(True)

        self.save_button = QPushButton("Guardar preferencias")
        self.export_button = QPushButton("Exportar diccionario…")

        # Rellenar combo de nota inicial:
        #  - A0
        #  - Todos los Cx dentro de A0–C8
        for n in range(MIN_NOTE, MAX_NOTE + 1):
            if n == MIN_NOTE or NOTE_NAMES[n % 12] == "C":
                label = f"{midi_to_name(n)} ({n})"
                self.start_combo.addItem(label, n)

        # Por defecto: C3, 3 octavas (C3–C6)
        default_start = midi_of_C(3)  # C3
        self._select_combo_value(self.start_combo, default_start)
        self.piano.set_range_from_start_and_octaves(default_start, self.octaves_spin.value())

        # Layout
        top_layout = QVBoxLayout()

        # Fila 1: MIDI
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("MIDI In:"))
        row1.addWidget(self.input_combo)
        row1.addWidget(self.refresh_button)
        top_layout.addLayout(row1)

        # Fila 2: rango por octavas
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Nota inicial:"))
        row2.addWidget(self.start_combo)
        row2.addWidget(QLabel("Octavas:"))
        row2.addWidget(self.octaves_spin)
        top_layout.addLayout(row2)

        # Fila 3: color
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Color base notas:"))
        row3.addWidget(self.color_button)
        top_layout.addLayout(row3)

        # Fila 4: color de cifrado
        row3b = QHBoxLayout()
        row3b.addWidget(QLabel("Color del cifrado:"))
        row3b.addWidget(self.chord_color_button)
        top_layout.addLayout(row3b)

        row3c = QHBoxLayout()
        row3c.addWidget(QLabel("Fondo de acordes:"))
        row3c.addWidget(self.chord_bg_button)
        top_layout.addLayout(row3c)

        # Fila 4: fuente acordes
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Fuente acordes:"))
        row4.addWidget(self.font_combo)
        row4.addWidget(QLabel("Tamaño:"))
        row4.addWidget(self.font_size_spin)
        top_layout.addLayout(row4)

        # Fila 5: botones de ventana
        row5 = QHBoxLayout()
        row5.addWidget(self.always_on_top)
        row5.addWidget(self.save_button)
        row5.addWidget(self.export_button)
        row5.addStretch()
        top_layout.addLayout(row5)

        # Fila 6: Midi learn
        self.learn_button = QPushButton("Midi learn: nuevo cifrado")
        row6 = QHBoxLayout()
        row6.addWidget(self.learn_button)
        row6.addStretch()
        top_layout.addLayout(row6)

        # Fila 7: duración ventana de captura para Midi learn
        capture_row = QHBoxLayout()
        capture_row.addWidget(QLabel("Ventana captura (ms):"))
        self.capture_window_spin = QSpinBox()
        self.capture_window_spin.setRange(100, 5000)
        self.capture_window_spin.setSingleStep(50)
        self.capture_window_spin.setValue(self.capture_window_ms)
        capture_row.addWidget(self.capture_window_spin)
        capture_row.addStretch()
        top_layout.addLayout(capture_row)

        # Lista de acordes aprendidos
        top_layout.addWidget(QLabel("Acordes aprendidos:"))
        self.learned_chords_container = QWidget()
        self.learned_chords_layout = QVBoxLayout()
        self.learned_chords_layout.setContentsMargins(0, 0, 0, 0)
        self.learned_chords_layout.setSpacing(6)
        self.learned_chords_container.setLayout(self.learned_chords_layout)
        top_layout.addWidget(self.learned_chords_container)

        central = QWidget()
        central.setLayout(top_layout)
        self.setCentralWidget(central)

        # MIDI
        self.midi_in = None

        # Conexiones
        self.refresh_button.clicked.connect(self.refresh_inputs)
        self.input_combo.currentIndexChanged.connect(self.change_input)
        self.start_combo.currentIndexChanged.connect(self.range_changed)
        self.octaves_spin.valueChanged.connect(self.range_changed)
        self.color_button.clicked.connect(self.choose_color)
        self.chord_color_button.clicked.connect(self.choose_chord_color)
        self.chord_bg_button.clicked.connect(self.choose_chord_background)
        self.font_combo.currentFontChanged.connect(self.font_changed)
        self.font_size_spin.valueChanged.connect(self.font_size_changed)
        self.always_on_top.toggled.connect(self.toggle_on_top)
        self.save_button.clicked.connect(self.save_preferences)
        self.export_button.clicked.connect(self.export_chord_dictionary)
        self.learn_button.clicked.connect(self.start_learning_mode)

        # Timer para leer MIDI

        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.poll_midi)
        self.timer.start(10)

        # Inicializar dispositivos y preferencias
        self._load_interval_settings()
        self.refresh_inputs()
        self.load_preferences()
        self._apply_chord_font()
        self._refresh_learned_chords_ui()

    # --- menú de ventanas ---

    def _setup_window_menu(self):
        window_menu = self.menuBar().addMenu("Ventana")

        self.controls_action = window_menu.addAction("Ocultar Controles")
        self.controls_action.setCheckable(True)
        self.controls_action.setChecked(True)
        self.controls_action.triggered.connect(
            lambda checked: self._toggle_window_visibility(self, checked)
        )

        self.keyboard_action = window_menu.addAction("Ocultar Teclado")
        self.keyboard_action.setCheckable(True)
        self.keyboard_action.setChecked(True)
        self.keyboard_action.triggered.connect(
            lambda checked: self._toggle_window_visibility(self.piano_window, checked)
        )

        self.chord_action = window_menu.addAction("Ocultar Acordes")
        self.chord_action.setCheckable(True)
        self.chord_action.setChecked(True)
        self.chord_action.triggered.connect(
            lambda checked: self._toggle_window_visibility(self.chord_window, checked)
        )

        window_menu.addSeparator()
        show_all = window_menu.addAction("Mostrar todas")
        show_all.triggered.connect(self.show_all_windows)

        dictionary_menu = self.menuBar().addMenu("Diccionario")
        load_dict = dictionary_menu.addAction("Cargar diccionario…")
        load_dict.triggered.connect(self.load_chord_dictionary_from_dialog)

        self._setup_interval_menu()

        for win in (self, self.piano_window, self.chord_window):
            win.installEventFilter(self)

        QTimer.singleShot(0, self._update_window_actions)

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
        for win in (self, self.piano_window, self.chord_window):
            self._bring_to_front(win)
        self._update_window_actions()

    def _update_window_actions(self):
        controls_visible = self._window_is_visible(self)
        keyboard_visible = self._window_is_visible(self.piano_window)
        chords_visible = self._window_is_visible(self.chord_window)

        self.controls_action.blockSignals(True)
        self.controls_action.setChecked(controls_visible)
        self.controls_action.setText(
            "Ocultar Controles" if controls_visible else "Mostrar Controles"
        )
        self.controls_action.blockSignals(False)

        self.keyboard_action.blockSignals(True)
        self.keyboard_action.setChecked(keyboard_visible)
        self.keyboard_action.setText(
            "Ocultar Teclado" if keyboard_visible else "Mostrar Teclado"
        )
        self.keyboard_action.blockSignals(False)

        self.chord_action.blockSignals(True)
        self.chord_action.setChecked(chords_visible)
        self.chord_action.setText(
            "Ocultar Acordes" if chords_visible else "Mostrar Acordes"
        )
        self.chord_action.blockSignals(False)

    def _setup_interval_menu(self):
        view_menu = self.menuBar().addMenu("Ver")
        intervals_menu = view_menu.addMenu("Intervalos en teclas")

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

    def _default_interval_label_settings(self) -> Dict:
        return {
            "font_family": "",
            "font_size": 14,
            "color_white": QColor(Qt.GlobalColor.black),
            "color_black": QColor(Qt.GlobalColor.white),
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
        font, ok = QFontDialog.getFont(current_font, self, "Fuente para intervalos")
        if not ok:
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["font_family"] = font.family()
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_size(self):
        current_size = int(self.interval_label_settings.get("font_size", 14))
        size, ok = QInputDialog.getInt(
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
        color = QColorDialog.getColor(current_color, self, title)
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
        color = QColorDialog.getColor(current_fill, self, "Color de relleno de etiqueta")
        if not color.isValid():
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_fill_color"] = color
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_opacity(self):
        current_opacity = float(self.interval_label_settings.get("frame_fill_opacity", 0.6))
        opacity, ok = QInputDialog.getDouble(
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
        color = QColorDialog.getColor(current_color, self, "Color del borde de etiqueta")
        if not color.isValid():
            self._sync_interval_position_actions()
            return
        self.interval_label_settings["frame_border_color"] = color
        self._apply_interval_settings_to_piano()
        self._save_interval_settings()

    def _choose_interval_frame_border_width(self):
        current_width = float(self.interval_label_settings.get("frame_border_width", 1.0))
        width, ok = QInputDialog.getDouble(
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
            percent, ok = QInputDialog.getInt(
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

    def eventFilter(self, source, event):
        if source in (self, self.piano_window, self.chord_window):
            if event.type() in (
                QEvent.Type.WindowStateChange,
                QEvent.Type.Hide,
                QEvent.Type.Show,
            ):
                QTimer.singleShot(0, self._update_window_actions)
        return super().eventFilter(source, event)

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
                    res = QMessageBox.question(
                        self,
                        "Duplicado",
                        (
                            "Ya existe un acorde con esos intervalos en la base.\n\n"
                            f"Actual: «{existing_base.get('nombre', '(sin nombre)')}».\n"
                            f"Nuevo: «{name}».\n\n¿Sobrescribirlo?"
                        ),
                    )
                    if res != QMessageBox.StandardButton.Yes:
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

    def _select_combo_value(self, combo: QComboBox, value: int):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # --- preferencias persistentes ---

    def _preferences_payload(self):
        return {
            "midi_in_name": self.input_combo.currentData() or "",
            "start_note": int(self.start_combo.currentData() or MIN_NOTE),
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
            "always_on_top": bool(self.always_on_top.isChecked()),
            "chord_text_color": self.chord_text_color.name(),
            "chord_background": self.chord_bg_color.name(),
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
            "window_geometries": {
                "controls": self._geometry_payload_for(self),
                "keyboard": self._geometry_payload_for(self.piano_window),
                "chords": self._geometry_payload_for(self.chord_window),
            },
        }

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
                QMessageBox.warning(self, "Error", f"No se pudieron guardar las preferencias:\n{e}")
        else:
            if show_message:
                QMessageBox.information(self, "OK", "Preferencias guardadas correctamente.")

    def save_preferences(self):
        self._write_preferences(True)

    def export_chord_dictionary(self):
        default_path = str(Path.home() / "diccionario_acordes.json")
        file_path, _ = QFileDialog.getSaveFileName(
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
            QMessageBox.warning(self, "Error", f"No se pudo exportar el diccionario:\n{e}")
        else:
            QMessageBox.information(
                self,
                "Exportación lista",
                f"Diccionario exportado en:\n{file_path}",
            )

    def load_chord_dictionary_from_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
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
        QMessageBox.information(
            self,
            "Diccionario cargado",
            (
                "El diccionario se cargó en memoria.\n\n"
                f"Acordes agregados o actualizados: {added}."
            ),
        )

    def load_preferences(self):
        if not self.CONFIG_PATH.exists():
            return
        try:
            prefs = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        start = prefs.get("start_note")
        if isinstance(start, int):
            self._select_combo_value(self.start_combo, start)

        octaves = prefs.get("octaves")
        if isinstance(octaves, int) and 1 <= octaves <= 7:
            self.octaves_spin.setValue(octaves)

        rgba = prefs.get("base_color_rgba")
        if (
            isinstance(rgba, list)
            and len(rgba) == 4
            and all(isinstance(x, int) for x in rgba)
        ):
            try:
                self.piano.base_color = QColor(rgba[0], rgba[1], rgba[2], rgba[3])
                self.piano.update()
            except Exception:
                pass

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
            try:
                color = QColor(chord_bg)
                if color.isValid():
                    self.chord_bg_color = color
                    self.chord_window.set_background_color(color)
            except Exception:
                pass

        self._restore_window_geometries(prefs)

        capture_window_ms = prefs.get("capture_window_ms")
        if isinstance(capture_window_ms, int) and 50 <= capture_window_ms <= 10000:
            self.capture_window_ms = capture_window_ms
            self.capture_window_spin.setValue(capture_window_ms)

        on_top = bool(prefs.get("always_on_top", False))
        self.always_on_top.setChecked(on_top)

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

        # Aplicar rango con las preferencias cargadas
        self.range_changed()

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

        self._apply_geometry_if_valid(self, rect_from_payload(geoms.get("controls")))
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
                QMessageBox.warning(
                    self,
                    "MIDI no disponible",
                    "No se pudo cargar el backend MIDI (python-rtmidi).\n\n"
                    "Solución:\n"
                    "• Si corres desde terminal: instala python-rtmidi en tu venv.\n"
                    "• Si es la app empaquetada: recompílala (PyInstaller) incluyendo mido.backends.rtmidi.",
                )
            names = []
        except Exception as e:
            if not self._midi_backend_error_shown:
                self._midi_backend_error_shown = True
                QMessageBox.critical(self, "Error MIDI", f"No se pudieron listar los dispositivos MIDI:\n{e}")
            names = []

        if not names:
            self.input_combo.addItem("No hay dispositivos MIDI", None)
        else:
            for n in names:
                self.input_combo.addItem(n, n)
        self.input_combo.blockSignals(False)

        if current_name:
            idx = self.input_combo.findData(current_name)
            if idx >= 0:
                self.input_combo.setCurrentIndex(idx)
                return

        self.change_input()

    def change_input(self):
        if self.midi_in is not None:
            try:
                self.midi_in.close()
            except Exception:
                pass
            self.midi_in = None

        name = self.input_combo.currentData()
        if not name:
            return
        try:
            self.midi_in = mido.open_input(name)
        except Exception as e:
            QMessageBox.critical(self, "Error MIDI", f"No se pudo abrir el dispositivo MIDI:\n{e}")
            self.midi_in = None

    def range_changed(self):
        start = self.start_combo.currentData()
        octaves = self.octaves_spin.value()
        if start is None:
            return
        self.piano.set_range_from_start_and_octaves(int(start), int(octaves))

    def choose_color(self):
        color = QColorDialog.getColor(self.piano.base_color, self, "Seleccionar color de notas")
        if color.isValid():
            self.piano.base_color = color
            self.piano.update()
            self._write_preferences(False)

    def choose_chord_color(self):
        color = QColorDialog.getColor(self.chord_text_color, self, "Seleccionar color del cifrado")
        if color.isValid():
            self.chord_text_color = color
            self.chord_window.set_chord_color(color)
            self._write_preferences(False)

    def choose_chord_background(self):
        color = QColorDialog.getColor(
            self.chord_bg_color, self, "Seleccionar fondo de la ventana de acordes"
        )
        if color.isValid():
            self.chord_bg_color = color
            self.chord_window.set_background_color(color)
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

    def _edit_custom_chord_name(self, index: int):
        if index < 0 or index >= len(self.custom_chords):
            return
        pattern = self.custom_chords[index]
        current_name = pattern.get("nombre", "")
        new_name, ok = QInputDialog.getText(
            self,
            "Editar cifrado",
            "Nuevo nombre para el acorde:",
            text=current_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Editar cifrado", "El nombre no puede estar vacío.")
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
            res = QMessageBox.question(
                self,
                "Midi learn",
                f"Ya existe un acorde aprendido con esos intervalos:\n«{old_name}».\n\n"
                f"¿Quieres reemplazarlo por «{name}»?",
            )
            if res != QMessageBox.StandardButton.Yes:
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
            res = QMessageBox.question(
                self,
                "Duplicado",
                (
                    "Ya existe un acorde en la base con esos intervalos.\n\n"
                    f"Actual: «{existing_base.get('nombre', '(sin nombre)')}».\n"
                    f"Nuevo: «{pattern.get('nombre', '(sin nombre)')}».\n\n¿Sobrescribirlo?"
                ),
            )
            if res != QMessageBox.StandardButton.Yes:
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
        pattern = self.custom_chords.pop(index)
        try:
            CHORD_PATTERNS.remove(pattern)
        except ValueError:
            pass
        self._refresh_learned_chords_ui()
        self._write_preferences(False)

    def _update_interval_labels(self, notas: Set[int], chord_info: Optional[Dict]):
        if not notas:
            self.piano.set_interval_labels({})
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
        labels: Dict[int, str] = {}
        for note in notas:
            interval = (note - root_note) % 12
            label = INTERVAL_LABELS.get(interval)
            if label:
                labels[note] = label

        self.piano.set_interval_labels(labels)

    def start_learning_mode(self):
        if self.learning_chord:
            self._reset_learning_state()
            QMessageBox.information(
                self,
                "Midi learn",
                "Modo aprendizaje cancelado.",
            )
            return

        current_notes = set(self.active_notes) | set(self.sustained_notes)
        if current_notes:
            self.learning_chord = True
            self.learn_button.setText("Midi learn: capturando acorde…")
            self._complete_learning_with_notes(current_notes)
            return

        self.learning_chord = True
        self.learning_waiting_first_note = True
        self.learn_button.setText("Midi learn: esperando acorde…")
        QMessageBox.information(
            self,
            "Midi learn",
            "Toca el acorde en tu teclado MIDI. Se abrirá una ventana de captura desde la primera nota.",
        )

    def _complete_learning_with_notes(self, notas):
        self._reset_learning_state()
        if not notas:
            QMessageBox.warning(self, "Midi learn", "No se detectaron notas para aprender.")
            return

        ordenadas = sorted(set(int(n) for n in notas))
        if len(ordenadas) < 2:
            QMessageBox.warning(
                self, "Midi learn", "El cifrado necesita al menos dos notas del acorde."
            )
            return

        root_note = ordenadas[0]
        intervals = [(n - root_note) % 12 for n in ordenadas]

        name, ok = QInputDialog.getText(
            self,
            "Midi learn: nuevo cifrado",
            "Escribe el nombre/cifrado del acorde:",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Midi learn", "El nombre del cifrado no puede estar vacío.")
            return

        self._register_custom_chord(name, intervals, persist=True)

    def _reset_learning_state(self):
        self.learning_chord = False
        self.learning_waiting_first_note = False
        self.learning_capture_notes.clear()
        if self.capture_timer.isActive():
            self.capture_timer.stop()
        self.learn_button.setText(self._learn_button_default_text)

    def _begin_capture_window(self, notas_actuales: Set[int]):
        self.learning_waiting_first_note = False
        self.learning_capture_notes = set(notas_actuales)
        self.learn_button.setText("Midi learn: capturando acorde…")
        self.capture_timer.start(int(self.capture_window_spin.value()))

    def _absorb_capture_notes(self, notas_actuales: Set[int]):
        self.learning_capture_notes.update(notas_actuales)

    def _finish_capture_window(self):
        notas = set(self.learning_capture_notes)
        self._complete_learning_with_notes(notas)

    # --- MIDI polling ---

    
    def poll_midi(self):
        if self.midi_in is None:
            return
        try:
            changed = False
            new_note_on = False
            for msg in self.midi_in.iter_pending():
                # Pedal de sustain (CC 64)
                if msg.type == "control_change" and getattr(msg, "control", None) == 64:
                    if msg.value >= 64:
                        # Sustain ON
                        self.sustain_on = True
                    else:
                        # Sustain OFF: limpiar todas las notas sostenidas
                        self.sustain_on = False
                        if self.sustained_notes:
                            for n in list(self.sustained_notes):
                                self.piano.set_sustained(n, False)
                            self.sustained_notes.clear()
                            changed = True
                elif msg.type in ("note_on", "note_off"):
                    note = msg.note
                    if msg.type == "note_on" and msg.velocity > 0:
                        # Pulsación física
                        self.piano.set_pressed(note, True)
                        self.active_notes.add(note)
                        # Si estaba en sustain, lo quitamos de ahí
                        if note in self.sustained_notes:
                            self.sustained_notes.discard(note)
                            self.piano.set_sustained(note, False)
                        new_note_on = True
                    else:
                        # Nota liberada físicamente
                        self.piano.set_pressed(note, False)
                        if self.sustain_on:
                            # Mientras el pedal está ON, pasamos la nota a sostenida
                            if note in self.active_notes:
                                self.active_notes.discard(note)
                            self.sustained_notes.add(note)
                            self.piano.set_sustained(note, True)
                        else:
                            # Sin pedal: simplemente se apaga
                            if note in self.active_notes:
                                self.active_notes.discard(note)
                            if note in self.sustained_notes:
                                self.sustained_notes.discard(note)
                                self.piano.set_sustained(note, False)
                    changed = True
            if changed:
                notas_para_acorde = set(self.active_notes) | set(self.sustained_notes)
                chord_info = self.chord_window.update_chord(notas_para_acorde)
                self._update_interval_labels(notas_para_acorde, chord_info)
                if self.learning_chord:
                    if self.learning_waiting_first_note and new_note_on and notas_para_acorde:
                        self._begin_capture_window(notas_para_acorde)
                    elif self.capture_timer.isActive():
                        self._absorb_capture_notes(notas_para_acorde)
        except Exception:
            # no queremos que un error de MIDI tumbe la interfaz
            pass




def main():
    app = QApplication(sys.argv)

    piano_window = PianoWindow()
    chord_window = ChordWindow()
    control_window = ControlWindow(piano_window, chord_window)

    piano_window.show()
    control_window.show()
    chord_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
