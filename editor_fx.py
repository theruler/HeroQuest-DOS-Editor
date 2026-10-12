"""
Sound bank editor mixin for ALB/RLD (HQFxFile).

Bank contents (see hq_fx.py):
  ♫ song     -> list of ORDERS -> each order points to a PATTERN
  ▦ pattern  -> 64 rows of cells [note, instrument, command, parameter]
  ♪ instrument-> 2-operator FM patch (ALB) or MT-32 timbre (RLD)
A "sound effect" is a song consisting of only 1 pattern. The listbox items
are therefore songs, patterns, and instruments; the panel below shows how they
are linked.

Play: all internal, no external player or Munt required.
 ALB -> OPL2 emulation (pyopl if installed, otherwise numpy fallback).
 RLD -> 'MT-32 lite' synthesizer in numpy using real timbre parameters
 (without PCM ROM: approximation). For exact MT-32: ⇩ MIDI.
"""

import os
import platform
import subprocess
import tempfile
import json
import queue
import threading
import wave

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from config import PAL
from models import HQFxFile, _is_fx_file
from models import hq_fx

_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fx_mt32_path.json")


def _load_mt32_cfg():
    try:
        with open(_CFG, "r", encoding="utf-8") as f:
            c = json.load(f)
        hq_fx.set_mt32_paths(c.get("dir") or None, c.get("lib") or None)
    except (OSError, ValueError):
        pass


def _save_mt32_cfg():
    try:
        with open(_CFG, "w", encoding="utf-8") as f:
            json.dump({"dir": hq_fx._MT32["dir"], "lib": hq_fx._MT32["lib"]}, f)
    except OSError:
        pass


FX_FILE_TYPES = [
    ("Sound bank", "*.alb;*.rld"),
    ("AdLib bank", "*.alb"),
    ("Roland bank", "*.rld"),
    ("All files", "*.*"),
]

_PARAM_LABELS = {"ksl": "KSL", "mult": "MULT", "fb": "FB", "attack": "ATK", "sustain": "SUS",
                 "eg": "EG", "decay": "DEC", "release": "REL", "level": "LVL",
                 "am": "AM", "vib": "VIB", "ksr": "KSR", "conn": "CON"}
_PARAM_HELP = ("ATK/DEC/REL: 0=slow..15=fast   SUS: 0=loud..15=soft   LVL: 63=maximum   "
               "MULT: frequency multiplier   FB: feedback (modulator only)   "
               "EG=1: sustained note until key-off   CON and carrier FB are ignored by the driver")

