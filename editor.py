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
    MAX_ROW, MAX_COL, MIN_ROW, MIN_COL, DRAG_THRESHOLD, FILE_TYPES, resource_path
)
from utils import (
    CHAR_DECODE, is_compressed_file, is_known_language_file, run_exe, encode_text, decode_text,
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
    VGA_WIDTH, VGA_HEIGHT, palette_to_rgb888, AVAILABLE_PALETTES,
    HQFxFile, _is_fx_file
)

from editor_fx import FxEditorMixin
from editor_vga import VgaEditorMixin
from editor_quest_map import QuestMapEditorMixin
from editor_lists import ListsEditorMixin
from editor_text import TextEditorMixin


class Editor(VgaEditorMixin, QuestMapEditorMixin, ListsEditorMixin, TextEditorMixin, FxEditorMixin):
    _MODE_DATA_ATTR = {
        "hq":        "hq",
        "quest":     "hq_quest",
        "paged":     "hq_paged",
        "intro":     "hq_intro",
        "quest_exe": "hq_quest_exe",
        "vga":       "hq_vga",
        "vga_multi": "hq_vga_multi",
        "fx":        "hq_fx",
    }

    UNDO_LEVELS = 100

    def __init__(self, root):
        self.root = root
        self.hq           = HQFile()
        self.hq_paged     = HQPagedFile()
        self.hq_quest     = HQQuestFile()
        self.hq_intro     = HQIntroFile()
        self.hq_quest_exe = HQQuestExeFile()
        self.hq_vga       = HQVgaFile()
        self.hq_vga_multi = HQMultiVgaFile()
        self.hq_fx        = HQFxFile()
        self._vga_multi_sprite_idx = None
        self.current_mode    = "hq"
        self._file_loaded    = False
        self._undo_stack     = []
        self._redo_stack     = []
        self._dirty          = False
        self._current_paged  = None
        self._current_intro_fixed = None
        self._current_quest_exe_tag = None
        self._current_quest_exe_dos = None
        self.current         = None
        self._quest_submode  = "text"
        self._pool_drag_active = False
        self._pool_drag_ghost  = None
        self._selected_monster_idx = None
        self._vga_tool        = "pixel"
        self._vga_color       = 0
        self._vga_zoom        = 2
        self._vga_brush_size  = 1
        self._vga_selection   = None
        self._vga_select_drag = None
        self._vga_photo       = None
        self._vga_pan_x       = 0
        self._vga_pan_y       = 0
        self._vga_pan_drag_start = None
        self._vga_clipboard   = None
        self._vga_paste_pending     = None
        self._vga_paste_drag_start  = None
        self._vga_panel_built_for_mode = None
        self.bg_image  = None
        self.bg_image2 = None
        self.bg_image3 = None
        self._show_bg  = False
        self._load_background()
        self._rebuilding = False
        self._drag_box         = False
        self._drag_line_idx    = None
        self._drag_sub_idx     = None
        self._drag_started     = False
        self._resize_active    = False
        self._drag_start_mouse = (0, 0)
        self._drag_start_pos   = (0, 0)
        self._drag_start_line  = (0, 0)
        self._drag_start_sub   = (0, 0)
        self._resize_start_mouse = (0, 0)
        self._resize_start_size  = (0, 0)
        self._select_after_id = None
        self._in_drag = False
        self._render_pending = False
        self.font_width, self.font_height, self.font_glyphs = load_dynamix_font_file(resource_path("heroquest.fnt"))
        self._glyph_imgs = self._prebuild_glyphs()
        self._build_ui()
        self._update_search_state()

    def _prebuild_glyphs(self):
        scale = max(1, CELL / self.font_width * 0.80)
        gw    = int(self.font_width  * scale)
        gh    = int(self.font_height * scale)
        self._glyph_w = gw
        self._glyph_h = gh

        result = {}
        for color in GLYPH_COLORS:
            for code in GLYPH_RANGE:
                glyph = self.font_glyphs.get(code)
                if glyph is None:
                    continue
                img = tk.PhotoImage(width=gw, height=gh)
                for j, row_bits in enumerate(glyph):
                    for i, px in enumerate(row_bits):
                        if px:
                            x0 = int(i * scale)
                            y0 = int(j * scale)
                            x1 = x0 + max(1, int(scale))
                            y1 = y0 + max(1, int(scale))
                            img.put(color, to=(x0, y0, x1, y1))
                result[(color, code)] = img
        return result

    def _load_background(self):
        base = resource_path()
        for attr, fname in [("bg_image", "background1.png"),
                             ("bg_image2", "background2.png"),
                             ("bg_image3", "background3.png")]:
            if getattr(self, attr) is None:
                try:
                    p = os.path.join(base, fname)
                    setattr(self, attr, tk.PhotoImage(file=p) if os.path.exists(p) else None)
                except Exception:
                    setattr(self, attr, None)

    def _on_right_configure(self, event):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _build_ui(self):
        self.root.title("HeroQuest Editor v6.8 — by TheRuler")
        self.root.configure(bg=PAL["bg"])
        self.root.minsize(1100, 660)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._setup_drag_and_drop()

        #TOOLBAR
        tb = tk.Frame(self.root, bg=PAL["toolbar"], pady=8, padx=10)
        tb.pack(fill=tk.X, side=tk.TOP)
        for lbl, cmd in [("💾▶\nLOAD", self._open_file), ("💾◀\nSAVE", self._save_file), ("↶\nUNDO", self._undo), ("↷\nREDO", self._redo)]:
            tk.Button(tb, text=lbl, command=cmd, bg=PAL["btn"], fg=PAL["text"], activebackground=PAL["btn_hover"], activeforeground=PAL["text"],
                      relief=tk.RAISED, font=("Consolas", 12), cursor="hand2").pack(side=tk.LEFT, padx=2)

        self._drag_hint = tk.Label(tb, text="", font=("Consolas", 12), fg=PAL["box_txt"], bg=PAL["toolbar"])
        self._status = tk.StringVar(value="No file loaded")
        self._status_label = tk.Label(tb, textvariable=self._status, font=("Consolas", 9), fg=PAL["label"], bg=PAL["toolbar"])
        self._status_label.pack(side=tk.RIGHT, padx=10)

        main = tk.Frame(self.root, bg=PAL["bg"])
        main.pack(fill=tk.BOTH, expand=True)

        #LEFT
        left = tk.Frame(main, bg=PAL["toolbar"], width=280)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        ff = tk.Frame(left, bg=PAL["toolbar"])
        ff.pack(fill=tk.X, padx=6, pady=4)
        self._search_frame = ff
        self._search_label = tk.Label(ff, text="SEARCH:", font=("Consolas", 10, "bold"), fg=PAL["box_txt"], bg=PAL["toolbar"], anchor="w", padx=8, pady=4)
        self._search_label.pack(side=tk.LEFT)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_filter)
        self._search_entry = tk.Entry(ff, textvariable=self._filter_var, bg=PAL["grid"], fg=PAL["text"], insertbackground=PAL["text"], relief=tk.GROOVE, font=("Consolas", 9))
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        sb = tk.Scrollbar(left, bg=PAL["toolbar"])
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(
            left, yscrollcommand=sb.set,
            bg=PAL["toolbar"], fg=PAL["text"],
            selectbackground=PAL["accent"], selectforeground="#000",
            activestyle="none", font=("Consolas", 9),
            relief=tk.FLAT, borderwidth=0, highlightthickness=0, exportselection=0)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self._list_indices = []

        #RIGHT
        right_container = tk.Frame(main, bg=PAL["bg"])
        right_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        #DRAW CANVAS — fixed, not scrollable
        self.canvas = tk.Canvas(
            right_container,
            width=max(GRID_COLS * CELL, 26*28+4), height=max(GRID_ROWS * CELL, 19*28+4),
            bg=PAL["bg"], highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side=tk.TOP, fill=tk.X)

        #SCROLLABLE EDIT PANEL below the canvas
        scroll_area = tk.Frame(right_container, bg=PAL["bg"])
        scroll_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.scroll_canvas = tk.Canvas(scroll_area, bg=PAL["bg"], highlightthickness=0)
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scrollbar = tk.Scrollbar(scroll_area, orient="vertical", command=self.scroll_canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_canvas.configure(yscrollcommand=v_scrollbar.set)

        self.right_frame = tk.Frame(self.scroll_canvas, bg=PAL["bg"])
        self.right_frame.columnconfigure(0, weight=1)
        self.scroll_canvas.create_window((0, 0), window=self.right_frame, anchor="nw")
        self.right_frame.bind("<Configure>", self._on_right_configure)

        #EDIT PANEL
        self._edit_frame_container = tk.Frame(self.right_frame, bg=PAL["toolbar"])
        self._edit_frame_container.grid(row=0, column=0, sticky="ew")

        self.canvas.bind("<Button-1>",        self._on_click)
        self.canvas.bind("<B1-Motion>",       self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<B3-Motion>",       self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<Motion>",          self._on_mouse_motion)
        self.canvas.bind("<Leave>",           self._on_mouse_leave)
        self.canvas.bind("<Configure>",       lambda e: self._render())
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>",        self._on_right_click)
        self.canvas.bind("<MouseWheel>",      self._on_vga_mousewheel)
        self.canvas.bind("<Button-2>",        self._vga_pan_button_press)
        self.canvas.bind("<B2-Motion>",       self._vga_pan_button_drag)
        self.canvas.bind("<ButtonRelease-2>", self._vga_pan_button_release)
        self.root.bind("<Control-c>", self._on_ctrl_c)
        self.root.bind("<Control-C>", self._on_ctrl_c)
        self.root.bind("<Control-v>", self._on_ctrl_v)
        self.root.bind("<Control-V>", self._on_ctrl_v)
        self.root.bind("<Control-z>", self._on_ctrl_z)
        self.root.bind("<Control-Z>", self._on_ctrl_z)
        self.root.bind("<Control-y>", self._on_ctrl_y)
        self.root.bind("<Control-Y>", self._on_ctrl_y)
        self.root.bind("<Control-Shift-Z>", self._on_ctrl_y)
        self.root.bind("<Control-Shift-z>", self._on_ctrl_y)
        self.root.bind("<Control-o>", self._on_ctrl_o)
        self.root.bind("<Control-O>", self._on_ctrl_o)
        self.root.bind("<Control-s>", self._on_ctrl_s)
        self.root.bind("<Control-S>", self._on_ctrl_s)
        self.root.bind("<Control-h>", self._on_ctrl_h)
        self.root.bind("<Control-H>", self._on_ctrl_h)
        self.root.bind("<Return>", self._on_vga_paste_confirm)
        self.root.bind("<Escape>", self._on_vga_paste_cancel)
        self.root.bind("<Delete>", self._on_vga_delete_key)

        def _on_mousewheel(e):
            top, bottom = self.scroll_canvas.yview()
            if top <= 0.0 and bottom >= 1.0:
                return
            self.scroll_canvas.yview_scroll(int(-e.delta / 120), "units")
            return "break"

        def _bind_mousewheel(e):
            self.root.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(e):
            self.root.unbind_all("<MouseWheel>")

        scroll_area.bind("<Enter>", _bind_mousewheel)
        scroll_area.bind("<Leave>", _unbind_mousewheel)

        self._build_edit_panel()

    def _build_edit_panel(self):
        self._base_edit_frame = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"], pady=6, padx=10)
        self._base_edit_frame.pack(fill=tk.X)
        ef = self._base_edit_frame
        self._lines_frame = tk.Frame(ef, bg=PAL["toolbar"])
        self._lines_frame.grid(row=1, column=1, columnspan=16, sticky="nw", padx=(10, 0), pady=(4, 0))
        self._line_entries = []
        self._add_line_btn = tk.Button(
            ef, text="Add line", font=("Consolas", 8),
            bg=PAL["btn"], fg=PAL["text"], relief=tk.RAISED,
            command=self._add_line, cursor="hand2")
        self._add_line_btn.grid(row=1, column=20, sticky="e", padx=20)
        self._add_line_btn.grid_remove()
        self._quest_map_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"])
        self._vga_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"])
        self._intro_fixed_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"])
        self._intro_fixed_panel_built = False
        self._quest_exe_dos_panel = tk.Frame(self._edit_frame_container, bg=PAL["toolbar"])
        self._quest_exe_dos_panel_built = False

    def _reset_mode(self):
        self.current_mode    = "hq"
        self._undo_stack      = []
        self._redo_stack      = []
        self._current_paged  = None
        self._current_intro_fixed = None
        self._current_quest_exe_tag = None
        self._current_quest_exe_dos = None
        self.current         = None
        self._show_bg        = False
        self._quest_submode  = "text"
        self._pool_drag_active = False
        self._pool_drag_ghost  = None
        self._selected_monster_idx = None
        self._vga_tool        = "pixel"
        self._vga_selection   = None
        self._vga_select_drag = None
        self._vga_pan_x       = 0
        self._vga_pan_y       = 0
        self._vga_pan_drag_start = None
        self._vga_paste_pending    = None
        self._vga_paste_drag_start = None
        self._vga_multi_sprite_idx = None
        self._vga_panel_built_for_mode = None
        self._fx_selected_idx = None
        self._fx_panel_built  = False
        if hasattr(self, "_fx_panel"):
            self._fx_panel.pack_forget()
        if hasattr(self, "canvas"):
            self.canvas.config(cursor="crosshair")
        if hasattr(self, "_quest_map_panel"):
            try:
                self._show_base_edit_panel()
            except Exception:
                pass

    def _push_undo(self):
        attr = self._MODE_DATA_ATTR.get(self.current_mode)
        if attr is None:
            return
        snapshot = copy.deepcopy(getattr(self, attr))
        self._undo_stack.append((self.current_mode, snapshot))
        if len(self._undo_stack) > self.UNDO_LEVELS:
            self._undo_stack.pop(0)
        self._redo_stack = [
            (mode, snap) for (mode, snap) in self._redo_stack
            if mode != self.current_mode
        ]
        self._dirty = True

    def _discard_last_undo_if_unchanged(self):
        if not self._undo_stack:
            return
        mode, snapshot = self._undo_stack[-1]
        if mode != self.current_mode:
            return
        attr = self._MODE_DATA_ATTR.get(mode)
        if attr is None:
            return
        current = getattr(self, attr)
        try:
            unchanged = (current.__dict__ == snapshot.__dict__)
        except Exception:
            unchanged = False
        if unchanged:
            self._undo_stack.pop()
            if not self._undo_stack:
                self._dirty = False

    def _mark_saved(self):
        self._dirty = False

    def _confirm_discard_changes(self):
        if not getattr(self, "_dirty", False):
            return True
        fname = os.path.basename(self._current_path) if hasattr(self, "_current_path") else "this file"
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"\"{fname}\" has unsaved changes.\nDo you want to save before continuing?")
        if answer is None:
            return False
        if answer:
            self._save_file()
            return not getattr(self, "_dirty", False)
        return True

    def _undo(self):
        for i in range(len(self._undo_stack) - 1, -1, -1):
            mode, snapshot = self._undo_stack[i]
            if mode == self.current_mode:
                attr = self._MODE_DATA_ATTR.get(mode)
                if attr is not None:
                    current_snapshot = copy.deepcopy(getattr(self, attr))
                    self._redo_stack.append((mode, current_snapshot))
                    if len(self._redo_stack) > self.UNDO_LEVELS:
                        self._redo_stack.pop(0)
                    setattr(self, attr, snapshot)
                del self._undo_stack[i]
                self._dirty = bool(self._undo_stack)
                self._render()
                self._update_status()
                if self.current_mode == "vga":
                    self._vga_clamp_pan()
                elif self.current_mode == "vga_multi":
                    source = self._vga_render_source()
                    if source is not None:
                        self._vga_clamp_pan(source[0], source[1])
                else:
                    self._on_select(None)
                    if self.current_mode == "quest" and getattr(self, "_quest_submode", None) == "events":
                        self._sync_event_combo_to_selected_room()
                return

    def _redo(self):
        for i in range(len(self._redo_stack) - 1, -1, -1):
            mode, snapshot = self._redo_stack[i]
            if mode == self.current_mode:
                attr = self._MODE_DATA_ATTR.get(mode)
                if attr is not None:
                    current_snapshot = copy.deepcopy(getattr(self, attr))
                    self._undo_stack.append((mode, current_snapshot))
                    if len(self._undo_stack) > self.UNDO_LEVELS:
                        self._undo_stack.pop(0)
                    setattr(self, attr, snapshot)
                del self._redo_stack[i]
                self._dirty = True
                self._render()
                self._update_status()
                if self.current_mode == "vga":
                    self._vga_clamp_pan()
                elif self.current_mode == "vga_multi":
                    source = self._vga_render_source()
                    if source is not None:
                        self._vga_clamp_pan(source[0], source[1])
                else:
                    self._on_select(None)
                    if self.current_mode == "quest" and getattr(self, "_quest_submode", None) == "events":
                        self._sync_event_combo_to_selected_room()
                return

    _SAVE_CONFIG = {
        "intro":     {"ext": ".exe", "ftypes": [("Executable", "*.exe"), ("All files", "*.*")],
                      "rebuild": lambda self: self.hq_intro.rebuild(),
                      "msg": lambda self, data: f"Saved {len(data)} bytes\nText: {self.hq_intro.bytes_used()}/{INTRO_MAX_BYTES} bytes used"},
        "quest_exe": {"ext": ".exe", "ftypes": [("Executable", "*.exe"), ("All files", "*.*")],
                      "rebuild": lambda self: self.hq_quest_exe.rebuild(),
                      "msg": lambda self, data: f"Saved {len(data)} bytes"},
        "quest":     {"ext": ".bin", "ftypes": [("Bin file", "*.bin"), ("All files", "*.*")],
                      "rebuild": lambda self: self.hq_quest.rebuild(),
                      "msg": lambda self, data: f"Saved {len(data)} bytes"},
        "paged":     {"ext": ".bin", "ftypes": [("Bin file", "*.bin"), ("All files", "*.*")],
                      "rebuild": lambda self: self.hq_paged.rebuild(),
                      "msg": lambda self, data: f"Saved {len(data)} bytes"},
        "fx": {"ext": None, "ftypes": None,
                    "rebuild": lambda self: self.hq_fx.rebuild(),
                    "msg": lambda self, data: f"Saved {len(data)} bytes ({len(self.hq_fx.effects)} effetti)"},
    }

    def _save_file(self):
        if not getattr(self, "_file_loaded", False):
            return
        cfg = self._SAVE_CONFIG.get(self.current_mode)
        if self.current_mode in ("vga", "vga_multi"):
            ext, ftypes = ".vga", [("VGA raw image", "*.vga"),
                                    ("UNP files (uncompressed)", "*.unp"),
                                    ("All files", "*.*")]
        elif self.current_mode == "fx":
            ext = os.path.splitext(self._current_path)[1] or ".alb"
            ftypes = FX_FILE_TYPES
        else:
            ext    = cfg["ext"] if cfg else ".bin"
            ftypes = cfg["ftypes"] if cfg else FILE_TYPES

        initial_name = os.path.basename(self._current_path) if hasattr(self, '_current_path') else ""
        path = filedialog.asksaveasfilename(initialfile=initial_name,defaultextension=ext,filetypes=ftypes)
        if not path: return

        try:
            if self.current_mode == "vga":
                self.hq_vga.save(path)
                data = self.hq_vga.raw
                msg  = f"Saved {VGA_WIDTH}x{VGA_HEIGHT} image ({len(data)} bytes raw)"
            elif self.current_mode == "vga_multi":
                self.hq_vga_multi.save(path)
                n = len(self.hq_vga_multi.sprites)
                msg = f"Saved {n} sprites ({self.hq_vga_multi.get_total_size()} bytes raw)"
            elif cfg:
                data = cfg["rebuild"](self)
                msg  = cfg["msg"](self, data)
                with open(path, "wb") as f:
                    f.write(data)
            else:
                raw_data = self.hq.rebuild()
                is_bin   = is_compressed_file(path)
                data     = run_exe("enc.exe", raw_data) if is_bin else raw_data
                msg      = f"New file size: {len(data)} bytes"
                with open(path, "wb") as f:
                    f.write(data)
            if self.current_mode == "hq":
                self.hq.load(path)
                self.current  = None
                self._show_bg = False
                self._render()
            self._populate_list()
            self._select_first()
            self._update_status()
            self._mark_saved()
            messagebox.showinfo("Saved", msg)
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def _load_intro(self, path, basename):
        self.hq_intro.load(path)
        return f"intro | {self.hq_intro.bytes_used()}/{INTRO_MAX_BYTES} bytes"

    def _load_quest_exe(self, path, basename):
        self.hq_quest_exe.load(path)
        qe = self.hq_quest_exe
        total = len(qe.pos_strings) + len(qe.page_blocks) + len(qe.plain_strings) + len(qe.dos_strings)
        return f"quest.exe | {total} strings"

    def _load_quest(self, path, basename):
        self._quest_filename = os.path.splitext(basename)[0].upper()
        self.hq_quest.load(path)
        self._ensure_object_groups(self.hq_quest)
        return f"quest | {len(self.hq_quest.text_lines)} text lines"

    def _load_paged(self, path, basename):
        self.hq_paged.load(path)
        return f"quests | {len(self.hq_paged.pages)} pages"

    def _load_hq(self, path, basename):
        self.hq.load(path)
        return f"{self.hq.get_total_size()}/16701 bytes"

    def _load_vga(self, path, basename):
        self.hq_vga.load(path)
        comp = "compressed" if self.hq_vga.is_compressed else "raw"
        return f"vga | {VGA_WIDTH}x{VGA_HEIGHT} ({comp})"

    def _load_vga_multi(self, path, basename):
        self.hq_vga_multi.load(path)
        comp = "compressed" if self.hq_vga_multi.is_compressed else "raw"
        n = len(self.hq_vga_multi.sprites)
        return f"vga_multi | {n} sprites ({comp})"
    def _load_fx(self, path, basename):
        return FxEditorMixin._load_fx(self, path, basename)

    _FORMAT_DETECTORS = [
        ("intro",     _is_intro_file,     _load_intro),
        ("quest_exe", _is_quest_exe_file, _load_quest_exe),
        ("quest",     _is_quest_file,     _load_quest),
        ("paged",     _is_paged_file,     _load_paged),
        ("vga_multi", _is_multi_vga_file, _load_vga_multi),
        ("vga",       _is_vga_file,       _load_vga),
        ("fx",        _is_fx_file,        _load_fx),
        ("hq",        lambda path: os.path.basename(path).upper().endswith(".BIN") or is_compressed_file(path) or is_known_language_file(path), _load_hq),
    ]

    _SEARCH_ENABLED_MODES = {"hq", "vga_multi"}

    def _update_search_state(self):
        if not hasattr(self, "_search_frame"):
            return
        enabled = self._file_loaded and self.current_mode in self._SEARCH_ENABLED_MODES
        if enabled:
            if not self._search_frame.winfo_ismapped():
                self._search_frame.pack(fill=tk.X, padx=6, pady=4, before=self.listbox)
        else:
            self._filter_var.set("")
            self._search_frame.pack_forget()

    def _setup_drag_and_drop(self):
        if not _DND_AVAILABLE:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_file_drop)
        except Exception:
            pass

    def _on_file_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return
        path = paths[0]
        if not os.path.isfile(path):
            return
        if not self._confirm_discard_changes():
            return
        self._load_file_path(path)

    def _on_close_request(self):
        if self._confirm_discard_changes():
            self.root.destroy()

    def _open_file(self):
        if not self._confirm_discard_changes():
            return
        path = filedialog.askopenfilename(filetypes=self._build_open_filetypes())
        if not path: return
        self._load_file_path(path)

    def _load_file_path(self, path):
        try:
            self._current_path = path
            self._reset_mode()
            basename = os.path.basename(path)

            for mode, detector, loader in self._FORMAT_DETECTORS:
                if detector(path):
                    self.current_mode = mode
                    info = loader(self, path, basename)
                    break
            else:
                messagebox.showerror("File \"{basename}\" unsupported.")
                return

            self._file_loaded = True
            self._update_search_state()
            self._mark_saved()
            self._populate_list()
            self._select_first()
            self._update_status()
        except Exception as e: messagebox.showerror("Open error", str(e))

    ROLL_H = CELL

    def _schedule_render(self):
        if not self._render_pending:
            self._render_pending = True
            self.root.after_idle(self._do_render)

    def _render(self):
        self._schedule_render()

    def _schedule_select_render(self):
        if self._select_after_id is not None:
            self.root.after_cancel(self._select_after_id)
        def _run():
            self._select_after_id = None
            self._render()
        self._select_after_id = self.root.after_idle(_run)

    def _draw_text_at(self, c, col, row, text, color):
        x = col * CELL
        y = row * CELL + (CELL - self._glyph_h) // 2
        for ch in text:
            code = self.char_to_font_code(ch)
            img  = self._glyph_imgs.get((color, code)) if code is not None else None
            if img:
                c.create_image(x, y, image=img, anchor="nw")
            x += self._glyph_w + 4

    def char_to_font_code(self, ch):
        for k, v in CHAR_DECODE.items():
            if v == ch:
                return k
        return ord(ch) if ord(ch) < 128 else None

    def _render_with_grid(self, bg_image=None):
        c = self.canvas
        c.delete("all")
        self._load_background()
        if bg_image:
            c.create_image(0, 0, image=bg_image, anchor="nw")
        _draw_grid(c)

    def _render_lines(self, c, lines, color, key_row="row", key_col="col"):
        for l in lines:
            row = l.get(key_row, l.get("row", 0))
            col = l.get(key_col, l.get("col", 0))
            tx = col * CELL
            ty = row * CELL
            txt = l["text"]
            c.create_rectangle(tx, ty, tx + len(txt)*CELL, ty + CELL, fill="", outline="#334455", dash=(2, 4))
            self._draw_text_at(c, l[key_col], l[key_row], txt, color)

    def _render_paged(self, page):
        self._render_with_grid(self.bg_image3)
        self._render_lines(self.canvas, page.get("lines", []), PAL["page_txt"])

    def _render_intro(self, page):
        self._render_with_grid(self.bg_image2)
        self._render_lines(self.canvas, page.get("lines", []), PAL["box_txt"])

    def _render_quest(self):
        submode = getattr(self, "_quest_submode", "text")
        if submode in ("map", "m&h", "objects", "events"):
            self._render_quest_map()
        else:
            self._render_with_grid(self.bg_image3)
            self._render_lines(self.canvas, self.hq_quest.text_lines, PAL["page_txt"], key_row="row", key_col="col")

    def _render_quest_exe(self):
        self.canvas.delete("all")
        if self._current_quest_exe_dos is not None:
            return
        tag = self._current_quest_exe_tag
        if tag is None: return
        kind, i = tag
        qe = self.hq_quest_exe

        if kind == "pos":
            entry = qe.pos_strings[i]
            self._render_lines(self.canvas, entry["lines"], PAL["text"])
        elif kind == "page":
            self._render_with_grid(self.bg_image3)
            self._render_lines(self.canvas, qe.page_blocks[i]["lines"], PAL["page_txt"])
        elif kind == "plain":
            txt = qe.plain_strings[i]["text"]
            self._render_with_grid(self.bg_image3)
            self._draw_text_at(self.canvas, 2, 2, txt, PAL["text"])

    def _do_render(self):
        self._render_pending = False
        c    = self.canvas
        cell = CELL
        rh   = self.ROLL_H

        c.delete("all")

        if self.current_mode == "intro":
            if self._current_paged is not None:
                page = self.hq_intro.get_page(self._current_paged)
                if page: self._render_intro(page)
            return

        if self.current_mode == "quest_exe":
            self._render_quest_exe()
            return

        if self.current_mode == "paged":
            if self._current_paged is not None:
                page = self.hq_paged.get_page(self._current_paged)
                if page: self._render_paged(page)
            return

        if self.current_mode == "quest":
            self._render_quest()
            return

        if self.current_mode == "vga":
            self._render_vga()
            return

        if self.current_mode == "vga_multi":
            self._render_vga_multi()
            return

        if self.current_mode == "fx":
            self._render_fx()
            return

        if self._show_bg and self.bg_image:
            c.create_image(0, 0, image=self.bg_image, anchor="nw")
        _draw_grid(c)
            
        if self.current is None: return
        b = self._get_block(self.current)
        if not b:
            self.current = None
            return
        t = b.get("type", "null")

        if t in ("empty", "null"):
            gw = GRID_COLS * cell
            gh = GRID_ROWS * cell
            c.create_text(gw // 2, gh // 2, text=f"[{t}]", fill=PAL["label"], font=("Consolas", 12))
            return

        if t == "btn_label":
            self._draw_text_at(c, 2, 2, b.get("text", ""), PAL["opt"])
            return

        if t == "text_pos":
            for l in b.get("lines", []):
                txt = l.get("text", "")
                x   = l.get("col", 2) * cell
                y   = l.get("row", 2) * cell
                c.create_rectangle(x - 2, y - 2, x + len(txt)*cell + 2, y + cell + 2, outline=PAL["text"], fill="", dash=(4, 2))
                self._draw_text_at(c, l.get("col", 2), l.get("row", 2), txt, PAL["text"])
            return

        if t == "text_plain":
            for seg in b.get("segments", []):
                txt = seg.get("text", "")
                row = seg.get("row")
                col = seg.get("col")
                if row is not None:
                    tx = col * cell
                    ty = row * cell
                    c.create_rectangle(tx, ty, tx + len(txt)*cell, ty + cell, fill="", outline=PAL["text"], dash=(2, 4))
                    self._draw_text_at(c, col, row, txt, PAL["text"])
                else:
                    self._draw_text_at(c, 1, 1, txt, PAL["accent"])
            return

        if t != "box":
            c.create_text(8, 8, text=f"[{t}]", fill=PAL["label"], font=("Consolas", 10), anchor="nw")
            return

        col, row = b.get("col", 1), b.get("row", 1)
        w,   h   = b.get("w",   4), b.get("h",   4)

        bx1 = col * cell;        by1 = row * cell
        bx2 = bx1 + w * cell;    by2 = by1 + (h - 2) * cell
        ow  = cell // 2
        rx1, rx2 = bx1 - ow, bx2 + ow
        ry_top1  = by1 - rh
        ry_bot2  = by2 + rh

        c.create_rectangle(bx1 - 10, by1, bx2 + 10, by2, fill=PAL["box_fill"], outline="#005533", width=2)
        draw_cylinder_roll(c, rx1, ry_top1 - 15, rx2, by1, "#0d3a2a")
        c.create_rectangle(rx1 - 40, ry_top1 - 15, rx2 + 40, by1, fill="", outline="#00cc88", width=1)
        c.create_line(bx1 - 10, by1 + 1, bx1 - 10, ry_top1 - 15, fill="#005533", width=3)
        c.create_line(bx2 + 10, by1 + 1, bx2 + 10, ry_top1 - 15, fill="#005533", width=3)
        draw_cylinder_roll(c, rx1, by2, rx2, ry_bot2 + 15, "#0d3a2a")
        c.create_rectangle(rx1 - 40, by2, rx2 + 40, ry_bot2 + 15, fill="", outline="#00cc88", width=1)
        c.create_line(bx1 - 10, by2, bx1 - 10, ry_bot2 + 17, fill="#005533", width=3)
        c.create_line(bx2 + 10, by2, bx2 + 10, ry_bot2 + 17, fill="#005533", width=3)

        tri = 12
        c.create_polygon(bx2 - tri + 9, by2 - 1, bx2 + 9, by2 - 1, bx2 + 9, by2 - tri - 1, fill=PAL["accent"])

        for li, l in enumerate(b.get("lines", [])):
            tx  = l["col"] * cell
            ty  = l["row"] * cell
            txt = l["text"]
            c.create_rectangle(tx, ty, tx + len(txt)*cell, ty + cell, fill="", outline="#334455", dash=(2, 4))
            self._draw_text_at(c, l["col"], l["row"], txt, PAL["box_txt"])

        for se in b.get("sub_entries", []):
            ptr = se["ptr"]
            if ptr == 0: continue
            txt = self.hq.get_btn_text(ptr)
            if txt is None:
                if ptr >= len(self.hq.raw): 
                    txt = ""
                else:
                    txt = f"[0x{ptr:04X}]"
            sx  = se["col"] * cell
            sy  = se["row"] * cell
            tw  = max(1, len(txt)) * cell
            c.create_rectangle(sx, sy, sx + tw, sy + cell, fill="#002218", outline=PAL["opt"], dash=(3, 2))
            if txt:
                self._draw_text_at(c, se["col"], se["row"], txt, PAL["opt"])

    def _reset_drag_state(self):
        self._drag_box       = False
        self._drag_line_idx  = None
        self._drag_sub_idx   = None
        self._drag_started   = False
        self._resize_active  = False
        self._drag_plain_idx = None

    def _clamp_box(self, col, row, w, h):
        col = max(MIN_COL, min(col, MAX_COL - w))
        row = max(MIN_ROW, min(row, MAX_ROW - h))
        return col, row

    def _mouse_delta_cells(self, ex, ey):
        mx, my = self._drag_start_mouse
        return round((ex - mx) / CELL), round((ey - my) / CELL)

    def _on_right_click(self, e):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_on_right_click(e)
            return
        if self.current_mode == "quest" and getattr(self, "_quest_submode", "text") in ("map", "m&h", "objects", "events"):
            self._quest_map_click(e.x, e.y, button=3)

    def _on_right_drag(self, e):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_on_right_click(e)
            return
        self._on_drag(e)

    def _on_right_release(self, e):
        if self.current_mode in ("vga", "vga_multi"):
            return
        self._on_release(e)

    def _on_double_click(self, e):
        self._reset_drag_state()
        lines, key_r, key_c = [], "row", "col"
        if self.current_mode == "paged":
            page = self.hq_paged.get_page(self._current_paged)
            if page: lines = page.get("lines", [])
        elif self.current_mode == "intro":
            page = self.hq_intro.get_page(self._current_paged)
            if page: lines = page.get("lines", [])
        elif self.current_mode == "quest":
            if getattr(self, "_quest_submode", "") != "text":
                self._on_click(e)
                return
            lines, key_r, key_c = self.hq_quest.text_lines, "row", "col"
        elif self.current_mode == "quest_exe":
            tag = self._current_quest_exe_tag
            if tag is None: return
            kind, i = tag
            qe = self.hq_quest_exe
            if   kind == "pos":   lines = qe.pos_strings[i]["lines"]
            elif kind == "page":  lines = qe.page_blocks[i]["lines"]
            elif kind == "plain":
                self._focus_line_entry(qe.plain_strings[i]["text"]); return
        else:
            if self.current is None: return
            b = self._get_block(self.current)
            if not b or b.get("type") != "box": return
            for se in b.get("sub_entries", []):
                ptr = se["ptr"]
                if ptr == 0: continue
                txt = self.hq.get_btn_text(ptr) or ""
                sx, sy = se["col"] * CELL, se["row"] * CELL
                if sx <= e.x <= sx + max(1, len(txt))*CELL and sy <= e.y <= sy + CELL:
                    if ptr in [self._get_block(idx).get("ptr") for idx in self._list_indices]:
                        list_pos = next(i for i, idx in enumerate(self._list_indices)
                                        if self._get_block(idx) and self._get_block(idx).get("ptr") == ptr)
                        self.listbox.selection_clear(0, tk.END)
                        self.listbox.selection_set(list_pos)
                        self.listbox.see(list_pos)
                        self._on_select(None)
                    return
            lines = b.get("lines", [])
        for line in lines:
            lx, ly = line[key_c] * CELL, line[key_r] * CELL
            txt = line.get("text", "")
            if lx <= e.x <= lx + max(1, len(txt))*CELL and ly <= e.y <= ly + CELL:
                self._focus_line_entry(txt)
                return

    def _focus_line_entry(self, text):
        for i, (rv, cv, tv, has_pos) in enumerate(self._line_entries):
            if tv.get() == text:
                entry_widget = None
                col = 4
                for widget in self._lines_frame.grid_slaves(row=i, column=col):
                    entry_widget = widget
                    break
                if entry_widget:
                    entry_widget.focus_set()
                    entry_widget.selection_range(0, tk.END)
                    self.root.update_idletasks()
                    y = entry_widget.winfo_y() + self._lines_frame.winfo_y()
                    canvas_h = self.scroll_canvas.winfo_height()
                    total_h  = self.right_frame.winfo_height()
                    fraction = max(0.0, (y - canvas_h // 2) / total_h)
                    self.scroll_canvas.yview_moveto(fraction)
                return

    def _on_click(self, e):
        if self.current_mode == "vga":
            self._vga_on_click(e)
            return
        if self.current_mode == "vga_multi":
            self._vga_on_click(e)
            return
        if self.current_mode == "quest" and getattr(self, "_quest_submode", "text") in ("map", "m&h", "objects", "events"):
            self._quest_map_click(e.x, e.y)
            return
        lines, _ = self._get_current_text_context()
        cell = CELL
        if lines:
            for li, l in enumerate(lines):
                row = l.get("row")
                col = l.get("col")
                if row is None or col is None:
                    continue
                text = l.get("text", "")
                w = max(1, len(text)) * cell
                h = cell
                lx, ly = col * cell, row * cell
                if lx <= e.x <= lx + w and ly <= e.y <= ly + h:
                    self._push_undo()
                    self._drag_line_idx = li
                    self._drag_start_mouse = (e.x, e.y)
                    self._drag_start_line = (row, col)
                    return
        b = self._get_block(self.current)
        if not b or b.get("type") not in ("box", "text_plain", "text_pos"):
            return
        if b.get("type") == "text_plain":
            cell = CELL
            for li, seg in enumerate(b.get("segments", [])):
                if seg.get("row") is None: continue
                sx = seg["col"] * cell; sy = seg["row"] * cell
                sw = max(1, len(seg["text"])) * cell
                if sx <= e.x <= sx + sw and sy <= e.y <= sy + cell:
                    self._push_undo()
                    self._drag_line_idx    = li
                    self._drag_start_mouse = (e.x, e.y)
                    self._drag_start_line  = (seg["row"], seg["col"])
                    return
            return
        if b.get("type") == "text_pos":
            return

        cell = CELL
        rh   = self.ROLL_H
        col, row, w, h = b["col"], b["row"], b["w"], b["h"]
        bx1 = col*cell; by1 = row*cell
        bx2 = bx1 + w*cell; by2 = by1 + (h-2)*cell
        ow  = cell // 2
        ry_top1 = by1 - rh; ry_bot2 = by2 + rh

        tri = 12
        if bx2 - tri + 10 <= e.x <= bx2 + 10 and by2 - tri - 1 <= e.y <= by2 - 1:
            self._push_undo()
            self._resize_active      = True
            self._resize_start_mouse = (e.x, e.y)
            self._resize_start_size  = (w, h)
            return

        for li, l in enumerate(b.get("lines", [])):
            lx  = l["col"] * cell; ly = l["row"] * cell
            lw  = len(l["text"]) * cell
            if lx <= e.x <= lx + lw and ly <= e.y <= ly + cell:
                self._push_undo()
                self._drag_line_idx    = li
                self._drag_start_mouse = (e.x, e.y)
                self._drag_start_line  = (l["row"], l["col"])
                return

        for si, se in enumerate(b.get("sub_entries", [])):
            sx  = se["col"] * cell; sy = se["row"] * cell
            txt = self.hq.get_btn_text(se["ptr"]) or ""
            tw  = max(1, len(txt)) * cell
            if sx <= e.x <= sx + tw and sy <= e.y <= sy + cell:
                self._push_undo()
                self._drag_sub_idx     = si
                self._drag_start_mouse = (e.x, e.y)
                self._drag_start_sub   = (se["row"], se["col"])
                return

        if (bx1 - ow - 40 <= e.x <= bx2 + ow + 40
                and ry_top1 - 15 <= e.y <= ry_bot2 + 17):
            self._push_undo()
            self._drag_box         = True
            self._drag_start_mouse = (e.x, e.y)
            self._drag_start_pos   = (col, row)

    def _on_drag(self, e):
        
        if self.current_mode == "quest":
            self._quest_map_hide_tooltip()
            self.canvas.delete("invalid_target_x")
        self._in_drag = True
        
        if self.current_mode == "vga":
            self._vga_on_drag(e)
            return
        if self.current_mode == "vga_multi":
            self._vga_on_drag(e)
            return
        if self.current_mode == "quest" and getattr(self, "_quest_submode", "text") in ("map", "m&h", "objects", "events"):
            self._quest_map_drag(e.x, e.y)
            return

        lines, render_fn = self._get_current_text_context()
        if lines is not None and self._drag_line_idx is not None:
            dx, dy = self._mouse_delta_cells(e.x, e.y)
            sr, sc = self._drag_start_line
            li = self._drag_line_idx
            
            if li < len(lines):
                new_row = max(0, min(sr + dy, MAX_ROW))
                new_col = max(0, min(sc + dx, MAX_COL))
                if "row" in lines[li]: lines[li]["row"] = new_row
                if "col" in lines[li]: lines[li]["col"] = new_col
                
                if li < len(self._line_entries):
                    rv, cv, tv, has_pos = self._line_entries[li]
                    if has_pos:
                        rv.set(new_row); cv.set(new_col)
            
            if self.current is not None and self._get_block(self.current).get("type") in ("box", "text_plain"):
                 if not self._drag_started:
                     raw_dx, raw_dy = e.x - self._drag_start_mouse[0], e.y - self._drag_start_mouse[1]
                     if abs(raw_dx) < DRAG_THRESHOLD and abs(raw_dy) < DRAG_THRESHOLD: return
                     self._drag_started = True

            render_fn()
            return

        if self.current is None: return
        b = self._get_block(self.current)
        if not b: return
        
        if b.get("type") == "text_plain" and self._drag_line_idx is not None:
            dx, dy = self._mouse_delta_cells(e.x, e.y)
            sr, sc = self._drag_start_line
            new_row = max(0, min(sr + dy, MAX_ROW))
            new_col = max(0, min(sc + dx, MAX_COL))

            segs = b["segments"]
            li   = self._drag_line_idx
            if li < len(segs):
                segs[li]["row"] = new_row
                segs[li]["col"] = new_col
                if li < len(self._line_entries):
                    rv, cv, tv, _ = self._line_entries[li]
                    rv.set(new_row); cv.set(new_col)
            self._render()
            return

        dx, dy = self._mouse_delta_cells(e.x, e.y)

        if self._drag_box:
            new_col, new_row = self._clamp_box(
                self._drag_start_pos[0] + dx, self._drag_start_pos[1] + dy, b["w"], b["h"])
            dc = new_col - b["col"]; dr = new_row - b["row"]
            b["col"], b["row"] = new_col, new_row
            for li, l in enumerate(b.get("lines", [])):
                l["col"] = max(0, min(l["col"] + dc, MAX_COL))
                l["row"] = max(0, min(l["row"] + dr, MAX_ROW))
                if li < len(self._line_entries):
                    rv, cv, tv, _ = self._line_entries[li]
                    rv.set(l["row"]); cv.set(l["col"])
            for se in b.get("sub_entries", []):
                se["col"] = max(0, min(se["col"] + dc, MAX_COL))
                se["row"] = max(0, min(se["row"] + dr, MAX_ROW))

        elif self._drag_sub_idx is not None:
            se = b["sub_entries"][self._drag_sub_idx]
            se["row"] = max(0, min(self._drag_start_sub[0] + dy, MAX_ROW))
            se["col"] = max(0, min(self._drag_start_sub[1] + dx, MAX_COL))

        elif self._drag_line_idx is not None and b.get("type") in ("box", "text_plain"):
            raw_dx = e.x - self._drag_start_mouse[0]
            raw_dy = e.y - self._drag_start_mouse[1]
            if not self._drag_started:
                if abs(raw_dx) < DRAG_THRESHOLD and abs(raw_dy) < DRAG_THRESHOLD: return
                self._drag_started = True
            li    = self._drag_line_idx
            lines = b["lines"] if b["type"] == "box" else b["segments"]
            if li < len(lines):
                lines[li]["row"] = max(0, min(self._drag_start_line[0] + dy, MAX_ROW))
                lines[li]["col"] = max(0, min(self._drag_start_line[1] + dx, MAX_COL))
                if li < len(self._line_entries):
                    rv, cv, tv, _ = self._line_entries[li]
                    rv.set(lines[li]["row"]); cv.set(lines[li]["col"])

        elif self._resize_active:
            rdx = round((e.x - self._resize_start_mouse[0]) / CELL)
            rdy = round((e.y - self._resize_start_mouse[1]) / CELL)
            b["w"] = max(3, min(self._resize_start_size[0] + rdx, MAX_COL - b["col"]))
            b["h"] = max(3, min(self._resize_start_size[1] + rdy, MAX_ROW - b["row"]))
            b["w"] = (b["w"] // 2) * 2

        self._render()

    def _on_release(self, e):
        self._in_drag = False

        if self.current_mode == "vga":
            self._vga_on_release(e)
            return

        if self.current_mode == "vga_multi":
            self._vga_on_release(e)
            return

        if self.current_mode == "quest" and getattr(self, "_quest_submode", "text") in ("map", "m&h", "objects", "events"):
            self._quest_map_drag_end(e.x, e.y)
            self._reset_drag_state()
            return

        lines, render_fn = self._get_current_text_context()
        if lines is not None and self._drag_line_idx is not None:
            li = self._drag_line_idx
            if li < len(lines) and li < len(self._line_entries):
                rv, cv, tv, has_pos = self._line_entries[li]
                if has_pos:
                    rv.set(lines[li].get("row", 0))
                    cv.set(lines[li].get("col", 0))
            self._discard_last_undo_if_unchanged()
            self._reset_drag_state()
            render_fn()
            return

        if self._drag_line_idx is not None and self.current is not None:
            b = self._get_block(self.current)
            if b and self._drag_line_idx < len(self._line_entries):
                lines = b["lines"] if b["type"] == "box" else b.get("segments", [])
                if self._drag_line_idx < len(lines):
                    l = lines[self._drag_line_idx]
                    rv, cv, tv, _ = self._line_entries[self._drag_line_idx]
                    rv.set(l["row"]); cv.set(l["col"])

        self._discard_last_undo_if_unchanged()
        self._reset_drag_state(); self._render()

    def _on_mouse_motion(self, e):
        if getattr(self, "_in_drag", False):
            return
        if self.current_mode == "quest" and getattr(self, "_quest_submode", "text") in ("map", "m&h", "objects", "events"):
            self._quest_map_on_motion(e.x, e.y)

    def _on_mouse_leave(self, e):
        if self.current_mode == "quest":
            self._quest_map_hide_tooltip()
            self.canvas.delete("invalid_target_x")