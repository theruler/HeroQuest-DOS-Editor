import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from collections import Counter
import os
import copy

from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from config import (
    PAL, CELL, GRID_COLS, GRID_ROWS, GLYPH_COLORS, GLYPH_RANGE,
    MAX_ROW, MAX_COL, MIN_ROW, MIN_COL, DRAG_THRESHOLD, FILE_TYPES
)
from utils import (
    CHAR_DECODE, is_compressed_file, is_known_language_file, run_exe, encode_text, decode_text,
    draw_cylinder_roll, _draw_grid, load_dynamix_font_file
)
from models import (
    HQFile, HQQuestFile, HQPagedFile, HQIntroFile, HQQuestExeFile, HQVgaFile,
    HQMultiVgaFile, HQFxFile,
    FURNITURE_BLOCK_NAME,
    _is_quest_file, _is_paged_file, _is_intro_file, _is_quest_exe_file, _is_vga_file,
    _is_multi_vga_file, _is_fx_file,
    MONSTER_TYPES, MONSTER_TABLE, OBJECT_TYPES, HERO_TYPES, TREASURE_EVENTS,
    QUEST_MAP_W, QUEST_MAP_H, DEFAULT_ROOMS,
    INTRO_MAX_BYTES, INTRO_FIXED_STRINGS, QUEST_EXE_PAGE_MAX_TOTAL,
    VGA_WIDTH, VGA_HEIGHT, palette_to_rgb888, AVAILABLE_PALETTES
)


