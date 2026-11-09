"""Sistema de diseño: tokens de color, tipografía y hoja de estilo global (claro y oscuro)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from string import Template

from PySide6.QtCore import QLibraryInfo, Qt, QTranslator
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

SCHEMES = {
    "light": Qt.ColorScheme.Light,
    "dark": Qt.ColorScheme.Dark,
    "system": Qt.ColorScheme.Unknown,  # sigue el esquema del sistema
}

ASSETS = Path(__file__).parent / "assets"
FONTS = (
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Medium.ttf",
)
UI_FAMILIES = ["Inter", "Segoe UI", "sans-serif"]
MONO_FAMILIES = ["JetBrains Mono", "Cascadia Mono", "Consolas", "monospace"]
UI_SIZE, MONO_SIZE = 10, 9  # puntos


@dataclass(frozen=True)
class Tokens:
    bg: str  # fondo principal
    surface: str  # barras laterales y superior
    panel: str  # tarjetas y tablas
    raised: str  # paneles elevados, cabeceras y controles
    border: str  # separadores (decorativo)
    control_border: str  # borde de controles: debe verse (3:1)
    hover: str
    selection: str
    accent: str
    on_accent: str  # texto sobre el color principal
    text: str
    muted: str  # texto secundario
    disabled: str
    danger_text: str  # texto de error: el rojo de severidad no llega a 4,5:1 sobre un panel
    critical: str  # severidad y estados: marcas, nunca texto
    high: str
    warning: str
    safe: str
    info: str
    neutral: str


DARK = Tokens(
    bg="#0B1120",
    surface="#111827",
    panel="#151F32",
    raised="#1C2940",
    border="#263449",
    control_border="#64748B",
    hover="#22314C",
    selection="#1D3B57",
    accent="#38BDF8",
    on_accent="#0B1120",
    text="#F1F5F9",
    muted="#94A3B8",
    disabled="#64748B",
    danger_text="#FCA5A5",
    critical="#EF4444",
    high="#F97316",
    warning="#F59E0B",
    safe="#22C55E",
    info="#38BDF8",
    neutral="#94A3B8",
)

LIGHT = Tokens(
    bg="#F1F5F9",
    surface="#FFFFFF",
    panel="#FFFFFF",
    raised="#F8FAFC",
    border="#E2E8F0",
    control_border="#64748B",
    hover="#E2E8F0",
    selection="#BAE6FD",
    accent="#0369A1",
    on_accent="#FFFFFF",
    text="#0F172A",
    muted="#475569",
    disabled="#94A3B8",
    danger_text="#B91C1C",
    critical="#DC2626",
    high="#C2410C",
    warning="#A16207",
    safe="#15803D",
    info="#0369A1",
    neutral="#64748B",
)

# Severidad de un hallazgo → token. La misma escala en toda la aplicación.
SEVERITY_TONES = {
    "critical": "critical",
    "high": "high",
    "medium": "warning",
    "low": "info",
    "info": "neutral",
}

_requested = "dark"
_fonts_loaded = False


def load_fonts() -> list[str]:
    """Registra las fuentes incluidas una sola vez; devuelve las que no se pudieron cargar."""
    global _fonts_loaded
    if _fonts_loaded:
        return []
    failed = [
        name
        for name in FONTS
        if QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name)) == -1
    ]
    _fonts_loaded = not failed
    return failed


def _effective() -> str:
    if _requested != "system":
        return _requested
    is_light = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
    return "light" if is_light else "dark"


def current() -> Tokens:
    return LIGHT if _effective() == "light" else DARK


def tone_color(tone: str) -> QColor:
    """Color de un tono semántico (`critical`, `safe`…), según el tema activo."""
    return QColor(getattr(current(), tone))


@lru_cache(maxsize=1)
def mono_font() -> QFont:
    """Para datos técnicos: IP, hashes, identificadores y fechas."""
    font = QFont(MONO_FAMILIES, MONO_SIZE)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def stylesheet(tokens: Tokens, scheme: str) -> str:
    template = Template((ASSETS / "theme.qss").read_text(encoding="utf-8"))
    glyphs = (ASSETS / "qss").as_posix()
    return template.substitute(
        asdict(tokens),
        check=f"{glyphs}/check-{scheme}.svg",
        chevron_down=f"{glyphs}/chevron-down-{scheme}.svg",
        chevron_up=f"{glyphs}/chevron-up-{scheme}.svg",
        close=f"{glyphs}/x-{scheme}.svg",
        tick=f"{glyphs}/tick-{scheme}.svg",
    )


def _palette(tokens: Tokens) -> QPalette:
    role = QPalette.ColorRole
    palette = QPalette()
    for color_role, value in (
        (role.Window, tokens.bg),
        (role.WindowText, tokens.text),
        (role.Base, tokens.panel),
        (role.AlternateBase, tokens.raised),
        (role.Text, tokens.text),
        (role.Button, tokens.raised),
        (role.ButtonText, tokens.text),
        (role.BrightText, tokens.text),
        (role.ToolTipBase, tokens.raised),
        (role.ToolTipText, tokens.text),
        (role.PlaceholderText, tokens.muted),
        (role.Highlight, tokens.selection),
        (role.HighlightedText, tokens.text),
        (role.Link, tokens.accent),
    ):
        palette.setColor(color_role, QColor(value))
    for color_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, color_role, QColor(tokens.disabled))
    return palette


def refresh() -> None:
    """Aplica a toda la aplicación los tokens del tema activo."""
    app = QApplication.instance()
    if app is None:
        return
    tokens = current()
    app.setPalette(_palette(tokens))
    app.setStyleSheet(stylesheet(tokens, _effective()))


def install(app: QApplication) -> None:
    """Prepara la aplicación: estilo base, fuentes y seguimiento del esquema del sistema."""
    app.setStyle("Fusion")  # el estilo nativo de Windows 11 ignora parte de la hoja de estilo
    load_fonts()
    translator = QTranslator(app)  # botones estándar en español: «Cancelar», no «Cancel»
    if translator.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    font = QFont(UI_FAMILIES, UI_SIZE)
    app.setFont(font)
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: refresh())


def apply_theme(theme: str) -> None:
    """Aplica uno de `settings.THEMES` a toda la aplicación."""
    global _requested
    _requested = theme
    QGuiApplication.styleHints().setColorScheme(SCHEMES[theme])
    refresh()
