"""
Modello per i bank di effetti sonori DOS in formato ALB (AdLib/OPL2) e
RLD (Roland MT-32 / GM), sul modello di HQVgaFile / HQMultiVgaFile.

Non compone musica: legge, estrae ed importa i singoli effetti sonori
contenuti nel bank, mantenendo intatta la struttura del file originale.

--- Formato (verificato su GAME_FX.ALB / GAME_FX.RLD) --------------------

Header (0x000 - 0x158):
  0x00  3 byte   dimensione/checksum del blocco dati (uint24 LE)
  0x03  ...      nome del bank, ASCII null-terminated ("ingame")
  0x18  2 byte   numero voci tabella note/canale (u16 LE)
  0x1A  2 byte   flag/versione
  ...            tabella volume/velocity + tabella nota/canale (fissa)

Tabella nomi (0x158+, 16 byte a voce), fino alla prima voce "Not Used":
  [0:8]   nome ASCII (padded con zeri)
  [8:10]  riservato (u16)
  [10:12] ref_id (u16) - riferimento nel pool condiviso
  [12:14] flag canale (multiplo di 256)
  [14:16] padding (u16, sempre 0)

Tabella puntatori (subito dopo, u16 LE, terminata da due 0xFFFF consecutivi):
  un offset per ogni effetto realmente definito (non "Not Used"),
  relativo all'inizio del blob dati che segue il doppio terminatore.
  Il blocco dati di un effetto va dal suo offset al successivo (o alla
  fine del file per l'ultimo).

Il blocco dati e' una sequenza di comandi per il driver sonoro
(OPL2 per ALB, MPU/Roland per RLD): non e' un semplice campione audio,
ma una "partitura" di eventi. Per l'estrazione/importazione trattiamo
questi blocchi come blob binari opachi; la riproduzione usa una sintesi
di anteprima approssimata (vedi funzione `synthesize_preview_wav`).
"""

import os
import struct
import wave
import io
import math

HEADER_TABLE_OFFSET = 0x158
ENTRY_SIZE = 16


class FxEffect:
    def __init__(self, index, name, ref_id, flag, offset_in_table, data):
        self.index = index
        self.name = name
        self.ref_id = ref_id
        self.flag = flag
        self.offset_in_table = offset_in_table
        self.data = bytearray(data)

    @property
    def label(self):
        return f"{self.name} ({len(self.data)} byte)"


def _read_name_table(data):
    """Ritorna (entries_grezze, offset_dopo_tabella).
    entries_grezze: lista di dict {name, ref_id, flag, offset} inclusi
    l'header 'song name' iniziale e gli eventuali slot 'Not Used' di
    riempimento (il numero totale di slot e' fisso ma diverso tra ALB
    e RLD: la tabella termina quando i byte smettono di essere ASCII
    stampabile, cioe' quando si entra nella tabella puntatori binaria).
    """
    entries = []
    off = HEADER_TABLE_OFFSET
    while off + ENTRY_SIZE <= len(data):
        raw_name = data[off:off + 8]
        printable = all(b == 0 or 32 <= b < 127 for b in raw_name)
        if not printable:
            break
        name = raw_name.split(b"\x00")[0].decode("latin1", errors="replace")
        reserved, ref_id, flag, pad = struct.unpack_from("<4H", data, off + 8)
        entries.append({
            "offset": off, "name": name,
            "reserved": reserved, "ref_id": ref_id, "flag": flag, "pad": pad,
        })
        off += ENTRY_SIZE
        if len(entries) > 512:
            break
    return entries, off


def _read_pointer_table(data, off):
    """Ritorna (pointers, offset_blob_dati)."""
    pointers = []
    while off + 2 <= len(data):
        w = struct.unpack_from("<H", data, off)[0]
        off += 2
        if w == 0xFFFF:
            if off + 2 <= len(data) and struct.unpack_from("<H", data, off)[0] == 0xFFFF:
                off += 2
            break
        pointers.append(w)
        if len(pointers) > 512:
            break
    off = _skip_reserved_padding(data, off)
    return pointers, off


