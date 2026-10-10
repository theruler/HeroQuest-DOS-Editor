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
    CHAR_DECODE, is_compressed_file, is_known_language_file, encode_text, decode_text,
    draw_cylinder_roll, _draw_grid, load_dynamix_font_file
)
from models import (
    HQFile, HQQuestFile, HQPagedFile, HQIntroFile, HQQuestExeFile, HQVgaFile,
    HQMultiVgaFile,
    FURNITURE_BLOCK_NAME,
    _is_quest_file, _is_paged_file, _is_intro_file, _is_quest_exe_file, _is_vga_file,
    _is_multi_vga_file,
    MONSTER_TYPES, MONSTER_TABLE, OBJECT_TYPES, HERO_TYPES, TREASURE_EVENTS,
    QUEST_MAP_W, QUEST_MAP_H, DEFAULT_ROOMS,
    INTRO_MAX_BYTES, INTRO_FIXED_STRINGS, QUEST_EXE_PAGE_MAX_TOTAL,
    VGA_WIDTH, VGA_HEIGHT, palette_to_rgb888, AVAILABLE_PALETTES
)

from editor_vga import VgaEditorMixin
from editor_fx import FxEditorMixin


class TextEditorMixin:
    def _set_add_line_visible(self, visible):
        is_mapped = bool(self._add_line_btn.winfo_ismapped())
        if visible and not is_mapped:
            self._add_line_btn.grid()
        elif not visible and is_mapped:
            self._add_line_btn.grid_remove()

    def _on_select_intro(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        if isinstance(idx, tuple) and idx[0] == "fixed":
            self._on_select_intro_fixed(idx[1])
            return
        if (self._current_paged == idx and self._current_intro_fixed is None
                and self._base_edit_frame.winfo_ismapped()):
            return
        self._current_paged = idx
        self._current_intro_fixed = None
        page = self.hq_intro.get_page(idx)
        if not page: return
        self._show_base_edit_panel()
        self._set_add_line_visible(True)
        self._rebuild_line_entries([{"row": l["row"], "col": l["col"], "text": l["text"]}
                                    for l in page["lines"]])
        self._drag_hint.config(text=f"Max {INTRO_MAX_BYTES} bytes total across all pages.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self._schedule_select_render()

    def _on_select_intro_fixed(self, i):
        self._current_paged = None
        self._current_intro_fixed = i
        fs = self.hq_intro.get_fixed_string(i)
        if fs is None: return
        self._set_add_line_visible(False)
        self._build_fixed_string_panel("intro_fixed")
        self._intro_fixed_text.delete("1.0", tk.END)
        self._intro_fixed_text.insert("1.0", fs["text"])
        self._update_fixed_string_counter("intro_fixed")
        self._drag_hint.config(text="HINT: edit text in the panel below.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self.current = None
        self._render()
        self._update_status()

    def _on_select_quest_exe_dos(self, i):
        self._current_quest_exe_tag = ("dos", i)
        self._current_quest_exe_dos = i
        qe = self.hq_quest_exe
        fs = qe.get_dos_string(i)
        if fs is None: return
        self._set_add_line_visible(False)
        self._build_fixed_string_panel("quest_exe_dos")
        self._quest_exe_dos_text.delete("1.0", tk.END)
        self._quest_exe_dos_text.insert("1.0", fs["text"])
        self._update_fixed_string_counter("quest_exe_dos")
        self._drag_hint.config(text="HINT: edit text in the panel below.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self.current = None
        self._render()
        self._update_status()

    def _on_select_quest_exe(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        if isinstance(idx, tuple) and idx[0] == "dos":
            self._on_select_quest_exe_dos(idx[1])
            return
        kind, i = idx
        self._current_quest_exe_tag = idx
        self._current_quest_exe_dos = None
        qe = self.hq_quest_exe
        self._set_add_line_visible(False)
        self._show_base_edit_panel()
        if kind == "pos":
            entry = qe.pos_strings[i]
            self._set_add_line_visible(True)
            self._rebuild_line_entries(
                [{"row": l["row"], "col": l["col"], "text": l["text"]}
                for l in entry["lines"]],
                lock_first=self._current_lock_first())
        elif kind == "page":
            page = qe.page_blocks[i]
            self._set_add_line_visible(True)
            self._rebuild_line_entries(
                [{"row": l["row"], "col": l["col"], "text": l["text"]}
                for l in page["lines"]])
        elif kind == "plain":
            entry = qe.plain_strings[i]
            self._rebuild_line_entries(
                [{"row": None, "col": None, "text": entry["text"]}],
                plain_mode=True)
        self._update_status()
        self._drag_hint.config(text="DOUBLE CLICK to edit, ✔ to apply.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self._schedule_select_render()

    def _lines_hint(self, add_line=False, resize=False):
        if resize:
            text = ("HINT: DOUBLE CLICK on lines jumps to entry. DRAG scroll,\nbuttons or lines. RESIZE with ◢.")
            return text + " ADD LINE to append." if add_line else text
        if add_line:
            return "HINT: DRAG lines or DOUBLE CLICK to edit.\nADD LINE to append."
        return "HINT: DRAG lines or DOUBLE CLICK to edit."

    def _on_select_paged(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        if self._current_paged == idx and self._base_edit_frame.winfo_ismapped():
            return
        self._current_paged = idx
        page = self.hq_paged.get_page(idx)
        if not page: return
        self._show_base_edit_panel()
        self._set_add_line_visible(False)
        self._rebuild_line_entries([{"row": l["row"], "col": l["col"], "text": l["text"]}
                                    for l in page["lines"]])
        self._drag_hint.config(text=self._lines_hint())
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self._schedule_select_render()

    _QUEST_SUBMODES = {
        "map": "HINT: Left click enables the selected map element, right click removes it.\nEach attribute is referred only to the element on the left.",
        "m&h": lambda self: (f"HINT: Drag from pool or map to map. Left Click on monster to edit\nRight click to remove. Click on heroes to change facing or drag."),
        "objects": lambda self: (f"HINT: Drag from pool or map to map. One big furniture per room.\nLeft click to toggle facing/function, Right to remove."),
        "events": "HINT: Click a room to select it and see its event.\nChoose from the list to assign it. Right-click clears.",
    }

    def _refresh_quest_hint(self, idx=None):
        idx = idx if idx is not None else getattr(self, "_quest_submode", None)
        entry = self._QUEST_SUBMODES.get(idx)
        if entry is None: return
        hint_text = entry(self) if callable(entry) else entry
        self._drag_hint.config(text=hint_text)

    def _on_select_quest(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        if idx in self._QUEST_SUBMODES:
            self._quest_submode = idx
            self._refresh_quest_hint(idx)
            self._drag_hint.pack(side=tk.RIGHT, padx=20)
            self._build_quest_map_panel(idx)
            self._render_quest_map()
            self._update_status()
        elif idx == "text":
            self._quest_submode = "text"
            self._show_base_edit_panel()
            self._rebuild_line_entries(self.hq_quest.text_lines)
            self._set_add_line_visible(True)
            self._drag_hint.config(text=self._lines_hint(add_line=True))
            self._drag_hint.pack(side=tk.RIGHT, padx=20)
            self._schedule_select_render()
            self._update_status()

    def _on_select_hq(self, idx):
        self.current = idx
        b = self._get_block(self.current)
        if not b:
            self.current  = None
            self._show_bg = False
            self._schedule_select_render()
            return
        self._show_bg = (b.get("type") == "box")
        if self._show_bg:
            self._load_background()
        self._schedule_select_render()
        self._load_edit_panel(b)
        cnt = Counter(self.hq.main_ptrs).get(b.get("ptr", 0), 1)
        t = b.get("type")
        if t in ("box", "text_plain", "btn_label"):
            hints = {
                "box":        self._lines_hint(add_line=True, resize=True),
                "text_plain": "HINT: RED text's position cannot be changed,\nsince it's coordinates are hardcoded into the exe.",
                "btn_label":  "HINT: GREEN text's position cannot be changed here,\nbut in the scroll where this button is used.",
            }
            self._drag_hint.config(text=hints[t])
            self._drag_hint.pack(side=tk.RIGHT, padx=20)
        else:
            self._drag_hint.pack_forget()

    _ON_SELECT_HANDLERS = {
        "intro":     _on_select_intro,
        "quest_exe": _on_select_quest_exe,
        "paged":     _on_select_paged,
        "quest":     _on_select_quest,
        "hq":        _on_select_hq,
        "vga":       VgaEditorMixin._on_select_vga,
        "vga_multi": VgaEditorMixin._on_select_vga_multi,
        "fx":        FxEditorMixin._on_select_fx,
    }

    def _on_select(self, _):
        if self._drag_box or self._drag_line_idx is not None or self._drag_sub_idx is not None:
            return
        if self._rebuilding: return
        sel = self.listbox.curselection()
        if not sel:
            if self.current_mode == "hq":
                if self.root.focus_get() is self.listbox:
                    self.current  = None
                    self._show_bg = False
                    self._schedule_select_render()
                self._drag_hint.pack_forget()
                self._set_add_line_visible(False)
            return
        idx = self._list_indices[sel[0]]
        handler = self._ON_SELECT_HANDLERS.get(self.current_mode, TextEditorMixin._on_select_hq)
        handler(self, idx)

    def _get_block(self, idx):
        for b in self.hq.blocks:
            if b["index"] == idx:
                return b
        return None

    _ADD_LINE_TYPES = {"box", "text_plain", "text_pos"}

    def _load_edit_panel(self, b):
        t = b.get("type", "null")
        if t in self._ADD_LINE_TYPES:
            self._set_add_line_visible(True)
        else:
            self._set_add_line_visible(False)
        if t == "box":
            self._rebuild_line_entries(b.get("lines", []))
        elif t == "text_plain":
            self._rebuild_line_entries(
                [{"row": s["row"], "col": s["col"], "text": s["text"]}
                 for s in b.get("segments", [])], plain_mode=True)
        elif t == "text_pos":
            self._rebuild_line_entries(
                [{"row": l["row"], "col": l["col"], "text": l["text"]}
                 for l in b.get("lines", [])],
                lock_first=self._current_lock_first())
        elif t == "btn_label":
            self._rebuild_line_entries(
                [{"row": None, "col": None, "text": b["text"]}], plain_mode=True)
        else:
            self._rebuild_line_entries([])

    def _rebuild_line_entries(self, lines, plain_mode=False, lock_first=False):
        self._rebuilding = True
        try:
            for w in self._lines_frame.winfo_children():
                w.destroy()
            self._line_entries = []

            for i, l in enumerate(lines):
                has_pos = (l.get("row") is not None and l.get("col") is not None)

                rv = tk.IntVar(value=l["row"] if has_pos else 0)
                cv = tk.IntVar(value=l["col"] if has_pos else 0)
                tv = tk.StringVar(value=l.get("text", ""))

                pos_lbl = " Row:" if has_pos else " Hardcoded "
                tk.Label(self._lines_frame, text=pos_lbl, font=("Consolas", 8),
                         fg=PAL["label"], bg=PAL["toolbar"],
                         width=10, anchor="e").grid(row=i, column=0)

                if has_pos:
                    sp_row = tk.Spinbox(self._lines_frame, from_=0, to=50, textvariable=rv, width=3,
                               bg=PAL["grid"], fg=PAL["text"],
                               buttonbackground=PAL["btn"],
                               relief=tk.FLAT, font=("Consolas", 9))
                    sp_row.grid(row=i, column=1)
                    sp_row.bind("<Return>", lambda e, i=i: self._apply_single_line(i))
                    sp_row.bind("<FocusOut>", lambda e, i=i: self._on_line_entry_focus_out(i))
                    tk.Label(self._lines_frame, text=" Column:", font=("Consolas", 8),
                             fg=PAL["label"], bg=PAL["toolbar"],
                             width=10, anchor="e").grid(row=i, column=2)
                    sp_col = tk.Spinbox(self._lines_frame, from_=0, to=50, textvariable=cv, width=3,
                               bg=PAL["grid"], fg=PAL["text"],
                               buttonbackground=PAL["btn"],
                               relief=tk.FLAT, font=("Consolas", 9))
                    sp_col.grid(row=i, column=3)
                    sp_col.bind("<Return>", lambda e, i=i: self._apply_single_line(i))
                    sp_col.bind("<FocusOut>", lambda e, i=i: self._on_line_entry_focus_out(i))

                base_col = 4
                entry_txt = tk.Entry(self._lines_frame, textvariable=tv, width=40,
                         bg=PAL["grid"], fg=PAL["box_txt"], insertbackground=PAL["box_txt"], relief=tk.GROOVE, font=("Consolas", 12))
                entry_txt.grid(row=i, column=base_col)
                if has_pos:
                    entry_txt.bind("<Return>", lambda e, i=i: self._on_text_entry_return(i))
                else:
                    entry_txt.bind("<Return>", lambda e, i=i: self._apply_single_line(i))
                entry_txt.bind("<FocusOut>", lambda e, i=i: self._on_line_entry_focus_out(i))

                tk.Button(self._lines_frame, text="✔", font=("Consolas", 8, "bold"),
                          bg="#003020", fg="#00ff99", relief=tk.RAISED,
                          command=lambda i=i: self._apply_single_line(i),
                          width=2, cursor="hand2").grid(row=i, column=base_col + 1, padx=2)

                can_delete = has_pos and not self.current_mode == "paged" and not (lock_first and i == 0)
                if can_delete:
                    tk.Button(self._lines_frame, text="−",
                              command=lambda i=i: self._delete_line_at(i),
                              bg="#402020", fg="#ff6666", relief=tk.RAISED,
                              width=2, cursor="hand2").grid(row=i, column=base_col + 2)

                self._line_entries.append((rv, cv, tv, has_pos))
        finally:
            self._rebuilding = False
            self.root.update_idletasks()

    def _current_lock_first(self):
        if self.current_mode == "quest_exe":
            tag = self._current_quest_exe_tag
            if tag is not None:
                kind, _ = tag
                return kind == "pos"
            return False
        if self.current_mode == "hq" and self.current is not None:
            b = self._get_block(self.current)
            return bool(b) and b.get("type") == "text_pos"
        return False

    def _get_current_text_context(self):
        if self.current_mode == "intro" and self._current_paged is not None:
            page = self.hq_intro.get_page(self._current_paged)
            if page: return page["lines"], lambda: self._render_intro(page)

        elif self.current_mode == "paged" and self._current_paged is not None:
            page = self.hq_paged.get_page(self._current_paged)
            if page: return page["lines"], lambda: self._render_paged(page)

        elif self.current_mode == "quest" and getattr(self, "_quest_submode", "text") == "text":
            return self.hq_quest.text_lines, self._render_quest

        elif self.current_mode == "quest_exe":
            tag = self._current_quest_exe_tag
            if tag is not None:
                kind, i = tag
                qe = self.hq_quest_exe
                if kind == "pos":  return qe.pos_strings[i]["lines"], self._render_quest_exe
                elif kind == "page": return qe.page_blocks[i]["lines"], self._render_quest_exe

        elif self.current is not None:
            b = self._get_block(self.current)
            if b:
                if b.get("type") == "box":
                    return b["lines"], self._render
                elif b.get("type") == "text_plain":
                    return b.get("segments", []), self._render
                elif b.get("type") == "text_pos":
                    return b["lines"], self._render

        return None, None

    def _on_line_entry_focus_out(self, i):
        if self._rebuilding:
            return
        self._apply_single_line(i)

    def _on_text_entry_return(self, i):
        if i < len(self._line_entries):
            rv, cv, tv, has_pos = self._line_entries[i]
            text = tv.get()
            stripped = text.lstrip(" ")
            n_spaces = len(text) - len(stripped)
            if n_spaces:
                tv.set(stripped)
                cv.set(cv.get() + n_spaces)
        self._apply_single_line(i)

    def _apply_single_line(self, i):
        lines, render_fn = self._get_current_text_context()

        if lines is not None and i < len(lines):
            self._push_undo()
            rv, cv, tv, has_pos = self._line_entries[i]
            lines[i]["text"] = tv.get()
            if has_pos:
                lines[i]["row"] = rv.get()
                lines[i]["col"] = cv.get()
            self._discard_last_undo_if_unchanged()
            self._update_status()
            render_fn()
            return

        if self.current_mode == "quest_exe":
            tag = self._current_quest_exe_tag
            if tag is not None and tag[0] == "plain":
                idx = tag[1]
                self._push_undo()
                self.hq_quest_exe.plain_strings[idx]["text"] = self._line_entries[i][2].get()
                self._discard_last_undo_if_unchanged()
                self._update_status()
                self._render_quest_exe()
                return

        if self.current is not None:
            b = self._get_block(self.current)
            if b and b["type"] == "btn_label":
                self._push_undo()
                b["text"] = self._line_entries[i][2].get()
                self._discard_last_undo_if_unchanged()
            self._update_status()
            self._render()

    def _delete_line_at(self, i):
        lines, render_fn = self._get_current_text_context()
        if lines is not None and 0 <= i < len(lines):
            self._push_undo()
            lines.pop(i)
            self._rebuild_line_entries(lines, lock_first=self._current_lock_first())
            render_fn()
            self._update_status()
            return
            
        if self.current is not None:
            b = self._get_block(self.current)
            if b and b["type"] == "btn_label":
                self._push_undo()
                b["text"] = ""
                self._load_edit_panel(b)
                self._update_status()
                self._render()

    def _add_line(self):
        lines, render_fn = self._get_current_text_context()
        if lines is not None:
            self._push_undo()
            new_row = (lines[-1].get("row") + 1) if lines and lines[-1].get("row") is not None else 5
            new_col = lines[-1].get("col") if lines and lines[-1].get("col") is not None else 5
            lines.append({"row": new_row, "col": new_col, "text": "NEW LINE"})
            
            self._rebuild_line_entries(lines, lock_first=self._current_lock_first())
            render_fn()
            self._update_status()
            return

        if self.current is not None:
            b = self._get_block(self.current)
            if b:
                if b["type"] == "btn_label":
                    self._push_undo()
                    b["text"] += " NEW"
                self._load_edit_panel(b)
                self._update_status()
                self._render()

    _FIXED_STRING_PANELS = {
        "intro_fixed": dict(
            panel_attr="_intro_fixed_panel",
            built_attr="_intro_fixed_panel_built",
            text_attr="_intro_fixed_text",
            counter_attr="_intro_fixed_counter",
            current_attr="_current_intro_fixed",
            get_source=lambda self: self.hq_intro,
            get_string="get_fixed_string",
            bytes_used="fixed_string_bytes_used",
        ),
        "quest_exe_dos": dict(
            panel_attr="_quest_exe_dos_panel",
            built_attr="_quest_exe_dos_panel_built",
            text_attr="_quest_exe_dos_text",
            counter_attr="_quest_exe_dos_counter",
            current_attr="_current_quest_exe_dos",
            get_source=lambda self: self.hq_quest_exe,
            get_string="get_dos_string",
            bytes_used="dos_string_bytes_used",
        ),
    }

    def _build_fixed_string_panel(self, key):
        cfg = self._FIXED_STRING_PANELS[key]
        outer = getattr(self, cfg["panel_attr"])
        if outer.winfo_ismapped() and getattr(self, cfg["built_attr"]):
            return
        self._base_edit_frame.pack_forget()
        self._quest_map_panel.pack_forget()
        self._vga_panel.pack_forget()
        for other_key, other_cfg in self._FIXED_STRING_PANELS.items():
            if other_key != key:
                getattr(self, other_cfg["panel_attr"]).pack_forget()

        outer = getattr(self, cfg["panel_attr"])
        outer.pack(fill=tk.X)
        if getattr(self, cfg["built_attr"]):
            return
        setattr(self, cfg["built_attr"], True)

        header = tk.Frame(outer, bg=PAL["toolbar"])
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        tk.Label(header, text="SYSTEM STRING", font=("Consolas", 9, "bold"),
                 fg=PAL["box_txt"], bg=PAL["toolbar"]).pack(side=tk.LEFT)
        counter = tk.Label(
            header, text="", font=("Consolas", 9), fg=PAL["label"], bg=PAL["toolbar"])
        counter.pack(side=tk.RIGHT)
        setattr(self, cfg["counter_attr"], counter)

        text_frame = tk.Frame(outer, bg=PAL["toolbar"])
        text_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        text = tk.Text(
            text_frame, height=8, font=("Consolas", 10),
            bg=PAL["box_fill"], fg=PAL["text"], insertbackground=PAL["text"],
            relief=tk.FLAT, wrap="none", undo=True)
        text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb = tk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        text.configure(yscrollcommand=sb.set)
        text.bind("<KeyRelease>", lambda e, k=key: self._on_fixed_string_text_change(k, e))
        text.bind("<<Modified>>", lambda e, k=key: self._on_fixed_string_text_change(k, e))
        setattr(self, cfg["text_attr"], text)

    def _on_fixed_string_text_change(self, key, event=None):
        cfg = self._FIXED_STRING_PANELS[key]
        current = getattr(self, cfg["current_attr"])
        if current is None:
            return
        source = cfg["get_source"](self)
        fs = getattr(source, cfg["get_string"])(current)
        if fs is None:
            return
        text = getattr(self, cfg["text_attr"])
        new_text = text.get("1.0", "end-1c")
        if new_text != fs["text"]:
            self._push_undo()
            fs["text"] = new_text
        self._update_fixed_string_counter(key)
        self._update_status()
        try:
            text.edit_modified(False)
        except Exception:
            pass

    def _update_fixed_string_counter(self, key):
        cfg = self._FIXED_STRING_PANELS[key]
        counter = getattr(self, cfg["counter_attr"])
        current = getattr(self, cfg["current_attr"])
        if current is None:
            counter.config(text="")
            return
        source = cfg["get_source"](self)
        fs = getattr(source, cfg["get_string"])(current)
        if fs is None:
            return
        used = getattr(source, cfg["bytes_used"])(current)
        max_b = fs["max_bytes"]
        counter.config(
            text=f"{used}/{max_b} bytes",
            fg=PAL["accent"] if used > max_b else PAL["label"])

    def _show_base_edit_panel(self):
        if self._base_edit_frame.winfo_ismapped():
            return
        self._quest_map_panel.pack_forget()
        self._vga_panel.pack_forget()
        self._intro_fixed_panel.pack_forget()
        self._quest_exe_dos_panel.pack_forget()
        self._base_edit_frame.pack(fill=tk.X)
