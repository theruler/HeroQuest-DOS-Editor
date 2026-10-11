"""
Header (0x000-0x157, 344 bytes)
  0x00       3 bytes id/version (RLD: word 0x9AB6 = magic for MT32.DRV)
  0x03       ASCII bank name ("ingame")
  0x18..0x97 ORDER LIST: 128 bytes, order index -> pattern number
  0x98..0x117 128 bytes = 64 pairs (slot_flag, default_volume[0..0x40])
              one per instrument (initial note volume, 0x40 = max)
  0x118      number of melodic columns (ALB 6, RLD 7)
  0x11B      (ALB only) number of entries in song table

Song table @0x158, 16 bytes per entry (ALB: n from [0x11B]; RLD: 128 slots)
  [0:10]  name, [10] initial order (loop-start), [11] final order
  [12] loop flag (0 = plays once and stops), [13] n. of voices/channels

Pointer table (immediately following): LE words, in PARAGRAPHS (16 bytes), relative
to the START OF THE TABLE ITSELF. ALB: ((maxpat+1)*2 & 0xFFF0)+0x10 bytes
(ends with 0xFFFF); RLD: always 0x200 bytes. The first maxpat+1 entries point
to patterns, the next entry points to the instrument bank (up to EOF).

Pattern = 64 rows, each:
  ALB: mask word (1 bit/column, MSB-first, ncol+5 bits: 6 melodic +
       5 rhythmic BD,SD,TOM,CYM,HH); for each bit set to 1: 4-byte cell
       [MIDI note, instrument (1-based), command, parameter]
  RLD: mask word (2 bits/column, MSB-first); per column:
       0 empty | 1 [cmd,par] | 2 [note,instrument] |
       3 [n1,n2,n3,n4,instrument,cmd,par]   (up to 4 notes = chord)
  Commands (ProTracker style): 1/2 slide up/down, 3 portamento, 4 vibrato
  (stub), A volume slide, B jump to order, C volume, D pattern end,
  F speed (ticks per row; tick = exact 50 Hz, PIT 0x5D37).
  RLD only: 5 pan, 6 all-notes-off, 7/8 reverb.

Instruments:
  ALB: 64 bytes = name[10] + modulator[13] + carrier[13] + wave_mod, wave_car
       (13 = ksl,mult,fb,attack,sustain,eg,decay,release,level,am,vib,ksr,conn)
  RLD: 256 bytes = patch[8] + name[10] + common[4] + 4 MT-32 partials of 58 bytes
"""

import os
import struct
import wave

HEADER_TABLE_OFFSET = 0x158
ENTRY_SIZE = 16
OPL_RATE = 49716
TICK_HZ = 50.0

CAR = [0x03, 0x04, 0x05, 0x0b, 0x0c, 0x0d, 0x13, 0x14, 0x12, 0x15, 0x11] 
MOD = [0x00, 0x01, 0x02, 0x08, 0x09, 0x0a, 0x10, 0x14, 0x12, 0x15, 0x11]
RHY = [0x10, 0x08, 0x04, 0x02, 0x01]
_FNUM_ROW = [343, 364, 385, 408, 433, 459, 486, 515, 546, 579, 614, 650]
FNUM = [(blk << 12) + f for blk in range(8) for f in _FNUM_ROW]
assert FNUM[12] == 4439 and FNUM[95] == 29322

