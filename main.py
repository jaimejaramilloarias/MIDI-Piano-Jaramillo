
import sys
import json
from pathlib import Path
from typing import List, Set

from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QPainter, QPen, QBrush, QFont, QColor, QCursor
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
    QColorDialog,
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

CHORD_PATTERNS = [
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

DETECT_NOTE_NAMES = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']


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
            es_grave_fundamental = (bass_pc == root_pc)

            matches.append({
                "root": root_pc,
                "nombre": ptn["nombre"],
                "numOblig": num_oblig,
                "opcionalesPresentes": opcionales_presentes,
                "esGraveFundamental": es_grave_fundamental,
                "obligatorias": oblig,
                "opcionales": opc,
            })

    if not matches:
        return {"principal": "", "alternativos": []}

    graves = [m for m in matches if m["esGraveFundamental"]]
    candidatos = graves or matches

    max_oblig = max(m["numOblig"] for m in candidatos)
    completos = [m for m in candidatos if m["numOblig"] == max_oblig]

    max_opc = max(m["opcionalesPresentes"] for m in completos)
    mas_opc = [m for m in completos if m["opcionalesPresentes"] == max_opc]

    min_oblig = min(m["numOblig"] for m in mas_opc)
    simples = [m for m in mas_opc if m["numOblig"] == min_oblig]

    def sort_key(m):
        return (
            0 if m["esGraveFundamental"] else 1,  # primero los que tienen bajo fundamental
            -m["numOblig"],
            -m["opcionalesPresentes"],
            m["nombre"],
        )

    simples.sort(key=sort_key)

    resultados = []
    for x in simples:
        root_name = DETECT_NOTE_NAMES[x["root"]]
        nombre = root_name + x["nombre"]
        if not x["esGraveFundamental"]:
            es_solo_triada_o_sep = all(ivl not in (2, 5, 9) for ivl in x["obligatorias"]) and \
                                   all(ivl not in (2, 5, 9) for ivl in x["opcionales"])
            if es_solo_triada_o_sep:
                bass_int = (bass_pc - x["root"] + 12) % 12
                if bass_int in (3, 4, 7, 10):
                    bass_name = DETECT_NOTE_NAMES[bass_pc]
                    nombre = nombre + "/" + bass_name
        resultados.append(nombre)

    if not resultados:
        return {"principal": "", "alternativos": []}

    principal = resultados[0]
    alternativos = []
    for n in resultados[1:]:
        if n not in alternativos:
            alternativos.append(n)
        if len(alternativos) >= 4:
            break

    return {"principal": principal, "alternativos": alternativos}



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

        # Proporción alto/ancho de una tecla blanca (alto = ancho * aspect)
        self.key_aspect_ratio = 4.5

        # Color base para notas presionadas
        self.base_color = QColor("cyan")

        self.setMinimumSize(300, 80)

        # Fondo transparente
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        # Para arrastrar y redimensionar la ventana desde el propio teclado
        self._drag_offset: QPoint | None = None
        self._resizing = False
        self._resize_start_pos: QPoint | None = None
        self._resize_start_size = None
        self._resize_margin = 16  # píxeles desde la esquina inferior derecha

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
        self.setWindowTitle("MIDI Piano Jaramillo - Acordes")

        # Contenedor blanco puro
        central = QWidget()
        central.setStyleSheet("background: #ffffff;")
        self.setCentralWidget(central)

        self.main_label = QLabel("")
        self.main_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.alt_label = QLabel("")
        self.alt_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.alt_label.setStyleSheet("color: #666666;")

        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        layout.addWidget(self.main_label, stretch=0)
        layout.addStretch(1)
        layout.addWidget(self.alt_label, stretch=0)
        central.setLayout(layout)

        # Fuente por defecto
        self.set_font_from_family_size("Avenir Next", 80)

        self.resize(740, 200)

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

    def update_chord(self, notas):
        info = analizar_cifrado_alternativos(notas)
        principal = info.get("principal") or ""
        alternativos = info.get("alternativos") or []

        if not principal:
            self.main_label.setText("")
            self.alt_label.setText("")
            return

        self.main_label.setText(principal)

        # Alternativos a la derecha
        if alternativos:
            self.alt_label.setText("   ·   ".join(alternativos))
        else:
            self.alt_label.setText("")

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

        self.piano_window = piano_window
        self.piano = piano_window.piano
        self.chord_window = chord_window
        self.active_notes: set[int] = set()
        self.sustained_notes: set[int] = set()
        self.sustain_on: bool = False
        self._midi_backend_error_shown: bool = False

        # Widgets
        self.input_combo = QComboBox()
        self.refresh_button = QPushButton("Actualizar dispositivos")

        self.start_combo = QComboBox()
        self.octaves_spin = QSpinBox()
        self.octaves_spin.setRange(1, 7)
        self.octaves_spin.setValue(3)

        # Colores (presets) + selector de color del sistema
        self.color_combo = QComboBox()
        self.color_combo.addItems(["Cian", "Azul", "Verde", "Rojo", "Naranja", "Morado"])
        self.color_button = QPushButton("Elegir color…")

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
        row3.addWidget(self.color_combo)
        row3.addWidget(self.color_button)
        top_layout.addLayout(row3)

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
        row5.addStretch()
        top_layout.addLayout(row5)

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
        self.color_combo.currentIndexChanged.connect(self.color_changed)
        self.color_button.clicked.connect(self.choose_color)
        self.font_combo.currentFontChanged.connect(self.font_changed)
        self.font_size_spin.valueChanged.connect(self.font_size_changed)
        self.always_on_top.toggled.connect(self.toggle_on_top)
        self.save_button.clicked.connect(self.save_preferences)

        # Timer para leer MIDI

        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_midi)
        self.timer.start(10)

        # Inicializar dispositivos y preferencias
        self.refresh_inputs()
        self.color_changed()
        self.load_preferences()
        self._apply_chord_font()

    # --- helpers ---

    def _select_combo_value(self, combo: QComboBox, value: int):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # --- preferencias persistentes ---

    def save_preferences(self):
        prefs = {
            "midi_in_name": self.input_combo.currentData() or "",
            "start_note": int(self.start_combo.currentData() or MIN_NOTE),
            "octaves": int(self.octaves_spin.value()),
            "color": self.color_combo.currentText(),
            "base_color_rgba": [
                int(self.piano.base_color.red()),
                int(self.piano.base_color.green()),
                int(self.piano.base_color.blue()),
                int(self.piano.base_color.alpha()),
            ],
            "font_family": self.font_combo.currentFont().family(),
            "font_size": int(self.font_size_spin.value()),
            "always_on_top": bool(self.always_on_top.isChecked()),
        }
        try:
            self.CONFIG_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudieron guardar las preferencias:\n{e}")
        else:
            QMessageBox.information(self, "OK", "Preferencias guardadas correctamente.")

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

        color = prefs.get("color")
        if isinstance(color, str) and color in [self.color_combo.itemText(i) for i in range(self.color_combo.count())]:
            self.color_combo.setCurrentText(color)

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

        font_family = prefs.get("font_family")
        if isinstance(font_family, str) and font_family:
            try:
                self.font_combo.setCurrentFont(QFont(font_family))
            except Exception:
                pass

        font_size = prefs.get("font_size")
        if isinstance(font_size, int) and 10 <= font_size <= 160:
            self.font_size_spin.setValue(int(font_size))

        on_top = bool(prefs.get("always_on_top", False))
        self.always_on_top.setChecked(on_top)

        midi_name = prefs.get("midi_in_name") or ""
        if midi_name:
            idx = self.input_combo.findData(midi_name)
            if idx >= 0:
                self.input_combo.setCurrentIndex(idx)

        # Aplicar rango con las preferencias cargadas
        self.range_changed()

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

    def color_changed(self):
        name = self.color_combo.currentText()
        self.piano.set_base_color_name(name)

    def choose_color(self):
        color = QColorDialog.getColor(self.piano.base_color, self, "Seleccionar color de notas")
        if color.isValid():
            self.piano.base_color = color
            self.piano.update()

    def _apply_chord_font(self):
        family = self.font_combo.currentFont().family()
        size = int(self.font_size_spin.value())
        self.chord_window.set_font_from_family_size(family, size)

    def font_changed(self, qfont):
        self._apply_chord_font()

    def font_size_changed(self, value: int):
        self._apply_chord_font()

    def toggle_on_top(self, on: bool):
        flags = self.piano_window.windowFlags()
        if on:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.piano_window.setWindowFlags(flags)
        self.piano_window.show()

    # --- MIDI polling ---

    
    def poll_midi(self):
        if self.midi_in is None:
            return
        try:
            changed = False
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
                self.chord_window.update_chord(notas_para_acorde)
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