class _Player:
    def __init__(self):
        self.proc = None
        self.token = 0

    def stop(self):
        self.token += 1
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def play_wav(self, path):
        system = platform.system()
        if system == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif system == "Darwin":
            self.proc = subprocess.Popen(["afplay", path])
        else:
            for player in (["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
                try:
                    self.proc = subprocess.Popen(player + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
            raise RuntimeError("No audio player found (paplay/aplay/ffplay).")

    def open_file(self, path):
        system = platform.system()
        if system == "Windows":
            os.startfile(path)
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


_PLAYER = _Player()


def _read_wav_float(path):
    import numpy as np
    with wave.open(path, "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    elif sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float64) / (1 << 23)
    elif sw == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / (1 << 31)
    else:
        raise ValueError("Unsupported WAV (use 8/16/24/32-bit PCM)")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


class FxEditorMixin:

    def _load_fx(self, path, basename):
        _load_mt32_cfg()
        self.hq_fx.load(path)
        h = self.hq_fx
        return (f"fx | {h.kind.upper()} bank \"{h.bank_name}\" | {len(h.songs)} songs, "
                f"{len(h.patterns)} patterns, {len(h.insts)} instruments")

    def fx_list_items(self):
        return [eff.label for eff in self.hq_fx.effects]

    def _on_select_fx(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END)
            return
        self._fx_selected_idx = idx
        self._base_edit_frame.pack_forget()
        self._quest_map_panel.pack_forget()
        self._vga_panel.pack_forget()
        if not getattr(self, "_fx_panel_built", False):
            self._build_fx_panel()
            self._fx_panel_built = True
        self._fx_panel.pack(fill=tk.X)
        self._fx_build_detail()
        self._render_fx()
        self._update_status()

    def _fx_current_effect(self):
        idx = getattr(self, "_fx_selected_idx", None)
        if idx is None or not (0 <= idx < len(self.hq_fx.effects)):
            return None
        return self.hq_fx.effects[idx]

    def _build_fx_panel(self):
        self._fx_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"], pady=6, padx=10)
        btn = dict(font=("Consolas", 9), bg=PAL["btn"], fg=PAL["text"], relief=tk.RAISED, cursor="hand2")
        bar = tk.Frame(self._fx_panel, bg=PAL["toolbar"])
        bar.pack(fill=tk.X)
        items = [("▶ Play", self._fx_play), ("■ Stop", _PLAYER.stop),
                 ("⇩ WAV", self._fx_extract_wav), ("⇩ MIDI", self._fx_export_midi),
                 ("⇧ WAV → instrument", self._fx_import_wav_inst),
                 ("＋ Effect from WAV", self._fx_new_from_wav),
                 ("＋ Instrument", self._fx_new_inst),
                 ("bin ⇩", self._fx_extract_bin), ("bin ⇧", self._fx_import),
                 ("MT-32 ROM…", self._fx_choose_mt32)]
        for i, (t, cmd) in enumerate(items):
            tk.Button(bar, text=t, command=cmd, **btn).pack(side=tk.LEFT, padx=3)
        self._fx_impact = tk.Label(self._fx_panel, text="", font=("Consolas", 8), fg=PAL["box_txt"], bg=PAL["toolbar"], justify=tk.LEFT, anchor="w", wraplength=1000)
        self._fx_impact.pack(fill=tk.X, pady=(6, 0))
        self._fx_detail = tk.Frame(self._fx_panel, bg=PAL["toolbar"])
        self._fx_detail.pack(fill=tk.X, pady=(6, 0))
        self._fx_info_label = tk.Label(self._fx_panel, text="", font=("Consolas", 8), fg=PAL["label"], bg=PAL["toolbar"], justify=tk.LEFT, anchor="w")
        self._fx_info_label.pack(fill=tk.X, pady=(6, 0))
        self._fx_wave = None
        self._fx_loading = False
        self._fx_after = None
        self._fx_last_undo = 0
        self._fx_queue = queue.Queue()
        self._fx_poll()

    def _fx_ui(self, fn):
        self._fx_queue.put(fn)

    def _fx_poll(self):
        try:
            while True:
                self._fx_queue.get_nowait()()
        except queue.Empty:
            pass
        except Exception as ex:
            print("fx ui error:", ex)
        try:
            self.canvas.after(60, self._fx_poll)
        except tk.TclError:
            pass

    def _fx_set_info(self, text):
        try:
            self._fx_info_label.config(text=text)
        except tk.TclError:
            pass

    def _fx_build_detail(self):
        for w in self._fx_detail.winfo_children():
            w.destroy()
        eff = self._fx_current_effect()
        if eff is None:
            return
        h = self.hq_fx
        lab = dict(font=("Consolas", 8), fg=PAL["label"], bg=PAL["toolbar"])
        self._fx_loading = True
        if eff.kind == "inst" and h.kind == "alb":
            k = eff.ref_id - 1
            p = h.inst_params(k)
            top = tk.Frame(self._fx_detail, bg=PAL["toolbar"])
            top.pack(fill=tk.X)
            tk.Label(top, text="name", **lab).pack(side=tk.LEFT)
            self._fx_vars = {}
            v = tk.StringVar(value=p["name"])
            self._fx_vars[("name", "")] = v
            e = tk.Entry(top, textvariable=v, width=11, font=("Consolas", 9))
            e.pack(side=tk.LEFT, padx=(4, 12))
            e.bind("<Return>", lambda ev: self._fx_param_changed())
            e.bind("<FocusOut>", lambda ev: self._fx_param_changed(play=False))
            self._fx_spin(top, ("vol", ""), "vol", p["vol"], 0, 64, lab)
            self._fx_spin(top, ("wave_mod", ""), "wave M", p["wave_mod"], 0, 3, lab)
            self._fx_spin(top, ("wave_car", ""), "wave C", p["wave_car"], 0, 3, lab)
            self._fx_note_var = tk.IntVar(value=60)
            tk.Label(top, text="test note", **lab).pack(side=tk.LEFT, padx=(12, 2))
            tk.Spinbox(top, from_=24, to=96, width=4, textvariable=self._fx_note_var, font=("Consolas", 9)).pack(side=tk.LEFT)
            grid = tk.Frame(self._fx_detail, bg=PAL["toolbar"])
            grid.pack(fill=tk.X, pady=(6, 0))
            for c, (n, lo, hi) in enumerate(hq_fx.OPL_PARAMS):
                tk.Label(grid, text=_PARAM_LABELS[n], **lab).grid(row=0, column=c + 1)
            for r, (op, title) in enumerate((("mod", "MODULATOR"), ("car", "CARRIER"))):
                tk.Label(grid, text=title, **lab).grid(row=r + 1, column=0, sticky="e", padx=(0, 4))
                for c, (n, lo, hi) in enumerate(hq_fx.OPL_PARAMS):
                    var = tk.IntVar(value=p[op][n])
                    self._fx_vars[(op, n)] = var
                    sb = tk.Spinbox(grid, from_=lo, to=hi, width=3, textvariable=var, font=("Consolas", 9), command=self._fx_param_changed)
                    sb.grid(row=r + 1, column=c + 1, padx=1, pady=1)
                    sb.bind("<Return>", lambda ev: self._fx_param_changed())
            tk.Label(self._fx_detail, text=_PARAM_HELP, wraplength=980, justify=tk.LEFT, **lab).pack(fill=tk.X, pady=(4, 0))
        elif eff.kind == "pattern":
            tk.Label(self._fx_detail, justify=tk.LEFT, anchor="w", wraplength=980,
                     text="One line per pattern row:  RR  [column] NOTE iINS CPP  — e.g.  00  [0] C-4 i01 C30   "
                          "(C=command: 0 none, 1/2 slide, 3 portamento, 6 key-off, A vol-slide, B jump order, "
                          "C volume, D end, F speed;  PP=hex parameter).  "
                          + ("Columns 0-5 voices, 6-10 BD/SD/TOM/CYM/HH." if h.kind == "alb"
                             else "Multiple notes in a cell = chord."), **lab).pack(fill=tk.X)
            fr = tk.Frame(self._fx_detail, bg=PAL["toolbar"])
            fr.pack(fill=tk.X)
            self._fx_text = tk.Text(fr, height=9, font=("Consolas", 9), wrap="none")
            sc = tk.Scrollbar(fr, command=self._fx_text.yview)
            self._fx_text.config(yscrollcommand=sc.set)
            self._fx_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            sc.pack(side=tk.LEFT, fill=tk.Y)
            self._fx_text.insert("1.0", h.pattern_text(eff.ref_id))
            tk.Button(self._fx_detail, text="✔ Apply text to pattern", command=self._fx_apply_text, font=("Consolas", 9), bg=PAL["btn"], fg=PAL["text"]).pack(anchor="w", pady=(4, 0))
        elif eff.kind == "song":
            s = eff.extra["song"]
            row = tk.Frame(self._fx_detail, bg=PAL["toolbar"])
            row.pack(fill=tk.X)
            self._fx_vars = {}
            v = tk.StringVar(value=s.name)
            self._fx_vars[("sname", "")] = v
            tk.Label(row, text="name", **lab).pack(side=tk.LEFT)
            tk.Entry(row, textvariable=v, width=11, font=("Consolas", 9)).pack(side=tk.LEFT, padx=(4, 10))
            for key, txt, val, hi in (("start", "start order", s.start, 127), ("end", "end order", s.end, 127), ("loop", "loop", s.loop, 1), ("nv", "voices", s.nvoices, 8)):
                self._fx_spin(row, ("song", key), txt, val, 0, hi, lab, cmd=self._fx_song_changed)
            tk.Button(row, text="✔ Apply", command=self._fx_song_changed, font=("Consolas", 9), bg=PAL["btn"], fg=PAL["text"]).pack(side=tk.LEFT, padx=10)
        else:
            tk.Label(self._fx_detail, justify=tk.LEFT, anchor="w", wraplength=980, **lab,
                     text="MT-32 Timbre: patch[8] + name[10] + common[4] + 4 partials of 58 bytes each. "
                          "Play = internal approximate preview (no PCM ROM); "
                          "to modify it use an MT-32 timbre editor and import the .bin.").pack(fill=tk.X)
        self._fx_loading = False
        self._fx_impact.config(text=self.hq_fx.impact_text(eff.index))
        self._fx_set_info(self.hq_fx.links(eff.index))

    def _fx_choose_mt32(self):
        d = filedialog.askdirectory(title="Folder with MT-32 ROMs (and mt32emu.dll if needed)")
        if not d:
            return
        lib = None
        for n in hq_fx._LIB_NAMES:
            if os.path.isfile(os.path.join(d, n)):
                lib = os.path.join(d, n)
                break
        hq_fx.set_mt32_paths(d, lib)
        _save_mt32_cfg()
        kind, why = hq_fx.mt32_status()
        if kind == "emu":
            messagebox.showinfo("MT-32", f"Real emulator active ({why}).\nRLD bank Playback will be faithful.")
        else:
            messagebox.showwarning("MT-32", "Real emulator NOT available, using 'lite' synthesizer.\n\n" + why)

    def _fx_spin(self, parent, key, text, val, lo, hi, lab, cmd=None):
        tk.Label(parent, text=text, **lab).pack(side=tk.LEFT, padx=(8, 2))
        var = tk.IntVar(value=val)
        self._fx_vars[key] = var
        sb = tk.Spinbox(parent, from_=lo, to=hi, width=4, textvariable=var, font=("Consolas", 9), command=cmd or self._fx_param_changed)
        sb.pack(side=tk.LEFT)
        sb.bind("<Return>", lambda ev: (cmd or self._fx_param_changed)())

    def _fx_undo_burst(self):
        import time
        now = time.time()
        if now - self._fx_last_undo > 1.5:
            self._push_undo()
        self._fx_last_undo = now

    def _fx_param_changed(self, play=True):
        if self._fx_loading:
            return
        eff = self._fx_current_effect()
        if eff is None or eff.kind != "inst":
            return
        k = eff.ref_id - 1
        self._fx_undo_burst()
        h = self.hq_fx
        try:
            for (op, n), var in self._fx_vars.items():
                val = var.get()
                if op == "name":
                    h.set_inst_param(k, "name", None, val)
                elif op in ("vol", "wave_mod", "wave_car"):
                    h.set_inst_param(k, op, None, val)
                else:
                    h.set_inst_param(k, op, n, val)
        except (tk.TclError, ValueError):
            return
        try:
            self.listbox.delete(eff.index)
            self.listbox.insert(eff.index, eff.label)
            self.listbox.selection_set(eff.index)
        except tk.TclError:
            pass
        self._render_fx()
        if play:
            if self._fx_after:
                self.canvas.after_cancel(self._fx_after)
            self._fx_after = self.canvas.after(250, self._fx_play)

    def _fx_song_changed(self):
        eff = self._fx_current_effect()
        if eff is None or eff.kind != "song":
            return
        try:
            s = eff.extra["song"]
            self._push_undo()
            s.name = self._fx_vars[("sname", "")].get()[:10]
            s.start = self._fx_vars[("song", "start")].get()
            s.end = self._fx_vars[("song", "end")].get()
            s.loop = self._fx_vars[("song", "loop")].get()
            s.nvoices = self._fx_vars[("song", "nv")].get()
        except (tk.TclError, ValueError):
            return
        eff.data = bytearray(s.pack())
        eff.name = s.name
        self._repopulate_keep(eff.index)

    def _fx_apply_text(self):
        eff = self._fx_current_effect()
        if eff is None or eff.kind != "pattern":
            return
        text = self._fx_text.get("1.0", tk.END)
        try:
            test = hq_fx.encode_pattern_text(text, self.hq_fx.kind, self.hq_fx.ncols)
        except ValueError as e:
            messagebox.showerror("Invalid Pattern", str(e))
            return
        self._push_undo()
        self.hq_fx.set_pattern_text(eff.ref_id, text)
        self._repopulate_keep(eff.index)
        messagebox.showinfo("Pattern", f"Pattern {eff.ref_id:02d} updated ({len(test)} bytes).")

    def _repopulate_keep(self, idx):
        self._populate_list()
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self._fx_selected_idx = idx
        self._fx_build_detail()
        self._render_fx()
        self._update_status()

    def _fx_play(self):
        self._fx_after = None
        eff = self._fx_current_effect()
        if eff is None:
            return
        h = self.hq_fx
        _PLAYER.stop()
        tok = _PLAYER.token
        idx = eff.index
        self._fx_set_info("⏳ rendering...")

        def work():
            try:
                if eff.kind == "inst":
                    note = self._fx_note
                    pcm, rate = h.render_inst_note(eff.ref_id - 1, note, 1.6, 44100)
                else:
                    pcm, rate = h.render_effect_pcm(idx, rate=44100, max_seconds=60)
                if tok != _PLAYER.token or not pcm:
                    self._fx_ui(lambda: self._fx_set_info(self.hq_fx.links(idx)))
                    return
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                chans = h.last_channels
                with wave.open(tmp.name, "wb") as w:
                    w.setnchannels(chans)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(pcm)
                _PLAYER.play_wav(tmp.name)
                engine = h.last_engine
                why = h.last_fallback_reason if "lite" in engine else ""

                def ui():
                    import numpy as np
                    x = np.frombuffer(pcm, "<i2")
                    self._fx_wave = x.reshape(-1, chans)[:, 0].astype("<i2").tobytes() if chans > 1 else pcm
                    self._render_fx()
                    self._fx_set_info(f"▶ {engine}" + (f"  —  {why[:160]}" if why else "") + "\n" + self.hq_fx.links(idx))
                self._fx_ui(ui)
            except Exception as ex:
                msg = str(ex)
                self._fx_ui(lambda: messagebox.showerror("Playback error", msg))

        try:
            self._fx_note = self._fx_note_var.get() if hasattr(self, "_fx_note_var") else 60
        except tk.TclError:
            self._fx_note = 60
        threading.Thread(target=work, daemon=True).start()

    def _render_fx(self):
        c = self.canvas
        c.delete("all")
        eff = self._fx_current_effect()
        if eff is None:
            return
        h = self.hq_fx
        c.create_text(10, 10, anchor="nw", fill=PAL["box_txt"], font=("Consolas", 13, "bold"), text=eff.name)
        kinds = {"song": "song", "pattern": "pattern", "inst": "instrument"}
        c.create_text(10, 34, anchor="nw", fill=PAL["label"], font=("Consolas", 9), text=f"bank {h.kind.upper()}   {kinds[eff.kind]}   {len(eff.data)} bytes")
        W = max(400, int(c.winfo_width() or 900)) - 20
        if eff.kind == "pattern":
            self._fx_draw_roll(c, eff.ref_id, 10, 60, W, 180)
        elif eff.kind == "song":
            self._fx_draw_song(c, eff.extra["song"], 10, 60, W)
        elif eff.kind == "inst" and h.kind == "alb":
            try:
                pcm, rate = h.render_inst_note(eff.ref_id - 1, 60, 1.2, 11025)
                self._fx_draw_wave(c, pcm, 10, 60, W, 160)
            except Exception:
                pass
        if self._fx_wave is not None and eff.kind != "inst":
            self._fx_draw_wave(c, self._fx_wave, 10, 260, W, 80)

    def _fx_draw_wave(self, c, pcm, x0, y0, w, hgt):
        import numpy as np
        x = np.frombuffer(pcm, "<i2").astype(float)
        if not len(x):
            return
        mid = y0 + hgt // 2
        c.create_rectangle(x0, y0, x0 + w, y0 + hgt, outline=PAL["label"])
        n = min(w, len(x))
        seg = len(x) / n
        for i in range(n):
            a = x[int(i * seg):int((i + 1) * seg) + 1]
            hi = a.max() / 32768 * (hgt / 2)
            lo = a.min() / 32768 * (hgt / 2)
            c.create_line(x0 + i, mid - hi, x0 + i, mid - lo - 1, fill=PAL["accent"])

    def _fx_draw_roll(self, c, k, x0, y0, w, hgt):
        h = self.hq_fx
        rows = h.decode_pattern(k)
        notes = [n for r in rows for cell in r for n in cell[1:5] if n]
        if not notes:
            c.create_text(x0, y0, anchor="nw", fill=PAL["label"], text="(pattern without notes)")
            return
        lo, hi = min(notes) - 1, max(notes) + 1
        cw = w / 64.0
        ch = hgt / max(1, hi - lo + 1)
        colors = ["#ff8f3d", "#4fc3f7", "#9ccc65", "#f06292", "#ffd54f", "#ba68c8", "#e57373", "#4db6ac", "#a1887f", "#90a4ae", "#fff176", "#80cbc4"]
        c.create_rectangle(x0, y0, x0 + w, y0 + hgt, outline=PAL["label"])
        for ri, r in enumerate(rows):
            for cell in r:
                for n in cell[1:5]:
                    if n:
                        y = y0 + (hi - n) * ch
                        c.create_rectangle(x0 + ri * cw, y, x0 + (ri + 1) * cw - 1, y + max(2, ch - 1), fill=colors[cell[0] % len(colors)], outline="")
        c.create_text(x0, y0 + hgt + 4, anchor="nw", fill=PAL["label"], font=("Consolas", 8),
                      text=f"64 rows  |  notes {hq_fx.note_name(lo + 1)}..{hq_fx.note_name(hi - 1)}")

    def _fx_draw_song(self, c, s, x0, y0, w):
        h = self.hq_fx
        n = max(1, s.end - s.start + 1)
        bw = min(60, (w - 10) / n)
        for i, o in enumerate(range(s.start, s.end + 1)):
            p = h.order[o]
            x = x0 + i * bw
            c.create_rectangle(x, y0, x + bw - 2, y0 + 44, fill=PAL["btn"], outline=PAL["label"])
            c.create_text(x + 4, y0 + 4, anchor="nw", fill=PAL["box_txt"], font=("Consolas", 8), text=f"o{o}")
            c.create_text(x + 4, y0 + 22, anchor="nw", fill=PAL["accent"], font=("Consolas", 9, "bold"), text=f"P{p:02d}")
        c.create_text(x0, y0 + 56, anchor="nw", fill=PAL["label"], font=("Consolas", 9), text="order (o) -> pattern (P); select a pattern in the list to view its notes")

    def _fx_extract_wav(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        path = filedialog.asksaveasfilename(initialfile=f"{eff.name.strip('♫▦♪ ')}.wav", defaultextension=".wav", filetypes=[("WAV", "*.wav")])
        if not path:
            return
        try:
            if eff.kind == "inst":
                pcm, rate = self.hq_fx.render_inst_note(eff.ref_id - 1, 60, 1.6, 44100)
                with wave.open(path, "wb") as w:
                    w.setnchannels(self.hq_fx.last_channels); w.setsampwidth(2)
                    w.setframerate(rate); w.writeframes(pcm)
            else:
                self.hq_fx.extract_effect_wav(eff.index, path)
        except Exception as e:
            messagebox.showerror("Export", str(e))
            return
        messagebox.showinfo("WAV", f"Saved {os.path.basename(path)}")

    def _fx_export_midi(self):
        if self.hq_fx.kind != "rld":
            messagebox.showinfo("MIDI", "MT-32 MIDI export (with timbre SysEx) is for RLD banks.")
            return
        eff = self._fx_current_effect()
        name = eff.extra["song"].name if eff and eff.kind == "song" else None
        path = filedialog.asksaveasfilename(initialfile=f"{name or 'bank'}.mid", defaultextension=".mid", filetypes=[("MIDI", "*.mid")])
        if path:
            self.hq_fx.export_midi(path, name)
            messagebox.showinfo("MIDI", f"Saved {os.path.basename(path)}")

    def _fx_extract_bin(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        path = filedialog.asksaveasfilename(initialfile=f"{eff.name.strip('♫▦♪ ')}.bin", defaultextension=".bin", filetypes=[("Bin", "*.bin")])
        if path:
            with open(path, "wb") as f:
                f.write(bytes(eff.data))

    def _fx_import(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        path = filedialog.askopenfilename(filetypes=[("Bin file", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        self._push_undo()
        self.hq_fx.import_effect(eff.index, data)
        self._discard_last_undo_if_unchanged()
        self._repopulate_keep(eff.index)

    def _fx_wave_fit(self, path, done):
        if self.hq_fx.kind != "alb":
            messagebox.showinfo(f"WAV", "MT-32 timbres (RLD) cannot be extracted from a WAV:\n use an MT-32 timbre editor and import the .bin.")
            return
        try:
            x, sr = _read_wav_float(path)
        except Exception as e:
            messagebox.showerror("WAV", str(e))
            return
        self._fx_set_info("⏳ analyzing WAV and matching FM parameters (a few seconds)...")

        def prog(p):
            self._fx_ui(lambda: self._fx_set_info(f"⏳ matching FM parameters... {int(p * 100)}%"))

        def work():
            try:
                res = hq_fx.fit_wav_to_inst(x, sr, progress=prog)
            except Exception as e:
                msg = str(e)
                self._fx_ui(lambda: messagebox.showerror("WAV", msg))
                return
            self._fx_ui(lambda: done(res))

        threading.Thread(target=work, daemon=True).start()

    def _fx_import_wav_inst(self):
        eff = self._fx_current_effect()
        if eff is None or eff.kind != "inst":
            messagebox.showinfo("WAV", "Select an instrument (♪) to replace.")
            return
        path = filedialog.askopenfilename(filetypes=[("WAV", "*.wav")])
        if not path:
            return
        stem = os.path.splitext(os.path.basename(path))[0].upper()[:10]

        def done(res):
            rec, note, dur = res
            self._push_undo()
            self.hq_fx.insts[eff.ref_id - 1][:] = rec
            self.hq_fx.set_inst_param(eff.ref_id - 1, "name", None, stem)
            self._repopulate_keep(eff.index)
            if hasattr(self, "_fx_note_var"):
                self._fx_note_var.set(note)
            self._fx_play()

        self._fx_wave_fit(path, done)

    def _fx_new_from_wav(self):
        h = self.hq_fx
        if h.kind != "alb":
            messagebox.showinfo("New effect", "For now new effects can only be created in ALB banks.")
            return
        path = filedialog.askopenfilename(filetypes=[("WAV", "*.wav")])
        if not path:
            return
        stem = os.path.splitext(os.path.basename(path))[0].upper()[:9]

        def done(res):
            rec, note, dur = res
            try:
                self._push_undo()
                k = h.add_instrument(rec, stem)
                i = h.add_effect_song(stem, k + 1, note, min(dur, 3.0))
            except ValueError as e:
                messagebox.showerror("New effect", str(e))
                return
            self._repopulate_keep(i)
            self._fx_play()

        self._fx_wave_fit(path, done)

    def _fx_new_inst(self):
        h = self.hq_fx
        eff = self._fx_current_effect()
        src = None
        if eff is not None and eff.kind == "inst" and h.kind == "alb":
            src = bytes(h.insts[eff.ref_id - 1])
        try:
            self._push_undo()
            k = h.add_instrument(src, "NEW")
        except ValueError as e:
            messagebox.showerror("Instrument", str(e))
            return
        idx = [e.index for e in h.effects if e.kind == "inst" and e.ref_id == k + 1][0]
        self._repopulate_keep(idx)