def _mt32_period_table():
    base = [6848, 6464, 6096, 5760, 5424, 5120, 4832, 4560, 4304, 4064, 3840, 3616]
    t = []
    for n in range(128):
        t.append(int(base[n % 12] / (2 ** (n // 12))))
    return t
MT32_PERIOD = _mt32_period_table()


class NoSynthError(Exception):
    pass

class FxEffect:
    def __init__(self, index, name, kind, data, ref_id=0, flag=0, offset_in_table=-1, extra=None):
        self.index = index
        self.name = name
        self.kind = kind
        self.ref_id = ref_id
        self.flag = flag
        self.offset_in_table = offset_in_table
        self.data = bytearray(data)
        self.extra = extra or {}

    @property
    def label(self):
        icon = {"song": "♫", "pattern": "▦", "inst": "♪"}.get(self.kind, "?")
        tag = self.extra.get("tag", "")
        return f"{icon} {self.name}  {tag}".rstrip()


class FxSong:
    def __init__(self, slot, name, start, end, loop, nvoices, offset):
        self.slot, self.name = slot, name
        self.start, self.end, self.loop, self.nvoices = start, end, loop, nvoices
        self.offset = offset

    def pack(self):
        nm = self.name.encode("latin1")[:10].ljust(10, b"\0")
        return nm + bytes([self.start, self.end, self.loop, self.nvoices, 0, 0])


class HQFxFile:

    def __init__(self):
        self.kind = None
        self.bank_name = ""
        self.raw_header = bytearray()
        self.order = []
        self.defvol = []
        self.ncols = 0
        self.songs = []
        self.patterns = []
        self.insts = []
        self.effects = []
        self.inst_size = 64
        self._pt_size = 0
        self._nsongs_total = 0
        self.use_mt32emu = True
        self.last_channels = 1
        self.last_engine = ""
        self.last_fallback_reason = ""

    def load(self, path):
        data = open(path, "rb").read()
        ext = os.path.splitext(path)[1].upper()
        self.kind = "rld" if ext == ".RLD" else "alb"
        self.from_bytes(data, self.kind)

    def from_bytes(self, data, kind):
        self.kind = kind
        self.bank_name = data[3:0x17].split(b"\0")[0].decode("latin1", "replace")
        self.order = list(data[0x18:0x98])
        self.defvol = [data[0x99 + 2 * i] for i in range(64)]
        self._free_slots = []
        self.defflag = [data[0x98 + 2 * i] for i in range(64)]
        self.ncols = data[0x118]
        maxpat = max(self.order)

        if kind == "rld":
            magic = struct.unpack_from("<H", data, 0)[0]
            pt = 0x958 if magic >= 0x9AB6 else 0x918
            nsongs = (pt - HEADER_TABLE_OFFSET) // ENTRY_SIZE
            self._pt_size = 0x200
            self.inst_size = 256
        else:
            nsongs = data[0x11B]
            pt = HEADER_TABLE_OFFSET + ENTRY_SIZE * nsongs
            self._pt_size = (((maxpat + 1) * 2) & 0xFFF0) + 0x10
            self.inst_size = 64
        self._nsongs_total = nsongs
        self._pt = pt

        nptr = maxpat + 2
        ptr = list(struct.unpack_from("<%dH" % nptr, data, pt))
        base = pt
        self.raw_header = bytearray(data[:pt])
        self._ptr0 = ptr[0]

        self.patterns = []
        for k in range(maxpat + 1):
            a = base + ptr[k] * 16
            b = base + ptr[k + 1] * 16
            self.patterns.append(bytearray(data[a:b]))
        inst_off = base + ptr[maxpat + 1] * 16
        raw = data[inst_off:]
        n = len(raw) // self.inst_size
        self.insts = [bytearray(raw[i * self.inst_size:(i + 1) * self.inst_size]) for i in range(n)]
        self._inst_tail = bytes(raw[n * self.inst_size:])

        self.songs = []
        for k in range(nsongs):
            o = HEADER_TABLE_OFFSET + ENTRY_SIZE * k
            e = data[o:o + ENTRY_SIZE]
            nm = e[:10].split(b"\0")[0].decode("latin1", "replace")
            if nm.strip().lower() == "not used" or not nm.strip():
                self._free_slots.append(o)
                continue
            self.songs.append(FxSong(k, nm, e[10], e[11], e[12], e[13], o))
        self._rebuild_effect_list()

    def _usage(self):
        pat_insts = [set(self.pattern_insts(k)) for k in range(len(self.patterns))]
        pat_songs = [[] for _ in self.patterns]
        for s in self.songs:
            for o in range(s.start, min(s.end, 127) + 1):
                p = self.order[o]
                if p < len(pat_songs) and s.name not in pat_songs[p]:
                    pat_songs[p].append(s.name)
        return pat_insts, pat_songs

    def song_is_music(self, s):
        return bool(s.loop) or s.end > s.start

    def _rebuild_effect_list(self):
        pat_insts, pat_songs = self._usage()
        eff = []
        for s in self.songs:
            kind = "music" if self.song_is_music(s) else "effect"
            eff.append(FxEffect(len(eff), s.name, "song", s.pack(), ref_id=s.start, flag=s.nvoices, offset_in_table=s.offset, extra={"song": s, "tag": f"[slot {s.slot} · {kind}]"}))
        for k, p in enumerate(self.patterns):
            used_by = [i for i, v in enumerate(self.order) if v == k]
            sg = pat_songs[k]
            tag = "→ " + (", ".join(sg[:2]) + ("…" if len(sg) > 2 else "") if sg else "(unused)")
            if len(sg) > 1:
                tag += " ⚠shared"
            eff.append(FxEffect(len(eff), f"PAT {k:02d}", "pattern", p, ref_id=k, flag=len(used_by), extra={"orders": used_by, "tag": f"[{tag}]"}))
        for k, p in enumerate(self.insts):
            users = [i for i in range(len(self.patterns)) if (k + 1) in pat_insts[i]]
            sg = []
            for i in users:
                for n in pat_songs[i]:
                    if n not in sg:
                        sg.append(n)
            tag = f"[{len(users)} pat · {len(sg)} sounds" + (" ⚠" if len(sg) > 1 else "") + "]"
            if self.kind == "rld" and k >= sum(1 for x in self.defflag if x):
                tag = "[not loaded by driver]"
            eff.append(FxEffect(len(eff), f"INS {k + 1:02d} {self.inst_name(k)}", "inst", p, ref_id=k + 1, extra={"tag": tag}))
        self.effects = eff

    def inst_name(self, k):
        d = self.insts[k]
        o = 0 if self.kind == "alb" else 8
        return bytes(d[o:o + 10]).split(b"\0")[0].decode("latin1", "replace").strip()

    def get_effect(self, index):
        return self.effects[index]

    def extract_effect(self, index, out_path):
        with open(out_path, "wb") as f:
            f.write(bytes(self.effects[index].data))

    def import_effect(self, index, new_data: bytes):
        e = self.effects[index]
        nd = bytearray(new_data)
        if e.kind == "pattern":
            if len(nd) % 16:
                nd += bytes(16 - len(nd) % 16)
            self.patterns[e.ref_id] = nd
        elif e.kind == "inst":
            nd = (nd + bytes(self.inst_size))[:self.inst_size]
            self.insts[e.ref_id - 1] = nd
        elif e.kind == "song":
            nd = (nd + bytes(16))[:16]
            s = e.extra["song"]
            s.name = bytes(nd[:10]).split(b"\0")[0].decode("latin1", "replace")
            s.start, s.end, s.loop, s.nvoices = nd[10], nd[11], nd[12], nd[13]
            nd = bytearray(s.pack())
        e.data = nd
        e.extra.pop("_cache", None)

    def get_total_size(self):
        return len(self.rebuild())

    def rebuild(self) -> bytes:
        hdr = bytearray(self.raw_header)
        hdr[0x18:0x98] = bytes(self.order)
        for i, v in enumerate(self.defvol):
            hdr[0x99 + 2 * i] = v
        if self.kind == "alb":
            self._pt_size = ((len(self.patterns) * 2) & 0xFFF0) + 0x10
        for s in self.songs:
            hdr[s.offset:s.offset + 16] = s.pack()
        ptrs = []
        cur = self._pt_size // 16
        for p in self.patterns:
            ptrs.append(cur)
            cur += len(p) // 16
        ptrs.append(cur)
        words = self._pt_size // 2
        table = bytearray(b"\xFF" * self._pt_size)
        for i, v in enumerate(ptrs):
            struct.pack_into("<H", table, i * 2, v)
        out = hdr + table
        for p in self.patterns:
            out += p
        for i in self.insts:
            out += i
        out += self._inst_tail
        return bytes(out)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.rebuild())

    def decode_pattern(self, k):
        d = self.patterns[k]
        p = 0
        rows = []
        try:
            for _ in range(64):
                mask = d[p] | (d[p + 1] << 8)
                p += 2
                cells = []
                if self.kind == "alb":
                    for c in range(self.ncols + 5):
                        if mask & (0x8000 >> c):
                            n, i, cm, pa = d[p:p + 4]
                            p += 4
                            cells.append((c, n, 0, 0, 0, i, cm, pa))
                else:
                    for c in range(self.ncols):
                        t = (mask >> (14 - 2 * c)) & 3
                        if t == 0:
                            continue
                        if t == 1:
                            cells.append((c, 0, 0, 0, 0, 0, d[p], d[p + 1])); p += 2
                        elif t == 2:
                            cells.append((c, d[p], 0, 0, 0, d[p + 1], 0, 0)); p += 2
                        else:
                            cells.append((c,) + tuple(d[p:p + 7])); p += 7
                rows.append(cells)
        except IndexError:
            while len(rows) < 64:
                rows.append([])
        return rows

    def pattern_text(self, k):
        nn = note_name
        out = []
        for i, row in enumerate(self.decode_pattern(k)):
            if not row:
                continue
            parts = []
            for c, n1, n2, n3, n4, ins, cm, pa in row:
                notes = " ".join(nn(x) for x in (n1, n2, n3, n4) if x) or "---"
                parts.append(f"[{c}] {notes} i{ins:02d} {cm:X}{pa:02X}")
            out.append(f"{i:02d}  " + "  ".join(parts))
        return "\n".join(out)

    def set_pattern_text(self, k, text):
        self.patterns[k] = bytearray(encode_pattern_text(text, self.kind, self.ncols))
        self._rebuild_effect_list()

    def inst_params(self, k):
        d = self.insts[k]
        r = {"name": bytes(d[0:10]).split(b"\0")[0].decode("latin1", "replace"), "wave_mod": d[36] & 3, "wave_car": d[37] & 3, "vol": self.defvol[k]}
        for key, base in (("mod", 10), ("car", 23)):
            r[key] = {n: d[base + i] for i, (n, lo, hi) in enumerate(OPL_PARAMS)}
        return r

    def set_inst_param(self, k, op, name, value):
        d = self.insts[k]
        if op == "name":
            d[0:10] = str(value).encode("latin1", "replace")[:10].ljust(10, b"\0")
        elif op == "wave_mod":
            d[36] = int(value) & 3
        elif op == "wave_car":
            d[37] = int(value) & 3
        elif op == "vol":
            self.defvol[k] = max(0, min(0x40, int(value)))
        else:
            base = 10 if op == "mod" else 23
            for i, (n, lo, hi) in enumerate(OPL_PARAMS):
                if n == name:
                    d[base + i] = max(lo, min(hi, int(value)))
        self._rebuild_effect_list_keep()

    def _rebuild_effect_list_keep(self):
        for e in self.effects:
            if e.kind == "inst":
                e.data = self.insts[e.ref_id - 1]
                e.name = f"INS {e.ref_id:02d} {self.inst_name(e.ref_id - 1)}"

    def add_instrument(self, params64=None, name="NEW", vol=0x40):
        if self.kind != "alb":
            raise ValueError("New instruments: ALB banks only (MT-32 timbres have their own format).")
        if len(self.insts) >= 64:
            raise ValueError("Maximum 64 instruments.")
        rec = bytearray(params64 if params64 else DEFAULT_INST)
        rec[0:10] = name.encode("latin1", "replace")[:10].ljust(10, b"\0")
        self.insts.append(rec)
        k = len(self.insts) - 1
        self.defvol[k] = vol
        self._rebuild_effect_list()
        return k

    def add_effect_song(self, name, inst_no, note, seconds, speed=6):
        if self.kind != "alb":
            raise ValueError("New effects: ALB banks only.")
        if not self._free_slots:
            raise ValueError("No free song slot ('Not Used').")
        rows = max(2, int(round(seconds / (speed * 0.02))) + 1)
        rows = min(rows, 60)
        txt = [f"00  [0] {note_name(note)} i{inst_no:02d} 000  [1] --- i00 F{speed:02X}",
               f"{rows:02d}  [0] --- i00 600",
               f"{rows + 1:02d}  [0] --- i00 B26"]
        blk = bytearray(encode_pattern_text("\n".join(txt), "alb", self.ncols))
        self.patterns.append(blk)
        pat = len(self.patterns) - 1
        oi = 39
        while oi < 127 and self.order[oi] != 0:
            oi += 1
        self.order[oi] = pat
        off = self._free_slots.pop(0)
        slot = (off - HEADER_TABLE_OFFSET) // ENTRY_SIZE
        self.songs.append(FxSong(slot, name[:10], oi, oi, 0, 1, off))
        self.songs.sort(key=lambda x: x.slot)
        self._rebuild_effect_list()
        for e in self.effects:
            if e.kind == "song" and e.extra["song"].slot == slot:
                return e.index
        return 0

    def pattern_insts(self, k):
        used = set()
        for row in self.decode_pattern(k):
            for c in row:
                if c[5]:
                    used.add(c[5])
        return sorted(used)

    def links(self, idx):
        e = self.effects[idx]
        L = []
        if e.kind == "song":
            s = e.extra["song"]
            L.append(f"SONG '{s.name}': orders {s.start}..{s.end}, voices {s.nvoices}, "
                     f"{'loop' if s.loop else 'play once'}")
            for o in range(s.start, s.end + 1):
                p = self.order[o]
                ins = self.pattern_insts(p)
                L.append(f"  order {o:3d} -> PAT {p:02d} -> instruments " + (", ".join(f"{i}:{self.inst_name(i - 1)}" for i in ins if i <= len(self.insts)) or "-"))
        elif e.kind == "pattern":
            k = e.ref_id
            ords = [i for i, v in enumerate(self.order[:64]) if v == k and (i < 39 or True)]
            songs = []
            for s in self.songs:
                if any(s.start <= o <= s.end for o in ords):
                    songs.append(s.name)
            L.append(f"PATTERN {k:02d}: used by orders {ords or '-'} (songs: {', '.join(songs) or '-'})")
            ins = self.pattern_insts(k)
            L.append("  plays instruments: " + (", ".join(f"{i}:{self.inst_name(i - 1)}" for i in ins if i <= len(self.insts)) or "-"))
        else:
            k = e.ref_id
            L.append(f"INSTRUMENT {k}: '{self.inst_name(k - 1)}'  initial volume {self.defvol[k - 1]}")
            pats = [p for p in range(len(self.patterns)) if k in self.pattern_insts(p)]
            L.append("  used by patterns: " + (", ".join(f"{p:02d}" for p in pats) or "-"))
            songs = []
            for s in self.songs:
                for o in range(s.start, s.end + 1):
                    if self.order[o] in pats and s.name not in songs:
                        songs.append(s.name)
            L.append("  thus by songs: " + (", ".join(songs) or "-"))
        return "\n".join(L)

    def impact_text(self, idx):
        e = self.effects[idx]
        pat_insts, pat_songs = self._usage()
        if e.kind == "song":
            s = e.extra["song"]
            kind = "MUSIC" if self.song_is_music(s) else "SOUND EFFECT"
            pats = [self.order[o] for o in range(s.start, s.end + 1)]
            ins = sorted({i for p in pats for i in pat_insts[p]})
            return "\n".join([
                f"{kind} «{s.name}» = slot {s.slot} of the song table. The game calls it by its slot NUMBER, "
                f"not by name (the name is just a label).",
                f"EDITABLE HERE: name, start order ({s.start}) / end order ({s.end}), loop, number of voices.",
                f"LINKED (not edited here): plays patterns {', '.join(f'{p:02d}' for p in pats)} "
                f"and uses instruments {', '.join(str(i) for i in ins) or '-'}.",
                "IN GAME: changing start/end plays OTHER patterns at that slot; patterns and instruments "
                "remain unchanged and other sound effects are not affected."])
        if e.kind == "pattern":
            k = e.ref_id
            sg = pat_songs[k]
            ords = [i for i, v in enumerate(self.order) if v == k and any(
                s.start <= i <= s.end for s in self.songs)]
            warn = (f"  ⚠ SHARED with {len(sg)} sound effects ({', '.join(sg)}): changes will be heard in ALL of them."
                    if len(sg) > 1 else "")
            return "\n".join([
                f"PATTERN {k:02d} = 64 rows of notes. Called by orders {ords or '-'} → sounds: "
                f"{', '.join(sg) or 'none (never heard)'}." + warn,
                "EDITABLE HERE: notes, duration, volume (C), speed (F), slides, jumps (B/D) — all text below.",
                f"LINKED: each cell has an instrument number iNN (here: {', '.join(str(i) for i in sorted(pat_insts[k])) or '-'}). "
                "Changing iNN selects ANOTHER timbre for that note; it does NOT modify the instrument.",
                "IN GAME: changes the melody/rhythm/duration of sound effects using this pattern."])
        k = e.ref_id - 1
        users = [i for i in range(len(self.patterns)) if (k + 1) in pat_insts[i]]
        sg = []
        for i in users:
            for n in pat_songs[i]:
                if n not in sg:
                    sg.append(n)
        warn = f"  ⚠ USED BY {len(sg)} SOUNDS ({', '.join(sg)}): any tweak changes ALL their notes with this timbre." if len(sg) > 1 else ""
        if self.kind == "rld":
            return "\n".join([
                f"MT-32 TIMBRE #{k + 1}: used by patterns {', '.join(f'{p:02d}' for p in users) or '-'} → {', '.join(sg) or 'no sound'}." + warn,
                "EDITABLE: only name here; parameters (partials, envelopes, filters) are changed with an MT-32 timbre editor and re-importing the .bin.",
                "IN GAME: on MT-32 changes the sound of notes using this timbre; the AdLib version (ALB) DOES NOT change, it is a separate file."])
        return "\n".join([
            f"INSTRUMENT {k + 1} «{self.inst_name(k)}» = 2-operator FM patch (64-byte record). "
            f"Used by patterns {', '.join(f'{p:02d}' for p in users) or '-'} → {', '.join(sg) or 'no sound'}." + warn,
            "EDITABLE HERE: all OPL parameters (grid), waveforms, initial volume, name.",
            "LINKED: patterns reference it by number; they are not touched. NOTES do not change, HOW they sound changes.",
            "IN GAME: ALB bank (AdLib) only. To hear the effect on a single sound effect, create a new instrument "
            "(＋ Instrument) and assign it to that pattern instead of tweaking a shared one."])

    def render_inst_note(self, k, note=60, seconds=1.5, rate=44100):
        if self.kind == "rld":
            return self._render_rld_inst(k, note, seconds, rate)
        self.last_channels = 1
        self.last_engine = "OPL2 (pyopl)" if _pyopl_ok() else "OPL2 (fallback numpy)"
        return render_inst_pcm(self.insts[k], self.defvol[k], note, seconds, rate)

    def _render_rld_inst(self, k, note, seconds, rate):
        snap = RldSnapshot(self)
        slots = [i for i in range(64) if snap.defflag[i]]
        slot = slots[k] if k < len(slots) else k
        ev = [(0, bytes([0xC1, slot])), (0, bytes([0x91, note, 0x7F])),
              (int(seconds * 500 * 0.7), bytes([0xB1, 0x7B, 0]))]
        self.last_channels, self.last_engine = 1, "MT-32 lite (numpy, approximate)"
        if self.use_mt32emu:
            try:
                pcm, sr = render_events_mt32emu(snap, ev, int(seconds * 500), rate, tail=1.5)
                self.last_channels, self.last_engine = 2, "MT-32 FAITHFUL (mt32emu + ROM)"
                return pcm, sr
            except Mt32EmuError as ex:
                self.last_fallback_reason = str(ex)
        return _render_events_pcm(snap, ev, int(seconds * 500), rate)


    def song_for_effect(self, idx):
        e = self.effects[idx]
        if e.kind == "song":
            return e.extra["song"]
        return None

    def render_effect_pcm(self, idx, rate=OPL_RATE, max_seconds=420, one_pass=True, start_order=None, end_order=None):
        e = self.effects[idx]
        if self.kind != "alb":
            return self._render_rld(e, rate, max_seconds)
        self.last_channels = 1
        self.last_engine = "OPL2 (pyopl)" if _pyopl_ok() else "OPL2 (fallback numpy)"
        snap = AlbSnapshot(self)
        if e.kind == "song":
            s = e.extra["song"]
            so = (s.name, s.start, s.end, s.loop, s.nvoices)
            order = list(self.order)
            if start_order is not None:
                so = (s.name, start_order, end_order if end_order is not None else s.end, 0, s.nvoices)
        elif e.kind == "pattern":
            order = [e.ref_id]
            so = (e.name, 0, 0, 0, self.ncols)
        else:
            return self._render_inst_test(e.ref_id - 1, rate)
        pcm = render_alb(snap, order, so, max_seconds=max_seconds)
        return _resample_s16(pcm, OPL_RATE, rate), rate

    def _render_rld(self, e, rate, max_seconds):
        snap = RldSnapshot(self)
        self.last_channels, self.last_engine = 1, "MT-32 lite (numpy, approximate)"
        if e.kind == "song":
            s = e.extra["song"]
            song = (s.name, s.start, s.end, s.loop, s.nvoices)
            order = list(self.order)
        elif e.kind == "pattern":
            order = [e.ref_id]
            song = (e.name, 0, 0, 0, self.ncols)
        else:
            return self.render_inst_note(e.ref_id - 1, 60, 1.6, rate)
        if self.use_mt32emu:
            try:
                ev, end = rld_events(snap, order, song, max_seconds=max_seconds, one_pass=True, t0=0)
                pcm, sr = render_events_mt32emu(snap, ev, end, rate)
                self.last_channels, self.last_engine = 2, "MT-32 FAITHFUL (mt32emu + ROM)"
                return pcm, sr
            except Mt32EmuError as ex:
                self.last_fallback_reason = str(ex)
        pcm = render_rld_pcm(snap, order, song, max_seconds=max_seconds)
        return _resample_s16(pcm, MT32_RATE, rate), rate

    def _render_inst_test(self, inst_idx, rate):
        snap = AlbSnapshot(self)
        order = [0]
        row0 = [(0, 60, inst_idx + 1, 0, 0)]
        blk = bytearray()
        for r in range(64):
            if r == 0:
                blk += struct.pack("<H", 0x8000) + bytes([60, inst_idx + 1, 0, 0])
            elif r == 14:
                blk += struct.pack("<H", 0x8000) + bytes([0, 0, 6, 0])
            elif r == 15:
                blk += struct.pack("<H", 0x0000)
                blk += b""
            else:
                blk += struct.pack("<H", 0)
        snap.patterns = [bytes(blk)]
        snap.order = [0]
        pcm = render_alb(snap, [0], ("test", 0, 0, 0, 1), max_seconds=6, speed=6, stop_after_rows=20)
        return _resample_s16(pcm, OPL_RATE, rate), rate

    def extract_effect_wav(self, index, out_path, sample_rate=44100):
        pcm, rate = self.render_effect_pcm(index, rate=sample_rate)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(self.last_channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm)

    def export_midi(self, path, song_name=None):
        if self.kind != "rld":
            raise ValueError("MT-32 MIDI export is available for RLD banks only.")
        snap = RldSnapshot(self)
        s = self.songs[0]
        if song_name:
            for x in self.songs:
                if x.name == song_name:
                    s = x
        data = render_rld_midi(snap, self.order, (s.name, s.start, s.end, s.loop, s.nvoices))
        with open(path, "wb") as f:
            f.write(data)


NOTE_NAMES = "C C# D D# E F F# G G# A A# B".split()
OPL_PARAMS = [("ksl", 0, 3), ("mult", 0, 15), ("fb", 0, 7), ("attack", 0, 15), ("sustain", 0, 15),
              ("eg", 0, 1), ("decay", 0, 15), ("release", 0, 15), ("level", 0, 63),
              ("am", 0, 1), ("vib", 0, 1), ("ksr", 0, 1), ("conn", 0, 1)]
DEFAULT_INST = bytes(b"NEW\0\0\0\0\0\0\0" + bytes([0, 1, 0, 15, 0, 0, 4, 6, 40, 0, 0, 0, 0])
                     + bytes([0, 1, 0, 15, 4, 0, 5, 6, 63, 0, 0, 0, 0]) + bytes([0, 0]) + bytes(26))

def note_name(n):
    return "---" if not n else f"{NOTE_NAMES[n % 12]:-<2}{n // 12 - 1}"


def parse_note(tok):
    import re
    if tok in ("---", "..."):
        return 0
    m = re.fullmatch(r"([A-Ga-g])([-#])(-?\d)", tok)
    if not m:
        raise ValueError(f"invalid note: '{tok}' (use e.g. C-4, F#3)")
    idx = NOTE_NAMES.index(m.group(1).upper() + ("#" if m.group(2) == "#" else ""))
    v = (int(m.group(3)) + 1) * 12 + idx
    if not 12 <= v <= 107:
        raise ValueError(f"note out of range: {tok}")
    return v


def encode_pattern_text(text, kind, ncols):
    import re
    rows = {}
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"(\d+)\s+(.*)", line)
        if not m:
            raise ValueError(f"line {ln}: missing line number")
        r = int(m.group(1))
        if not 0 <= r < 64:
            raise ValueError(f"line {ln}: line number {r} out of range 0..63")
        cells = {}
        for cm in re.finditer(r"\[(\d+)\]\s+((?:\S+\s+)*?)i(\d+)\s+([0-9A-Fa-f])([0-9A-Fa-f]{2})", m.group(2)):
            c = int(cm.group(1))
            lim = ncols + 5 if kind == "alb" else ncols
            if c >= lim:
                raise ValueError(f"line {ln}: column {c} (max {lim - 1})")
            notes = [parse_note(t) for t in cm.group(2).split()]
            if kind == "alb" and len(notes) > 1:
                raise ValueError(f"line {ln}: in ALB format a cell can only have one note")
            notes = (notes + [0, 0, 0, 0])[:4]
            cells[c] = (notes, int(cm.group(3)), int(cm.group(4), 16), int(cm.group(5), 16))
        if m.group(2).strip() and not cells:
            raise ValueError(f"line {ln}: no recognized cell")
        rows[r] = cells
    out = bytearray()
    for r in range(64):
        cells = rows.get(r, {})
        if kind == "alb":
            mask = 0
            body = bytearray()
            for c in sorted(cells):
                notes, ins, cmd, par = cells[c]
                mask |= 0x8000 >> c
                body += bytes([notes[0], ins, cmd, par])
            out += struct.pack("<H", mask) + body
        else:
            mask = 0
            body = bytearray()
            for c in sorted(cells):
                notes, ins, cmd, par = cells[c]
                if not any(notes) and not ins and (cmd or par):
                    t, b = 1, bytes([cmd, par])
                elif not any(notes[1:]) and not cmd and not par:
                    t, b = 2, bytes([notes[0], ins])
                else:
                    t, b = 3, bytes(notes + [ins, cmd, par])
                mask |= t << (14 - 2 * c)
                body += b
            out += struct.pack("<H", mask) + body
    if len(out) % 16:
        out += bytes(16 - len(out) % 16)
    return bytes(out)


def render_inst_pcm(inst64, defvol, note, seconds, rate=44100, backend=None):
    class _S:
        pass
    sn = _S()
    sn.ncols = 6
    sn.insts = [bytes(inst64)]
    sn.defvol = [defvol] + [0] * 63
    sn.order = [0]
    rows = max(4, int(seconds / 0.12))
    cut = max(2, rows - 6)
    blk = bytearray()
    for r in range(64):
        if r == 0:
            blk += struct.pack("<H", 0x8000) + bytes([note, 1, 0, 0])
        elif r == cut:
            blk += struct.pack("<H", 0x8000) + bytes([0, 0, 6, 0])
        else:
            blk += struct.pack("<H", 0)
    sn.patterns = [bytes(blk)]

    def rows_(b, d=sn):
        d_ = d.patterns[b]
        p = 0
        out = []
        for _ in range(64):
            mask = d_[p] | (d_[p + 1] << 8)
            p += 2
            cells = {}
            for c in range(11):
                if mask & (0x8000 >> c):
                    cells[c] = tuple(d_[p:p + 4])
                    p += 4
            out.append(cells)
        return out
    sn.rows = rows_
    pcm = render_alb(sn, [0], ("t", 0, 0, 0, 1), max_seconds=seconds + 1, speed=6, stop_after_rows=rows, backend=backend)
    return _resample_s16(pcm, OPL_RATE, rate), rate


def fit_wav_to_inst(samples, sr, progress=None, iters=160, seed=1):
    import numpy as np
    rng = np.random.default_rng(seed)
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x / (np.abs(x).max() + 1e-9)
    thr = 0.03
    nz = np.nonzero(np.abs(x) > thr)[0]
    if not len(nz):
        raise ValueError("Silent WAV")
    x = x[nz[0]:nz[0] + int(1.5 * sr)]
    t = np.arange(len(x)) / sr
    x49 = np.interp(np.arange(int(len(x) * OPL_RATE / sr)) * (sr / OPL_RATE), np.arange(len(x)), x)
    dur = len(x) / sr
    hop = int(OPL_RATE * 0.01)
    def env_db(y):
        n = len(y) // hop
        if n == 0:
            return np.zeros(1)
        e = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-6
        return 20 * np.log10(e / (e.max() + 1e-9))
    et = env_db(x49)
    seg = x49[:min(len(x49), 16384)]
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    fr = np.fft.rfftfreq(len(seg), 1 / OPL_RATE)
    band = (fr > 60) & (fr < 2000)
    f0 = fr[band][sp[band].argmax()]
    note = int(round(69 + 12 * np.log2(f0 / 440.0)))
    note = max(24, min(96, note))
    edges = np.geomspace(80, 12000, 49)
    def spec(y):
        y = y[:int(0.5 * OPL_RATE)]
        if len(y) < 2048:
            y = np.pad(y, (0, 2048 - len(y)))
        w = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
        f = np.fft.rfftfreq(len(y), 1 / OPL_RATE)
        b = np.array([w[(f >= edges[i]) & (f < edges[i + 1])].sum() + 1e-9 for i in range(48)])
        b = 10 * np.log10(b)
        return b - b.max()
    st = spec(x49)
    def tdb(level):
        idx = np.nonzero(et <= level)[0]
        return (idx[0] if len(idx) else len(et)) * 0.01
    pk = int(et.argmax())
    atk = max(0.0, pk * 0.01)
    decay_t = max(0.02, tdb(-20) - atk)
    a_reg = int(np.clip(round(15 - np.log2(max(atk, 0.002) / 0.002) * 1.4), 1, 15))
    d_reg = int(np.clip(round(15 - np.log2(decay_t / 0.02) * 1.2), 1, 15))
    sus = int(np.clip(round(-float(np.median(et[len(et) // 2:])) / 3.0), 0, 15)) if dur > 0.3 else 8
    best = bytearray(DEFAULT_INST)
    best[10 + 3] = a_reg; best[23 + 3] = a_reg
    best[10 + 6] = d_reg; best[23 + 6] = d_reg
    best[10 + 4] = min(15, sus); best[23 + 4] = min(15, sus)
    best[10 + 7] = 6; best[23 + 7] = 7
    best[23 + 5] = 1 if dur > 0.8 else 0
    best[10 + 5] = best[23 + 5]
    secs = min(dur, 1.0)
    def cost(rec):
        pcm, _ = render_inst_pcm(rec, 0x40, note, secs, OPL_RATE)
        y = np.frombuffer(pcm, "<i2").astype(np.float64)
        if np.abs(y).max() < 50:
            return 1e9
        y = y / np.abs(y).max()
        sc = np.mean((spec(y) - st) ** 2)
        e = env_db(y)
        m = min(len(e), len(et), int(secs * 100))
        ec = np.mean((e[:m] - et[:m]) ** 2)
        return sc + 0.35 * ec
    cur = cost(bytes(best))
    mutable = [(10, 1, 0, 15), (10, 2, 0, 7), (10, 8, 20, 63), (10, 0, 0, 3),
               (23, 1, 0, 15), (23, 8, 40, 63), (23, 3, 1, 15), (23, 6, 0, 15), (23, 4, 0, 15),
               (10, 3, 1, 15), (10, 6, 0, 15), (10, 4, 0, 15), (36, 0, 0, 3), (37, 0, 0, 3)]
    for it in range(iters):
        cand = bytearray(best)
        for _ in range(rng.integers(1, 3)):
            off, i, lo, hi = mutable[rng.integers(len(mutable))]
            pos = off + i if off < 36 else off
            if off in (36, 37):
                pos = off
            if rng.random() < 0.3:
                cand[pos] = int(rng.integers(lo, hi + 1))
            else:
                cand[pos] = int(np.clip(cand[pos] + rng.integers(-2, 3), lo, hi))
        c = cost(bytes(cand))
        if c < cur:
            best, cur = cand, c
        if progress and it % 8 == 0:
            progress(it / iters)
    return bytes(best), note, dur


def _is_fx_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].upper()
    if ext not in (".ALB", ".RLD"):
        return False
    try:
        data = open(path, "rb").read()
    except Exception:
        return False
    if len(data) < HEADER_TABLE_OFFSET + ENTRY_SIZE:
        return False
    return data[3:3 + 16].split(b"\x00")[0].lower() == b"ingame"


def synthesize_preview_wav(chunk: bytes, kind: str, sample_rate=22050) -> bytes:
    raise NoSynthError("Use HQFxFile.render_effect_pcm(index).")


def _resample_s16(pcm, rate_in, rate_out):
    if rate_in == rate_out or not pcm:
        return pcm
    import numpy as np
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    n_out = int(len(x) * rate_out / rate_in)
    t = np.arange(n_out) * (rate_in / rate_out)
    y = np.interp(t, np.arange(len(x)), x)
    return np.clip(y, -32768, 32767).astype("<i2").tobytes()


class AlbSnapshot:
    def __init__(self, fx):
        self.order = list(fx.order)
        self.defvol = list(fx.defvol)
        self.ncols = fx.ncols
        self.patterns = [bytes(p) for p in fx.patterns]
        self.insts = [bytes(i) for i in fx.insts]

    def rows(self, blk):
        d = self.patterns[blk]
        p = 0
        rows = []
        for _ in range(64):
            mask = d[p] | (d[p + 1] << 8)
            p += 2
            cells = {}
            for c in range(self.ncols + 5):
                if mask & (0x8000 >> c):
                    cells[c] = tuple(d[p:p + 4])
                    p += 4
            rows.append(cells)
        return rows


class _V:
    def __init__(self):
        self.note = self.inst = self.cmd = self.par = 0
        self.vol = 0
        self.cur = 0
        self.target = 0
        self.dir = 0
        self.pspd = 0
        self.fw = 0
        self.blk = 0
        self.fn = 0
        self.last = 0
        self.tlm = 0
        self.tlc = 0


class AlbSeq:
    def __init__(self, snap, write, order, song):
        self.b = snap
        self.w = write
        self.order = order
        self.sh = {}
        self.volcache = [0xFF] * 11
        self.v = [_V() for _ in range(11)]
        self.bd = 0x20
        self.ksl = {}
        self.b0 = [0] * 9
        write(0x01, 0x20)
        write(0xBD, 0x20)
        for r in range(0x20, 0x36): write(r, 1)
        for r in range(0x40, 0x56): write(r, 0x3F)
        for r in range(0x60, 0x96): write(r, 0xF0)
        name, start, end, loop, nv = song
        self.st = dict(voices=list(range(min(nv, 6))), speed=6, cnt=0, order=start, row=0,
                       brk=False, rows=None, loop=loop, end=end + 1, start=start,
                       active=True, wrapped=False)
        for v in self.v:
            v.cur = 0
        self.rows_played = 0

    def reg(self, r, v):
        self.w(r, v & 0xFF)

    def keyoff(self, bp):
        if bp < 6:
            self.b0[bp] &= 0xDF
            self.reg(0xB0 + bp, self.b0[bp])
        else:
            self.bd &= ~RHY[bp - 6]
            self.reg(0xBD, self.bd)

    def keyon(self, bp):
        if bp < 6:
            self.b0[bp] |= 0x20
            self.reg(0xB0 + bp, self.b0[bp])
        else:
            self.bd |= RHY[bp - 6]
            self.reg(0xBD, self.bd)

    def writefreq(self, bp, fw):
        if bp >= 8:
            return
        al = (((fw >> 8) & 0x70) >> 2) | ((fw >> 8) & 3)
        self.b0[bp] = (self.b0[bp] & 0x20) | al
        self.reg(0xB0 + bp, self.b0[bp])
        self.reg(0xA0 + bp, fw & 0xFF)

    def setfreq_note(self, v, bp, note):
        fw = FNUM[note - 12]
        v.fw = fw
        v.fn = fw & 0x3FF
        v.blk = fw >> 12
        self.writefreq(bp, fw)

    def setvol(self, bp, al):
        v = self.v[bp]
        if al >= 0x40:
            al = 0x3F
        if al == self.volcache[bp]:
            return
        self.volcache[bp] = al
        v.vol = al
        tl = v.tlc if bp <= 6 else v.tlm
        att = 63 - (tl * v.vol) // 63
        op = CAR[bp]
        self.reg(0x40 + op, self.ksl.get(op, 0) | att)

    def loadinst(self, bp, i):
        v = self.v[bp]
        if i >= len(self.b.insts):
            return
        ins = self.b.insts[i][10:]
        m, c, wm, wc = ins[0:13], ins[13:26], ins[26], ins[27]
        v.tlm, v.tlc = m[8], c[8]

        def opregs(op, d, wave_):
            self.reg(0xE0 + op, wave_ & 3)
            al = (0x80 if d[9] else 0) | (0x40 if d[10] else 0) | (0x20 if d[5] else 0) | (0x10 if d[11] else 0)
            self.reg(0x20 + op, al | (d[1] & 0xF))
            self.reg(0x60 + op, ((d[3] & 0xF) << 4) | (d[6] & 0xF))
            self.reg(0x80 + op, (((15 - d[4]) & 0xF) << 4) | (d[7] & 0xF))

        if bp < 9:
            self.reg(0xC0 + bp, ((m[2] & 7) << 1) & 0xFE)
        if bp <= 6:
            mo = MOD[bp]
            self.ksl[mo] = m[0] << 6
            self.reg(0x40 + mo, self.ksl[mo] | ((0x3F - m[8]) & 0x3F))
            opregs(mo, m, wm)
            co = CAR[bp]
            self.ksl[co] = c[0] << 6
            self.reg(0x40 + co, self.ksl[co] | ((63 - (v.tlc * v.vol) // 63) & 0x3F))
            opregs(co, c, wc)
        else:
            co = CAR[bp]
            self.ksl[co] = m[0] << 6
            self.reg(0x40 + co, self.ksl[co] | ((63 - (m[8] * v.vol) // 63) & 0x3F))
            opregs(co, m, wm)

    def noteon(self, bp, note):
        v = self.v[bp]
        self.keyoff(bp)
        if bp < 7:
            fw = FNUM[note - 12]
            v.fw, v.fn, v.blk = fw, fw & 0x3FF, fw >> 12
            self.writefreq(bp, fw)
        elif bp == 8:
            self.writefreq(7, FNUM[note + 7])
        self.keyon(bp)

    def wrapup(self, v, add):
        bx, dl = v.fn + add, v.blk
        while bx >= 0x2AE:
            bx = bx - 0x2AE + 0x157
            dl += 1
        return bx, dl

    def wrapdn(self, v, sub):
        bx, dl = v.fn - sub, v.blk
        while bx <= 0x142:
            bx = -(bx - 0x142) + 0x28A
            dl -= 1
        return bx, dl

    def tick_fx(self, bp):
        v = self.v[bp]
        if v.cmd == 0 and v.par == 0:
            return
        c = v.cmd & 0x1F
        if c == 1:
            v.fn, v.blk = self.wrapup(v, v.par * 2)
            self.writefreq(bp, v.fn | (v.blk << 12))
        elif c == 2:
            v.fn, v.blk = self.wrapdn(v, v.par * 2)
            self.writefreq(bp, v.fn | (v.blk << 12))
        elif c == 3:
            if v.par:
                v.pspd = v.par
                v.par = 0
            if v.target == 0:
                return
            step = v.pspd * 2
            if v.dir == 0:
                v.fn, v.blk = self.wrapdn(v, step)
                if (v.fn | (v.blk << 12)) > v.target:
                    self.writefreq(bp, v.fn | (v.blk << 12))
                else:
                    v.target = 0
                    self.setfreq_note(v, bp, v.last)
            else:
                v.fn, v.blk = self.wrapup(v, step)
                if (v.fn | (v.blk << 12)) < v.target:
                    self.writefreq(bp, v.fn | (v.blk << 12))
                else:
                    v.target = 0
                    self.setfreq_note(v, bp, v.last)
        elif c == 0xA:
            hi = v.par >> 4
            if hi:
                v.vol = min(0x40, v.vol + hi)
            else:
                v.vol = max(0, v.vol - (v.par & 0xF))
            self.setvol(bp, v.vol)

    def row_fx(self, bp):
        v, st = self.v[bp], self.st
        c = v.cmd & 0x1F
        if c == 6:
            v.cmd = 0
            self.keyoff(bp)
        elif c == 0xB:
            st["order"] = v.par - 1
            st["brk"] = True
        elif c == 0xC:
            v.par = min(v.par, 0x40)
            v.vol = v.par
            self.setvol(bp, v.vol)
        elif c == 0xD:
            st["brk"] = True
        elif c == 0xF:
            a = v.par & 0x1F
            if a:
                st["cnt"] = 0
                st["speed"] = a

    def row_cell(self, bp):
        v = self.v[bp]
        if v.inst and v.note:
            al = self.b.defvol[v.inst - 1]
            if v.cmd == 0xC:
                al = v.par
                v.cmd = v.par = 0
            self.setvol(bp, al)
            if v.inst != v.cur:
                v.cur = v.inst
                self.loadinst(bp, v.inst - 1)
        if v.note == 0:
            self.row_fx(bp)
            return
        if (v.cmd & 0x1F) == 3:
            v.last = v.note
            bx = FNUM[v.note - 12]
            v.target, v.dir = bx, 0
            if bx == v.fw:
                v.target = 0
            elif bx > v.fw:
                v.dir = 1
            self.row_fx(bp)
            return
        self.row_fx(bp)
        self.noteon(bp, v.note)

    def fetch(self):
        st, b = self.st, self.b
        if st["rows"] is None:
            st["rows"] = b.rows(self.order[st["order"] % len(self.order)])
        cells = st["rows"][st["row"]]
        for k, vid in enumerate(st["voices"]):
            n, i, cm, p = cells.get(k, (0, 0, 0, 0))
            vv = self.v[vid]
            vv.note, vv.inst, vv.cmd, vv.par = n, i, cm, p
        for k in range(5):
            n, i, cm, p = cells.get(b.ncols + k, (0, 0, 0, 0))
            vv = self.v[6 + k]
            vv.note, vv.inst, vv.cmd, vv.par = n, i, cm, p
        st["row"] += 1

    def stop(self):
        st = self.st
        st["active"] = False
        for vid in st["voices"]:
            self.v[vid].cur = 0
            self.keyoff(vid)
            self.setvol(vid, 0)

    def advance_order(self):
        st = self.st
        st["cnt"] = 0
        st["brk"] = False
        st["row"] = 0
        st["rows"] = None
        st["order"] += 1
        if st["loop"] == 0 and not (st["start"] <= st["order"] < st["end"]):
            self.stop()
            return
        if st["order"] == st["end"]:
            st["wrapped"] = True
            if st["loop"] == 0:
                self.stop()
                return
            st["order"] = st["start"]

    def tick(self):
        st = self.st
        if not st["active"]:
            return
        st["cnt"] += 1
        if st["cnt"] < st["speed"]:
            for vid in st["voices"]:
                self.tick_fx(vid)
            for bp in range(6, 11):
                self.tick_fx(bp)
            if st["brk"]:
                self.advance_order()
        else:
            st["cnt"] = 0
            self.fetch()
            self.rows_played += 1
            for vid in st["voices"]:
                self.row_cell(vid)
            for bp in range(6, 11):
                self.row_cell(bp)
            if st["row"] == 64 or st["brk"]:
                self.advance_order()


class _PyOPLBackend:
    def __init__(self, rate):
        import pyopl
        self.o = pyopl.opl(rate, 2, 1)

    def write(self, r, v):
        self.o.writeReg(r, v)

    def samples(self, n):
        import numpy as np
        parts = []
        while n > 0:
            k = min(n, 512)
            buf = bytearray(k * 2)
            self.o.getSamples(buf)
            parts.append(np.frombuffer(bytes(buf), dtype="<i2"))
            n -= k
        return np.concatenate(parts) if parts else np.zeros(0, "<i2")


class MiniOPL2:
    OFF2OP = {o: i for i, o in enumerate([0,1,2,3,4,5,8,9,10,11,12,13,16,17,18,19,20,21])}
    MULT = [0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 12, 12, 15, 15]
    KSLROM = [0, 32, 40, 45, 48, 51, 53, 55, 56, 58, 59, 60, 61, 62, 63, 64]
    CHMOD = [0, 1, 2, 6, 7, 8, 12, 13, 14]

    def __init__(self, rate=OPL_RATE):
        import numpy as np
        self.np = np
        self.rate = rate
        n = 18
        self.r20 = [0] * n; self.r40 = [0] * n; self.r60 = [0] * n; self.r80 = [0] * n; self.rE0 = [0] * n
        self.fn = [0] * 9; self.blk = [0] * 9; self.key = [0] * 9; self.fb = [0] * 9; self.cnt = [0] * 9
        self.bd = 0
        self.stage = [0] * n
        self.att = [96.0] * n
        self.ph = [0.0] * n
        self.rhy_prev = [0] * 5
        self.lfo = 0.0
        self.rng = np.random.default_rng(1)
        self.fbhist = [0.0] * 9

    def write(self, r, v):
        np = self.np
        if r == 0xBD:
            old = self.bd
            self.bd = v
            if v & 0x20:
                for k, op in enumerate([16, 7, 8, 17, 6]):
                    pass
                for k, bit in enumerate(RHY):
                    opn = [15, 16 if False else 16, 8, 17, 12][k]
            return
        grp = r & 0xE0
        if 0x20 <= r <= 0xF5 and (r & 0x1F) in self.OFF2OP and grp in (0x20, 0x40, 0x60, 0x80, 0xE0):
            op = self.OFF2OP[r & 0x1F]
            {0x20: self.r20, 0x40: self.r40, 0x60: self.r60, 0x80: self.r80, 0xE0: self.rE0}[grp][op] = v
        elif 0xA0 <= r <= 0xA8:
            c = r - 0xA0
            self.fn[c] = (self.fn[c] & 0x300) | v
        elif 0xB0 <= r <= 0xB8:
            c = r - 0xB0
            self.fn[c] = (self.fn[c] & 0xFF) | ((v & 3) << 8)
            self.blk[c] = (v >> 2) & 7
            k = (v >> 5) & 1
            if k and not self.key[c]:
                self._keyon(c)
            elif not k and self.key[c]:
                self._keyoff(c)
            self.key[c] = k
        elif 0xC0 <= r <= 0xC8:
            c = r - 0xC0
            self.fb[c] = (v >> 1) & 7
            self.cnt[c] = v & 1

    def _ops_of(self, c):
        m = self.CHMOD[c]
        return m, m + 3

    def _keyon(self, c):
        for op in self._ops_of(c):
            self.stage[op] = 1
            self.ph[op] = 0.0

    def _keyoff(self, c):
        for op in self._ops_of(c):
            if self.stage[op]:
                self.stage[op] = 4

    def _rate(self, op, c, reg):
        ksr = (self.r20[op] >> 4) & 1
        rks = ((self.blk[c] << 1) | (self.fn[c] >> 9)) >> (0 if ksr else 2)
        return min(63, reg * 4 + rks) if reg else 0

    def _env(self, op, c, n):
        np = self.np
        st = self.stage[op]
        out = np.zeros(n)
        if st == 0:
            return out
        a = self.att[op]
        sl = ((self.r80[op] >> 4) & 15)
        sl_db = 93.0 if sl == 15 else sl * 3.0
        egt = (self.r20[op] >> 5) & 1
        i = 0
        guard = 0
        while i < n and guard < 6:
            guard += 1
            if st == 1:
                r = self._rate(op, c, (self.r60[op] >> 4) & 15)
                if r >= 60:
                    a = 0.0
                    st = 2
                    continue
                if r == 0:
                    out[i:] = a
                    i = n
                    break
                T = 2.82624 * 1000 / (2 ** ((r - 4) / 4.0)) / 1000.0
                tau = max(1.0, T * self.rate / 5.25)
                k = n - i
                idx = np.arange(1, k + 1)
                seg = a * np.exp(-idx / tau)
                done = np.nonzero(seg < 0.4)[0]
                if len(done):
                    j = done[0]
                    out[i:i + j + 1] = seg[:j + 1]
                    a = 0.0
                    i += j + 1
                    st = 2
                else:
                    out[i:] = seg
                    a = seg[-1]
                    i = n
            elif st in (2, 3, 4):
                if st == 2:
                    reg = self.r60[op] & 15
                elif st == 3:
                    reg = (self.r80[op] & 15) if not egt else 0
                else:
                    reg = self.r80[op] & 15
                r = self._rate(op, c, reg)
                if st == 3 and egt:
                    out[i:] = a
                    i = n
                    break
                slope = 0.0 if r == 0 else 96.0 / (39.28 * self.rate / (2 ** ((r - 4) / 4.0)))
                k = n - i
                seg = a + slope * np.arange(1, k + 1)
                lim = sl_db if st == 2 else 96.0
                over = np.nonzero(seg >= lim)[0]
                if len(over):
                    j = over[0]
                    out[i:i + j + 1] = np.minimum(seg[:j + 1], lim)
                    a = lim
                    i += j + 1
                    if st == 2:
                        st = 3
                    else:
                        st = 0
                        out[i:] = 96.0
                        i = n
                else:
                    out[i:] = seg
                    a = seg[-1]
                    i = n
        if i < n:
            out[i:] = 96.0 if st == 0 else a
        self.stage[op], self.att[op] = st, min(a, 96.0)
        return out

    def _wave(self, w, ph):
        np = self.np
        s = np.sin(2 * np.pi * ph)
        w &= 3
        if w == 0:
            return s
        if w == 1:
            return np.maximum(s, 0)
        if w == 2:
            return np.abs(s)
        return np.where((ph % 0.5) < 0.25, np.abs(s), 0.0)

    def _op(self, op, c, n, pmod=None, fbk=0):
        np = self.np
        if self.stage[op] == 0:
            return np.zeros(n)
        mult = self.MULT[self.r20[op] & 15]
        fnum, blk = self.fn[c], self.blk[c]
        inc = fnum * (2 ** blk) * mult / 2 ** 20
        ph = self.ph[op] + inc * np.arange(1, n + 1)
        self.ph[op] = float(ph[-1] % 1.0)
        att = self._env(op, c, n)
        ksl = (self.r40[op] >> 6) & 3
        kl = 0.0
        if ksl:
            kl = max(0.0, self.KSLROM[fnum >> 6] * 0.75 - 3.0 * (7 - blk))
            kl = kl / [1e9, 2.0, 1.0, 0.5][ksl] * (1.0 if ksl != 1 else 1.0)
            kl = kl * [0, 1, 0.5, 2][ksl] / (1 if ksl else 1) if False else kl
            kl *= [0, 0.5, 0.25, 1.0][ksl] * 2
        tl = (self.r40[op] & 63) * 0.75
        db = att + tl + kl
        if self.r20[op] & 0x80:
            db = db + 0.5 + 0.5 * np.sin(2 * np.pi * 3.7 * (np.arange(n) + self.lfo) / self.rate)
        amp = 10 ** (-db / 20.0)
        amp = np.where(db >= 90, 0.0, amp)
        if pmod is not None:
            ph = ph + pmod
        if fbk:
            y = self._wave(self.rE0[op], ph)
            beta = np.pi * (2 ** (fbk - 1)) / 16.0 * 2
            for _ in range(3):
                prev = np.concatenate(([self.fbhist[c]], y[:-1]))
                y = self._wave(self.rE0[op], ph + beta * prev)
            self.fbhist[c] = float(y[-1])
            return y * amp
        return self._wave(self.rE0[op], ph) * amp

    def samples(self, n):
        np = self.np
        out = np.zeros(n)
        for c in range(9):
            m, ca = self._ops_of(c)
            if self.stage[m] == 0 and self.stage[ca] == 0:
                continue
            if self.bd & 0x20 and c >= 7:
                continue
            mo = self._op(m, c, n, fbk=self.fb[c])
            if self.cnt[c]:
                co = self._op(ca, c, n)
                out += mo + co
            else:
                co = self._op(ca, c, n, pmod=mo * 2 * np.pi)
                out += co
        if self.bd & 0x20:
            out += self._rhythm(n)
        self.lfo += n
        return np.clip(out * 7000, -32768, 32767).astype("<i2")

    def _rhythm(self, n):
        np = self.np
        out = np.zeros(n)
        bits = [(self.bd >> b) & 1 for b in (3, 2, 1, 0)]
        ops = [(16, 7), (14, 8), (17, 8), (13, 7)]
        for k, (op, ch) in enumerate(ops):
            on = bits[k]
            if on and not self.rhy_prev[k]:
                self.stage[op] = 1
                self.ph[op] = 0.0
            if not on and self.rhy_prev[k] and self.stage[op]:
                self.stage[op] = 4
            self.rhy_prev[k] = on
            if self.stage[op] == 0:
                continue
            if k == 1:
                out += self._op(op, ch, n)
            else:
                noise = self.rng.uniform(-1, 1, n)
                env = 10 ** (-(self._env(op, ch, n) + (self.r40[op] & 63) * 0.75) / 20.0)
                out += noise * env * (0.7 if k != 0 else 0.9)
        return out


def _pyopl_ok():
    try:
        import pyopl
        return True
    except Exception:
        return False


def make_opl(rate=OPL_RATE, prefer_pyopl=True):
    if prefer_pyopl:
        try:
            return _PyOPLBackend(rate)
        except Exception:
            pass
    return MiniOPL2(rate)


def render_alb(snap, order, song, max_seconds=420, speed=None, stop_after_rows=None, backend=None):
    import numpy as np
    opl = backend or make_opl(OPL_RATE)
    seq = AlbSeq(snap, opl.write, order, song)
    if speed:
        seq.st["speed"] = speed
    out = []
    per = OPL_RATE / TICK_HZ
    acc = 0.0
    t = 0
    tail_ticks = 25
    while t < max_seconds * TICK_HZ and seq.st["active"] and not seq.st["wrapped"]:
        seq.tick()
        acc += per
        n = int(acc)
        acc -= n
        out.append(opl.samples(n))
        t += 1
        if stop_after_rows and seq.rows_played >= stop_after_rows:
            break
    if seq.st["active"]:
        seq.stop()
    for _ in range(tail_ticks):
        n = int(per)
        out.append(opl.samples(n))
    pcm = np.concatenate(out) if out else np.zeros(0, "<i2")
    return pcm.astype("<i2").tobytes()


class RldSnapshot:
    def __init__(self, fx):
        self.order = list(fx.order)
        self.defvol = list(fx.defvol)
        self.defflag = list(fx.defflag)
        self.ncols = fx.ncols
        self.patterns = [bytes(p) for p in fx.patterns]
        self.insts = [bytes(i) for i in fx.insts]
        self._fx = fx

    def rows(self, blk):
        fx = self._fx
        saved = fx.patterns
        fx.patterns = self.patterns
        try:
            rows = fx.decode_pattern(blk)
        finally:
            fx.patterns = saved
        return [{c: (n1, n2, n3, n4, ins, cm, pa) for c, n1, n2, n3, n4, ins, cm, pa in r} for r in rows]


def _roland_sysex(addr3, data):
    body = bytes(addr3) + bytes(data)
    chk = (-sum(body)) & 0x7F
    return bytes([0xF0, 0x41, 0x10, 0x16, 0x12]) + body + bytes([chk, 0xF7])


def _addr_add(a, off):
    v = (a[0] << 14) | (a[1] << 7) | a[2]
    v += off
    return [(v >> 14) & 0x7F, (v >> 7) & 0x7F, v & 0x7F]


def mt32_upload_events(snap):
    msgs = []
    msgs.append(_roland_sysex([0x10, 0x00, 0x04], [4] * 8 + [0]))
    rec = 0
    for slot in range(64):
        if not snap.defflag[slot]:
            continue
        if rec >= len(snap.insts):
            break
        r = snap.insts[rec]
        rec += 1
        if r[0] == 0x20:
            continue
        patch = bytearray(r[0:8])
        if patch[0] != 3:
            patch[1] = slot
        a = (slot * 8)
        msgs.append(_roland_sysex([0x05, (a >> 7) & 0x7F, a & 0x7F], patch))
        tbase = [0x08, (slot * 2) & 0x7F, 0x0A]
        msgs.append(_roland_sysex(tbase, r[18:22]))
        addr = [0x08, (slot * 2) & 0x7F, 0x0E]
        for k in range(4):
            msgs.append(_roland_sysex(addr, r[22 + 58 * k:22 + 58 * (k + 1)]))
            addr = _addr_add(addr, 0x3A)
    return msgs


class _RV:
    def __init__(self):
        self.n = [0, 0, 0, 0]
        self.inst = self.cmd = self.par = 0
        self.vol7 = 0
        self.cur = 0xFF
        self.cache = 0
        self.bend = 0
        self.last = 0
        self.target = 0
        self.dir = 0
        self.pspd = 0
        self.pcur = 0
        self.ptarget_note = 0


class RldSeq:

    def __init__(self, snap, order, song, emit):
        self.b = snap
        self.order = order
        self.emit = emit
        self.t = 0
        name, start, end, loop, nv = song
        self.st = dict(voices=list(range(min(nv, 8))), speed=6, cnt=0, order=start, row=0, brk=False, rows=None, loop=loop, end=end + 1, start=start, active=True, wrapped=False)
        self.v = [_RV() for _ in range(9)]
        self.rev = [0, 4, 4] 
        self.rows_played = 0

    def ev(self, *b):
        self.emit(self.t, bytes(b))

    def cc(self, ch, cc, val):
        self.ev(0xB0 + ch, cc, val & 0x7F)

    def send_bend(self, ch, v):
        v.bend &= 0xFFFF
        self.ev(0xE0 + ch, v.bend & 0x7F, ((v.bend << 1) >> 8) & 0x7F)

    def send_vol(self, ch, v, val):
        self.cc(ch, 7, val)

    def note_first(self, ch, v, note):
        if not note:
            return
        if v.bend != 0x2000:
            v.bend = 0x2000
            self.send_bend(ch, v)
        self.cc(ch, 0x7B, 0)
        self.ev(0x90 + ch, note, 0x7F)
        v.last = note

    def note_more(self, ch, note):
        if note:
            self.ev(0x90 + ch, note, 0x7F)

    def row_fx(self, ch, vid):
        v, st = self.v[vid], self.st
        c = v.cmd & 0x1F
        if c == 4:
            self.cc(ch, 1, ((v.n[3] & 0xF) << 3))
        elif c == 5:
            p = v.par
            if (p & 0xF0) == 0 and (p & 0x0F) == 0:
                v.cmd = 0
                val = 0x40
            elif p & 0xF0:
                val = ((p & 0xF0) >> 2) + 0x40
            else:
                val = 0x40 - ((p & 0xF) << 2)
            self.cc(ch, 10, val)
        elif c == 6:
            v.cmd = 0
            self.cc(ch, 0x7B, 0)
        elif c == 7:
            v.cmd = 0
            self.rev[0] = v.par
            self.sysex_reverb()
        elif c == 8:
            v.cmd = 0
            self.rev[1] = v.par & 0xF
            self.rev[2] = v.par >> 4
            self.sysex_reverb()
        elif c == 0xB:
            st["order"] = v.par - 1
            st["brk"] = True
        elif c == 0xC:
            v.par = min(v.par, 0x40)
            v.vol7 = v.par
            self.vol_apply(ch, v)
        elif c == 0xD:
            st["brk"] = True
        elif c == 0xF:
            a = v.par & 0x1F
            if a:
                st["cnt"] = 0
                st["speed"] = a

    def sysex_reverb(self):
        self.emit(self.t, _roland_sysex([0x10, 0x00, 0x01], self.rev))

    def vol_apply(self, ch, v):
        al = v.vol7
        if al == v.cache:
            return
        v.cache = al
        self.send_vol(ch, v, min(al * 2, 0x7F))

    def tick_fx(self, ch, vid):
        v = self.v[vid]
        if v.cmd == 0 and v.par == 0:
            return
        c = v.cmd & 0x1F
        if c == 1:
            v.bend += v.par * 32
            self.send_bend(ch, v)
        elif c == 2:
            v.bend -= v.par * 32
            self.send_bend(ch, v)
        elif c == 3:
            if v.par:
                v.pspd = v.par
                v.par = 0
            if v.target == 0:
                return
            sp = v.pspd
            if v.dir == 0:
                v.pcur += sp
                v.bend -= sp * 32
                if v.pcur < v.target:
                    self.send_bend(ch, v)
                else:
                    v.target = 0
                    self.note_first(ch, v, v.ptarget_note)
            else:
                v.pcur -= sp
                if v.pcur < 0:
                    v.target = 0
                    self.note_first(ch, v, v.ptarget_note)
                    return
                v.bend += sp * 32
                if v.pcur > v.target:
                    self.send_bend(ch, v)
                else:
                    v.target = 0
                    self.note_first(ch, v, v.ptarget_note)
        elif c == 0xA:
            hi = v.par >> 4
            if hi:
                v.vol7 = min(0x40, v.vol7 + hi)
            else:
                v.vol7 = max(0, v.vol7 - (v.par & 0xF))
            self.vol_apply(ch, v)

    def row_cell(self, vid):
        ch = vid + 1
        v = self.v[vid]
        has_notes = any(v.n)
        if v.inst:
            if has_notes:
                al = self.b.defvol[v.inst - 1] * 2
                al = min(al, 0x7F)
                if v.cmd == 0xC:
                    al = min(v.par * 2, 0x7F)
                    v.cmd = v.par = 0
                if al != v.cache:
                    v.cache = al
                    self.send_vol(ch, v, al)
            if v.inst - 1 != v.cur:
                v.cur = v.inst - 1
                self.ev(0xC0 + ch, v.cur)
        if not has_notes:
            self.row_fx(ch, vid)
            return
        if (v.cmd & 0x1F) == 3:
            v.ptarget_note = v.n[0]
            tb = MT32_PERIOD[v.n[0]]
            v.target = tb
            ax = MT32_PERIOD[v.last]
            v.pcur = ax
            v.dir = 0
            if tb == ax:
                v.target = 0
            elif tb < ax:
                v.dir = 1
            self.row_fx(ch, vid)
            return
        self.row_fx(ch, vid)
        self.note_first(ch, v, v.n[0])
        for x in v.n[1:]:
            self.note_more(ch, x)

    def fetch(self):
        st, b = self.st, self.b
        if st["rows"] is None:
            st["rows"] = b.rows(self.order[st["order"] % len(self.order)])
        cells = st["rows"][st["row"]]
        for k, vid in enumerate(st["voices"]):
            c = cells.get(k, (0, 0, 0, 0, 0, 0, 0))
            vv = self.v[vid]
            vv.n = [c[0], c[1], c[2], c[3]]
            vv.inst, vv.cmd, vv.par = c[4], c[5], c[6]
        st["row"] += 1

    def stop(self):
        self.st["active"] = False
        for vid in self.st["voices"]:
            self.cc(vid + 1, 0x7B, 0)

    def advance_order(self):
        st = self.st
        st["cnt"] = 0
        st["brk"] = False
        st["row"] = 0
        st["rows"] = None
        st["order"] += 1
        if st["loop"] == 0 and not (st["start"] <= st["order"] < st["end"]):
            self.stop()
            return
        if st["order"] == st["end"]:
            st["wrapped"] = True
            if st["loop"] == 0:
                self.stop()
                return
            st["order"] = st["start"]

    def tick(self):
        st = self.st
        if not st["active"]:
            return
        st["cnt"] += 1
        if st["cnt"] < st["speed"]:
            for vid in st["voices"]:
                self.tick_fx(vid + 1, vid)
            if st["brk"]:
                self.advance_order()
        else:
            st["cnt"] = 0
            self.fetch()
            self.rows_played += 1
            for vid in st["voices"]:
                self.row_cell(vid)
            if st["row"] == 64 or st["brk"]:
                self.advance_order()


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def rld_events(snap, order, song, max_seconds=420, one_pass=True, t0=0):
    events = []
    seq = RldSeq(snap, order, song, lambda t, b: events.append((t, b)))
    t = 0
    while t < max_seconds * TICK_HZ and seq.st["active"] and not (one_pass and seq.st["wrapped"]):
        seq.t = t * 10 + t0
        seq.tick()
        t += 1
    if seq.st["active"]:
        seq.t = t * 10 + t0
        seq.stop()
    return events, t * 10 + t0


def render_rld_midi(snap, order, song, max_seconds=420, ppq=500, one_pass=True):
    events = [(0, m) for m in mt32_upload_events(snap)]
    ev, end = rld_events(snap, order, song, max_seconds, one_pass, t0=400)
    events += ev
    end += 500
    track = bytearray()
    track += _vlq(0) + b"\xFF\x51\x03" + (1000000).to_bytes(3, "big")
    last = 0
    for _, (tk, b) in sorted(enumerate(events), key=lambda x: (x[1][0], x[0])):
        track += _vlq(tk - last)
        last = tk
        if b[0] == 0xF0:
            track += b"\xF0" + _vlq(len(b) - 1) + b[1:]
        else:
            track += b
    track += _vlq(max(0, end - last)) + b"\xFF\x2F\x00"
    head = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq)
    return head + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


_KF = [-1, -0.5, -0.25, 0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1, 1.25, 1.5, 2, 1, 1]
MT32_RATE = 32000


def _tmap(t):
    return 0.0005 * 2.0 ** (t / 7.5)


def _step(timeline, ts, default):
    import numpy as np
    if not timeline:
        return np.full(len(ts), default, dtype=np.float64)
    tt = np.array([a for a, _ in timeline], dtype=np.float64)
    vv = np.array([b for _, b in timeline], dtype=np.float64)
    idx = np.searchsorted(tt, ts, side="right") - 1
    out = np.where(idx >= 0, vv[np.clip(idx, 0, len(vv) - 1)], default)
    return out


def _lowpass(x, fc, rate):
    import numpy as np
    a = np.exp(-2 * np.pi * min(fc, rate * 0.45) / rate)
    n = int(min(len(x), max(8, 6 / max(1e-6, 1 - a)), 6000))
    k = (1 - a) * a ** np.arange(n)
    N = 1
    while N < len(x) + n:
        N *= 2
    y = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(k, N), N)[:len(x)]
    return y


def _render_partial(p, note, t, off_t, envmode, bend_semis, rate):
    import numpy as np
    coarse, fine, kf = p[0], p[1], min(p[2], 16)
    wave, pw = p[4], p[6]
    semis = 60 + (note - 60) * _KF[kf] + (coarse - 24) + (fine - 50) / 100.0
    f = 440.0 * 2 ** ((semis + bend_semis - 69) / 12.0)
    ph = np.cumsum(f / rate)
    frac = ph % 1.0
    if wave & 1:
        w = 2 * frac - 1
    else:
        duty = 0.5 - 0.45 * (1 - min(pw, 100) / 100.0) * 0.9 if pw else 0.5
        w = np.where(frac < max(0.05, duty), 1.0, -1.0)
    if wave & 2:
        rng = np.random.default_rng(p[5])
        w = 0.7 * w + 0.3 * rng.uniform(-1, 1, len(w))
    tv = [_tmap(x) for x in p[0x31:0x36]]
    lv = [min(x, 100) / 100.0 for x in p[0x36:0x3A]]
    pts_t = [0.0]
    pts_v = [0.0]
    for i in range(4):
        pts_t.append(pts_t[-1] + tv[i])
        pts_v.append(lv[i] ** 1.5)
    sus_level = pts_v[-1]
    if envmode == 0:
        t_rel = max(off_t, pts_t[-1])
        pts_t += [t_rel, t_rel + tv[4]]
        pts_v += [sus_level, 0.0]
    else:
        pts_t.append(pts_t[-1] + tv[4])
        pts_v.append(0.0)
    env = np.interp(t, pts_t, pts_v, right=0.0)
    amp = (p[0x29] / 100.0)
    y = w * env * amp
    cutoff = p[0x17]
    fc = 120.0 * (150.0 ** (min(cutoff, 100) / 100.0))
    if fc < 15000:
        y = _lowpass(y, fc, rate)
    return y


def _render_events_pcm(snap, ev, end, rate=44100):
    pcm = _synth_events(snap, ev, end, MT32_RATE)
    return _resample_s16(pcm, MT32_RATE, rate), rate


def render_rld_pcm(snap, order, song, max_seconds=60, rate=MT32_RATE, progress=None):
    import numpy as np
    ev, end = rld_events(snap, order, song, max_seconds=max_seconds, one_pass=True, t0=0)
    return _synth_events(snap, ev, end, rate, progress)


def _synth_events(snap, ev, end, rate=MT32_RATE, progress=None):
    import numpy as np
    recs = {}
    r = 0
    for slot in range(64):
        if snap.defflag[slot] and r < len(snap.insts):
            recs[slot] = snap.insts[r]
            r += 1
    notes, active = [], {}
    bend = {c: [] for c in range(16)}
    vol = {c: [] for c in range(16)}
    prog = {c: [] for c in range(16)}
    for _, b in sorted(enumerate(ev), key=lambda x: (x[1][0], x[0])):
        t = b[0] / 500.0
        m = b[1]
        st, ch = m[0] & 0xF0, m[0] & 0x0F
        if m[0] == 0xF0:
            continue
        if st == 0x90:
            active.setdefault(ch, []).append([m[1], t])
        elif st == 0xB0 and m[1] == 0x7B:
            for n, t0 in active.pop(ch, []):
                notes.append((ch, n, t0, t))
        elif st == 0xB0 and m[1] == 7:
            vol[ch].append((t, m[2] / 127.0))
        elif st == 0xC0:
            prog[ch].append((t, m[1]))
        elif st == 0xE0:
            bend[ch].append((t, ((m[2] << 7) | m[1]) - 0x2000))
    tend = end / 500.0
    for ch, lst in active.items():
        for n, t0 in lst:
            notes.append((ch, n, t0, tend))
    total = int((tend + 3.0) * rate)
    mix = np.zeros(total)
    for i, (ch, n, t0, t1) in enumerate(notes):
        pg = _step(prog[ch], np.array([t0]), -1)[0]
        rec = recs.get(int(pg))
        if rec is None:
            continue
        common = rec[18:22]
        mask = common[2]
        envmode = common[3] & 1
        dur = max(0.02, t1 - t0)
        L = int((dur + 2.5) * rate)
        L = max(64, min(L, total - int(t0 * rate)))
        t = np.arange(L) / rate
        rng_ = rec[4] if rec[4] else 12
        bs = _step(bend[ch], t0 + t, 0.0) / 8192.0 * min(rng_, 24)
        out = np.zeros(L)
        for k in range(4):
            if (mask >> k) & 1:
                out += _render_partial(rec[22 + 58 * k:22 + 58 * (k + 1)], n, t, dur, envmode, bs, rate)
        g = _step(vol[ch], t0 + t, 100 / 127.0)
        a = int(t0 * rate)
        mix[a:a + L] += out * g * 0.18
        if progress and i % 20 == 0:
            progress(i / max(1, len(notes)))
    pk = np.abs(mix).max()
    if pk <= 0:
        return b""
    nz = np.nonzero(np.abs(mix) > pk * 0.01)[0]
    mix = mix[:min(len(mix), int(nz[-1]) + int(0.15 * rate))]
    mix *= 0.85 / pk
    return (mix * 32767).astype("<i2").tobytes()


import ctypes
import ctypes.util
import sys

_MT32 = {"dir": None, "lib": None}
_LIB_NAMES = ["mt32emu.dll", "libmt32emu.dll", "libmt32emu.so", "libmt32emu.so.2",
              "libmt32emu.dylib", "libmt32emu.2.dylib"]


class Mt32EmuError(Exception):
    pass


def set_mt32_paths(rom_dir=None, lib_path=None):
    if rom_dir is not None:
        _MT32["dir"] = rom_dir or None
    if lib_path is not None:
        _MT32["lib"] = lib_path or None


def _search_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    ds = []
    if _MT32["dir"]:
        ds.append(_MT32["dir"])
    for base in (here, os.path.dirname(here), os.getcwd()):
        for sub in ("mt32", "MT32", "roms", "rom", ""):
            ds.append(os.path.join(base, sub) if sub else base)
    env = os.environ.get("HQ_MT32_DIR")
    if env:
        ds.insert(0, env)
    seen, out = set(), []
    for d in ds:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def _find_lib():
    cands = []
    if _MT32["lib"]:
        cands.append(_MT32["lib"])
    if os.environ.get("HQ_MT32_LIB"):
        cands.append(os.environ["HQ_MT32_LIB"])
    for d in _search_dirs():
        for n in _LIB_NAMES:
            cands.append(os.path.join(d, n))
    for c in cands:
        if os.path.isfile(c):
            return c
    return ctypes.util.find_library("mt32emu")


def _rom_candidates():
    files = []
    for d in _search_dirs():
        try:
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                if os.path.isfile(p) and 32 * 1024 <= os.path.getsize(p) <= 2 * 1024 * 1024 \
                        and os.path.splitext(fn)[1].lower() in (".rom", ".bin", ".ic"):
                    files.append(p)
        except OSError:
            pass
    return files


class Mt32Emu:

    def __init__(self, lib_path):
        if sys.platform == "win32" and hasattr(os, "add_dll_directory") and os.path.isfile(lib_path):
            try:
                os.add_dll_directory(os.path.dirname(os.path.abspath(lib_path)))
            except OSError:
                pass
        try:
            L = self.L = ctypes.CDLL(lib_path)
        except OSError as e:
            raise Mt32EmuError(f"mt32emu library failed to load ({e}). On Windows it must have "
                               f"the same architecture as Python (64-bit).")
        vp, u32 = ctypes.c_void_p, ctypes.c_uint32
        L.mt32emu_create_context.restype = vp
        L.mt32emu_create_context.argtypes = [vp, vp]
        L.mt32emu_free_context.argtypes = [vp]
        L.mt32emu_add_rom_file.restype = ctypes.c_int
        L.mt32emu_add_rom_file.argtypes = [vp, ctypes.c_char_p]
        L.mt32emu_set_stereo_output_samplerate.argtypes = [vp, ctypes.c_double]
        L.mt32emu_open_synth.restype = ctypes.c_int
        L.mt32emu_open_synth.argtypes = [vp]
        L.mt32emu_close_synth.argtypes = [vp]
        L.mt32emu_get_actual_stereo_output_samplerate.restype = u32
        L.mt32emu_get_actual_stereo_output_samplerate.argtypes = [vp]
        L.mt32emu_play_msg.restype = ctypes.c_int
        L.mt32emu_play_msg.argtypes = [vp, u32]
        L.mt32emu_play_sysex.restype = ctypes.c_int
        L.mt32emu_play_sysex.argtypes = [vp, ctypes.c_char_p, u32]
        L.mt32emu_render_bit16s.argtypes = [vp, ctypes.POINTER(ctypes.c_int16), u32]
        try:
            L.mt32emu_get_library_version_string.restype = ctypes.c_char_p
            self.version = L.mt32emu_get_library_version_string().decode()
        except AttributeError:
            self.version = "?"
        self.lib_path = lib_path

    def session(self, rate=44100):
        return _Mt32Session(self, rate)


class _Mt32Session:
    def __init__(self, emu, rate):
        self.emu, self.L = emu, emu.L
        L = self.L
        self.ctx = L.mt32emu_create_context(None, None)
        if not self.ctx:
            raise Mt32EmuError("mt32emu_create_context failed")
        added = 0
        for p in _rom_candidates():
            rc = L.mt32emu_add_rom_file(self.ctx, p.encode(sys.getfilesystemencoding() or "utf-8"))
            if rc > 0:
                added += 1
        L.mt32emu_set_stereo_output_samplerate(self.ctx, float(rate))
        rc = L.mt32emu_open_synth(self.ctx)
        if rc != 0:
            L.mt32emu_free_context(self.ctx)
            self.ctx = None
            why = {-4: "ROMs missing or incomplete (requires CONTROL + PCM for the same device: "
                       "MT-32 or CM-32L)", -1: "Unrecognized ROMs", -2: "ROM file not found"}
            raise Mt32EmuError(why.get(rc, f"open_synth code {rc}") +
                               f" — Valid ROMs added: {added}, folders: {_search_dirs()[:3]}")
        self.rate = int(L.mt32emu_get_actual_stereo_output_samplerate(self.ctx)) or int(rate)
        self.chunks = []

    def close(self):
        if self.ctx:
            self.L.mt32emu_close_synth(self.ctx)
            self.L.mt32emu_free_context(self.ctx)
            self.ctx = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def render(self, frames, keep=True):
        import numpy as np
        while frames > 0:
            n = min(frames, 32768)
            buf = (ctypes.c_int16 * (2 * n))()
            self.L.mt32emu_render_bit16s(self.ctx, buf, n)
            if keep:
                self.chunks.append(np.frombuffer(buf, dtype="<i2").copy())
            frames -= n

    def send(self, b):
        for _ in range(8):
            if b[0] == 0xF0:
                rc = self.L.mt32emu_play_sysex(self.ctx, bytes(b), len(b))
            else:
                msg = b[0] | ((b[1] if len(b) > 1 else 0) << 8) | ((b[2] if len(b) > 2 else 0) << 16)
                rc = self.L.mt32emu_play_msg(self.ctx, msg)
            if rc != -6:
                return
            self.render(int(self.rate * 0.01), keep=self._started)
        return

    _started = False

    def pcm(self):
        import numpy as np
        if not self.chunks:
            return b""
        x = np.concatenate(self.chunks)
        return x.astype("<i2").tobytes()


_EMU_CACHE = {}


def get_mt32emu():
    lib = _find_lib()
    if not lib:
        raise Mt32EmuError("mt32emu library not found (mt32emu.dll / libmt32emu.so): "
                           "place it in the 'mt32' directory next to the editor")
    if lib not in _EMU_CACHE:
        _EMU_CACHE[lib] = Mt32Emu(lib)
    return _EMU_CACHE[lib]


def mt32_status():
    try:
        emu = get_mt32emu()
        with emu.session(44100):
            pass
        return "emu", f"mt32emu {emu.version}"
    except Mt32EmuError as e:
        return "lite", str(e)


def render_events_mt32emu(snap, ev, end_tick, rate=44100, tail=3.0):
    import numpy as np
    emu = get_mt32emu()
    with emu.session(rate) as s:
        for m in mt32_upload_events(snap):
            s.send(m)
            s.render(int(s.rate * 0.02), keep=False)
        s.render(int(s.rate * 0.1), keep=False)
        s._started = True
        cur = 0
        for _, (tk, b) in sorted(enumerate(ev), key=lambda x: (x[1][0], x[0])):
            tgt = int(round(tk * s.rate / 500.0))
            if tgt > cur:
                s.render(tgt - cur)
                cur = tgt
            s.send(b)
        tgt = int(round(end_tick * s.rate / 500.0)) + int(tail * s.rate)
        if tgt > cur:
            s.render(tgt - cur)
        pcm = s.pcm()
        sr = s.rate
    x = np.frombuffer(pcm, dtype="<i2")
    if not len(x):
        return b"", sr
    pk = np.abs(x).max()
    nz = np.nonzero(np.abs(x) > max(8, pk * 0.003))[0]
    if len(nz):
        x = x[:min(len(x), (int(nz[-1]) // 2 + int(0.2 * sr)) * 2)]
    return x.astype("<i2").tobytes(), sr
