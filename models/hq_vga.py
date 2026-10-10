import os
from encoder import compress, decompress

VGA_WIDTH  = 320
VGA_HEIGHT = 200
VGA_FULLSCREEN_SIZE = VGA_WIDTH * VGA_HEIGHT  # 64000

_HQ_PAL_HEX = (
    "ff00ff04040c0c0c1414141c1c1c241000080c000c18040c1c10102414183020"
    "280410040c140c1018102810082c20000c04001408001c10082418100808080c"
    "0c0c1010101414141000001c00002400001c1c1c3030303430343438383c3c3c"
    "3d2b223a271e37241a342117321e142f1c112c190e29170b2715092412072110"
    "051f0e041c0d02190b011609001408003e3c383b383438353035322c322e292f"
    "2b252c282229251f26221c231f19201c161d19131a161117130e14100c110e0a"
    "0d0a0609060224243d2020391b1b3618183214142f11112b0e0e280b0b240909"
    "2107071d05051a0303170202130101100c150e09120b061008030d06020b0405"
    "0f072f2f2f2b2b2b2727272323231f1f1f1b1b1b1717171313130f0f0f0b0b0b"
    "3428173123142f1e122c1a0f2a150d28110b250d092309072006061e04071c03"
    "071902071701081400081200081000082618252212211e0c1d1b081917041613"
    "011210000f000000000000000000000000000000000000000000000000000000"
    "3e3e333b3b2d39392836362333331f31311a2e2e162c2b1229290f27260c2423"
    "092221061f1e041d1c02001010000c0c1a1501233f2d1e3b281a372316331e12"
    "301a0f2c160c281209250e07210b051d08031905011603011201000e00000b00"
    "3f3f173b3b1437371133330e302e0c2c2a0a282608242306211f051d1b031917"
    "021614011210010e0d000a09000706003f00003b00003800003400003100002d"
    "00002a00002600002300001f00001c00001800001500001200000e00000b0000"
    "002928002726002625002424002323002221002020001f1e001d1d001c1c001b"
    "1a00191900181800161600151500141400000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "3f3f2a3d3d273c3b253a392338372037351e35331c34311a322e18312c162f2a"
    "152e28132c26112b240f29220e28200c261e0b251c0a231a082118072016061e"
    "15051d13041b11031a0f02180e02170c01150b011409001208001107003f3f3f"
)

GREMLIN_PALETTE = (
    "0000003838381018302C00003C20001C00140008000C180C08081C24283C3C0C"
    "00000C0000000C0010003830000000142C303C20243C0814081C00001800003C"
    "0C003C14003C2800101C14142418203024242C38141C2C3408003C18003C1C00"
)

TEXT1_PALETTE = (
    "0400042818101008101810182418202820283C28181008081810102018182820"
    "20101010181818382010301808281000100C100C000804040010000814000818"
    "00081C00082400080804080804040C080C141414201C1C0C0808140C0C181010"
)

PIC1_PALETTE = (
    "0400042818101008101810182418202820283C28181008081810102018182820"
    "20101010181818382010301808281000100C100C000804040010000814000818"
    "00081C00082400080804080804040C080C141414201C1C0C0808140C0C181010"
)

HERO1_PALETTE = (
    "0808081008081010181818202020283028303C30381810102018182820203028"
    "2810101018181820202428282C3030380C04040C0C1414141C1C1C242C242C38"
    "2C34140C0C1C1414241C1C2C24240C0C0C1414141C1C202424282C2C34202824"
)

HERO2_PALETTE = (
    "0000000C040C140C141C141C241C2414040C1C0C1424141C2C1C241810102018"
    "18240C000C0C0C1414141C1C1C2C140008000008000810081018101820182010"
    "0008180810201018241820140C0C1C1414200800080808101010181818281000"
)

HERO3_PALETTE = (
    "08080828181010081018101820182028202830283010000C18101420181C2820"
    "24101010181818202020282828303030100C0C2C1C14140C141C141C241C242C"
    "242C342C34140C101C1418241C1C2C24241414141C1C1C2424242C2C2C343434"
)

HERO4_PALETTE = (
    "08080828181010081018101820182028202830283010080C1810102018182820"
    "2010101018181820202028282830303020100824140C140C141C141C241C242C"
    "242C342C34140C0C100C101C1414241C1C10080C1414141C1C1C2424240C080C"
)

