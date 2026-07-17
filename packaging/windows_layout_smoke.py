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

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtGui import QColor, QFontInfo, QFontMetrics, QPainter, QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QWidget  # noqa: E402

import main  # noqa: E402
from midi_study import StudyNote  # noqa: E402
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


def capture(widget: QWidget, path: Path, app: QApplication) -> QPixmap:
    widget.ensurePolished()
    widget.show()
    process(app)
    widget.repaint()
    process(app)
    ratio = max(1.0, widget.devicePixelRatioF())
    pixmap = QPixmap(
        max(1, int(round(widget.width() * ratio))),
        max(1, int(round(widget.height() * ratio))),
    )
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    widget.render(painter)
    painter.end()
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"No se pudo guardar {path.name}")
    return pixmap


def capture_native(widget: QWidget, path: Path, app: QApplication) -> QPixmap:
    widget.ensurePolished()
    widget.show()
    process(app)
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"No se pudo guardar {path.name}")
    return pixmap


def opaque_pixel_coverage(pixmap: QPixmap) -> float:
    image = pixmap.toImage()
    total = image.width() * image.height()
    if total <= 0:
        return 0.0
    opaque = 0
    for y in range(image.height()):
        for x in range(image.width()):
            opaque += int(image.pixelColor(x, y).alpha() > 16)
    return opaque / total


def horizontal_content_coverage(
    pixmap: QPixmap,
    root: QWidget,
    child: QWidget,
) -> float:
    image = pixmap.toImage()
    ratio = max(1.0, pixmap.devicePixelRatio())
    origin = child.mapTo(root, QPoint(0, 0))
    y = int(round((origin.y() + child.height() * 0.5) * ratio))
    left = int(round(origin.x() * ratio))
    right = int(round((origin.x() + child.width()) * ratio))
    if y < 0 or y >= image.height() or right <= left:
        return 0.0
    populated = 0
    samples = 0
    for x in range(max(0, left), min(image.width(), right)):
        color = image.pixelColor(x, y)
        populated += int(max(color.red(), color.green(), color.blue()) > 18)
        samples += 1
    return populated / samples if samples else 0.0


def label_fits(label: QLabel) -> bool:
    text = label.text().strip()
    if not text:
        return True
    metrics = QFontMetrics(label.font())
    contents = label.contentsRect()
    ink_bounds = metrics.tightBoundingRect(text)
    return (
        metrics.horizontalAdvance(text) <= contents.width() + 2
        and ink_bounds.height() <= contents.height() + 2
    )


def visible_children_fit(parent: QWidget) -> bool:
    bounds = parent.rect()
    for child in parent.findChildren(QWidget):
        if not child.isVisible():
            continue
        geometry = child.geometry()
        if geometry.right() > bounds.right() + 1:
            return False
        if geometry.bottom() > bounds.bottom() + 1:
            return False
    return True


def render_menu(menu: QMenu, path: Path, app: QApplication) -> QPixmap:
    hint = menu.sizeHint()
    menu.resize(max(menu.minimumWidth(), hint.width()), max(40, hint.height()))
    pixmap = capture_native(menu, path, app)
    menu.hide()
    return pixmap


