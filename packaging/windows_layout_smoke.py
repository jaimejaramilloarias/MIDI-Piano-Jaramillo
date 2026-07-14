"""Render and validate the Windows UI before publishing an installer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtGui import QColor, QFontInfo, QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget  # noqa: E402

import main  # noqa: E402
from main import (  # noqa: E402
    ChordWindow,
    ControlWindow,
    FretboardWidget,
    PianoWindow,
    StaffWindow,
)


def process(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def capture(widget: QWidget, path: Path, app: QApplication) -> None:
    widget.ensurePolished()
    widget.show()
    process(app)
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"No se pudo guardar {path.name}")


def label_fits(label: QLabel) -> bool:
    text = label.text().strip()
    if not text:
        return True
    metrics = QFontMetrics(label.font())
    bounds = metrics.boundingRect(text)
    contents = label.contentsRect()
    return bounds.width() <= contents.width() and bounds.height() <= contents.height()


def render_menu(menu: QMenu, path: Path, app: QApplication) -> None:
    hint = menu.sizeHint()
    menu.resize(max(menu.minimumWidth(), hint.width()), max(40, hint.height()))
    capture(menu, path, app)
    menu.hide()


def main_smoke(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"platform": sys.platform, "checks": {}}
    checks: dict[str, bool] = report["checks"]  # type: ignore[assignment]

    if not sys.platform.startswith("win"):
        raise RuntimeError("Esta verificación debe ejecutarse en Windows.")

    app = QApplication.instance() or QApplication([])
    app.setFont(main.ui_font(10))
    app.setQuitOnLastWindowClosed(False)
    main.mido.get_input_names = lambda: []

    ControlWindow.CONFIG_PATH = output_dir / "preferences.json"
    ControlWindow.APPEARANCE_CONFIG_PATH = output_dir / "appearance.json"

    piano_window = PianoWindow()
    chord_window = ChordWindow()
    staff_window = StaffWindow()
    fretboard = FretboardWidget()
    controls = ControlWindow(piano_window, chord_window, staff_window, fretboard)

    try:
        if controls.view_mode != "single":
            controls.set_view_mode("single", persist=False)
        piano_window.show()
        process(app)

        display = chord_window.display_widget
        display.main_label.setText("C13sus4(b9)")
        display.alt_label.setText("F∆(b5)   B11(b5)no3   E♭sus4(add♭2)")
        display.alt_label.show()

        expected_font = "Segoe UI"
        font_widgets = {
            "application": app.font(),
            "main_chord": display.main_label.font(),
            "alternate_chord": display.alt_label.font(),
            "panel_button": controls.display_panel_section_buttons[0].font(),
            "chord_combo": controls.display_panel_chord_combo.font(),
        }
        resolved_fonts = {
            name: QFontInfo(font).family() for name, font in font_widgets.items()
        }
        report["resolved_fonts"] = resolved_fonts
        checks["segoe_ui_resolves_everywhere"] = all(
            expected_font.lower() in family.lower()
            for family in resolved_fonts.values()
        )

        responsive_sizes: dict[str, dict[str, int]] = {}
        stable_sizes: dict[str, list[int]] = {}
        for width, height in ((800, 600), (1280, 760)):
            piano_window.resize(width, height)
            process(app)
            display._apply_responsive_fonts()
            process(app)
            responsive_sizes[f"{width}x{height}"] = {
                "main": display.main_label.font().pointSize(),
                "alternate": display.alt_label.font().pointSize(),
            }
            checks[f"main_chord_fits_{width}x{height}"] = label_fits(display.main_label)
            checks[f"alternate_chords_fit_{width}x{height}"] = label_fits(display.alt_label)
            checks[f"chord_hierarchy_{width}x{height}"] = (
                display.main_label.font().pointSize()
                > display.alt_label.font().pointSize()
            )

            before = [piano_window.width(), piano_window.height()]
            controls.octaves_spin.setValue(2 if width == 800 else 5)
            chord_index = min(3, controls.display_panel_chord_combo.count() - 1)
            controls.display_panel_chord_combo.setCurrentIndex(max(0, chord_index))
            process(app)
            after = [piano_window.width(), piano_window.height()]
            stable_sizes[f"{width}x{height}"] = after
            checks[f"window_does_not_resize_{width}x{height}"] = before == after
            capture(piano_window, output_dir / f"piano-{width}x{height}.png", app)

        report["responsive_chord_sizes"] = responsive_sizes
        report["stable_window_sizes"] = stable_sizes
        checks["responsive_chord_font_scales"] = (
            responsive_sizes["800x600"]["main"]
            <= responsive_sizes["1280x760"]["main"]
        )
        checks["alternate_chords_are_one_line"] = "\n" not in display.alt_label.text()

        piano = piano_window.piano
        white_size = piano._interval_label_font_size(42.0, 220.0, False)
        black_size = piano._interval_label_font_size(25.0, 135.0, True)
        report["keyboard_label_sizes"] = {"white": white_size, "black": black_size}
        checks["black_key_labels_are_smaller"] = black_size < white_size

        controls._set_instrument_view("guitar", persist=False, show_status=False)
        fretboard.set_notes(
            {60, 64, 67, 70, 74},
            main.analizar_cifrado_alternativos({60, 64, 67, 70, 74}),
            [60, 64, 67, 70, 74],
        )
        piano_window.resize(1280, 760)
        process(app)

        stack_width = piano_window.instrument_stack.contentsRect().width()
        checks["fretboard_fills_instrument_width"] = abs(fretboard.width() - stack_width) <= 2
        mapped_right = fretboard._embedded_map_point(
            fretboard.IMAGE_WIDTH,
            fretboard.EMBEDDED_SOURCE_TOP + fretboard.EMBEDDED_SOURCE_HEIGHT,
        )
        checks["fretboard_image_maps_full_width"] = abs(mapped_right.x() - fretboard.width()) <= 1

        string_positions = [
            fretboard._embedded_map_point(0.0, y).y() for y in fretboard.STRING_Y
        ]
        minimum_gap = min(
            abs(second - first)
            for first, second in zip(string_positions, string_positions[1:])
        )
        marker_diameter = fretboard._embedded_marker_radius() * 2.0
        report["fretboard_marker_geometry"] = {
            "minimum_string_gap": minimum_gap,
            "marker_diameter": marker_diameter,
        }
        checks["marker_diameter_matches_string_gap"] = abs(marker_diameter - minimum_gap) < 0.01
        capture(piano_window, output_dir / "guitar-chord-1280x760.png", app)

        fretboard.set_notes(set(), {})
        scale_notes = FretboardWidget.guitar_scale_notes(0, main.SCALE_PATTERNS["Mayor"])
        scale_colors = {
            note: QColor(52, 199, 89) if note % 12 == 0 else QColor(45, 105, 220)
            for note in scale_notes
        }
        fretboard.set_display_overlays({}, scale_colors, {}, 0, "C")
        process(app)
        checks["scale_keeps_every_note"] = {
            placement[0] for placement in fretboard.display_assignment
        } == set(scale_notes)
        checks["scale_markers_are_full_opacity"] = all(
            fretboard._marker_opacity(note, secondary) == 1.0
            for note, _string, _fret, _x, _y, secondary in fretboard.display_assignment
        )
        capture(piano_window, output_dir / "guitar-scale-1280x760.png", app)

        controls.resize(700, 560)
        capture(controls, output_dir / "controls-700x560.png", app)
        checks["controls_keep_requested_size"] = controls.size().width() == 700 and controls.size().height() == 560

        for name, menu in (
            ("chords", controls.chord_menu),
            ("scales", controls.scale_menu),
            ("controls", controls.controls_menu),
        ):
            render_menu(menu, output_dir / f"menu-{name}.png", app)
            checks[f"menu_{name}_meets_minimum_width"] = menu.width() >= menu.minimumWidth()

        report["screenshots"] = sorted(path.name for path in output_dir.glob("*.png"))
        report["passed"] = all(checks.values())
        (output_dir / "windows-ui-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0 if report["passed"] else 1
    finally:
        controls.timer.stop()
        controls.capture_timer.stop()
        controls._close_midi_inputs()
        controls.close()
        piano_window.close()
        chord_window.close()
        staff_window.close()
        process(app)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(main_smoke(arguments.output.resolve()))
