"""
Mixin editor per i bank di effetti sonori ALB/RLD (HQFxFile).
Stile analogo a editor_vga.py: un pannello dedicato con Play/Estrai/Importa,
mostrato quando current_mode è "fx".

Nota sulla riproduzione: i bank contengono sequenze di comandi per il
driver sonoro originale (OPL2/MPU), non campioni PCM pronti. La Play
qui genera un'anteprima sintetizzata (vedi hq_fx.synthesize_preview_wav);
non è il suono esatto del gioco, ma un'approssimazione utile per
riconoscere/verificare velocemente i blocchi durante l'editing.
"""

import os
import tempfile
import platform
import subprocess
import wave

import tkinter as tk
from tkinter import filedialog, messagebox

from config import PAL, FILE_TYPES
from models import HQFxFile, synthesize_preview_wav, _is_fx_file


FX_FILE_TYPES = [
    ("Sound bank", "*.alb;*.rld"),
    ("AdLib bank", "*.alb"),
    ("Roland bank", "*.rld"),
    ("All files", "*.*"),
]


def _play_wav_file(path):
    """Riproduce un file WAV usando il player di sistema disponibile."""
    system = platform.system()
    try:
        if system == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif system == "Darwin":
            subprocess.Popen(["afplay", path])
        else:
            # prova alcuni player comuni su Linux, in ordine di probabilità
            for player in ("aplay", "paplay", "ffplay"):
                try:
                    args = [player, path] if player != "ffplay" else [player, "-nodisp", "-autoexit", path]
                    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except FileNotFoundError:
                    continue
    except Exception as e:
        messagebox.showerror("Playback error", str(e))


class FxEditorMixin:

    # ------------------------------------------------------------------ #
    # Caricamento (da agganciare in editor.py, vedi PATCH.md)
    # ------------------------------------------------------------------ #
    def _load_fx(self, path, basename):
        self.hq_fx.load(path)
        n = len(self.hq_fx.effects)
        return f"fx | {self.hq_fx.kind.upper()} bank \"{self.hq_fx.bank_name}\" | {n} effetti"

    # ------------------------------------------------------------------ #
    # Selezione / pannello
    # ------------------------------------------------------------------ #
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
        self._render_fx()
        self._update_status()

    def fx_list_items(self):
        """Etichette per il listbox principale (usato da _populate_list)."""
        return [eff.label for eff in self.hq_fx.effects]

    def _build_fx_panel(self):
        self._fx_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"], pady=6, padx=10)

        btn_opts = dict(font=("Consolas", 9), bg=PAL["btn"], fg=PAL["text"],
                         relief=tk.RAISED, cursor="hand2")

        tk.Button(self._fx_panel, text="▶  Play", command=self._fx_play,
                   **btn_opts).grid(row=0, column=0, padx=(0, 8))
        tk.Button(self._fx_panel, text="⇩  Estrai (bin)", command=self._fx_extract_bin,
                   **btn_opts).grid(row=0, column=1, padx=8)
        tk.Button(self._fx_panel, text="⇩  Estrai anteprima (wav)", command=self._fx_extract_wav,
                   **btn_opts).grid(row=0, column=2, padx=8)
        tk.Button(self._fx_panel, text="⇧  Importa", command=self._fx_import,
                   **btn_opts).grid(row=0, column=3, padx=8)

        self._fx_info_label = tk.Label(self._fx_panel, text="", font=("Consolas", 8),
                                        fg=PAL["label"], bg=PAL["toolbar"], justify=tk.LEFT)
        self._fx_info_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def _fx_current_effect(self):
        idx = getattr(self, "_fx_selected_idx", None)
        if idx is None or not (0 <= idx < len(self.hq_fx.effects)):
            return None
        return self.hq_fx.effects[idx]

    # ------------------------------------------------------------------ #
    # Rendering (canvas): metadati + rappresentazione a barre dei byte
    # ------------------------------------------------------------------ #
    def _render_fx(self):
        c = self.canvas
        c.delete("all")
        eff = self._fx_current_effect()
        if eff is None:
            return

        c.create_text(10, 10, anchor="nw", fill=PAL["box_txt"], font=("Consolas", 13, "bold"),
                       text=eff.name)
        c.create_text(10, 34, anchor="nw", fill=PAL["label"], font=("Consolas", 9),
                       text=f"bank: {self.hq_fx.kind.upper()}   ref_id: {eff.ref_id}   "
                            f"flag: {eff.flag}   bytes: {len(eff.data)}")

        # rappresentazione grezza del blocco dati come barre (solo per
        # riconoscimento visivo, non è una forma d'onda reale)
        base_y = 70
        bar_w = 4
        max_h = 120
        for i, b in enumerate(eff.data[:150]):
            x = 10 + i * bar_w
            h = int((b / 255.0) * max_h)
            c.create_rectangle(x, base_y + max_h - h, x + bar_w - 1, base_y + max_h,
                                fill=PAL["accent"], outline="")

        if len(eff.data) > 150:
            c.create_text(10, base_y + max_h + 16, anchor="nw", fill=PAL["label"],
                           font=("Consolas", 8),
                           text=f"... troncato nella preview ({len(eff.data)} byte totali)")

        self._fx_info_label.config(
            text="Anteprima audio sintetizzata (non è il suono OPL2/MT-32 reale, "
                 "solo un riferimento per riconoscere il blocco)."
        )

    # ------------------------------------------------------------------ #
    # Azioni
    # ------------------------------------------------------------------ #
    def _fx_play(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        try:
            pcm = synthesize_preview_wav(bytes(eff.data), self.hq_fx.kind)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            with wave.open(tmp.name, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(22050)
                w.writeframes(pcm)
            _play_wav_file(tmp.name)
        except Exception as e:
            messagebox.showerror("Playback error", str(e))

    def _fx_extract_bin(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        path = filedialog.asksaveasfilename(
            initialfile=f"{eff.name}.bin", defaultextension=".bin",
            filetypes=[("Bin file", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "wb") as f:
            f.write(bytes(eff.data))
        messagebox.showinfo("Estratto", f"Salvato {len(eff.data)} byte in {os.path.basename(path)}")

    def _fx_extract_wav(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        idx = self._fx_selected_idx
        path = filedialog.asksaveasfilename(
            initialfile=f"{eff.name}.wav", defaultextension=".wav",
            filetypes=[("WAV file", "*.wav"), ("All files", "*.*")])
        if not path:
            return
        self.hq_fx.extract_effect_wav(idx, path)
        messagebox.showinfo("Estratto", f"Anteprima audio salvata in {os.path.basename(path)}")

    def _fx_import(self):
        eff = self._fx_current_effect()
        if eff is None:
            return
        idx = self._fx_selected_idx
        path = filedialog.askopenfilename(
            filetypes=[("Bin file", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        try:
            new_data = open(path, "rb").read()
        except Exception as e:
            messagebox.showerror("Import error", str(e))
            return

        old_len = len(eff.data)
        self._push_undo()
        self.hq_fx.import_effect(idx, new_data)
        self._discard_last_undo_if_unchanged()
        self._populate_list()
        self.listbox.selection_set(idx)
        self._render_fx()
        self._update_status()
        if len(new_data) != old_len:
            messagebox.showinfo(
                "Importato",
                f"Blocco sostituito: {old_len} → {len(new_data)} byte.\n"
                f"La tabella puntatori verrà ricalcolata al salvataggio."
            )
