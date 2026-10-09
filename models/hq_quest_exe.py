# Sezione 9: Formato QUEST.EXE
import struct
import os
from utils import decode_text, encode_text

QUEST_EXE_PTR_BASE = 0x9BE0
QUEST_EXE_POS_BASE = 0xA543

QUEST_EXE_POS_STRINGS = [
    (None,           None),
    (0x04CF,         None),
    (0x04EA,         None),
]

QUEST_EXE_POS_FIXED = [
    (0xA96F,         0x80),
]

QUEST_EXE_PAGE_MAX_TOTAL = 0x03CA

QUEST_EXE_PLAIN_STRINGS = [
    (0xD482,         0x09),
    (0xD490,         0x09),
    (0xD49E,         0x09),
    (0xD4AC,         0x09),
    (0xD4BA,         0x09),
    (0xE1C5,         0x0E),
    (0xE1D5,         0x0E),
    (0xE1E5,         0x0E),
    (0xE1F5,         0x0E),
    (0xE205,         0x0E),
]

DOS_STRING_TERMINATOR = 0x24  # '$'
DOS_STRING_CR         = 0x0D  # prefisso silente prima di ogni riga di testo
DOS_STRING_LF         = 0x0A  # separatore di riga (anche per righe vuote)

QUEST_EXE_DOS_STRINGS = [
    (0xD21A,         0x1B),
    (0xD235,         0x1A),
    (0xD29F,         0x45),
    (0xD2DF,         0x15),
]

def _decode_dos_string(raw_bytes: bytes) -> str:
    """Decodifica una DOS string mostrando solo ASCII stampabile.
    0x0A separa le righe (comprese quelle vuote); 0x0D è un prefisso
    tecnico silente e non viene mai mostrato; ogni altro byte non
    stampabile viene scartato."""
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
    """Codifica il testo in una DOS string. Ogni riga viene separata da
    0x0A; le righe che contengono testo vengono precedute silenziosamente
    da 0x0D. Le righe vuote producono solo 0x0A, senza 0x0D."""
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

def _is_quest_exe_file(path: str) -> bool:
    return os.path.basename(path).upper() == "QUEST.EXE"

def _qexe_parse_lines(raw: bytes, abs_off: int, max_bytes=None) -> list:
    lines = []
    pos   = abs_off
    limit = (abs_off + max_bytes) if max_bytes is not None else len(raw)

    while pos < limit and pos < len(raw):
        if raw[pos] == 0x00: break
        if raw[pos] != 0x11: break
        if pos + 2 >= len(raw): break
        row, col = raw[pos + 1], raw[pos + 2]
        pos += 3
        end = pos
        while end < limit and end < len(raw) and raw[end] != 0x11 and raw[end] != 0x00:
            end += 1
        lines.append({"row": row, "col": col, "text": decode_text(raw[pos:end])})
        pos = end
    return lines

def _qexe_build_lines(lines: list) -> bytes:
    body = bytearray()
    for l in lines:
        body += bytes([0x11, l["row"], l["col"]])
        body += encode_text(l["text"])
    body += b'\x00'
    return bytes(body)

