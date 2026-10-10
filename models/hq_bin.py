import struct
import itertools
from utils import decode_text, encode_text, is_compressed_file
from encoder import decompress
from config import PTR_COUNT, HEADER_SIZE, MAX_SIZE

def _find_aaaa(data, p, limit=32):
    for j in range(p, min(p + limit, len(data) - 1)):
        if data[j] == 0x00:
            return None
        if data[j] == 0xAA and data[j + 1] == 0xAA:
            return j
    return None

def _probe_box_end(data, p, max_subentries=64):
    if p + 4 > len(data):
        return None
    pos = p + 4
    count = 0
    while count < max_subentries:
        if pos == p + 4:
            if pos + 4 > len(data):
                return None
            if data[pos] == 0xAA and data[pos + 1] == 0xAA and data[pos + 2] == 0xFF and data[pos + 3] == 0xFF:
                return pos + 4
        else:
            if pos + 2 > len(data):
                return None
            if data[pos] == 0xFF and data[pos + 1] == 0xFF:
                return pos + 2
        if pos + 6 > len(data):
            return None
        if data[pos + 4] == 0xAA and data[pos + 5] == 0xAA:
            pos += 6
            count += 1
            continue
        return None
    return None
    return None


def _decode_subentries(sub_raw_bytes):
    entries, sp = [], 0
    sb = sub_raw_bytes
    while sp + 6 <= len(sb):
        if sb[sp] == 0xFF and sb[sp + 1] == 0xFF:
            break
        if sb[sp + 4] == 0xAA and sb[sp + 5] == 0xAA:
            entries.append({
                "col": sb[sp],
                "row": sb[sp + 1],
                "ptr": sb[sp + 2] | (sb[sp + 3] << 8),
            })
            sp += 6
        else:
            sp += 1
    return entries

def parse_block(data, ptr):
    if ptr == 0 or ptr >= len(data):
        return {"type": "null"}
    p = ptr
    if data[p] == 0x00:
        return {"type": "empty"}
    is_box = _probe_box_end(data, p) is not None

    if data[p] == 0x11 and not is_box:
        if p + 2 < len(data) and data[p + 1] == 0xAA and data[p + 2] == 0xAA:
            end = p + 3
            while end < len(data) and data[end] != 0x00:
                end += 1
            return {"type": "btn_label", "text": decode_text(data[p + 3:end])}

        pos = p
        lines = []
        while pos < len(data) and data[pos] == 0x11:
            row, col = data[pos + 1], data[pos + 2]
            end = pos + 3
            while end < len(data) and data[end] not in (0x00, 0x11):
                end += 1
            lines.append({"row": row, "col": col, "text": decode_text(data[pos + 3:end])})
            pos = end
        return {"type": "text_pos", "lines": lines}

    if is_box:
        col, row, w, h = data[p], data[p + 1], data[p + 2], data[p + 3]
        pos = p + 4
        sub_raw = bytearray()
        while pos < len(data) - 1:
            if data[pos] == 0xFF and data[pos + 1] == 0xFF:
                sub_raw += b'\xff\xff'
                pos += 2
                break
            sub_raw.append(data[pos])
            pos += 1
        sub_entries = _decode_subentries(bytes(sub_raw))

        lines = []
        while pos < len(data) and data[pos] != 0x00:
            if data[pos] == 0x11:
                r2, c2 = data[pos + 1], data[pos + 2]
                pos += 3
                s = pos
                while pos < len(data) and data[pos] not in (0x00, 0x11):
                    pos += 1
                lines.append({"row": r2, "col": c2,
                               "text": decode_text(data[s:pos])})
            else:
                pos += 1

        return {"type": "box", "col": col, "row": row, "w": w, "h": h,
                "preamble": [col, row, w, h], "sub_raw": list(sub_raw),
                "sub_entries": sub_entries, "lines": lines}

    end = p
    while end < len(data) and data[end] != 0x00:
        end += 1
    raw_text = data[p:end]

    segments, i = [], 0
    while i < len(raw_text):
        if raw_text[i] == 0x11:
            r2 = raw_text[i + 1] if i + 1 < len(raw_text) else 0
            c2 = raw_text[i + 2] if i + 2 < len(raw_text) else 0
            s = i + 3
            j = s
            while j < len(raw_text) and raw_text[j] != 0x11:
                j += 1
            segments.append({"row": r2, "col": c2, "text": decode_text(raw_text[s:j])})
            i = j
        else:
            j = i
            while j < len(raw_text) and raw_text[j] != 0x11:
                j += 1
            txt = decode_text(raw_text[i:j])
            if txt:
                segments.append({"row": None, "col": None, "text": txt})
            i = j

    return {"type": "text_plain", "segments": segments}