HERO6_PALETTE = (
    "0000000C040C140C141C141C241C2414040C1C0C1424141C2820201810102018"
    "18240C000C0C0C1414141C1C1C30282808000008000810081018101820182010"
    "0008180810201018241820140C0C1C1414200800080808101010181818281000"
)

HERO7_PALETTE = (
    "0000002418202810082004001800001000000800003C10003008002800002000"
    "003400083C180818140010080C180C10240C041C04001400000C000024202438"
    "0C042C08002400043000043814043C1C083C240C3C2C10280C08200C081C1418"
)

DEFAULT_PALETTE = bytes.fromhex(_HQ_PAL_HEX)
assert len(DEFAULT_PALETTE) == 768, f"Malformed palette: {len(DEFAULT_PALETTE)} byte"


def load_palette_file(path: str) -> bytes:
    data = open(path, "rb").read()
    if len(data) < 768:
        data += bytes(768 - len(data))
    return data
    
def _pad_palette(hex_str: str) -> bytes:
    b = bytes.fromhex(hex_str)
    if len(b) < 768:
        b += bytes(768 - len(b))
    return b

AVAILABLE_PALETTES = {
    "Default": DEFAULT_PALETTE,
    "Gremlin": _pad_palette(GREMLIN_PALETTE),
    "Text 1": _pad_palette(TEXT1_PALETTE),
    "Pic 1": _pad_palette(PIC1_PALETTE),
    "Hero 1": _pad_palette(HERO1_PALETTE),
    "Hero 2": _pad_palette(HERO2_PALETTE),
    "Hero 3": _pad_palette(HERO3_PALETTE),
    "Hero 4": _pad_palette(HERO4_PALETTE),
    "Hero 6": _pad_palette(HERO6_PALETTE),
    "Hero 7": _pad_palette(HERO7_PALETTE),
}

FILENAME_PALETTE_MAP = {
    "gremlin": "Gremlin",
    "text1":   "Text 1",
    "pic1":    "Pic 1",
    "hero1":   "Hero 1",
    "hero2":   "Hero 2",
    "hero3":   "Hero 3",
    "hero4":   "Hero 4",
    "hero6":   "Hero 6",
    "hero7":   "Hero 7",
}

class VgaPaletteMixin:

    def __init__(self):
        self.palette = DEFAULT_PALETTE
        self.palette_name = "Default"

    def _auto_select_palette(self, path: str):
        basename = os.path.splitext(os.path.basename(path))[0].lower()
        palette_name = FILENAME_PALETTE_MAP.get(basename, "Default")
        self.load_preset_palette(palette_name)

    def load_palette(self, path: str):
        self.palette = load_palette_file(path)
        self.palette_name = os.path.basename(path)

    def load_preset_palette(self, name: str):
        if name in AVAILABLE_PALETTES:
            self.palette = AVAILABLE_PALETTES[name]
            self.palette_name = name

    def use_default_palette(self):
        self.palette = DEFAULT_PALETTE
        self.palette_name = "Default"


def palette_to_rgb888(pal_6bit: bytes) -> bytes:
    return bytes(min(255, v * 4) for v in pal_6bit)


def _is_vga_file(path: str) -> bool:
    basename_upper = os.path.basename(path).upper()
    if basename_upper.endswith(".UNP"):
        try:
            raw = open(path, "rb").read()
        except Exception:
            return False
        return len(raw) == VGA_FULLSCREEN_SIZE
    if not basename_upper.endswith((".VGA", ".RAW")):
        return False
    try:
        raw = open(path, "rb").read()
        try:
            decompressed = decompress(raw)
        except Exception:
            decompressed = None
        if decompressed is not None and len(decompressed) == VGA_FULLSCREEN_SIZE:
            return True
        return len(raw) == VGA_FULLSCREEN_SIZE
    except Exception:
        return False


