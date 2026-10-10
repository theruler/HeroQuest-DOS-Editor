import os
from config import (
    COMPRESSED_FILES, UNCOMPRESSED_FILES, KNOWN_DATA_FILES, KNOWN_LANGUAGE_FILES,
    CELL, GRID_COLS, GRID_ROWS, PAL, resource_path
)

CHAR_DECODE = {
    0x24: 'à', 0x25: 'ì', 0x5e: 'ò',
    0x61: 'ä', 0x62: 'á', 0x63: 'ç',
    0x64: '¿', 0x65: 'é', 0x66: 'è',
    0x67: 'ú', 0x68: 'ù', 0x69: 'í',
    0x6a: '¡', 0x6b: 'ü', 0x6c: 'ö',
    0x6d: 'ó', 0x6e: 'ñ',
}
CHAR_ENCODE = {v: chr(k) for k, v in CHAR_DECODE.items()}

def decode_text(raw_bytes):
    return ''.join(CHAR_DECODE.get(b, chr(b)) for b in raw_bytes)

def encode_text(s):
    result = bytearray()
    for ch in s:
        if ch in CHAR_ENCODE:
            result.append(ord(CHAR_ENCODE[ch]))
        else:
            try:
                result += ch.encode('latin-1')
            except UnicodeEncodeError:
                result.append(ord('?'))
    return bytes(result)

def is_compressed_file(path):
    return os.path.basename(path).upper() in COMPRESSED_FILES

def is_known_data_file(path):
    return os.path.basename(path).upper() in KNOWN_DATA_FILES

def is_known_language_file(path):
    return os.path.basename(path).upper() in KNOWN_LANGUAGE_FILES

def load_dynamix_font_file(path):
    with open(path, "rb") as f:
        raw = f.read()

    data = raw[8:]
    width, height, start_char, count = data[0], data[1], data[2], data[3]
    bytes_per_glyph = ((width + 7) // 8) * height
    row_bytes = (width + 7) // 8
    offset = 4
    glyphs = {}

    for i in range(count):
        char_code = start_char + i
        chunk = data[offset: offset + bytes_per_glyph]
        offset += bytes_per_glyph
        bitmap = [
            [(chunk[y * row_bytes + (x // 8)] >> (7 - x % 8)) & 1
             for x in range(width)]
            for y in range(height)
        ]
        glyphs[char_code] = bitmap

    return width, height, glyphs

def draw_cylinder_roll(canvas, x1, y1, x2, y2, base_color="#1a3a2a"):
    w = x2 - x1
    h = y2 - y1
    if h <= 0 or w <= 0:
        return
    steps = max(h, 1)
    br, bg, bb = int(base_color[1:3],16), int(base_color[3:5],16), int(base_color[5:7],16)
    for i in range(steps):
        t    = i / max(steps-1, 1)
        bell = 1.0 - (2*t - 1)**2
        r     = min(255, int(br + bell * 120))
        g     = min(255, int(bg + bell * 100))
        b_val = min(255, int(bb + bell * 60))
        color = f"#{r:02x}{g:02x}{b_val:02x}"
        py = y1 + int(i * h / steps)
        ph = max(1, int(h / steps) + 1)
        canvas.create_rectangle(x1-40, py, x2+40, py + ph, fill=color, outline="")

def _draw_grid(canvas, cell=CELL):
    gw = GRID_COLS * cell
    gh = GRID_ROWS * cell
    for r in range(GRID_ROWS + 1):
        canvas.create_line(0, r*cell, gw, r*cell, fill=PAL["grid"])
    for col in range(GRID_COLS + 1):
        canvas.create_line(col*cell, 0, col*cell, gh, fill=PAL["grid"])
    for col in range(0, GRID_COLS+1, 5):
        canvas.create_text(col*cell+2, 2, text=str(col),
                           fill=PAL["grid_num"], anchor="nw", font=("Courier", 7))
    for row in range(0, GRID_ROWS+1, 5):
        canvas.create_text(2, row*cell+2, text=str(row),
                           fill=PAL["grid_num"], anchor="nw", font=("Courier", 7))
