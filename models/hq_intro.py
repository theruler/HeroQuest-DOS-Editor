# Sezione 8: Formato INTRO.EXE
import struct
import os
from utils import decode_text, encode_text

INTRO_DATA_BASE    = 0x01C0
INTRO_PAGE0_OFFSET = 0x02BD
INTRO_MAX_END      = 0x0E7F
INTRO_MAX_BYTES    = INTRO_MAX_END - INTRO_PAGE0_OFFSET + 1

INTRO_PTR_TABLE = [
    (1, 0x0212), (2, 0x0214), (3, 0x0216),
    (4, 0x0218), (5, 0x021A), (6, 0x021C),
]
INTRO_PAGE_COUNT = 7

INTRO_FIXED_STRINGS = [
    (0x1452, 0x48),
    (0x149a, 0x44),
    (0x14de, 0x3E),
    (0x151c, 0x41),
    (0x19cf, 0x46),
    (0x1a15, 0x3B),
    (0x1a50, 0x22),
    (0x1a72, 0x2F),
    (0x1aa1, 0x27),
    (0x1ac8, 0x27),
    (0x1b21, 0x40),
    (0x1b61, 0x15),
    (0x1e85, 0x4D),
]

DOS_STRING_TERMINATOR = 0x24
DOS_STRING_CR         = 0x0D
DOS_STRING_LF         = 0x0A

def _decode_dos_string(raw_bytes: bytes) -> str:

    end = raw_bytes.find(bytes([DOS_STRING_TERMINATOR]))
    if end == -1:
        end = len(raw_bytes)
    body = raw_bytes[:end]
    lines = []
    cur = []
    for b in body:
        if b == DOS_STRING_LF:
            lines.append(''.join(cur))
            cur = []
        elif b == DOS_STRING_CR:
            continue
        elif 0x20 <= b <= 0x7E:
            cur.append(chr(b))
        else:
            continue
    lines.append(''.join(cur))
    return '\n'.join(lines)

def _encode_dos_string(text: str) -> bytes:
    lines = text.split('\n')
    out = bytearray()
    for i, line in enumerate(lines):
        if i > 0:
            out.append(DOS_STRING_LF)
        if line != '':
            out.append(DOS_STRING_CR)
            out += line.encode("latin-1", errors="replace")
    out.append(DOS_STRING_TERMINATOR)
    return bytes(out)

def _is_intro_file(path: str) -> bool:
    return os.path.basename(path).upper() == "INTRO.EXE"

class HQIntroFile:
    def __init__(self):
        self.pages = []
        self.raw   = b""
        self.fixed_strings = []

    def load(self, path: str):
        self.raw = open(path, "rb").read()
        raw      = self.raw
        self.pages = []

        page_starts = [(0, INTRO_PAGE0_OFFSET)]
        for pg_idx, ptr_off in INTRO_PTR_TABLE:
            ptr_val  = struct.unpack_from("<H", raw, ptr_off)[0]
            page_starts.append((pg_idx, INTRO_DATA_BASE + ptr_val))
        page_starts.sort(key=lambda x: x[1])

        for i, (pg_idx, start) in enumerate(page_starts):
            end_hint = page_starts[i + 1][1] if i + 1 < len(page_starts) else INTRO_MAX_END + 1
            lines, pos = [], start
            while pos < end_hint and pos < len(raw):
                if raw[pos] != 0x11: break
                if pos + 2 >= len(raw): break
                row, col = raw[pos + 1], raw[pos + 2]
                pos += 3
                end = pos
                while end < end_hint and end < len(raw) and raw[end] not in (0x11, 0x00):
                    end += 1
                lines.append({"row": row, "col": col, "text": decode_text(raw[pos:end])})
                pos = end
            self.pages.append({"index": pg_idx, "start": start, "lines": lines})

        self.pages.sort(key=lambda p: p["index"])

        self.fixed_strings = []
        for offset, max_bytes in INTRO_FIXED_STRINGS:
            chunk = raw[offset: offset + max_bytes]
            self.fixed_strings.append({
                "offset":    offset,
                "max_bytes": max_bytes,
                "text":      _decode_dos_string(chunk),
            })

    def rebuild(self) -> bytes:
        raw = bytearray(self.raw)
        buf, new_starts = bytearray(), {}
        for page in self.pages:
            new_starts[page["index"]] = INTRO_PAGE0_OFFSET + len(buf)
            for l in page["lines"]:
                buf += bytes([0x11, l["row"], l["col"]])
                buf += encode_text(l["text"])
            buf += b'\x00'
        if len(buf) > INTRO_MAX_BYTES:
            raise Exception(f"INTRO.EXE too large: {len(buf)}/{INTRO_MAX_BYTES} bytes")
        raw[INTRO_PAGE0_OFFSET : INTRO_PAGE0_OFFSET + len(buf)] = buf
        for pg_idx, ptr_off in INTRO_PTR_TABLE:
            struct.pack_into("<H", raw, ptr_off, new_starts[pg_idx] - INTRO_DATA_BASE)

        for fs in self.fixed_strings:
            encoded = _encode_dos_string(fs["text"])
            if len(encoded) > fs["max_bytes"]:
                raise Exception(
                    f"Fixed string at 0x{fs['offset']:04x} too large: "
                    f"{len(encoded)}/{fs['max_bytes']} bytes")
            padded_encoded = encoded.ljust(fs["max_bytes"], b'\x00')
            offset = fs["offset"]
            raw[offset: offset + fs["max_bytes"]] = padded_encoded
        return bytes(raw)

    def get_page(self, index: int):
        return next((p for p in self.pages if p["index"] == index), None)

    def get_fixed_string(self, idx: int):
        if 0 <= idx < len(self.fixed_strings):
            return self.fixed_strings[idx]
        return None

    def bytes_used(self) -> int:
        return sum(3 + len(encode_text(l["text"]))
                   for page in self.pages for l in page["lines"])

    def fixed_string_bytes_used(self, idx: int) -> int:
        fs = self.get_fixed_string(idx)
        if fs is None:
            return 0
        return len(_encode_dos_string(fs["text"]))