class ListsEditorMixin:
    def _status_intro(self):
        used = self.hq_intro.bytes_used()
        base = f"{used}/{INTRO_MAX_BYTES} bytes"
        over = used > INTRO_MAX_BYTES
        if self._current_intro_fixed is not None:
            fs = self.hq_intro.get_fixed_string(self._current_intro_fixed)
            if fs is not None:
                fused = self.hq_intro.fixed_string_bytes_used(self._current_intro_fixed)
                fmax  = fs["max_bytes"]
                base += f"  |  String 0x{fs['offset']:04x}: {fused}/{fmax} bytes"
                over  = over or (fused > fmax)
        return base, over

    def _status_quest(self):
        sm = getattr(self, "_quest_submode", "text")
        if sm == "m&h":
            count = len(self.hq_quest.monsters)
            return f"{count}/31 monsters", True if count > 31 else False
        elif sm == "objects":
            return f"{len(self.hq_quest.objects)} objects", False
        elif sm == "text":
            return f"{len(self.hq_quest.text_lines)} lines", False
        else:
            return "—", False

    def _status_paged(self):
        return f"{len(self.hq_paged.pages)} pages", False

    def _status_hq(self):
        used = self.hq.get_total_size()
        return f"{used}/16701 bytes", used > 16701

    def _status_vga(self):
        return f"{VGA_WIDTH}x{VGA_HEIGHT}", False

    def _status_vga_multi(self):
        n = len(self.hq_vga_multi.sprites)
        group_name = self._vga_multi_current_furniture_group()
        if group_name is not None:
            group = next((g for g in self.hq_vga_multi.get_furniture_groups()
                          if g["name"] == group_name), None)
            if group is not None:
                w = group["cols"] * 8
                h = group["rows"] * 8
                return (f"{group_name}  |  {w}x{h}  ({len(group['tiles'])} tiles)", False)
        spr = self._vga_multi_current_sprite()
        if spr is None:
            return f"{n} sprites", False
        return (f"sprite {spr.index+1}/{n} | {spr.width}x{spr.height}", False)

    def _status_fx(self):
        n = len(self.hq_fx.effects)
        eff = self._fx_current_effect() if hasattr(self, "_fx_current_effect") else None
        base = f"{self.hq_fx.kind.upper()} bank \"{self.hq_fx.bank_name}\" | {n} effetti"
        if eff is not None:
            base += f"  |  {eff.name}: {len(eff.data)} bytes"
        return base, False

    _STATUS_PROVIDERS = {
        "intro":     _status_intro,
        "quest":     _status_quest,
        "paged":     _status_paged,
        "hq":        _status_hq,
        "vga":       _status_vga,
        "vga_multi": _status_vga_multi,
        "fx":        _status_fx,
    }

    def _update_status(self):
        fname = os.path.basename(self._current_path) if hasattr(self, '_current_path') else "Untitled"

        if self.current_mode == "quest_exe":
            self._update_status_quest_exe(fname)
            return

        provider = self._STATUS_PROVIDERS.get(self.current_mode, ListsEditorMixin._status_hq)
        text, over_limit = provider(self)
        self._status.set(f"{fname}\n{text}")
        self._status_label.config(fg=PAL["accent"] if over_limit else PAL["label"])

    def _update_status_quest_exe(self, fname):
        qe = self.hq_quest_exe
        tag = self._current_quest_exe_tag
        if tag is None:
            self._status.set(f"{fname}")
            return
        kind, i = tag
        if kind == "pos":
            entry = qe.pos_strings[i]
            max_b = entry["max_bytes"]
            used = qe.bytes_used_pos(i)
            self._status.set(f"{fname} | String | {used}{f'/{max_b}' if max_b is not None else ''} bytes")
            self._status_label.config(fg=PAL["accent"] if max_b and used > max_b else PAL["label"])
        elif kind == "page":
            used = qe.bytes_used_pages()
            self._status.set(f"{fname} | Page | {used}/{QUEST_EXE_PAGE_MAX_TOTAL} bytes")
            self._status_label.config(fg=PAL["accent"] if used > QUEST_EXE_PAGE_MAX_TOTAL else PAL["label"])
        elif kind == "plain":
            entry = qe.plain_strings[i]
            used = len(encode_text(entry["text"]))
            self._status.set(f"{fname} | Name | {used}/{entry['max_bytes']} bytes")
            self._status_label.config(fg=PAL["accent"] if used > entry['max_bytes'] else PAL["label"])
        elif kind == "dos":
            entry = qe.dos_strings[i]
            used = qe.dos_string_bytes_used(i)
            self._status.set(f"{fname} | SYSTEM | {used}/{entry['max_bytes']} bytes")
            self._status_label.config(fg=PAL["accent"] if used > entry['max_bytes'] else PAL["label"])

    def _select_first(self):
        for i, idx in enumerate(self._list_indices):
            if idx is not None:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                self._on_select(None)
                return

    def _build_open_filetypes(self):
        patterns = []
        for label, pattern in FILE_TYPES:
            if label.strip().lower() in ("all files", "tutti i file"):
                continue
            for p in pattern.split():
                if p and p not in patterns:
                    patterns.append(p)
        if not patterns:
            return FILE_TYPES
        return [("All supported files", " ".join(patterns))] + list(FILE_TYPES)

    def _populate_list_intro(self, ft):
        self._drag_hint.pack_forget()
        self.listbox.insert(tk.END, " INTRO.EXE")
        self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
        self._list_indices.append(None)
        for page in self.hq_intro.pages:
            if ft and not any(ft in l["text"].lower() for l in page["lines"]): continue
            self.listbox.insert(tk.END, f"    ↳  Page {page['index']}")
            self.listbox.itemconfig(tk.END, fg=PAL["opt"])
            self._list_indices.append(page["index"])

        if any(not ft or ft in fs["text"].lower() for fs in self.hq_intro.fixed_strings):
            self.listbox.insert(tk.END, "  ── System Strings ──")
            self.listbox.itemconfig(tk.END, fg=PAL["label"])
            self._list_indices.append(None)
        for i, fs in enumerate(self.hq_intro.fixed_strings):
            if ft and ft not in fs["text"].lower(): continue
            preview = fs["text"].replace("\n", "").replace("\r", " ")[:22]
            self.listbox.insert(tk.END, f"    ↳  0x{fs['offset']:04x}  {preview}")
            self.listbox.itemconfig(tk.END, fg=PAL["plain"])
            self._list_indices.append(("fixed", i))

    def _populate_list_quest_exe(self, ft):
        self._drag_hint.pack_forget()
        qe = self.hq_quest_exe
        self.listbox.insert(tk.END, " QUEST.EXE")
        self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
        self._list_indices.append(None)
        self.listbox.insert(tk.END, "  ── Positioned Strings ──")
        self.listbox.itemconfig(tk.END, fg=PAL["label"])
        self._list_indices.append(None)
        for i, s in enumerate(qe.pos_strings):
            label = f"    ↳  POS 0x{s['str_off']:05X}  {(s['lines'][0]['text'] if s['lines'] else '')[:24]}"
            if ft and ft not in label.lower(): continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=PAL["text"])
            self._list_indices.append(("pos", i))
        self.listbox.insert(tk.END, "  ── Page Blocks ──")
        self.listbox.itemconfig(tk.END, fg=PAL["label"])
        self._list_indices.append(None)
        for i, page in enumerate(qe.page_blocks):
            preview = page["lines"][0]["text"][:20] if page["lines"] else "—"
            label = f"    ↳  PAGE 0x{page['str_off']:05X}  {preview}"
            if ft and ft not in label.lower(): continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=PAL["opt"])
            self._list_indices.append(("page", i))
        self.listbox.insert(tk.END, "  ── Plain Strings ──")
        self.listbox.itemconfig(tk.END, fg=PAL["label"])
        self._list_indices.append(None)
        for i, s in enumerate(qe.plain_strings):
            label = f"    ↳  0x{s['str_off']:05X}  \"{s['text']}\""
            if ft and ft not in label.lower(): continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=PAL["plain"])
            self._list_indices.append(("plain", i))
        if any(not ft or ft in fs["text"].lower() for fs in qe.dos_strings):
            self.listbox.insert(tk.END, "  ── System Strings ──")
            self.listbox.itemconfig(tk.END, fg=PAL["label"])
            self._list_indices.append(None)
        for i, fs in enumerate(qe.dos_strings):
            if ft and ft not in fs["text"].lower(): continue
            preview = fs["text"].replace("\n", "").replace("\r", " ")[:22]
            self.listbox.insert(tk.END, f"    ↳  0x{fs['offset']:04x}  {preview}")
            self.listbox.itemconfig(tk.END, fg=PAL["plain"])
            self._list_indices.append(("dos", i))

    _QUEST_SUBMENU = [
        ("  ↳ MISSION BRIEFING",       PAL["opt"], "text"),
        ("  ↳ MAP EDITOR",             "#00ccff",  "map"),
        ("     ↳ MONSTERS & HEROES",   "#ff6644",  "m&h"),
        ("     ↳ FURNITURES & TRAPS",  "#ffaa44",  "objects"),
        ("     ↳ ROOM EVENTS",         "#ffdd44",  "events"),
    ]

    def _populate_list_quest(self, ft):
        self._drag_hint.pack_forget()
        name = getattr(self, "_quest_filename", "QUEST")
        self.listbox.insert(tk.END, f" {name}")
        self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
        self._list_indices.append(None)
        for label, color, idx in self._QUEST_SUBMENU:
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=color)
            self._list_indices.append(idx)

    def _populate_list_paged(self, ft):
        self._drag_hint.pack_forget()
        last_lang = None
        for page in self.hq_paged.pages:
            if ft and not any(ft in l["text"].lower() for l in page["lines"]): continue
            if page["lang"] != last_lang:
                self.listbox.insert(tk.END, f" {page['lang']}")
                self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
                self._list_indices.append(None)
                last_lang = page["lang"]
            self.listbox.insert(tk.END, f"    ↳  Page {page['page_num']}")
            self.listbox.itemconfig(tk.END, fg=PAL["plain"])
            self._list_indices.append(page["index"])

    def _populate_list_hq(self, ft):
        ptr_count = Counter(self.hq.main_ptrs)
        TYPE_COLORS = {
            "box":        PAL["box_txt"],
            "text_plain": PAL["text"],
            "text_pos":   PAL["text"],
            "btn_label":  PAL["opt"],
        }
        for b in self.hq.blocks:
            if b.get("type") == "null": continue
            label = self._block_label(b, ptr_count)
            if ft and ft not in label.lower(): continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=TYPE_COLORS.get(b.get("type"), PAL["text"]))
            self._list_indices.append(b["index"])

    def _populate_list_vga(self, ft):
        self._drag_hint.pack_forget()
        self.listbox.insert(tk.END, f" IMAGE {VGA_WIDTH}x{VGA_HEIGHT}")
        self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
        self._list_indices.append(0)

    def _populate_list_vga_multi(self, ft):
        self._drag_hint.pack_forget()
        furniture_groups = self.hq_vga_multi.get_furniture_groups()
        grouped_block_name = FURNITURE_BLOCK_NAME if furniture_groups else None
        grouped_tile_indices = set()
        if grouped_block_name:
            for g in furniture_groups:
                grouped_tile_indices.update(g["tiles"])

        seen_grouped_block = False
        for spr in self.hq_vga_multi.sprites:
            if spr.block_name == grouped_block_name:
                if not seen_grouped_block:
                    seen_grouped_block = True
                    self._populate_furniture_groups(furniture_groups, ft)
                if spr.index_in_block in grouped_tile_indices:
                    continue  # già mostrata sotto il suo gruppo
                label = f"  0x{spr.offset:04X}  {spr.label}"
                if ft and ft not in label.lower():
                    continue
                self.listbox.insert(tk.END, label)
                self.listbox.itemconfig(tk.END, fg=PAL["text"])
                self._list_indices.append(spr.index)
                continue
            label = f"  0x{spr.offset:04X}  {spr.label}"
            if ft and ft not in label.lower():
                continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=PAL["text"])
            self._list_indices.append(spr.index)

    def _populate_furniture_groups(self, furniture_groups, ft):
        block_sprites = self.hq_vga_multi.sprites_in_block(FURNITURE_BLOCK_NAME)
        for group in furniture_groups:
            tiles = [block_sprites[i] for i in group["tiles"]]
            header_label = f"  {group['name']}  ({group['cols']}x{group['rows']})"
            header_matches = bool(ft) and ft in header_label.lower()
            child_labels = [f"    ↳  0x{spr.offset:04X}  tile {n + 1}/{len(tiles)}"
                            for n, spr in enumerate(tiles)]
            matching_children = [
                (spr, lbl) for spr, lbl in zip(tiles, child_labels)
                if not ft or ft in lbl.lower()
            ]
            if ft and not header_matches and not matching_children:
                continue
            self.listbox.insert(tk.END, header_label)
            self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
            self._list_indices.append(("furn_group", group["name"]))
            shown = list(zip(tiles, child_labels)) if (header_matches or not ft) else matching_children
            for spr, lbl in shown:
                self.listbox.insert(tk.END, lbl)
                self.listbox.itemconfig(tk.END, fg=PAL["opt"])
                self._list_indices.append(spr.index)

    def _populate_list_fx(self, ft):
        self._drag_hint.pack_forget()
        self.listbox.insert(tk.END, f" {self.hq_fx.kind.upper()}  \"{self.hq_fx.bank_name}\"")
        self.listbox.itemconfig(tk.END, fg=PAL["box_txt"])
        self._list_indices.append(None)
        for eff in self.hq_fx.effects:
            label = f"    ↳  {eff.label}"
            if ft and ft not in label.lower():
                continue
            self.listbox.insert(tk.END, label)
            self.listbox.itemconfig(tk.END, fg=PAL["plain"])
            self._list_indices.append(eff.index)

    _POPULATE_LIST_HANDLERS = {
        "intro":     _populate_list_intro,
        "quest_exe": _populate_list_quest_exe,
        "quest":     _populate_list_quest,
        "paged":     _populate_list_paged,
        "hq":        _populate_list_hq,
        "vga":       _populate_list_vga,
        "vga_multi": _populate_list_vga_multi,
        "fx":        _populate_list_fx,
    }

    def _populate_list(self, filter_text=""):
        self.listbox.delete(0, tk.END)
        self._list_indices = []
        ft = filter_text.lower()
        handler = self._POPULATE_LIST_HANDLERS.get(self.current_mode, ListsEditorMixin._populate_list_hq)
        handler(self, ft)

    def _block_label(self, b, ptr_count=None):
        t       = b.get("type", "null")
        idx     = b.get("index", 0)
        hex_idx = f"{(idx * 2):04X}"
        pfx     = "    ↳" if b.get("orphan") else " "
        dup     = f" ×{ptr_count[b.get('ptr', 0)]}" \
                  if ptr_count and ptr_count.get(b.get("ptr", 0), 1) > 1 else ""
        if t == "box":
            txt = b["lines"][0]["text"][:22] if b.get("lines") else "—"
            return f"{pfx}{hex_idx} [scroll]{dup} {txt}"
        if t == "text_plain":
            segs = b.get("segments", [])
            txt  = segs[0]["text"][:22] if segs else "—"
            return f"{pfx}{hex_idx} [text]{dup} {txt}"
        if t == "btn_label":
            label = f"[button]{dup} {b.get('text', '')[:22]}"
            return f"{pfx} {label}" if b.get("orphan") else f" {hex_idx} {label}"
        if t == "text_pos":
            txt = b["lines"][0]["text"][:22] if b.get("lines") else "—"
            return f"{pfx}{hex_idx} [text]{dup} {txt}"
        return f"{pfx}{hex_idx} [{t}]{dup}"

    def _on_filter(self, *_):
        ft = self._filter_var.get()
        self._populate_list(ft)