class HQVgaFile(VgaPaletteMixin):

    def __init__(self):
        super().__init__()
        self.raw = b"" 
        self.is_compressed = False

    def load(self, path: str):
        raw = open(path, "rb").read()

        if os.path.basename(path).upper().endswith(".UNP"):
            self.is_compressed = False
            if len(raw) != VGA_FULLSCREEN_SIZE:
                raise Exception(
                    f"Unexpected size for full-screen VGA image: "
                    f"{len(raw)}/{VGA_FULLSCREEN_SIZE} byte"
                )
            self.raw = bytearray(raw)
            self._auto_select_palette(path)
            return

        self.is_compressed = True
        try:
            decompressed = decompress(raw)
        except Exception:
            decompressed = None

        if decompressed is not None and len(decompressed) == VGA_FULLSCREEN_SIZE:
            raw = decompressed
        elif len(raw) == VGA_FULLSCREEN_SIZE:
            self.is_compressed = False
        else:
            raise Exception(
                f"Unepected size for full-screen VGA image: "
                f"{len(decompressed) if decompressed is not None else len(raw)}"
                f"/{VGA_FULLSCREEN_SIZE} byte"
            )
        self.raw = bytearray(raw)
        self._auto_select_palette(path)

    def get_pixel(self, x: int, y: int) -> int:
        return self.raw[y * VGA_WIDTH + x]

    def set_pixel(self, x: int, y: int, color_index: int):
        self.raw[y * VGA_WIDTH + x] = color_index & 0xFF

    def rebuild(self) -> bytes:
        if len(self.raw) != VGA_FULLSCREEN_SIZE:
            raise Exception(
                f"Corrupted VGA image: {len(self.raw)}/{VGA_FULLSCREEN_SIZE} bytes"
            )
        return bytes(self.raw)

    def save(self, path: str):
        data = self.rebuild()
        if not os.path.basename(path).upper().endswith(".UNP"):
            data = compress(data)
        with open(path, "wb") as f:
            f.write(data)

    def import_image_bytes(self, pixel_bytes: bytes):
        if len(pixel_bytes) != VGA_FULLSCREEN_SIZE:
            raise Exception(
                f"Imported image must be {VGA_FULLSCREEN_SIZE} bytes"
                f"({VGA_WIDTH}x{VGA_HEIGHT}), received {len(pixel_bytes)}"
            )
        self.raw = bytearray(pixel_bytes)

    def get_total_size(self) -> int:
        return len(self.raw)


