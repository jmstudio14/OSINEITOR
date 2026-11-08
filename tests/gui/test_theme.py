"""Sistema de diseño: contraste WCAG por tema, hoja de estilo válida y assets presentes."""

from __future__ import annotations

import os
from dataclasses import fields

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QtMsgType  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402

from osineitor_gui.ui import icons, theme  # noqa: E402
from osineitor_gui.ui.widgets import safe_tooltip  # noqa: E402


def luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


THEMES = {"dark": theme.DARK, "light": theme.LIGHT}


@pytest.mark.parametrize("tokens", THEMES.values(), ids=THEMES.keys())
def test_text_reaches_aa_on_every_surface(tokens):
    for surface in (tokens.bg, tokens.surface, tokens.panel, tokens.raised, tokens.selection):
        assert contrast(tokens.text, surface) >= 4.5
    for surface in (tokens.bg, tokens.surface, tokens.panel, tokens.raised):
        assert contrast(tokens.muted, surface) >= 4.5
        assert contrast(tokens.danger_text, surface) >= 4.5
    assert contrast(tokens.on_accent, tokens.accent) >= 4.5


@pytest.mark.parametrize("tokens", THEMES.values(), ids=THEMES.keys())
def test_marks_and_controls_reach_three_to_one(tokens):
    marks = (tokens.critical, tokens.high, tokens.warning, tokens.safe, tokens.info, tokens.neutral)
    for surface in (tokens.panel, tokens.raised):
        assert contrast(tokens.control_border, surface) >= 3
        assert contrast(tokens.accent, surface) >= 3
        for mark in marks:
            assert contrast(mark, surface) >= 3


def test_dark_tokens_keep_the_requested_palette():
    dark = theme.DARK
    assert (dark.bg, dark.surface, dark.panel, dark.raised, dark.border) == (
        "#0B1120",
        "#111827",
        "#151F32",
        "#1C2940",
        "#263449",
    )
    assert (dark.accent, dark.text, dark.muted) == ("#38BDF8", "#F1F5F9", "#94A3B8")
    assert (dark.critical, dark.high, dark.warning, dark.safe, dark.info) == (
        "#EF4444",
        "#F97316",
        "#F59E0B",
        "#22C55E",
        "#38BDF8",
    )


def test_both_themes_define_the_same_tokens_and_every_severity_has_a_tone():
    assert {f.name for f in fields(theme.DARK)} == {f.name for f in fields(theme.LIGHT)}
    for tone in theme.SEVERITY_TONES.values():
        assert hasattr(theme.DARK, tone)


@pytest.mark.parametrize("scheme", THEMES)
def test_the_stylesheet_resolves_every_token_and_only_points_to_existing_glyphs(scheme):
    sheet = theme.stylesheet(THEMES[scheme], scheme)
    assert "$" not in sheet
    for key in ("check", "chevron-down", "chevron-up", "x"):
        assert (theme.ASSETS / "qss" / f"{key}-{scheme}.svg").exists()


def test_qt_parses_the_stylesheet_without_warnings(qapp, qtlog):
    for name in ("light", "dark"):  # acaba en oscuro: el tema es global
        theme.apply_theme(name)
    qapp.processEvents()
    problems = [r.message for r in qtlog.records if r.type != QtMsgType.QtDebugMsg]
    assert not [m for m in problems if "style" in m.lower() or "parse" in m.lower()]


def test_included_fonts_load(qapp):
    theme._fonts_loaded = False
    assert theme.load_fonts() == []
    families = QFontDatabase.families()
    assert "Inter" in families and "JetBrains Mono" in families


def test_every_icon_renders(qapp):
    names = sorted(p.stem for p in icons.ICONS.glob("*.svg"))
    assert len(names) >= 20
    for name in names:
        assert not icons.icon(name).isNull()


def test_tooltips_with_third_party_data_are_inert():
    assert safe_tooltip('<a href="https://evil.test">x</a>') == (
        "<qt>&lt;a href=&quot;https://evil.test&quot;&gt;x&lt;/a&gt;</qt>"
    )
    assert safe_tooltip("") == ""
    assert safe_tooltip("x" * 600).endswith("…</qt>")
