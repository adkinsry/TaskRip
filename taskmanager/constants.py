"""Grid, snap, color, and hotkey constants for the task manager."""

# Grid system — all window dimensions are multiples of GRID_UNIT
GRID_UNIT = 40  # pixels

# Window size limits (in grid units)
MIN_WIDTH_UNITS = 5    # 200px
MIN_HEIGHT_UNITS = 3   # 120px
MAX_WIDTH_UNITS = 20   # 800px
MAX_HEIGHT_UNITS = 15  # 600px
DEFAULT_WIDTH_UNITS = 6   # 240px
DEFAULT_HEIGHT_UNITS = 4  # 160px

# Snapping
SNAP_THRESHOLD = 20  # pixels — windows snap when edges are within this distance

# Title bar
TITLE_BAR_HEIGHT = 28

# ── Themes ────────────────────────────────────────────────────────
# Each theme is a dict of color keys. The active theme is selected at runtime.

THEMES = {
    "light": {
        "border": "#bdbdbd",
        "border_focused": "#757575",
        "bg": "#ffffff",
        "title_bg": "#f5f5f5",
        "text": "#212121",
        "subtitle": "#757575",
        "accent": "#1976d2",
        "done_btn": "#4caf50",
        "done_btn_hover": "#388e3c",
        "archive_header_bg": "#fafafa",
        "input_bg": "#ffffff",
        "dialog_bg": "#fafafa",
    },
    "dark": {
        "border": "#555555",
        "border_focused": "#888888",
        "bg": "#2d2d2d",
        "title_bg": "#353535",
        "text": "#e0e0e0",
        "subtitle": "#9e9e9e",
        "accent": "#64b5f6",
        "done_btn": "#66bb6a",
        "done_btn_hover": "#43a047",
        "archive_header_bg": "#252525",
        "input_bg": "#383838",
        "dialog_bg": "#252525",
    },
}

# Fallback color references (overwritten at runtime by theme loader)
BORDER_COLOR = "#bdbdbd"
BORDER_COLOR_FOCUSED = "#757575"
BG_COLOR = "#ffffff"
TITLE_BG = "#f5f5f5"
TEXT_COLOR = "#212121"
SUBTITLE_COLOR = "#757575"
ACCENT_COLOR = "#1976d2"
DONE_BUTTON_COLOR = "#4caf50"
DONE_BUTTON_HOVER = "#388e3c"
ARCHIVE_HEADER_BG = "#fafafa"
INPUT_BG = "#ffffff"
DIALOG_BG = "#fafafa"

# Animations (ms)
ARCHIVE_ANIM_DURATION = 350
SLIDE_ANIM_DURATION = 250
APPEAR_ANIM_DURATION = 200

# Default hotkey for screen capture (Super+T)
DEFAULT_HOTKEY = "<cmd>+t"

# Database
DB_FILENAME = "taskmanager.db"
SETTINGS_FILENAME = "settings.json"

# Archive viewer
ARCHIVE_WINDOW_WIDTH = 600
ARCHIVE_WINDOW_HEIGHT = 500


def apply_theme(name):
    """Apply a named theme by updating module-level color globals.

    Uses sys.modules[__name__] rather than re-importing by string path so
    it works regardless of how the package was loaded (normal import,
    PyInstaller bundle, or when taskmanager lives under a different
    top-level name).
    """
    import sys
    c = sys.modules[__name__]
    theme = THEMES.get(name, THEMES["light"])
    c.BORDER_COLOR = theme["border"]
    c.BORDER_COLOR_FOCUSED = theme["border_focused"]
    c.BG_COLOR = theme["bg"]
    c.TITLE_BG = theme["title_bg"]
    c.TEXT_COLOR = theme["text"]
    c.SUBTITLE_COLOR = theme["subtitle"]
    c.ACCENT_COLOR = theme["accent"]
    c.DONE_BUTTON_COLOR = theme["done_btn"]
    c.DONE_BUTTON_HOVER = theme["done_btn_hover"]
    c.ARCHIVE_HEADER_BG = theme["archive_header_bg"]
    c.INPUT_BG = theme.get("input_bg", "#ffffff")
    c.DIALOG_BG = theme.get("dialog_bg", "#fafafa")