MULTI_VGA_SPECS = {
    "MEN": {
        "blocks": [
            {"name": "Barbarian (attack)",  "width": 0x18, "height": 0x28, "count": 0x3},
            {"name": "Barbarian (defend)",  "width": 0x18, "height": 0x28, "count": 0x1},
            {"name": "Elf (attack)",  "width": 0x18, "height": 0x28, "count": 0x3},
            {"name": "Elf (defend)",  "width": 0x18, "height": 0x28, "count": 0x1},
            {"name": "Wizard (attack)",  "width": 0x18, "height": 0x28, "count": 0x1},
            {"name": "Ragnar (attack)",  "width": 0x18, "height": 0x28, "count": 0x3},
            {"name": "Ragnar (defend)",  "width": 0x18, "height": 0x28, "count": 0x1},
            {"name": "Dwarf (attack)",  "width": 0x20, "height": 0x28, "count": 0x3},
            {"name": "Dwarf (defend)",  "width": 0x20, "height": 0x28, "count": 0x2},
            {"name": "Barbarian (defend)",  "width": 0x20, "height": 0x28, "count": 0x1},
            {"name": "Wizard (attack)",  "width": 0x20, "height": 0x28, "count": 0x2},
            {"name": "Wizard (defend)",  "width": 0x20, "height": 0x28, "count": 0x2},
            {"name": "Ragnar (defend)",  "width": 0x20, "height": 0x28, "count": 0x1},
            {"name": "Elf (defend)",  "width": 0x20, "height": 0x28, "count": 0x1},
            {"name": "Barbarian (dead)", "width": 0x20, "height": 0x14, "count": 1},
            {"name": "Elf (dead)", "width": 0x20, "height": 0x14, "count": 1},
            {"name": "Dwarf (dead)", "width": 0x20, "height": 0x14, "count": 1},
            {"name": "Wizard (dead)", "width": 0x20, "height": 0x14, "count": 1},
            {"name": "Ragnar (dead)", "width": 0x20, "height": 0x14, "count": 1},
            {"name": "Dwarf (attack)", "width": 0x18, "height": 0x21, "count": 1},
        ],
    },
    "MAPS": {
        "blocks": [
            {"name": "2D Map",      "width": 0x100,"height": 0xC5, "count": 1},
            {"name": "Room tiles",   "width": 0x08, "height": 0x08, "count": 0x16},
            {"name": "Free tiles",   "width": 0x08, "height": 0x08, "count": 0x9},
            {"name": "Witch Lord",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "free space",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "Walls & doors",   "width": 0x08, "height": 0x08, "count": 0xF},
            {"name": "Rock",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "Pit",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "heroes",   "width": 0x08, "height": 0x08, "count": 4},
            {"name": "monsters",   "width": 0x08, "height": 0x08, "count": 8},
            {"name": "Stairs",   "width": 0x08, "height": 0x08, "count": 4},
            {"name": "F?",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "furnitures",   "width": 0x08, "height": 0x08, "count": 0x49},
            {"name": "Chest (east)",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "free space",   "width": 0x08, "height": 0x08, "count": 1},
            {"name": "Chest (South)",   "width": 0x08, "height": 0x08, "count": 1},            
            {"name": "free space",   "width": 0x08, "height": 0x08, "count": 0x10},
            {"name": "unknown",     "width": 0x8,  "height": 0x2,  "count": 1},
            {"name": "Monster Selection",   "width": 0x18, "height": 0x1A, "count": 1},
        ],
    },
    "GRAPHICS": {
        "blocks": [
            {"name": "3D tiles","width": 0x30, "height": 0x18, "count": 0x1C},
            {"name": "Walls",   "width": 0x18, "height": 0x34, "count": 0x4},
            {"name": "Doors",   "width": 0x18, "height": 0x2C, "count": 0xC},
        ],
    },
    "SHOPSP": {
        "blocks": [
            {"name": "Shop item",   "width": 0x20, "height": 0x20, "count": 0x20},
            {"name": "Heroes selection",   "width": 0x30, "height": 0x40, "count": 8},
        ],
    },
    "SHOPMP": {
        "blocks": [
            {"name": "Spell Element",   "width": 0x30, "height": 0x40, "count": 4},
            {"name": "Menu items",      "width": 0x30, "height": 0x40, "count": 4},
            {"name": "Character",       "width": 0x20, "height": 0x30, "count": 4},
            {"name": "In Play",         "width": 0x30, "height": 0xC, "count": 1},
            {"name": "Exit",            "width": 0x20, "height": 0x10, "count": 1},
            {"name": "HeroQuest logo",  "width": 0xE0, "height": 0x44, "count": 1},
            {"name": "Selection?",      "width": 0x10, "height": 0x10, "count": 8},
        ],
    },
    "INVENT": {
        "blocks": [
            {"name": "Inventory",   "width": 0x40, "height": 0x5E, "count": 3},
            {"name": "Items",       "width": 0x20, "height": 0x20, "count": 0x20},
            {"name": "Items",       "width": 0x10, "height": 0x14, "count": 3},
        ],
    },
    "ODDS&SOD": {
        "blocks": [
            {"name": "Portrait",        "width": 0x20, "height": 0x2D, "count": 5},
            {"name": "Coin",            "width": 0x20, "height": 0x20, "count": 4},
            {"name": "Mouse pointer",   "width": 0x10, "height": 0x10, "count": 4},
            {"name": "Action icons",    "width": 0x10, "height": 0x10, "count": 0x24},
            {"name": "Small arrows",    "width": 0x10, "height": 0x6, "count": 4},
            {"name": "Scroll roll",     "width": 0x10, "height": 0x10, "count": 3},
            {"name": "Scroll paper",    "width": 0x8, "height": 0x8, "count": 3},           
            {"name": "Number",          "width": 0x8, "height": 0xc, "count": 0xA}, 
            {"name": "Character icon",  "width": 0x10, "height": 0x10, "count": 7},
            {"name": "Projectile",      "width": 0x10, "height": 0x14, "count": 1},
        ],
    },
    "SPELLIT": {
        "blocks": [
            {"name": "Spell icon",   "width": 0x20, "height": 0x20, "count": 0xC},
        ],
    },
    "FURN": {
        "blocks": [
            {"name": "Library",   "width": 0x40, "height": 0x40, "count": 2},
            {"name": "Chest",   "width": 0x20, "height": 0x18, "count": 2},
            {"name": "Closet",   "width": 0x40, "height": 0x40, "count": 2},
            {"name": "Fireplace",   "width": 0x30, "height": 0x3C, "count": 2},
            {"name": "Table",   "width": 0x40, "height": 0x2A, "count": 2},
            {"name": "Throne",   "width": 0x20, "height": 0x2C, "count": 2},
            {"name": "Torture table",   "width": 0x48, "height": 0x3C, "count": 2},
            {"name": "Tomb",   "width": 0x48, "height": 0x34, "count": 2},
            {"name": "Armour rack",   "width": 0x40, "height": 0x3C, "count": 2},
            {"name": "Alchemy table",   "width": 0x40, "height": 0x36, "count": 2},
        ],
    },
    "SPRITES": {
        "blocks": [
            {"name": "Barbarian",  "width": 0x18, "height": 0x28, "count": 0xC},
            {"name": "Dwarf",  "width": 0x18, "height": 0x28, "count": 0xC},
            {"name": "Elf",  "width": 0x18, "height": 0x28, "count": 0xC},
            {"name": "Wizard",  "width": 0x18, "height": 0x28, "count": 0xC},
            {"name": "Ragnar",  "width": 0x18, "height": 0x26, "count": 0xC},
        ],
    },
    "MONSTERS": {
        "blocks": [
            {"name": "Zombie",  "width": 0x18, "height": 0x28, "count": 5},
            {"name": "Mummy",  "width": 0x18, "height": 0x28, "count": 5},
            {"name": "Chaos warrior",  "width": 0x20, "height": 0x30, "count": 5},
            {"name": "Fimir",   "width": 0x20, "height": 0x28, "count": 5},
            {"name": "Skeleton",  "width": 0x20, "height": 0x2C, "count": 5},
            {"name": "Orc",  "width": 0x20, "height": 0x20, "count": 5},
            {"name": "Goblin",  "width": 0x18, "height": 0x20, "count": 5},
            {"name": "Gargoyle",  "width": 0x20, "height": 0x32, "count": 5},
            {"name": "Death",  "width": 0x18, "height": 0x26, "count": 6},
        ],
    },
}