def build_block(b):
    t = b.get("type", "null")
    if t == "null":     return b""
    if t == "empty":    return b"\x00"
    if t == "btn_label":
        return b'\x11\xaa\xaa' + encode_text(b["text"]) + b'\x00'
    if t == "text_pos":
        raw = bytearray()
        for l in b["lines"]:
            raw += bytes([0x11, l["row"], l["col"]])
            raw += encode_text(l["text"])
        return bytes(raw) + b'\x00'
    if t == "text_plain":
        raw = bytearray()
        for seg in b["segments"]:
            if seg["row"] is None:
                raw += encode_text(seg["text"])
            else:
                raw += bytes([0x11, seg["row"], seg["col"]])
                raw += encode_text(seg["text"])
        return bytes(raw) + b'\x00'
    if t == "box":
        raw = bytearray([b["col"], b["row"], b["w"], b["h"]])
        raw += bytes(b["sub_raw"])
        for l in b["lines"]:
            raw += bytes([0x11, l["row"], l["col"]])
            raw += encode_text(l["text"])
        return bytes(raw) + b'\x00'
    return b""

def _rebuild_sub_raw(sub_raw, sub_entries, btn_ptr_map):
    sb = bytearray(sub_raw)
    coord_map = {se["ptr"]: se for se in sub_entries}
    sp = 0
    while sp + 6 <= len(sb):
        if sb[sp] == 0xFF and sb[sp + 1] == 0xFF:
            break
        if sb[sp + 4] == 0xAA and sb[sp + 5] == 0xAA:
            old_ptr = sb[sp + 2] | (sb[sp + 3] << 8)
            if old_ptr in coord_map:
                se = coord_map[old_ptr]
                sb[sp], sb[sp + 1] = se["col"], se["row"]
            if old_ptr in btn_ptr_map:
                new_ptr = btn_ptr_map[old_ptr]
                sb[sp + 2] = new_ptr & 0xFF
                sb[sp + 3] = (new_ptr >> 8) & 0xFF
                if new_ptr != old_ptr and old_ptr in coord_map:
                    coord_map[new_ptr] = coord_map.pop(old_ptr)
            sp += 6
        else:
            sp += 1
    return list(sb)

_orphan_id_counter = itertools.count(10000)

