import os
import sys


def resource_path(*parts):
    """Percorso di una risorsa: funziona sia da sorgente sia in PyInstaller (--onefile, sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


PTR_COUNT   = 298
HEADER_SIZE = 0x254
MAX_SIZE    = 16701
GRID_ROWS   = 25
GRID_COLS   = 40
CELL        = 20
MIN_COL     = 3
MIN_ROW     = 2
MAX_COL     = GRID_COLS - 3
MAX_ROW     = GRID_ROWS - 2
DRAG_THRESHOLD  = 4
REQUIRED_FILES  = ["heroquest.fnt", "background1.png", "background2.png", "background3.png"]


PAL = {
    "bg":         "#0d0f14",
    "grid":       "#1a1e2a",
    "grid_num":   "#2a3a4a",
    "box_border": "#00e5ff",
    "box_fill":   "#0a1a20",
    "page_txt":   "#3e2723",
    "text":       "#e8f4f8",
    "btn":        "#1e2840",
    "btn_hover":  "#2a3860",
    "accent":     "#ff6b35",
    "label":      "#6b8090",
    "opt":        "#00ff99",
    "plain":      "#aaccee",
    "toolbar":    "#10141f",
    "box_txt":    "#ffe566",
}

GLYPH_COLORS = (PAL["box_txt"], PAL["page_txt"], PAL["text"], PAL["opt"], PAL["accent"])
GLYPH_RANGE  = range(0x20, 0x6F)
COMPRESSED_LANGUAGE_FILES = {"ITALIAN.BIN", "ENGLISH.BIN", "SPANISH.BIN", "GERMAN.BIN", "FRENCH.BIN"}
COMPRESSED_VGA_FILES = {
                    "BOOK.VGA",
                    "BORDERED.VGA",
                    "FURN.VGA",
                    "GRAPHICS.VGA",
                    "GREMLIN.VGA",
                    "HERO1.VGA",
                    "HERO2.VGA",
                    "HERO3.VGA",
                    "HERO4.VGA",
                    "HERO6.VGA",
                    "HERO7.VGA",
                    "INVENT.VGA",
                    "MAPS.VGA",
                    "MEN.VGA",
                    "MONSTERS.VGA",
                    "ODDS&SOD.VGA",
                    "PIC1.VGA",
                    "QUESTB.VGA",
                    "shopmp.vga",
                    "SHOPSP.VGA",
                    "SPELLIT.VGA",
                    "SPRITES.VGA",
                    "TEXT1.VGA",
                    "WIZBACK.VGA"
                    }

COMPRESSED_FILES = COMPRESSED_LANGUAGE_FILES | COMPRESSED_VGA_FILES

def _unp_variants(names):
    return {os.path.splitext(name)[0].upper() + ".UNP" for name in names}

UNCOMPRESSED_LANGUAGE_FILES = _unp_variants(COMPRESSED_LANGUAGE_FILES)
UNCOMPRESSED_VGA_FILES      = _unp_variants(COMPRESSED_VGA_FILES)
UNCOMPRESSED_FILES          = UNCOMPRESSED_LANGUAGE_FILES | UNCOMPRESSED_VGA_FILES
KNOWN_DATA_FILES = COMPRESSED_FILES | UNCOMPRESSED_FILES
KNOWN_LANGUAGE_FILES = COMPRESSED_LANGUAGE_FILES | UNCOMPRESSED_LANGUAGE_FILES

FILE_TYPES = [
    ("BIN files",  "*.bin"),
    ("EXE files",  "*.exe"),
    ("VGA files",  "*.VGA"),
    ("Sound bank", "*.alb;*.rld"),   # <-- nuovo
    ("RAW image", "*.raw"),
    ("UNP files (uncompressed)", "*.unp"),
    ("All files",  "*.*"),
]