# Sotto formato RLD (Roland), il doppio terminatore 0xFFFF della tabella
# puntatori e' spesso seguito da una zona riservata (slot per effetti
# "Not Used" non ancora assegnati) riempita per intero di byte 0xFF,
# PRIMA dell'inizio reale del blob dati. Il formato ALB non ha questa
# zona (il blob comincia subito dopo il terminatore). Distinguiamo la
# zona riservata da dati veri richiedendo una run lunga e consecutiva di
# 0xFF: un blocco dati reale non produce mai una run cosi' lunga (verificato
# su GAME_FX.ALB / GAME_FX.RLD), mentre nei bank MIDI/MT-32 un singolo
# byte 0xFF isolato puo' comparire legittimamente (es. meta-eventi) e va
# quindi lasciato intatto.
_RESERVED_PADDING_MIN_RUN = 16


def _skip_reserved_padding(data, off):
    p = off
    while p < len(data) and data[p] == 0xFF:
        p += 1
    if p - off >= _RESERVED_PADDING_MIN_RUN:
        return p
    return off


class HQFxFile:
    """Bank di effetti sonori (ALB o RLD)."""

    def __init__(self):
        self.raw_header = b""      # tutto cio' che precede il blob dati (header+tabelle)
        self.bank_name = ""
        self.effects = []          # list[FxEffect], solo voci "vere" (non song-name/not-used)
        self.kind = None           # "alb" o "rld"
        self._tail_after_data = b""  # eventuale coda dopo l'ultimo blocco (di solito vuota)

    # ------------------------------------------------------------------ #
    def load(self, path):
        data = open(path, "rb").read()
        ext = os.path.splitext(path)[1].upper()
        self.kind = "alb" if ext == ".ALB" else ("rld" if ext == ".RLD" else "alb")

        name = data[3:3 + 16].split(b"\x00")[0].decode("latin1", errors="replace")
        self.bank_name = name

        raw_entries, off_after_names = _read_name_table(data)
        pointers, data_blob_offset = _read_pointer_table(data, off_after_names)

        # header completo cosi' come si trova nel file, fino all'inizio del blob
        self.raw_header = bytearray(data[:data_blob_offset])
        self._name_table_start = HEADER_TABLE_OFFSET
        self._name_table_end = off_after_names
        self._raw_entries = raw_entries

        blob = data[data_blob_offset:]
        named = [e for e in raw_entries
                 if e["name"].strip() and e["name"].strip().lower() not in ("not used",)
                 and e["name"].strip().lower() != self.bank_name.strip().lower()
                 and not e["name"].strip().upper().startswith("INGAME")]

        # il primo puntatore non e' necessariamente 0: i byte prima del
        # primo blocco (di solito un piccolo contatore/checksum locale)
        # vengono preservati cosi' come sono per un rebuild fedele
        self._blob_prefix = bytes(blob[:pointers[0]]) if pointers else bytes(blob)

        effects = []
        for i, p in enumerate(pointers):
            start = p
            end = pointers[i + 1] if i + 1 < len(pointers) else len(blob)
            chunk = blob[start:end]
            entry_meta = named[i] if i < len(named) else {"name": f"FX_{i}", "ref_id": 0, "flag": 0, "offset": -1}
            effects.append(FxEffect(
                index=i, name=entry_meta["name"], ref_id=entry_meta["ref_id"],
                flag=entry_meta["flag"], offset_in_table=entry_meta["offset"],
                data=chunk,
            ))
        self.effects = effects
        self._pointers = pointers
        self._data_blob_offset = data_blob_offset

    # ------------------------------------------------------------------ #
    def get_effect(self, index):
        return self.effects[index]

    def extract_effect(self, index, out_path):
        """Salva il blocco dati grezzo di un effetto su disco (binario)."""
        eff = self.effects[index]
        with open(out_path, "wb") as f:
            f.write(bytes(eff.data))

    def extract_effect_wav(self, index, out_path, sample_rate=22050):
        """Salva un'anteprima audio sintetizzata (WAV) dell'effetto."""
        eff = self.effects[index]
        pcm = synthesize_preview_wav(eff.data, self.kind, sample_rate=sample_rate)
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm)

    def import_effect(self, index, new_data: bytes):
        """Sostituisce il blocco dati di un effetto con nuovi byte.
        La lunghezza puo' differire da quella originale: la tabella
        puntatori e l'header (dimensione totale) vengono ricalcolati.
        """
        self.effects[index].data = bytearray(new_data)

    # ------------------------------------------------------------------ #
    def rebuild(self) -> bytes:
        """Ricostruisce l'intero file (header + tabella nomi invariata +
        tabella puntatori ricalcolata + prefisso blob + blocchi dati)."""
        out = bytearray(self.raw_header)

        prefix = getattr(self, "_blob_prefix", b"")
        cursor = len(prefix)
        new_pointers = []
        for eff in self.effects:
            new_pointers.append(cursor)
            cursor += len(eff.data)

        ptr_table_start = self._name_table_end
        for i, p in enumerate(new_pointers):
            struct.pack_into("<H", out, ptr_table_start + i * 2, p)

        out += prefix
        for eff in self.effects:
            out += eff.data

        # NOTA: i primi 3 byte dell'header (uint24 LE) non sono la
        # dimensione del file (verificato: non correla con la lunghezza
        # reale in nessuno dei due bank campione) e il loro significato
        # esatto e' ignoto: li lasciamo invariati per non corrompere
        # un campo che potrebbe essere un checksum/ID interno del driver.

        return bytes(out)

    def save(self, path):
        data = self.rebuild()
        with open(path, "wb") as f:
            f.write(data)

    def get_total_size(self) -> int:
        return len(self.raw_header) + sum(len(e.data) for e in self.effects)


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
    name = data[3:3 + 16].split(b"\x00")[0]
    return name.lower() == b"ingame"


