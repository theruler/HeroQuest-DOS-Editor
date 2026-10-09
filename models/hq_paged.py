# Sezione 7: Formato EQUESTS.BIN
import struct
from utils import decode_text, encode_text

PAGED_PTR_COUNT  = 10
PAGED_HDR_SIZE   = 0x14
PAGE_HEADER_SIZE = 10

PAGED_LANG_MAP = [
    ("ENGLISH", 1), ("ENGLISH", 2),
    ("FRENCH",  1), ("FRENCH",  2),
    ("SPANISH", 1), ("SPANISH", 2),
    ("GERMAN",  1), ("GERMAN",  2),
    ("ITALIAN", 1), ("ITALIAN", 2),
]

def _is_paged_file(path: str) -> bool:
    try:
        raw = open(path, "rb").read()
        if len(raw) < PAGED_HDR_SIZE:
            return False
        ptrs = struct.unpack(f"<{PAGED_PTR_COUNT}H", raw[:PAGED_HDR_SIZE])
        if ptrs[0] != PAGED_HDR_SIZE:
            return False
        if not all(p == 0 or p < len(raw) for p in ptrs):
            return False
        for p in ptrs:
            if p == 0: continue
            if p + 2 > len(raw) or raw[p] != 0x04 or raw[p+1] != 0x02:
                return False
        return True
    except Exception:
        return False

class HQPagedFile:
    def __init__(self):
        self.pages = []
        self.raw   = b""

    def load(self, path: str):
        self.raw = open(path, "rb").read()
        raw      = self.raw
        ptrs     = list(struct.unpack(f"<{PAGED_PTR_COUNT}H", raw[:PAGED_HDR_SIZE]))
        self.pages = []

        for i, ptr in enumerate(ptrs):
            lang, page_num = PAGED_LANG_MAP[i]
            page = {"index": i, "ptr": ptr, "lang": lang, "page_num": page_num,
                    "header": b"", "lines": []}
            if ptr == 0 or ptr + PAGE_HEADER_SIZE > len(raw):
                self.pages.append(page)
                continue

            page["header"] = raw[ptr : ptr + PAGE_HEADER_SIZE]
            pos = ptr + PAGE_HEADER_SIZE
            lines = []

            while pos < len(raw):
                if raw[pos] != 0x11: break
                if pos + 2 >= len(raw): break
                row, col = raw[pos + 1], raw[pos + 2]
                pos += 3
                end = pos
                while end < len(raw) and raw[end] != 0x00:
                    end += 1
                lines.append({"row": row, "col": col, "text": decode_text(raw[pos:end])})
                pos = end + 1

            page["lines"] = lines
            self.pages.append(page)

    def rebuild(self) -> bytes:
        body, new_ptrs = bytearray(), []

        for page in self.pages:
            if page["ptr"] == 0:
                new_ptrs.append(0)
                continue
            new_ptrs.append(len(body) + PAGED_HDR_SIZE)
            body += page["header"]
            for l in page["lines"]:
                body += bytes([0x11, l["row"], l["col"]])
                body += encode_text(l["text"])
                body += b'\x00'

        result  = bytearray()
        result += struct.pack(f"<{PAGED_PTR_COUNT}H", *new_ptrs)
        result += body
        return bytes(result)

    def get_page(self, index: int):
        return next((p for p in self.pages if p["index"] == index), None)