class HQQuestExeFile:
    def __init__(self):
        self.raw           = b""
        self.pos_strings   = []
        self.page_blocks   = []
        self.plain_strings = []
        self.dos_strings   = []

    def load(self, path: str):
        self.raw = open(path, "rb").read()
        raw = self.raw
        self.pos_strings   = []
        self.page_blocks   = []
        self.plain_strings = []
        self.dos_strings   = []
        
        # 1. Stringhe di posizione dinamiche
        seq_off = QUEST_EXE_POS_BASE
        for (ptr_off, max_bytes) in QUEST_EXE_POS_STRINGS:
            str_off = seq_off
            lines = _qexe_parse_lines(raw, str_off, max_bytes)
            self.pos_strings.append({
                "str_off":   str_off,
                "ptr_off":   ptr_off,
                "max_bytes": max_bytes,
                "lines":     lines,
            })
            seq_off = str_off + len(_qexe_build_lines(lines))

        # 2. Stringhe di posizione fisse
        for (str_off, max_bytes) in QUEST_EXE_POS_FIXED:
            lines = _qexe_parse_lines(raw, str_off, max_bytes)
            self.pos_strings.append({
                "str_off":   str_off,
                "ptr_off":   None,
                "max_bytes": max_bytes,
                "lines":     lines,
            })

        # 3. CARICAMENTO RIGIDEZZA PAGINE (Logica interamente dinamica)
        # Pagina 1: Offset fisico fisso
        p1_off = 0x141A4
        p1_lines = _qexe_parse_lines(raw, p1_off, QUEST_EXE_PAGE_MAX_TOTAL)
        self.page_blocks.append({
            "str_off": p1_off,
            "ptr_off": None,
            "lines":   p1_lines,
        })

        # Pagina 2: Offset ricavato dinamicamente dal puntatore a 0x0652
        p2_ptr = struct.unpack_from("<H", raw, 0x0652)[0]
        p2_off = p2_ptr + QUEST_EXE_PTR_BASE
        p2_lines = _qexe_parse_lines(raw, p2_off, QUEST_EXE_PAGE_MAX_TOTAL)
        self.page_blocks.append({
            "str_off": p2_off,
            "ptr_off": 0x0652,
            "lines":   p2_lines,
        })

        # 4. Plain strings
        for (str_off, max_bytes) in QUEST_EXE_PLAIN_STRINGS:
            end = str_off
            while end < len(raw) and raw[end] != 0x00 and (end - str_off) < max_bytes:
                end += 1
            self.plain_strings.append({
                "str_off":   str_off,
                "max_bytes": max_bytes,
                "text":      decode_text(raw[str_off:end]),
            })

        # 5. DOS strings
        for (offset, max_bytes) in QUEST_EXE_DOS_STRINGS:
            chunk = raw[offset: offset + max_bytes]
            self.dos_strings.append({
                "offset":    offset,
                "max_bytes": max_bytes,
                "text":      _decode_dos_string(chunk),
            })

    def rebuild(self) -> bytes:
        raw = bytearray(self.raw)
        
        # 1. Stringhe di posizione dinamiche
        buf = bytearray()
        new_str_offs = []
        base_off = QUEST_EXE_POS_BASE
        for entry in self.pos_strings:
            if entry["max_bytes"] is not None:
                continue
            new_str_offs.append((entry, base_off + len(buf)))
            buf += _qexe_build_lines(entry["lines"])
        raw[base_off : base_off + len(buf)] = buf
        for entry, new_off in new_str_offs:
            if entry["ptr_off"] is not None:
                rel = new_off - QUEST_EXE_PTR_BASE
                struct.pack_into("<H", raw, entry["ptr_off"], rel)

        # 2. Stringhe di posizione FISSE (con padding 0x00)
        for entry in self.pos_strings:
            if entry["max_bytes"] is None:
                continue
            body = _qexe_build_lines(entry["lines"])
            if len(body) > entry["max_bytes"]:
                raise Exception("QUEST.EXE pos string too large")
            raw[entry["str_off"] : entry["str_off"] + entry["max_bytes"]] = body.ljust(entry["max_bytes"], b'\x00')

        # 3. BLOCCHI PAGINA (Scrittura consecutiva a 0x141A4 e calcolo puntatore esplicito)
        base_off = 0x141A4
        
        page1_body = _qexe_build_lines(self.page_blocks[0]["lines"])
        page2_body = _qexe_build_lines(self.page_blocks[1]["lines"])
        
        combined_pages = page1_body + page2_body
        
        if len(combined_pages) > QUEST_EXE_PAGE_MAX_TOTAL:
            raise Exception(f"QUEST.EXE page blocks total too large: {len(combined_pages)}/{QUEST_EXE_PAGE_MAX_TOTAL} bytes")
            
        # Padda l'intera area di 0x03CA byte pulendo ogni rimasuglio precedente
        raw[base_off : base_off + QUEST_EXE_PAGE_MAX_TOTAL] = combined_pages.ljust(QUEST_EXE_PAGE_MAX_TOTAL, b'\x00')
        
        # Calcolo esatto del nuovo offset richiesto: 0xA5C4 + lunghezza prima pagina (incluso lo 0x00)
        new_ptr = 0xA5C4 + len(page1_body)
        
        # Scrive il valore in Little Endian (LE) direttamente all'offset fisico 0x0652
        struct.pack_into("<H", raw, 0x0652, new_ptr)

        # 4. Plain strings (con padding)
        for entry in self.plain_strings:
            str_off = entry["str_off"]
            max_b   = entry["max_bytes"]
            body    = encode_text(entry["text"])
            if len(body) > max_b:
                raise Exception("QUEST.EXE plain string too large")
            raw[str_off : str_off + max_b] = body.ljust(max_b, b'\x00')

        # 5. DOS system strings (con padding 0x00 dopo il $)
        for fs in self.dos_strings:
            encoded = _encode_dos_string(fs["text"])
            if len(encoded) > fs["max_bytes"]:
                raise Exception(
                    f"QUEST.EXE DOS string at 0x{fs['offset']:04x} too large: "
                    f"{len(encoded)}/{fs['max_bytes']} bytes")
            raw[fs["offset"] : fs["offset"] + fs["max_bytes"]] = encoded.ljust(fs["max_bytes"], b'\x00')

        return bytes(raw)

    def bytes_used_pages(self) -> int:
        return sum(len(_qexe_build_lines(pb["lines"])) for pb in self.page_blocks)

    def bytes_used_pos(self, i) -> int:
        return len(_qexe_build_lines(self.pos_strings[i]["lines"]))

    def get_dos_string(self, idx: int):
        if 0 <= idx < len(self.dos_strings):
            return self.dos_strings[idx]
        return None

    def dos_string_bytes_used(self, idx: int) -> int:
        fs = self.get_dos_string(idx)
        if fs is None:
            return 0
        return len(_encode_dos_string(fs["text"]))