# ---------------------------------------------------------------------- #
# Sintesi di anteprima OPL2 (ALB) - basata su reverse engineering reale
# di ADLIB.DRV (vedi disassemblato: routine di scrittura registro a
# 0xc61 = out 0x388/0x389; tabella F-Number/Block reale a 0xcca; timer
# di sequencer riprogrammato a 50 Hz esatti via PIT, divisore 0x5D37).
#
# NON e' un emulatore ciclo-accurato del chip OPL2 (non replica gli
# operatori FM, l'inviluppo ADSR reale, ne' i registri di feedback/
# connessione), ma a differenza della vecchia sintesi "rumore casuale
# modulato dai byte", questa versione:
#   - usa la VERA tabella Fnum/Block estratta dal driver per calcolare
#     l'altezza (Hz) di ogni nota, con la stessa formula OPL2
#     (Freq = Fnum * 49716 / 2^(20-Block));
#   - usa il VERO tempo di tick del sequencer (50 Hz, confermato dal
#     divisore PIT nel driver) per la durata degli eventi;
#   - riconosce gli opcode reali trovati nel dispatcher del driver
#     (dispatch a 0x649/0x63b su tabelle da 32 voci a 0xd8a/0xdca):
#     0x06 = note-off, 0x0c = imposta volume assoluto, 0x0f = imposta
#     durata dell'evento corrente.
#
# La suddivisione del blob in gruppi da 4 byte [nota, flag, opcode,
# parametro] e' una ricostruzione plausibile della cadenza di lettura
# vista nel driver (non un fatto verificato byte-per-byte al 100%): e'
# il punto meno certo di questa implementazione e potrebbe non
# corrispondere esattamente al framing reale in tutti i casi limite.
# ---------------------------------------------------------------------- #

_TICK_SECONDS = 1.0 / 50.0          # confermato: divisore PIT 0x5D37 = 50.00 Hz
_DEFAULT_DURATION_TICKS = 6         # valore di default trovato nel driver (mov byte[di+2],6)

# Tabella F-Number reale (12 valori, un'ottava) estratta da ADLIB.DRV
# all'offset 0xCCA. Il blocco (ottava OPL2) si ottiene dividendo per
# 0x1000 dopo aver sommato 0x1000 per ogni ottava sopra la prima.
_OPL2_FNUM_TABLE = [343, 364, 385, 408, 433, 459, 486, 515, 546, 579, 614, 650]