def main_smoke(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"platform": sys.platform, "checks": {}}
    checks: dict[str, bool] = report["checks"]  # type: ignore[assignment]

    if not sys.platform.startswith("win"):
        raise RuntimeError("Esta verificación debe ejecutarse en Windows.")

    app = QApplication.instance() or QApplication([])
    app.setFont(main.ui_font(10))
    app.setQuitOnLastWindowClosed(False)
    report["qt_platform"] = QApplication.platformName()
    checks["native_windows_platform"] = QApplication.platformName() == "windows"
    main.mido.get_input_names = lambda: []

    ControlWindow.CONFIG_PATH = output_dir / "preferences.json"
    ControlWindow.APPEARANCE_CONFIG_PATH = output_dir / "appearance.json"
    ControlWindow.STUDY_LIBRARY_PATH = output_dir / "study-library"

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
            "study_name": controls.study_name_edit.font(),
            "study_mode": controls.study_mode_buttons[0][1].font(),
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
        chord_label_geometry: dict[str, dict[str, list[int]]] = {}
        for width, height in ((800, 600), (1280, 760)):
            piano_window.resize(width, height)
            process(app)
            display._apply_responsive_fonts()
            process(app)
            responsive_sizes[f"{width}x{height}"] = {
                "main": display.main_label.font().pointSize(),
                "alternate": display.alt_label.font().pointSize(),
            }
            chord_label_geometry[f"{width}x{height}"] = {
                "window": [piano_window.width(), piano_window.height()],
                "display": [display.width(), display.height()],
                "main": [display.main_label.width(), display.main_label.height()],
                "alternate": [display.alt_label.width(), display.alt_label.height()],
                "main_text": [
                    QFontMetrics(display.main_label.font()).horizontalAdvance(
                        display.main_label.text()
                    ),
                    QFontMetrics(display.main_label.font())
                    .tightBoundingRect(display.main_label.text())
                    .height(),
                ],
                "alternate_text": [
                    QFontMetrics(display.alt_label.font()).horizontalAdvance(
                        display.alt_label.text()
                    ),
                    QFontMetrics(display.alt_label.font())
                    .tightBoundingRect(display.alt_label.text())
                    .height(),
                ],
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
        report["chord_label_geometry"] = chord_label_geometry
        report["stable_window_sizes"] = stable_sizes
        checks["responsive_chord_font_scales"] = (
            responsive_sizes["800x600"]["main"]
            <= responsive_sizes["1280x760"]["main"]
        )
        checks["alternate_chords_are_one_line"] = "\n" not in display.alt_label.text()

        controls._set_display_panel_section(2)
        controls.study_notes = [
            StudyNote(60, 0, 400, 96, 0),
            StudyNote(64, 20, 380, 92, 0),
            StudyNote(67, 35, 365, 88, 0),
            StudyNote(72, 620, 300, 90, 0),
        ]
        controls.study_selected_channels = {0}
        controls._study_rebuild_steps()
        controls._study_set_mode("guided")
        study_geometry: dict[str, object] = {}
        for width, height in ((800, 600), (1280, 760)):
            piano_window.resize(width, height)
            process(app)
            page = controls.display_panel_section_stack.currentWidget()
            before = [piano_window.width(), piano_window.height()]
            controls.study_speed_slider.setValue(12)
            controls.study_tolerance_slider.setValue(75)
            process(app)
            after = [piano_window.width(), piano_window.height()]
            study_geometry[f"{width}x{height}"] = {
                "window": after,
                "page": [page.width(), page.height()],
                "chord_display": [display.width(), display.height()],
                "instrument": [
                    piano_window.instrument_stack.width(),
                    piano_window.instrument_stack.height(),
                ],
            }
            checks[f"study_window_does_not_resize_{width}x{height}"] = before == after
            checks[f"study_controls_fit_{width}x{height}"] = visible_children_fit(page)
            checks[f"study_chord_is_visible_{width}x{height}"] = (
                bool(display.main_label.text().strip())
                and display.height() >= 48
                and label_fits(display.main_label)
            )
            capture(
                piano_window,
                output_dir / f"study-piano-{width}x{height}.png",
                app,
            )
        report["study_geometry"] = study_geometry
        checks["study_expected_notes_reach_piano"] = set(
            controls.piano.display_chord_notes
        ) == {60, 64, 67}
        before_instrument_switch = [piano_window.width(), piano_window.height()]
        controls._set_instrument_view("guitar", persist=False, show_status=False)
        process(app)
        checks["study_instrument_switch_does_not_resize"] = (
            before_instrument_switch
            == [piano_window.width(), piano_window.height()]
        )
        checks["study_expected_notes_reach_fretboard"] = set(
            controls.fretboard_widget.display_chord_notes
        ) == {60, 64, 67}
        for width, height in ((800, 600), (1280, 760)):
            piano_window.resize(width, height)
            process(app)
            checks[f"study_guitar_keeps_size_{width}x{height}"] = (
                [piano_window.width(), piano_window.height()] == [width, height]
            )
            capture(
                piano_window,
                output_dir / f"study-guitar-{width}x{height}.png",
                app,
            )
        controls._set_display_panel_section(0)
        controls._set_instrument_view("piano", persist=False, show_status=False)

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
        scale_notes = FretboardWidget.guitar_scale_notes(0, main.SCALE_PATTERNS["mayor"])
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
        scale_capture = capture(
            piano_window,
            output_dir / "guitar-scale-1280x760.png",
            app,
        )
        scale_coverage = horizontal_content_coverage(
            scale_capture,
            piano_window,
            fretboard,
        )
        report["scale_fretboard_horizontal_coverage"] = scale_coverage
        checks["scale_fretboard_renders_continuously"] = scale_coverage >= 0.85

        controls.resize(700, 560)
        capture(controls, output_dir / "controls-700x560.png", app)
        report["controls_size"] = [controls.width(), controls.height()]
        checks["controls_keep_requested_size"] = controls.size().width() == 700 and controls.size().height() == 560

        menu_coverages: dict[str, float] = {}
        for name, menu in (
            ("chords", controls.chord_menu),
            ("scales", controls.scale_menu),
            ("controls", controls.controls_menu),
        ):
            menu_pixmap = render_menu(menu, output_dir / f"menu-{name}.png", app)
            menu_coverages[name] = opaque_pixel_coverage(menu_pixmap)
            checks[f"menu_{name}_meets_minimum_width"] = menu.width() >= menu.minimumWidth()
            checks[f"menu_{name}_renders_visible_content"] = menu_coverages[name] >= 0.95
        report["menu_opaque_coverage"] = menu_coverages

        report["screenshots"] = sorted(path.name for path in output_dir.glob("*.png"))
        report["passed"] = all(checks.values())
        (output_dir / "windows-ui-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0 if report["passed"] else 1
    finally:
        controls._study_shutdown()
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