FURNITURE_GROUPS = [
    {"name": "Tomb",              "cols": 3, "rows": 2, "tiles": [0, 1, 2, 3, 4, 5]},
    {"name": "Torture table",     "cols": 3, "rows": 2, "tiles": [6, 7, 8, 9, 10, 11]},
    {"name": "Table",             "cols": 3, "rows": 2, "tiles": [13, 14, 15, 16, 17, 18]},
    {"name": "Alchemist's table", "cols": 3, "rows": 2, "tiles": [19, 20, 21, 22, 23, 24]},
    {"name": "Fireplace",         "cols": 3, "rows": 1, "tiles": [25, 26, 27]},
    {"name": "Cupboard",          "cols": 3, "rows": 1, "tiles": [28, 29, 30]},
    {"name": "Closet",            "cols": 3, "rows": 1, "tiles": [31, 32, 33]},
    {"name": "Armour rack",       "cols": 3, "rows": 1, "tiles": [34, 35, 36]},
    {"name": "Tomb (rotated)",              "cols": 2, "rows": 3, "tiles": [37, 38, 39, 40, 41, 42]},
    {"name": "Torture table (rotated)",     "cols": 2, "rows": 3, "tiles": [43, 44, 45, 46, 47, 48]},
    {"name": "Table (rotated)",             "cols": 2, "rows": 3, "tiles": [49, 50, 51, 52, 53, 54]},
    {"name": "Alchemist's table (rotated)", "cols": 2, "rows": 3, "tiles": [55, 56, 57, 58, 59, 60]},
    {"name": "Fireplace (rotated)",         "cols": 1, "rows": 3, "tiles": [61, 62, 63]},
    {"name": "Cupboard (rotated)",          "cols": 1, "rows": 3, "tiles": [64, 65, 66]},
    {"name": "Closet (rotated)",            "cols": 1, "rows": 3, "tiles": [67, 68, 69]},
    {"name": "Armour rack (rotated)",       "cols": 1, "rows": 3, "tiles": [70, 71, 72]},
]

FURNITURE_BLOCK_NAME = "furnitures"

def _is_multi_vga_file(path: str) -> bool:
    basename = os.path.splitext(os.path.basename(path))[0].upper()
    return basename in MULTI_VGA_SPECS