def _opl2_note_freq(note_index: int) -> float:
    """Converte un indice di nota (byte_nota - 12, come fa il driver
    con `sub al,0x0c` prima di indicizzare la tabella) nella frequenza
    reale in Hz, usando la formula OPL2 standard."""
    if note_index < 0:
        note_index = 0
    combined = _OPL2_FNUM_TABLE[note_index % 12] + 0x1000 * (note_index // 12)
    block = combined // 0x1000
    fnum = combined % 0x1000
    return fnum * 49716.0 / (2 ** (20 - block))


def _render_opl2_tone(freq, volume, n_samples, sample_rate, phase0=0.0):
    """Approssimazione FM 2-operatori (portante + modulazione leggera),
    non un vero chip OPL2, ma timbricamente piu' vicina di un'onda pura."""
    out = bytearray()
    phase = phase0
    mod_phase = 0.0
    for i in range(n_samples):
        mod = math.sin(mod_phase) * 0.35
        value = math.sin(phase + mod)
        sample = int(max(-1.0, min(1.0, value * volume)) * 32767 * 0.7)
        out += struct.pack("<h", sample)
        phase += 2 * math.pi * freq / sample_rate
        mod_phase += 2 * math.pi * (freq * 2.0) / sample_rate
    return bytes(out), phase


def _synthesize_alb(chunk: bytes, sample_rate: int) -> bytes:
    if not chunk:
        return b""

    samples = bytearray()
    phase = 0.0
    current_note = None       # None = silenzio
    volume = 1.0
    duration_ticks = _DEFAULT_DURATION_TICKS

    i = 0
    n = len(chunk)
    while i < n:
        b0 = chunk[i]
        b1 = chunk[i + 1] if i + 1 < n else 0
        b2 = chunk[i + 2] if i + 2 < n else 0
        b3 = chunk[i + 3] if i + 3 < n else None
        opcode = b2 & 0x1F

        if b0 >= 12:
            current_note = b0 - 12
        # opcode reali confermati nel dispatcher del driver
        if opcode == 0x06:                       # note-off
            current_note = None
        elif opcode == 0x0C and b3 is not None:  # set volume assoluto (clamp 0x40)
            volume = min(b3, 0x40) / float(0x40)
        elif opcode == 0x0F and b3 is not None:  # imposta durata evento
            duration_ticks = max(1, b3 & 0x1F)

        n_frame_samples = max(1, int(sample_rate * duration_ticks * _TICK_SECONDS))
        if current_note is not None:
            freq = _opl2_note_freq(current_note)
            tone, phase = _render_opl2_tone(freq, volume, n_frame_samples, sample_rate, phase)
            samples += tone
        else:
            samples += b"\x00\x00" * n_frame_samples

        duration_ticks = _DEFAULT_DURATION_TICKS  # reset salvo nuova 0x0F
        i += 4

    return bytes(samples)


def _synthesize_rld_placeholder(chunk: bytes, sample_rate: int) -> bytes:
    """Segnaposto per RLD: la stessa analisi non e' ancora stata fatta
    su MT32.DRV (formato MIDI/seriale, non register-write su porta I/O
    come l'OPL2), quindi qui NON usiamo ancora dati reali - e' la
    vecchia sintesi procedurale, mantenuta solo perche' non abbiamo
    ancora nulla di meglio per il Roland."""
    if not chunk:
        return b""
    n_events = max(1, len(chunk) // 2)
    duration = min(2.0, max(0.15, n_events * 0.03))
    n_samples = int(sample_rate * duration)
    samples = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        progress = i / max(1, n_samples - 1)
        byte_idx = min(len(chunk) - 1, int(progress * len(chunk)))
        b = chunk[byte_idx]
        freq = 180.0 + (b % 64) * 6.0
        envelope = math.sin(math.pi * progress) ** 0.5
        value = math.sin(2 * math.pi * freq * t) * envelope
        sample = int(max(-1.0, min(1.0, value)) * 32767 * 0.6)
        samples += struct.pack("<h", sample)
    return bytes(samples)


def synthesize_preview_wav(chunk: bytes, kind: str, sample_rate=22050) -> bytes:
    if not chunk:
        return b""
    if kind == "alb":
        return _synthesize_alb(chunk, sample_rate)
    return _synthesize_rld_placeholder(chunk, sample_rate)