class HQFile:
    def __init__(self):
        self.blocks    = []
        self.raw       = b""
        self.main_ptrs = []

    def load(self, path):
        raw = open(path, "rb").read()
        self.is_compressed = is_compressed_file(path)
        if self.is_compressed:
            raw = decompress(raw)
        self.raw = raw

        ptrs = struct.unpack(f"<{PTR_COUNT}H", self.raw[:HEADER_SIZE])
        self.main_ptrs = list(ptrs)
        self.blocks = []

        seen_ptr = {}
        for i, ptr in enumerate(ptrs):
            if ptr not in seen_ptr:
                b = parse_block(self.raw, ptr)
                b["index"] = i
                b["ptr"]   = ptr
                self.blocks.append(b)
                seen_ptr[ptr] = i

        self._ptr_to_canonical = seen_ptr
        self._inject_orphan_labels()

    def _inject_orphan_labels(self):
        existing_btn_ptrs = {b["ptr"] for b in self.blocks if b.get("type") == "btn_label"}
        inserted_ptrs = set()
        inserts = []

        for b in self.blocks:
            if b.get("type") != "box":
                continue
            for se in b.get("sub_entries", []):
                ptr = se["ptr"]
                if ptr == 0 or ptr >= MAX_SIZE or ptr in existing_btn_ptrs or ptr in inserted_ptrs:
                    continue
                raw = self.raw
                if ptr >= len(raw):
                    continue
                if raw[ptr] == 0x11 and ptr + 2 < len(raw) and raw[ptr + 1] == 0xAA and raw[ptr + 2] == 0xAA:
                    end = ptr + 3
                    while end < len(raw) and raw[end] != 0x00:
                        end += 1
                    inserts.append((b["index"], {
                        "type":         "btn_label",
                        "text":         decode_text(raw[ptr + 3:end]),
                        "ptr":          ptr,
                        "index":        next(_orphan_id_counter),
                        "orphan":       True,
                        "parent_index": b["index"],
                    }))
                    inserted_ptrs.add(ptr)

        inserts.sort(key=lambda x: x[0], reverse=True)
        for after_idx, orphan_block in inserts:
            pos = next((i for i, b in enumerate(self.blocks) if b["index"] == after_idx), None)
            if pos is not None:
                self.blocks.insert(pos + 1, orphan_block)

    def rebuild(self):
        data, ptr_map, emitted_ptrs = bytearray(), {}, set()

        for b in self.blocks:
            if b.get("orphan"): continue
            orig = b.get("ptr", 0)
            if orig in emitted_ptrs: continue
            raw = build_block(b)
            if not raw:
                ptr_map[orig] = orig if orig >= MAX_SIZE else 0
            else:
                ptr_map[orig] = len(data) + HEADER_SIZE
                data += raw
            emitted_ptrs.add(orig)

        for b in self.blocks:
            if not b.get("orphan"): continue
            orig = b.get("ptr", 0)
            if orig in emitted_ptrs: continue
            raw = build_block(b)
            if raw:
                ptr_map[orig] = len(data) + HEADER_SIZE
                data += raw
            emitted_ptrs.add(orig)

        expected_size = (len(self.main_ptrs) * 2) + len(data)
        if expected_size > MAX_SIZE:
            raise Exception(f"File too large: {expected_size} > {MAX_SIZE} bytes. Rebuild aborted.")

        data2, ptr_map2, emitted2 = bytearray(), {}, set()

        for b in self.blocks:
            if b.get("orphan"): continue
            orig = b.get("ptr", 0)
            if orig in emitted2: continue
            if b["type"] == "box":
                b["sub_raw"]     = _rebuild_sub_raw(b["sub_raw"], b.get("sub_entries", []), ptr_map)
                b["sub_entries"] = _decode_subentries(bytes(b["sub_raw"]))
            raw = build_block(b)
            if not raw:
                ptr_map2[orig] = orig if orig >= MAX_SIZE else 0
            else:
                ptr_map2[orig] = len(data2) + HEADER_SIZE
                data2 += raw
            emitted2.add(orig)

        for b in self.blocks:
            if not b.get("orphan"): continue
            orig = b.get("ptr", 0)
            if orig in emitted2: continue
            raw = build_block(b)
            if raw:
                ptr_map2[orig] = len(data2) + HEADER_SIZE
                data2 += raw
            emitted2.add(orig)

        final = bytearray()
        for orig in self.main_ptrs:
            final += struct.pack("<H", ptr_map2.get(orig, orig))
        final += data2

        return bytes(final)

    def get_btn_text(self, ptr):
        for b in self.blocks:
            if b.get("ptr") == ptr and b["type"] == "btn_label":
                return b["text"]
        if ptr == 0 or ptr >= len(self.raw):
            return None
        raw = self.raw
        if raw[ptr] == 0x11 and ptr + 2 < len(raw) and raw[ptr + 1] == 0xAA and raw[ptr + 2] == 0xAA:
            end = ptr + 3
            while end < len(raw) and raw[end] != 0x00:
                end += 1
            return decode_text(raw[ptr + 3:end])
        return None

    def get_total_size(self):
        total = HEADER_SIZE
        for b in self.blocks:
            data = build_block(b)
            total += len(data)
        return total