class VgaSprite:

    def __init__(self, index: int, block_name: str, index_in_block: int,
                 width: int, height: int, offset: int, data: bytearray,
                 format_name: str = ""):
        self.index          = index            # indice globale (0-based) nel file
        self.block_name      = block_name        # nome del blocco di provenienza (solo info)
        self.index_in_block  = index_in_block    # indice (0-based) dentro al blocco
        self.width           = width
        self.height          = height
        self.offset          = offset            # offset assoluto nel file decompresso
        self.data            = data              # bytearray di width*height byte
        self.format_name     = format_name       # nome dello spec/file (es. "MEN", "MAPS", ...)

    @property
    def label(self) -> str:
        MONSTER_FRAME_CODES = {
            "Goblin":        ["00", "58", "59", "5A", "5B"],
            "Orc":           ["01", "5C", "5D", "5E", "5F"],
            "Fimir":         ["02", "60", "61", "62", "63"],
            "Chaos warrior": ["03", "64", "65", "66", "67"],
            "Skeleton":      ["04", "68", "69", "6A", "6B"],
            "Zombie":        ["05", "6C", "6D", "6E", "6F"],
            "Mummy":         ["06", "70", "71", "72", "73"],
            "Gargoyle":      ["07", "74", "75", "76", "77"],
            "Death":         ["78", "79", "7A", "7B", "7C", "7D"],
        }
        
        SPRITE_FRAME_RANGES = {
            "Barbarian": (0x1C, 0x27),
            "Dwarf":     (0x28, 0x33),
            "Elf":       (0x34, 0x3F),
            "Wizard":    (0x40, 0x4B),
            "Ragnar":    (0x4C, 0x57),
        }
        
        SPRITE_FRAME_CODES = {
            name: [f"{i:02X}" for i in range(start, end + 1)]
            for name, (start, end) in SPRITE_FRAME_RANGES.items()
        }
        SEQUENTIAL_HEX_FORMATS = {"MEN"}  # add other files here

        codes = MONSTER_FRAME_CODES.get(self.block_name) or SPRITE_FRAME_CODES.get(self.block_name)

        if codes and self.index_in_block < len(codes):
            return f"{self.block_name} [{codes[self.index_in_block]}] ({self.width}x{self.height})"

        if self.format_name in SEQUENTIAL_HEX_FORMATS:
            code = f"{self.index:02X}"
            return f"{self.block_name} [{code}] ({self.width}x{self.height})"

        return f"{self.block_name} #{self.index_in_block + 1} ({self.width}x{self.height})"

    def get_pixel(self, x: int, y: int) -> int:
        return self.data[y * self.width + x]

    def set_pixel(self, x: int, y: int, color_index: int):
        self.data[y * self.width + x] = color_index & 0xFF


