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
    HQMultiVgaFile,
    FURNITURE_BLOCK_NAME,
    _is_quest_file, _is_paged_file, _is_intro_file, _is_quest_exe_file, _is_vga_file,
    _is_multi_vga_file,
    MONSTER_TYPES, MONSTER_TABLE, OBJECT_TYPES, HERO_TYPES, TREASURE_EVENTS,
    QUEST_MAP_W, QUEST_MAP_H, DEFAULT_ROOMS,
    INTRO_MAX_BYTES, INTRO_FIXED_STRINGS, QUEST_EXE_PAGE_MAX_TOTAL,
    VGA_WIDTH, VGA_HEIGHT, palette_to_rgb888, AVAILABLE_PALETTES
)


class VgaEditorMixin:
    def _on_select_vga(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        self._base_edit_frame.pack_forget()
        self._quest_map_panel.pack_forget()
        if self._vga_panel_built_for_mode != "vga":
            self._build_vga_panel()
            self._vga_panel_built_for_mode = "vga"
        self._vga_panel.pack(fill=tk.X)
        self.canvas.config(cursor=self._VGA_TOOL_CURSORS.get(self._vga_tool, "crosshair"))
        self._drag_hint.config(text="HINT: Select tool to create a rectangle,\nCtrl-C to copy, Ctrl-V to paste, then drag.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self._schedule_select_render()
        self._update_status()

    def _on_select_vga_multi(self, idx):
        if idx is None:
            self.listbox.selection_clear(0, tk.END); return
        self._vga_multi_sprite_idx = idx
        self._vga_selection   = None
        self._vga_paste_pending = None
        self._vga_pan_x = 0
        self._vga_pan_y = 0
        self._base_edit_frame.pack_forget()
        self._quest_map_panel.pack_forget()
        if self._vga_panel_built_for_mode != "vga_multi":
            self._build_vga_panel()
            self._vga_panel_built_for_mode = "vga_multi"
        self._vga_panel.pack(fill=tk.X)
        self.canvas.config(cursor=self._VGA_TOOL_CURSORS.get(self._vga_tool, "crosshair"))
        if isinstance(idx, tuple) and idx[0] == "furn_group":
            self._drag_hint.config(text="HINT: Composed view: changes\nare applied to the corresponding tile.")
        else:
            self._drag_hint.config(text="HINT: Use wheel to zoom, middle button to drag.\nRight click to pick color. Select then Ctrl-C/Ctrl-V.")
        self._drag_hint.pack(side=tk.RIGHT, padx=20)
        self._schedule_select_render()
        self._update_status()

    def _vga_canvas_size(self):
        c = self.canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1: w = int(c["width"])
        if h <= 1: h = int(c["height"])
        return w, h

    def _vga_clamp_pan(self, img_w=None, img_h=None):
        img_w = VGA_WIDTH  if img_w is None else img_w
        img_h = VGA_HEIGHT if img_h is None else img_h
        zoom = max(1, self._vga_zoom)
        cw, ch = self._vga_canvas_size()
        view_w = max(1, cw // zoom)
        view_h = max(1, ch // zoom)
        max_pan_x = max(0, img_w - view_w)
        max_pan_y = max(0, img_h - view_h)
        self._vga_pan_x = max(0, min(self._vga_pan_x, max_pan_x))
        self._vga_pan_y = max(0, min(self._vga_pan_y, max_pan_y))

    def _vga_render_source(self):
        if self.current_mode == "vga_multi":
            group_name = self._vga_multi_current_furniture_group()
            if group_name is not None:
                composed = self.hq_vga_multi.compose_furniture_group(group_name)
                if composed is None:
                    return None
                w, h, raw = composed
                return w, h, raw, self.hq_vga_multi.palette
            spr = self._vga_multi_current_sprite()
            if spr is None:
                return None
            return spr.width, spr.height, bytes(spr.data), self.hq_vga_multi.palette
        return VGA_WIDTH, VGA_HEIGHT, bytes(self.hq_vga.raw), self.hq_vga.palette

    def _render_vga_canvas(self):
        c = self.canvas
        c.delete("all")
        source = self._vga_render_source()
        if source is None:
            return
        img_w, img_h, raw, palette = source
        zoom = max(1, self._vga_zoom)
        self._vga_clamp_pan(img_w, img_h)
        cw, ch = self._vga_canvas_size()
        view_w = min(img_w, cw // zoom + 1)
        view_h = min(img_h, ch // zoom + 1)
        px, py = self._vga_pan_x, self._vga_pan_y
        try:
            full = Image.frombytes("P", (img_w, img_h), raw)
            full.putpalette(palette_to_rgb888(palette))
            if self._vga_paste_pending is not None:
                full = full.copy()
                ppx0, ppy0, pw, ph, pdata = self._vga_paste_pending
                patch = Image.frombytes("P", (pw, ph), pdata)
                patch.putpalette(palette_to_rgb888(palette))
                full.paste(patch, (ppx0, ppy0))
            crop = full.crop((px, py, px + view_w, py + view_h)).convert("RGB")
            if zoom != 1:
                crop = crop.resize((view_w * zoom, view_h * zoom), Image.NEAREST)
            self._vga_photo = ImageTk.PhotoImage(crop)
            c.create_image(0, 0, image=self._vga_photo, anchor="nw")
        except Exception as e:
            c.create_text(10, 10, anchor="nw", fill=PAL["accent"], text=f"VGA render error: {e}")
            return
        if self._vga_paste_pending is not None:
            ppx0, ppy0, pw, ph, _data = self._vga_paste_pending
            sx0 = (ppx0 - px) * zoom
            sy0 = (ppy0 - py) * zoom
            sx1 = (ppx0 + pw - px) * zoom
            sy1 = (ppy0 + ph - py) * zoom
            c.create_rectangle(sx0, sy0, sx1, sy1, outline="#ffcc00", dash=(4, 2), width=1)
            c.create_text(sx0 + 2, sy0 - 12, anchor="nw", fill="#ffffff", font=("Consolas", 8), text="Drag, Del or Flip H. Enter to apply, Esc to cancel.")
        elif self._vga_selection:
            x0, y0, x1, y1 = self._vga_selection
            sx0 = (x0 - px) * zoom
            sy0 = (y0 - py) * zoom
            sx1 = (x1 + 1 - px) * zoom
            sy1 = (y1 + 1 - py) * zoom
            c.create_rectangle(sx0, sy0, sx1, sy1, outline="#00ff99", dash=(4, 2), width=2)
        self._vga_update_info()

    def _vga_update_info(self):
        if not hasattr(self, "_vga_info_label"):
            return
        source = self._vga_render_source()
        if source is None:
            self._vga_info_label.config(text="")
            return
        img_w, img_h, raw, _palette = source
        n_colors = len(set(raw))
        palette_name = getattr(self._vga_active_file(), "palette_name", "?")
        self._vga_info_label.config(
            text=f"Current zoom: {self._vga_zoom}x\nPalette: {palette_name}\nImage Size: {img_w}x{img_h}\nColors used: {n_colors}\nColor: {self._vga_color}")

    def _render_vga(self):
        self._render_vga_canvas()

    def _vga_multi_current_sprite(self):
        idx = self._vga_multi_sprite_idx
        if idx is None or isinstance(idx, tuple):
            return None
        sprites = self.hq_vga_multi.sprites
        if not (0 <= idx < len(sprites)):
            return None
        return sprites[idx]

    def _vga_multi_current_furniture_group(self):
        idx = self._vga_multi_sprite_idx
        if isinstance(idx, tuple) and idx[0] == "furn_group":
            return idx[1]
        return None

    def _render_vga_multi(self):
        self._render_vga_canvas()

    def _vga_active_context(self):
        if self.current_mode == "vga_multi":
            group_name = self._vga_multi_current_furniture_group()
            if group_name is not None:
                accessors = self.hq_vga_multi.get_furniture_pixel_accessors(group_name)
                if accessors is None:
                    return None
                w, h, get_px, set_px = accessors
                return (w, h, get_px, set_px, self._render_vga_multi)
            spr = self._vga_multi_current_sprite()
            if spr is None:
                return None
            return (spr.width, spr.height, spr.get_pixel, spr.set_pixel, self._render_vga_multi)
        return (VGA_WIDTH, VGA_HEIGHT, self.hq_vga.get_pixel, self.hq_vga.set_pixel, self._render_vga)

    def _vga_event_to_pixel(self, e):
        ctx = self._vga_active_context()
        img_w, img_h = (ctx[0], ctx[1]) if ctx else (VGA_WIDTH, VGA_HEIGHT)
        zoom = max(1, self._vga_zoom)
        x = e.x // zoom + self._vga_pan_x
        y = e.y // zoom + self._vga_pan_y
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        return x, y

    def _vga_paint_brush(self, x, y, color):
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, _get_px, set_px, _render_fn = ctx
        size = max(1, min(10, self._vga_brush_size))
        half = size // 2
        x0 = max(0, x - half)
        y0 = max(0, y - half)
        x1 = min(img_w - 1, x0 + size - 1)
        y1 = min(img_h - 1, y0 + size - 1)
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                set_px(px, py, color)

    def _vga_on_right_click(self, e):
        ctx = self._vga_active_context()
        if ctx is None:
            return
        _img_w, _img_h, get_px, _set_px, _render_fn = ctx
        x, y = self._vga_event_to_pixel(e)
        self._vga_set_color(get_px(x, y))

    def _vga_on_click(self, e):
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, get_px, _set_px, render_fn = ctx
        x, y = self._vga_event_to_pixel(e)
        if self._vga_paste_pending is not None:
            px0, py0, pw, ph, _data = self._vga_paste_pending
            if px0 <= x < px0 + pw and py0 <= y < py0 + ph:
                self._vga_paste_drag_start = (e.x, e.y, px0, py0)
                return
            self._vga_commit_paste()
            return
        if self._vga_tool == "pixel":
            self._push_undo()
            self._vga_paint_brush(x, y, self._vga_color)
            render_fn()
        elif self._vga_tool == "fill":
            self._push_undo()
            self._vga_flood_fill(x, y, self._vga_color)
            render_fn()
        elif self._vga_tool == "select":
            self._vga_select_drag = (x, y)

    def _vga_on_drag(self, e):
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, get_px, _set_px, render_fn = ctx
        if self._vga_paste_pending is not None:
            if self._vga_paste_drag_start is not None:
                sx, sy, start_x0, start_y0 = self._vga_paste_drag_start
                zoom = max(1, self._vga_zoom)
                w, h, data = self._vga_paste_pending[2], self._vga_paste_pending[3], self._vga_paste_pending[4]
                new_x0 = start_x0 + (e.x - sx) // zoom
                new_y0 = start_y0 + (e.y - sy) // zoom
                self._vga_paste_pending = (new_x0, new_y0, w, h, data)
                render_fn()
            return
        x, y = self._vga_event_to_pixel(e)
        if self._vga_tool == "pixel":
            self._vga_paint_brush(x, y, self._vga_color)
            render_fn()
        elif self._vga_tool == "select" and self._vga_select_drag is not None:
            sx, sy = self._vga_select_drag
            x0, x1 = min(sx, x), max(sx, x)
            y0, y1 = min(sy, y), max(sy, y)
            self._vga_selection = (x0, y0, x1, y1)
            render_fn()

    def _vga_on_release(self, e):
        if self._vga_paste_pending is not None:
            self._vga_paste_drag_start = None
            return
        if self._vga_tool == "select":
            self._vga_select_drag = None

    def _vga_flood_fill(self, x0, y0, new_color):
        from collections import deque
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, get_px, set_px, _render_fn = ctx
        target = get_px(x0, y0)
        if target == new_color:
            return
        q = deque([(x0, y0)])
        seen = bytearray(img_w * img_h)
        seen[y0 * img_w + x0] = 1
        while q:
            x, y = q.popleft()
            if get_px(x, y) != target:
                continue
            set_px(x, y, new_color)
            for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0 <= nx < img_w and 0 <= ny < img_h:
                    nidx = ny * img_w + nx
                    if not seen[nidx]:
                        seen[nidx] = 1
                        q.append((nx, ny))

    def _build_vga_panel(self):
        for w in self._vga_panel.winfo_children():
            w.destroy()
        outer = self._vga_panel

        row1 = tk.Frame(outer, bg=PAL["toolbar"])
        row1.pack(fill=tk.X, padx=8, pady=(6, 2))

        tk.Label(row1, text="Brush:", font=("Consolas", 8), fg=PAL["label"], bg=PAL["toolbar"]).pack(side=tk.LEFT, padx=(2, 2))
        self._vga_brush_var = tk.IntVar(value=self._vga_brush_size)
        brush_box = tk.Spinbox(row1, from_=1, to=10, textvariable=self._vga_brush_var, width=2, bg=PAL["grid"], fg=PAL["text"], buttonbackground=PAL["btn"], relief=tk.FLAT,
                                font=("Consolas", 8), command=self._on_vga_brush_change)
        brush_box.pack(side=tk.LEFT)
        brush_box.bind("<Return>", self._on_vga_brush_change)
        brush_box.bind("<FocusOut>", self._on_vga_brush_change)

        self._vga_tool_var = tk.StringVar(value=self._vga_tool)
        tools_row1 = [
            ("pixel",  "✎ Draw"),
            ("fill",   "🫗 Fill"),
            ("select", "▭ Select ➜"),
        ]
        for val, lbl in tools_row1:
            tk.Radiobutton(
                row1, text=lbl, variable=self._vga_tool_var, value=val,
                font=("Consolas", 10), fg=PAL["text"], bg=PAL["toolbar"],
                selectcolor=PAL["grid"], activeforeground=PAL["text"],
                activebackground=PAL["toolbar"],
                command=self._on_vga_tool_change
            ).pack(side=tk.LEFT, padx=4)

        sel_actions_col = tk.Frame(row1, bg=PAL["toolbar"])
        sel_actions_col.pack(side=tk.LEFT, padx=(0, 4))
        for text, cmd in [
            ("Delete", self._vga_delete_selection),
            ("H flip", self._vga_mirror_h_selection),
            ("↷ 90°", self._vga_rotate90_selection),
        ]:
            tk.Button(sel_actions_col, text=text, font=("Consolas", 8), bg=PAL["btn"], fg=PAL["text"],  relief=tk.RAISED, cursor="hand2", command=cmd).pack(side=tk.LEFT, padx=2)

        row2 = tk.Frame(outer, bg=PAL["toolbar"])
        row2.pack(fill=tk.X, padx=8, pady=(2, 6))

        sw = 14
        self._vga_pal_canvas = tk.Canvas(row2, width=16 * sw, height=16 * sw, bg=PAL["bg"], highlightthickness=0)
        self._vga_pal_canvas.pack(side=tk.LEFT, anchor="n")
        self._vga_pal_canvas.bind("<Button-1>", self._on_vga_palette_click)

        info_col = tk.Frame(row2, bg=PAL["toolbar"])
        info_col.pack(side=tk.LEFT, padx=16, anchor="n")

        tk.Button(info_col, text="Import image", font=("Consolas", 8), bg=PAL["btn"], fg=PAL["text"], relief=tk.RAISED, cursor="hand2", command=self._vga_import_image).pack(anchor="w", fill=tk.X, pady=1)
        tk.Button(info_col, text="Export PNG", font=("Consolas", 8), bg=PAL["btn"], fg=PAL["text"], relief=tk.RAISED, cursor="hand2", command=self._vga_export_png).pack(anchor="w", fill=tk.X, pady=1)

        self._vga_info_label = tk.Label(info_col, text="", font=("Consolas", 8), fg=PAL["label"], bg=PAL["toolbar"])
        self._vga_info_label.pack(anchor="w")
        self._render_vga_palette_swatches()
        self._vga_update_info()

    def _vga_active_file(self):
        return self.hq_vga_multi if self.current_mode == "vga_multi" else self.hq_vga

    def _render_vga_palette_swatches(self):
        c = self._vga_pal_canvas
        c.delete("all")
        sw = 14
        vga_file = self._vga_active_file()
        rgb = palette_to_rgb888(vga_file.palette)
        try:
            current_selected = int(self._vga_color)
        except (ValueError, TypeError):
            current_selected = 0
        p_name = str(getattr(vga_file, 'palette_name', ""))
        max_colors = 32 if p_name.startswith("Hero") else 256
        for idx in range(max_colors):
            r, g, b = rgb[idx*3], rgb[idx*3+1], rgb[idx*3+2]
            col = f"#{r:02x}{g:02x}{b:02x}"
            x0 = (idx % 16) * sw
            y0 = (idx // 16) * sw
            c.create_rectangle(x0, y0, x0 + sw, y0 + sw, fill=col, outline=col, width=1, tags=f"sw{idx}")
        if current_selected < max_colors:
            x0 = (current_selected % 16) * sw
            y0 = (current_selected // 16) * sw
            c.create_rectangle(x0, y0, x0 + sw, y0 + sw, outline="#ffffff", width=2, tags="palette_selector")

    def _vga_set_color(self, idx):
        if not (0 <= idx <= 255):
            return
        self._vga_color = idx
        self._vga_update_info()
        if hasattr(self, "_vga_pal_canvas"):
            c = self._vga_pal_canvas
            sw = 14
            vga_file = self._vga_active_file()
            p_name = str(getattr(vga_file, 'palette_name', ""))
            max_colors = 32 if p_name.startswith("Hero") else 256
            if idx >= max_colors:
                return
            x0 = (idx % 16) * sw
            y0 = (idx // 16) * sw
            if c.find_withtag("palette_selector"):
                c.coords("palette_selector", x0, y0, x0 + sw, y0 + sw)
                c.tag_raise("palette_selector")
            else:
                c.create_rectangle(x0, y0, x0 + sw, y0 + sw, outline="#ffffff", width=2, tags="palette_selector")

    def _on_vga_palette_click(self, e):
        sw = 14
        col = e.x // sw
        row = e.y // sw
        self._vga_set_color(row * 16 + col)

    _VGA_TOOL_CURSORS = {
        "pixel":  "crosshair",
        "fill":   "crosshair",
        "select": "tcross",
        "picker": "crosshair",
    }

    def _render_vga_active(self):
        if self.current_mode == "vga_multi":
            self._render_vga_multi()
        else:
            self._render_vga()

    def _on_vga_tool_change(self):
        if self._vga_paste_pending is not None:
            self._vga_commit_paste()
        new_tool = self._vga_tool_var.get()
        if self._vga_tool == "select" and new_tool != "select":
            self._vga_selection = None
        self._vga_tool = new_tool
        cursor = self._VGA_TOOL_CURSORS.get(self._vga_tool, "crosshair")
        self.canvas.config(cursor=cursor)
        self._render_vga_active()

    def _vga_zoom_step(self, delta, mouse_x=None, mouse_y=None):
        old_zoom = max(1, self._vga_zoom)
        new_zoom = max(1, min(64, self._vga_zoom + delta))
        if new_zoom == self._vga_zoom:
            return
        if mouse_x is not None and mouse_y is not None:
            img_x = mouse_x / old_zoom + self._vga_pan_x
            img_y = mouse_y / old_zoom + self._vga_pan_y
            self._vga_zoom = new_zoom
            self._vga_pan_x = round(img_x - mouse_x / new_zoom)
            self._vga_pan_y = round(img_y - mouse_y / new_zoom)
        else:
            self._vga_zoom = new_zoom
        if hasattr(self, "_vga_zoom_label"):
            self._vga_zoom_label.config(text=f"Zoom: {self._vga_zoom}x")
        self._render_vga_active()

    def _on_vga_mousewheel(self, e):
        if self.current_mode not in ("vga", "vga_multi"):
            return
        delta = getattr(e, "delta", 0)
        if delta > 0 or getattr(e, "num", None) == 4:
            self._vga_zoom_step(1, e.x, e.y)
        elif delta < 0 or getattr(e, "num", None) == 5:
            self._vga_zoom_step(-1, e.x, e.y)
        return "break"

    def _vga_pan_button_press(self, e):
        if self.current_mode not in ("vga", "vga_multi"):
            return
        self._vga_pan_drag_start = (e.x, e.y, self._vga_pan_x, self._vga_pan_y)

    def _vga_pan_button_drag(self, e):
        if self.current_mode not in ("vga", "vga_multi"):
            return
        if self._vga_pan_drag_start is None:
            return
        sx, sy, start_px, start_py = self._vga_pan_drag_start
        zoom = max(1, self._vga_zoom)
        self._vga_pan_x = start_px - (e.x - sx) // zoom
        self._vga_pan_y = start_py - (e.y - sy) // zoom
        self._render_vga_active()

    def _vga_pan_button_release(self, e):
        if self.current_mode not in ("vga", "vga_multi"):
            return
        self._vga_pan_drag_start = None

    def _on_vga_brush_change(self, _e=None):
        try:
            size = int(self._vga_brush_var.get())
        except (ValueError, tk.TclError):
            size = self._vga_brush_size
        self._vga_brush_size = max(1, min(10, size))
        self._vga_brush_var.set(self._vga_brush_size)

    def _vga_use_default_palette(self):
        self.hq_vga.use_default_palette()
        self._render_vga_palette_swatches()
        self._render_vga()
        self._update_status()

    def _vga_export_png(self):
        if self.current_mode == "vga_multi":
            source = self._vga_render_source()
            if source is None:
                messagebox.showerror("Export error", "No sprite selected.")
                return
            width, height, raw, palette = source
        else:
            width, height, raw, palette = VGA_WIDTH, VGA_HEIGHT, bytes(self.hq_vga.raw), self.hq_vga.palette

        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=[("PNG image", "*.png")])
        if not path: return
        try:
            img = Image.frombytes("P", (width, height), raw)
            img.putpalette(palette_to_rgb888(palette))
            img.convert("RGB").save(path)
            messagebox.showinfo("Exported", f"Saved {path}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def _vga_import_image(self):
        ctx = self._vga_active_context()
        if ctx is None:
            messagebox.showerror("Import error", "Nessun contesto VGA attivo o sprite selezionato.")
            return
        img_w, img_h, _, _, render_fn = ctx

        path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.png *.bmp *.jpg *.jpeg *.gif"), ("All files", "*.*")])
        if not path: return
        try:
            src = Image.open(path).convert("RGB")
            w, h = src.size

            vga_file = self._vga_active_file()
            pal_img = Image.new("P", (1, 1))
            pal_img.putpalette(palette_to_rgb888(vga_file.palette))
            quantized = src.quantize(palette=pal_img, dither=Image.FLOYDSTEINBERG)
            data = quantized.tobytes()

            if self._vga_paste_pending is not None:
                self._vga_commit_paste()

            x0, y0 = self._vga_pan_x, self._vga_pan_y
            if self._vga_selection:
                x0, y0 = self._vga_selection[0], self._vga_selection[1]
            x0 = max(0, min(x0, max(0, img_w - w)))
            y0 = max(0, min(y0, max(0, img_h - h)))
            self._vga_paste_pending = (x0, y0, w, h, data)
            render_fn()
            self._update_status()
        except Exception as e:
            messagebox.showerror("Import error", str(e))

    def _vga_delete_selection(self):
        if self._vga_paste_pending is not None:
            self._vga_cancel_paste()
            return
        if not self._vga_selection:
            return
        ctx = self._vga_active_context()
        if ctx is None:
            return
        _w, _h, _get_pixel, set_pixel, render_fn = ctx
        x0, y0, x1, y1 = self._vga_selection
        self._push_undo()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                set_pixel(x, y, 0)
        self._discard_last_undo_if_unchanged()
        render_fn()

    def _vga_mirror_h_selection(self):
        if self._vga_paste_pending is not None:
            x0, y0, w, h, data = self._vga_paste_pending
            flipped = bytearray(w * h)
            for row in range(h):
                src = row * w
                flipped[src:src + w] = data[src:src + w][::-1]
            self._vga_paste_pending = (x0, y0, w, h, bytes(flipped))
            self._render_vga_active()
            return

        if not self._vga_selection:
            return
        ctx = self._vga_active_context()
        if ctx is None:
            return
        _w, _h, get_pixel, set_pixel, render_fn = ctx
        x0, y0, x1, y1 = self._vga_selection
        w = x1 - x0 + 1
        self._push_undo()
        for y in range(y0, y1 + 1):
            row = [get_pixel(x0 + col, y) for col in range(w)]
            row.reverse()
            for col, val in enumerate(row):
                set_pixel(x0 + col, y, val)
        self._discard_last_undo_if_unchanged()
        render_fn()

    def _vga_rotate90_selection(self):
        if self._vga_paste_pending is not None:
            x0, y0, w, h, data = self._vga_paste_pending
            rotated = bytearray(w * h)
            for row in range(h):
                for col in range(w):
                    rotated[col * h + (h - 1 - row)] = data[row * w + col]
            self._vga_paste_pending = (x0, y0, h, w, bytes(rotated))
            self._render_vga_active()
            return
        if not self._vga_selection:
            return
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, get_pixel, set_pixel, render_fn = ctx
        x0, y0, x1, y1 = self._vga_selection
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        block = [get_pixel(x0 + col, y0 + row) for row in range(h) for col in range(w)]
        new_w, new_h = h, w
        rotated = bytearray(new_w * new_h)
        for row in range(h):
            for col in range(w):
                new_col = h - 1 - row
                new_row = col
                rotated[new_row * new_w + new_col] = block[row * w + col]
        self._push_undo()
        for row in range(h):
            for col in range(w):
                set_pixel(x0 + col, y0 + row, 0)
        self._vga_paste_pending = (x0, y0, new_w, new_h, bytes(rotated))
        self._vga_selection = None 
        self._discard_last_undo_if_unchanged()
        self._render_vga_active()

    def _vga_copy_selection(self):
        if not self._vga_selection:
            return
        ctx = self._vga_active_context()
        if ctx is None:
            return
        _w, _h, get_pixel, _set_pixel, _render_fn = ctx
        x0, y0, x1, y1 = self._vga_selection
        w, h = x1 - x0 + 1, y1 - y0 + 1
        data = bytearray(w * h)
        for row in range(h):
            for col in range(w):
                data[row * w + col] = get_pixel(x0 + col, y0 + row)
        self._vga_clipboard = (w, h, bytes(data))
        try:
            vga_file = self._vga_active_file()
            img = Image.frombytes("P", (w, h), bytes(data))
            img.putpalette(palette_to_rgb888(vga_file.palette))
            
            if os.name == 'nt':
                import io
                import ctypes
                output = io.BytesIO()
                img.convert("RGB").save(output, "BMP")
                dib_data = output.getvalue()[14:]
                output.close()
                
                if ctypes.windll.user32.OpenClipboard(None):
                    ctypes.windll.user32.EmptyClipboard()
                    hCd = ctypes.windll.kernel32.GlobalAlloc(2, len(dib_data))
                    pCd = ctypes.windll.kernel32.GlobalLock(hCd)
                    ctypes.memmove(pCd, dib_data, len(dib_data))
                    ctypes.windll.kernel32.GlobalUnlock(hCd)
                    ctypes.windll.user32.SetClipboardData(8, hCd)
                    ctypes.windll.user32.CloseClipboard()
        except Exception:
            pass

    def _vga_paste_clipboard(self):
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, _, _, render_fn = ctx

        sys_img = None
        try:
            from PIL import ImageGrab
            sys_img = ImageGrab.grabclipboard()
        except Exception:
            pass

        if sys_img is not None:
            if isinstance(sys_img, list) and len(sys_img) > 0:
                try:
                    sys_img = Image.open(sys_img[0])
                except Exception:
                    sys_img = None

            if isinstance(sys_img, Image.Image):
                try:
                    src = sys_img.convert("RGB")
                    w, h = src.size
                    if w > img_w or h > img_h:
                        src.thumbnail((img_w, img_h), Image.LANCZOS)
                        w, h = src.size

                    vga_file = self._vga_active_file()
                    pal_img = Image.new("P", (1, 1))
                    pal_img.putpalette(palette_to_rgb888(vga_file.palette))
                    quantized = src.quantize(palette=pal_img, dither=Image.FLOYDSTEINBERG)
                    data = quantized.tobytes()

                    if self._vga_paste_pending is not None:
                        self._vga_commit_paste()
                    x0, y0 = self._vga_pan_x, self._vga_pan_y

                    if self._vga_selection:
                        x0, y0 = self._vga_selection[0], self._vga_selection[1]
                    x0 = max(0, min(x0, max(0, img_w - w)))
                    y0 = max(0, min(y0, max(0, img_h - h)))
                    self._vga_paste_pending = (x0, y0, w, h, data)
                    render_fn()
                    return
                except Exception:
                    pass

        if not self._vga_clipboard:
            return
        if self._vga_paste_pending is not None:
            self._vga_commit_paste()
        w, h, data = self._vga_clipboard
        x0, y0 = self._vga_pan_x, self._vga_pan_y
        if self._vga_selection:
            x0, y0 = self._vga_selection[0], self._vga_selection[1]
        x0 = max(0, min(x0, max(0, img_w - w)))
        y0 = max(0, min(y0, max(0, img_h - h)))
        self._vga_paste_pending = (x0, y0, w, h, data)
        render_fn()

    def _vga_commit_paste(self):
        if self._vga_paste_pending is None:
            return
        ctx = self._vga_active_context()
        if ctx is None:
            return
        img_w, img_h, get_pixel, set_pixel, render_fn = ctx
        x0, y0, w, h, data = self._vga_paste_pending
        self._push_undo()
        for row in range(h):
            for col in range(w):
                dest_x = x0 + col
                dest_y = y0 + row
                if 0 <= dest_x < img_w and 0 <= dest_y < img_h:
                    set_pixel(dest_x, dest_y, data[row * w + col])
        self._discard_last_undo_if_unchanged()
        new_x0 = max(0, min(x0, img_w - 1))
        new_y0 = max(0, min(y0, img_h - 1))
        new_x1 = max(0, min(x0 + w - 1, img_w - 1))
        new_y1 = max(0, min(y0 + h - 1, img_h - 1))
        self._vga_selection = (new_x0, new_y0, new_x1, new_y1)
        self._vga_paste_pending = None
        self._vga_paste_drag_start = None
        render_fn()

    def _vga_cancel_paste(self):
        if self._vga_paste_pending is None:
            return
        self._vga_paste_pending = None
        self._vga_paste_drag_start = None
        self._render_vga_active()

    def _on_ctrl_c(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_copy_selection()

    def _on_ctrl_v(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_paste_clipboard()

    def _on_vga_paste_confirm(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_commit_paste()

    def _on_vga_paste_cancel(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_cancel_paste()

    def _on_ctrl_z(self, e=None):
        self._undo()

    def _on_ctrl_y(self, e=None):
        self._redo()

    def _on_ctrl_o(self, e=None):
        self._open_file()
        return "break"

    def _on_ctrl_s(self, e=None):
        self._save_file()
        return "break"

    def _on_ctrl_h(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_mirror_h_selection()
            return "break"

    def _on_vga_delete_key(self, e=None):
        if self.current_mode in ("vga", "vga_multi"):
            self._vga_delete_selection()