class HQMultiVgaFile(VgaPaletteMixin):

    def __init__(self):
        super().__init__()
        self.raw = b""
        self.is_compressed = False
        self.sprites: list[VgaSprite] = []
        self.format_name = None

    @staticmethod
    def get_spec(path: str) -> dict | None:
        basename = os.path.splitext(os.path.basename(path))[0].upper()
        return MULTI_VGA_SPECS.get(basename)

    def load(self, path: str):
        spec = self.get_spec(path)
        if spec is None:
            raise Exception(
                f"No multi-sprite specs for \"{os.path.basename(path)}\""
            )
        basename_noext = os.path.splitext(os.path.basename(path))[0].upper()
        expected_total = sum(b["width"] * b["height"] * b["count"] for b in spec["blocks"])

        raw = open(path, "rb").read()

        if os.path.basename(path).upper().endswith(".UNP"):
            self.is_compressed = False
            if len(raw) != expected_total:
                raise Exception(
                    f"Unexpected size for VGA multi-sprite file \"{basename_noext}\": "
                    f"{len(raw)}/{expected_total} expected bytes"
                )
        else:
            self.is_compressed = True
            try:
                decompressed = decompress(raw)
            except Exception:
                decompressed = None

            if decompressed is not None and len(decompressed) == expected_total:
                raw = decompressed
            elif len(raw) == expected_total:
                self.is_compressed = False
            else:
                raise Exception(
                    f"Unexpected size for VGA multi-sprite file\"{basename_noext}\": "
                    f"{len(decompressed) if decompressed is not None else len(raw)}"
                    f"/{expected_total} expected bytes"
                )

        self.raw         = bytearray(raw)
        self.format_name = basename_noext
        self._split_sprites(spec)
        self._auto_select_palette(path)

    def _split_sprites(self, spec: dict):
        self.sprites = []
        offset = 0
        global_idx = 0
        for block in spec["blocks"]:
            w, h, count, name = block["width"], block["height"], block["count"], block["name"]
            frame_size = w * h
            for i in range(count):
                chunk = self.raw[offset: offset + frame_size]
                self.sprites.append(VgaSprite(
                    index=global_idx, block_name=name, index_in_block=i,
                    width=w, height=h, offset=offset, data=bytearray(chunk),
                    format_name=self.format_name,
                ))
                offset     += frame_size
                global_idx += 1

    def get_sprite(self, index: int) -> VgaSprite:
        return self.sprites[index]

    def sprites_in_block(self, block_name: str) -> list:
        return [s for s in self.sprites if s.block_name == block_name]

    def get_furniture_groups(self) -> list:
        if self.format_name != "MAPS":
            return []
        block_sprites = self.sprites_in_block(FURNITURE_BLOCK_NAME)
        if not block_sprites:
            return []
        max_tile_idx = max(t for g in FURNITURE_GROUPS for t in g["tiles"])
        if max_tile_idx >= len(block_sprites):
            return []
        return FURNITURE_GROUPS

    def get_furniture_group_sprites(self, group_name: str) -> list:
        group = next((g for g in self.get_furniture_groups() if g["name"] == group_name), None)
        if group is None:
            return []
        block_sprites = self.sprites_in_block(FURNITURE_BLOCK_NAME)
        return [block_sprites[i] for i in group["tiles"]]

    def compose_furniture_group(self, group_name: str):
        group = next((g for g in self.get_furniture_groups() if g["name"] == group_name), None)
        if group is None:
            return None
        sprites = self.get_furniture_group_sprites(group_name)
        if not sprites:
            return None
        tile_w, tile_h = sprites[0].width, sprites[0].height
        cols, rows = group["cols"], group["rows"]
        out_w, out_h = cols * tile_w, rows * tile_h
        out = bytearray(out_w * out_h)
        for i, spr in enumerate(sprites):
            r, c = divmod(i, cols)
            ox, oy = c * tile_w, r * tile_h
            for y in range(tile_h):
                src_off = y * tile_w
                dst_off = (oy + y) * out_w + ox
                out[dst_off: dst_off + tile_w] = spr.data[src_off: src_off + tile_w]
        return out_w, out_h, bytes(out)

    def get_furniture_pixel_accessors(self, group_name: str):
        group = next((g for g in self.get_furniture_groups() if g["name"] == group_name), None)
        if group is None:
            return None
        sprites = self.get_furniture_group_sprites(group_name)
        if not sprites:
            return None
        tile_w, tile_h = sprites[0].width, sprites[0].height
        cols, rows = group["cols"], group["rows"]
        out_w, out_h = cols * tile_w, rows * tile_h

        def _locate(x: int, y: int):
            col, lx = divmod(x, tile_w)
            row, ly = divmod(y, tile_h)
            spr = sprites[row * cols + col]
            return spr, lx, ly

        def get_pixel(x: int, y: int) -> int:
            spr, lx, ly = _locate(x, y)
            return spr.get_pixel(lx, ly)

        def set_pixel(x: int, y: int, color_index: int):
            spr, lx, ly = _locate(x, y)
            spr.set_pixel(lx, ly, color_index)

        return out_w, out_h, get_pixel, set_pixel

    def rebuild(self) -> bytes:
        out = bytearray()
        for spr in self.sprites:
            expected = spr.width * spr.height
            if len(spr.data) != expected:
                raise Exception(
                    f"Sprite #{spr.index} ({spr.label}) is corrupted: "
                    f"{len(spr.data)}/{expected} byte"
                )
            out += spr.data
        return bytes(out)

    def save(self, path: str):
        data = self.rebuild()
        if not os.path.basename(path).upper().endswith(".UNP"):
            data = compress(data)
        with open(path, "wb") as f:
            f.write(data)

    def get_total_size(self) -> int:
        return sum(len(s.data) for s in self.sprites)
