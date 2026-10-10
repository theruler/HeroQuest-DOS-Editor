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


class QuestMapEditorMixin:
    MAP_CELL = 28

    def _room_color(self, room_id):
        clean_id = room_id & 0x3F
        
        if room_id & 0x40:
            if clean_id % 2 == 0: return "#0077ee"  # Azzurro
            else: return "#0099ff"                  # Ciano
            
        if room_id & 0x80:
            if clean_id % 2 == 0: return "#0033aa"  # Blu
            else: return "#0044cc"                  # Blu cobalto
        
        if clean_id == 0: return "#080a0e"
        
        if 1 <= clean_id <= 0x14:
            if clean_id % 2 == 0: return "#252c34"  #grigio chiaro
            else: return "#151a22" #grigio scuro

        idx = (clean_id - 0x15) % 22
        palcols = [
            "#1a2a3a","#2a1a3a","#3a2a1a","#1a3a2a","#2a3a1a","#3a1a2a",
            "#1a3a3a","#3a1a1a","#2a2a3a","#3a3a1a","#1a2a2a","#2a3a3a",
            "#223322","#222233","#332222","#223333","#332233","#333322",
            "#1a2233","#331a22","#22331a","#331a33",
        ]
        return palcols[idx]

    def _update_adjacent_revealed(self, q, gx, gy, adding_revealed, removing_revealed):
        if not (adding_revealed or removing_revealed):
            return
            
        for dx, dy in ((1, 0), (0, 1)):
            nx, ny = gx + dx, gy + dy
            if nx < QUEST_MAP_W and ny < QUEST_MAP_H:
                adj_val = q.get_room_at(nx, ny) or 0
                if adding_revealed:
                    adj_val |= 0x80
                else:
                    adj_val &= ~0x80
                q.set_room_at(nx, ny, adj_val)

    def _build_quest_map_panel(self, mode):
        self._base_edit_frame.pack_forget()
        for w in self._quest_map_panel.winfo_children():
            w.destroy()
        self._quest_map_panel.pack(fill=tk.X)

        outer = self._quest_map_panel

        if mode == "m&h":
            self._build_monster_pool(outer)
        elif mode == "objects":
            self._build_object_pool(outer)
        elif mode == "events":
            self._build_event_panel(outer)
        elif mode == "map":
            self._build_map_tools_panel(outer)

    def _build_monster_pool(self, parent):
        header_frame = tk.Frame(parent, bg=PAL["toolbar"])
        header_frame.pack(fill=tk.X, padx=8, pady=(6,2))
        tk.Label(header_frame, text="MONSTER POOL — drag to map", font=("Consolas",9,"bold"), fg="#ff6644", bg=PAL["toolbar"]).pack(side=tk.LEFT)
        wm_names = [f"{k:02X} {v[0]}" for k, v in MONSTER_TABLE.items() if k <= 0x07]
        self._wandering_var = tk.StringVar(value=self._wandering_monster_display())
        # Wandering Monster
        om_wandering = ttk.Combobox(header_frame, textvariable=self._wandering_var, values=wm_names, state="readonly", width=16, font=("Consolas",8))
        om_wandering.bind("<<ComboboxSelected>>", lambda e: self._on_wandering_monster_change(self._wandering_var.get()))
        om_wandering.pack(side=tk.RIGHT, padx=(0, 0))
        tk.Label(header_frame, text="   Wandering Monster:", font=("Consolas",8), fg=PAL["label"], bg=PAL["toolbar"]).pack(side=tk.RIGHT, padx=(0, 1))

        pool_frame = tk.Frame(parent, bg=PAL["toolbar"])
        pool_frame.pack(fill=tk.X, padx=8, pady=4)
        for tid, (name, sym, col) in MONSTER_TYPES.items():
            if tid > 0x07: continue
            btn = tk.Label(pool_frame, text=f"{sym} {name}", font=("Consolas",8), fg=col, bg=PAL["grid"], relief=tk.FLAT, padx=6, pady=3, cursor="fleur")
            btn.pack(side=tk.LEFT, padx=3)
            btn.bind("<ButtonPress-1>",   lambda e, t=tid: self._start_pool_drag(e, "monster", t))
            btn.bind("<B1-Motion>",       self._pool_drag_motion)
            btn.bind("<ButtonRelease-1>", self._pool_drag_drop)

        self._mon_edit_frame = tk.LabelFrame(parent, text=" ✎ Edit Selected Monster ", font=("Consolas",8,"bold"), fg="#ff6644", bg=PAL["toolbar"], pady=5, padx=8)
        self._mon_edit_frame.pack(fill=tk.X, padx=8, pady=(2,4))
        self._mon_edit_vars = {}
        
        grid_frame = tk.Frame(self._mon_edit_frame, bg=PAL["toolbar"])
        grid_frame.pack(fill=tk.X, pady=4)
        
        LBL_STYLE = dict(font=("Consolas",8), fg=PAL["label"], bg=PAL["toolbar"])
        BOX_STYLE = dict(font=("Consolas",11,"bold"), bg=PAL["grid"], fg=PAL["text"], relief=tk.FLAT, highlightbackground=PAL["label"], highlightthickness=1, bd=0, justify="center")
        
        # Riga 0: etichette
        for col, text in enumerate(["Monster type","Stats","Body","Mind","Movement","Attack","Defense","Reward"]):
            tk.Label(grid_frame, text=text, **LBL_STYLE).grid(row=0, column=col, padx=4, pady=(2,0))
        
        # Monster
        self._mon_edit_vars["atk_dice"] = tk.StringVar(value="—")
        preset_names = [f"{k:02X} {v[0]}" for k, v in MONSTER_TABLE.items()]
        om_preset = ttk.Combobox(grid_frame, textvariable=self._mon_edit_vars["atk_dice"], values=preset_names, state="readonly", width=22, font=("Consolas",8))
        def _on_preset_selected(e=None):
            self._on_preset_change(self._mon_edit_vars["atk_dice"].get())
            self._apply_monster_edit()
        om_preset.bind("<<ComboboxSelected>>", _on_preset_selected)
        om_preset.grid(row=1, column=1, padx=4, pady=(0,4), sticky="w")
        
        # Graphic
        self._mon_edit_vars["mtype"] = tk.StringVar(value="—")
        graphic_names = [v[0] for v in MONSTER_TYPES.values()]
        om_graphic = ttk.Combobox(grid_frame, textvariable=self._mon_edit_vars["mtype"], values=graphic_names, state="readonly", width=19, font=("Consolas",8))
        om_graphic.bind("<<ComboboxSelected>>", lambda e: self._apply_monster_edit())
        om_graphic.grid(row=1, column=0, padx=4, pady=(0,4), sticky="w")
        
        # Body / Mind
        for col, key in [(2,"bp_body"), (3,"bp_mind")]:
            self._mon_edit_vars[key] = tk.StringVar(value="—")
            sp = ttk.Spinbox(grid_frame, from_=0, to=15, textvariable=self._mon_edit_vars[key], width=2, justify="center", font=("Consolas", 10))
            sp.grid(row=1, column=col, padx=4, pady=(0,4))
            sp.bind("<Return>", lambda e: self._apply_monster_edit())
            sp.bind("<FocusOut>", lambda e: self._on_monster_entry_focus_out())
        
        # read-only stats
        self._mon_stat_labels = {}
        for col, stat_key in enumerate(["Movement","Attack","Defense","Reward"], start=4):
            width = 11 if stat_key == "Reward" else 2
            lbl = tk.Label(grid_frame, text="—", width=width, **BOX_STYLE)
            lbl.grid(row=1, column=col, padx=4, pady=(0,4))
            self._mon_stat_labels[stat_key] = lbl
        
        # apply
        tk.Button(grid_frame, text="✔", font=("Consolas",8,"bold"), bg="#003020", fg="#00ff99", relief=tk.RAISED, cursor="hand2", command=self._apply_monster_edit).grid(row=1, column=8, padx=4, pady=(0,4))
        
        # info
        self._mon_info_label = tk.Label(self._mon_edit_frame, font=("Consolas",9), fg="#556677", bg=PAL["toolbar"])
        self._mon_info_label.pack(anchor="w", padx=12, pady=(4,2))
        self._selected_monster_idx = None

    def _on_preset_change(self, selected_val):
        try:
            preset_id = int(selected_val.split(" ")[0], 16)
        except (ValueError, IndexError):
            return
        entry = MONSTER_TABLE.get(preset_id)
        if not entry: 
            return
        name, mtype, bp_body, bp_mind, *stats_vals = entry
        g_entry = MONSTER_TYPES.get(mtype)
        self._mon_edit_vars["mtype"].set(g_entry[0] if g_entry else "Unknown")
        self._mon_edit_vars["bp_body"].set(str(bp_body))
        self._mon_edit_vars["bp_mind"].set(str(bp_mind))
        for stat, val in zip(["Movement", "Attack", "Defense", "Reward"], stats_vals):
            self._mon_stat_labels[stat].config(text=str(val))

    def _populate_monster_panel(self, m):
        if not hasattr(self, "_mon_edit_vars"): 
            return
        v = self._mon_edit_vars
        preset_id = m.get("atk_dice", 0)
        p_entry = MONSTER_TABLE.get(preset_id)
        v["atk_dice"].set(f"{preset_id:02X} {p_entry[0]}" if p_entry else f"{preset_id:02X} Unknown")
        stats_vals = p_entry[4:] if p_entry else ["?"] * 4
        for stat, val in zip(["Movement", "Attack", "Defense", "Reward"], stats_vals):
            self._mon_stat_labels[stat].config(text=str(val))
        g_entry = MONSTER_TYPES.get(m.get("type", 0))
        v["mtype"].set(g_entry[0] if g_entry else "Unknown")
        v["bp_body"].set(str(m.get("bp_body", 1)))
        v["bp_mind"].set(str(m.get("bp_mind", 0)))
        if hasattr(self, "_mon_info_label"):
            mname = p_entry[0] if p_entry else "?"
            self._mon_info_label.config(
                text=f"Selected: #{self._selected_monster_idx}  {mname}  @ ({m['x']},{m['y']})",
                fg="#aabbcc"
            )

    def _read_monster_panel(self):
        v = self._mon_edit_vars
        res = {}
        try: res["atk_dice"] = int(v["atk_dice"].get().split(" ")[0], 16)
        except: res["atk_dice"] = 0
        try: res["type"] = int(v["mtype"].get().split(" ")[0], 16)
        except: res["type"] = 0
        try: res["bp_body"] = max(0, min(15, int(v["bp_body"].get())))
        except: res["bp_body"] = 1
        try: res["bp_mind"] = max(0, min(15, int(v["bp_mind"].get())))
        except: res["bp_mind"] = 0
        return res

    def _on_monster_entry_focus_out(self):
        if self._selected_monster_idx is None:
            return
        self._apply_monster_edit()

    def _apply_monster_edit(self):
        if self._selected_monster_idx is None:
            return
        info_text = self._mon_info_label.cget("text")
        if "@" not in info_text:
            return
        try:
            coords_part = info_text.split("@")[-1].strip().replace("(", "").replace(")", "")
            target_x, target_y = map(int, coords_part.split(","))
        except Exception:
            return
        target_monster = None
        for m in self.hq_quest.monsters:
            if m.get("x") == target_x and m.get("y") == target_y:
                target_monster = m
                break
        if not target_monster:
            return
        self._push_undo()
        selected_graphic_name = self._mon_edit_vars["mtype"].get()
        mtype_id = 0x00
        for tid, target_tuple in MONSTER_TYPES.items():
            if target_tuple[0] == selected_graphic_name:
                mtype_id = tid
                break
        try:
            selected_preset = self._mon_edit_vars["atk_dice"].get()
            preset_id = int(selected_preset.split(" ")[0], 16)
        except Exception:
            preset_id = 0x00
        target_monster["type"] = mtype_id
        target_monster["atk_dice"] = preset_id
        try:
            target_monster["bp_body"] = int(self._mon_edit_vars["bp_body"].get())
            target_monster["bp_mind"] = int(self._mon_edit_vars["bp_mind"].get())
        except ValueError:
            pass
        self._discard_last_undo_if_unchanged()
        self._render_quest()
        self._populate_monster_panel(target_monster)

    def _wandering_monster_display(self):
        wm = getattr(self.hq_quest, "wandering_monster", None)
        if not wm:
            return "—"
        preset_id = wm.get("atk_dice", 0)
        entry = MONSTER_TABLE.get(preset_id)
        name = entry[0] if entry else "Unknown"
        return f"{preset_id:02X} {name}"

    def _on_wandering_monster_change(self, selected_val):
        try:
            preset_id = int(selected_val.split(" ")[0], 16)
        except (ValueError, IndexError):
            return
        entry = MONSTER_TABLE.get(preset_id)
        if not entry:
            return
        name, mtype, bp_body, bp_mind, *stats_vals = entry
        wm = getattr(self.hq_quest, "wandering_monster", None)
        if not wm:
            wm = {"flags": 0, "x": 0, "y": 0, "room_ph": 0, "mem_ph": 0, "cond": 1}
        wm["atk_dice"] = preset_id
        wm["type"]     = mtype
        wm["bp_body"]  = bp_body
        wm["bp_mind"]  = bp_mind
        self.hq_quest.wandering_monster = wm
        self._update_status()

    _POOL_OBJ_TIDS  = [0x38, 0x5E, 0x5C, 0x30, 0x37]

    _POOL_TRAP_TIDS = [0x32, 0x36, 0x34]

    _POOL_FURN_TIDS = [0x4B, 0x4D, 0x4F, 0x54, 0x56]

    _POOL_FURN_TIDS_GREY = [0x53, 0x55, 0x57]

    def _build_object_pool(self, parent):
        tk.Label(parent, text="OBJECT POOL — drag to map", font=("Consolas",9,"bold"), fg="#ffaa44", bg=PAL["toolbar"]).pack(anchor="w", padx=8, pady=(6,2))
        import tkinter.font as tkfont
        map_width = max(GRID_COLS * CELL, 26*28+4)
        self._pool_btn_font = tkfont.Font(family="Consolas", size=8)

        top_frame = tk.Frame(parent, bg=PAL["toolbar"])
        top_frame.pack(fill=tk.X, padx=8, pady=2, anchor="w")

        col_objects = tk.Frame(top_frame, bg=PAL["toolbar"])
        col_objects.pack(side=tk.LEFT, anchor="n", padx=(0,16))
        col_traps = tk.Frame(top_frame, bg=PAL["toolbar"])
        col_traps.pack(side=tk.LEFT, anchor="n")

        tk.Label(col_objects, text="OBJECTS", font=("Consolas",8,"bold"), fg="#888888", bg=PAL["toolbar"]).pack(anchor="w")
        self._pack_pool_items(col_objects, self._POOL_OBJ_TIDS, max_width=None)

        tk.Label(col_traps, text="TRAPS", font=("Consolas",8,"bold"), fg="#888888", bg=PAL["toolbar"]).pack(anchor="w")
        self._pack_pool_items(col_traps, self._POOL_TRAP_TIDS, max_width=None)

        tk.Label(parent, text="FURNITURE", font=("Consolas",8,"bold"), fg="#888888", bg=PAL["toolbar"]).pack(anchor="w", padx=8, pady=(6,0))
        furn_frame = tk.Frame(parent, bg=PAL["toolbar"])
        furn_frame.pack(fill=tk.X, padx=8, pady=2, anchor="w")
        self._pack_pool_items(furn_frame, self._POOL_FURN_TIDS, max_width=map_width)
        furn_frame_grey = tk.Frame(parent, bg=PAL["toolbar"])
        furn_frame_grey.pack(fill=tk.X, padx=8, pady=2, anchor="w")
        self._pack_pool_items(furn_frame_grey, self._POOL_FURN_TIDS_GREY, max_width=map_width)

    def _pack_pool_items(self, container, tids, max_width=None):
        btn_font = self._pool_btn_font
        btn_h = 28

        row_frame = tk.Frame(container, bg=PAL["toolbar"])
        row_frame.pack(anchor="w")
        used_w = 0

        for tid in tids:
            entry = OBJECT_TYPES.get(tid)
            if not entry:
                continue
            name = entry[0]
            icon = entry[2] if len(entry) > 2 else ""
            col  = entry[3] if len(entry) > 3 else "#ffaa44"
            text = entry[4] if len(entry) > 4 else name
            btn_w = btn_font.measure(text) + 45  # spazio per icona + nome

            if max_width and used_w > 0 and used_w + btn_w + 4 > max_width:
                row_frame = tk.Frame(container, bg=PAL["toolbar"])
                row_frame.pack(anchor="w")
                used_w = 0

            btn = tk.Canvas(row_frame, width=btn_w, height=btn_h,
                             bg=PAL["grid"], highlightthickness=1,
                             highlightbackground=col, cursor="fleur")
            btn.pack(side=tk.LEFT, padx=2, pady=1)
            btn.create_rectangle(1, 1, btn_w, btn_h, outline=col, width=1)
            if icon:
                btn.create_text(16, btn_h//2, text=icon, fill=col, font=("Segoe UI Emoji", 14))
                btn.create_text(30, btn_h//2, text=text, fill=col, font=("Consolas", 9), anchor="w", width=btn_w)
            else:
                btn.create_text(btn_w//2, btn_h//2, text=text, fill=col, font=("Consolas", 8), width=btn_w-6)

            btn.bind("<ButtonPress-1>",   lambda e, t=tid: self._start_pool_drag(e, "object", t))
            btn.bind("<B1-Motion>",       self._pool_drag_motion)
            btn.bind("<ButtonRelease-1>", self._pool_drag_drop)
            used_w += btn_w + 4

    def _build_event_panel(self, parent):
        if not hasattr(self, "_event_mode"):
            self._event_mode = "treasure"
        self._selected_event_room = None

        top_frame = tk.Frame(parent, bg=PAL["toolbar"])
        top_frame.pack(fill=tk.X, padx=8, pady=(6, 2))

        tk.Label(top_frame, text="Select type:", font=("Consolas", 9, "bold"), fg=PAL["label"], bg=PAL["toolbar"]).pack(side=tk.LEFT, padx=(0, 10))

        self._event_type_var = tk.StringVar(value=self._event_mode)

        rb_treasure = tk.Radiobutton(top_frame, text="Treasure Events", variable=self._event_type_var,
                                     value="treasure", font=("Consolas", 9, "bold"), fg="#ffdd44",
                                     bg=PAL["toolbar"], selectcolor=PAL["grid"], activeforeground="#ffdd44",
                                     activebackground=PAL["toolbar"], command=self._on_event_type_toggle)
        rb_treasure.pack(side=tk.LEFT, padx=10)

        rb_traps = tk.Radiobutton(top_frame, text="Trap Events", variable=self._event_type_var,
                                  value="traps", font=("Consolas", 9, "bold"), fg="#ff4488",
                                  bg=PAL["toolbar"], selectcolor=PAL["grid"], activeforeground="#ff4488",
                                  activebackground=PAL["toolbar"], command=self._on_event_type_toggle)
        rb_traps.pack(side=tk.LEFT, padx=10)

        self._event_content_frame = tk.Frame(parent, bg=PAL["toolbar"])
        self._event_content_frame.pack(fill=tk.X)
        self._refresh_event_panel_content()
        self._event_room_label = tk.Label(parent, font=("Consolas", 9), fg="#556677", bg=PAL["toolbar"])
        self._event_room_label.pack(anchor="w", padx=12, pady=(4, 2))

    def _on_event_type_toggle(self):
        self._event_mode = self._event_type_var.get()
        self._drag_hint.config(text=f"HINT: Click a room to select it and see its event.\nChoose from the list to assign. Right-click to clear.")

        self._refresh_event_panel_content()
        self._sync_event_combo_to_selected_room()
        self._render_quest_map()

    def _refresh_event_panel_content(self):
        parent = self._event_content_frame
        for w in parent.winfo_children():
            w.destroy()
        mode = self._event_mode
        color = "#ffdd44" if mode == "treasure" else "#ff4488"
        try:
            import tkinter.ttk as ttk
            self._event_selected_id = tk.IntVar(value=0)
            combo_frame = tk.Frame(parent, bg=PAL["toolbar"])
            combo_frame.pack(fill=tk.X, padx=8, pady=4)
            tk.Label(combo_frame, text="Event:", font=("Consolas", 9), fg=color, bg=PAL["toolbar"]).pack(side=tk.LEFT)
            event_labels = [f"0x{eid:02X}  {desc}" for eid, desc in TREASURE_EVENTS.items()]
            self._event_combo_var = tk.StringVar(value=event_labels[0])
            cb = ttk.Combobox(combo_frame, textvariable=self._event_combo_var, values=event_labels, state="readonly", width=44, font=("Consolas", 9))
            cb.pack(side=tk.LEFT, padx=8)
            cb.bind("<<ComboboxSelected>>", self._on_event_combo_select)
        except ImportError:
            self._event_selected_id = tk.IntVar(value=0)
            pool_frame = tk.Frame(parent, bg=PAL["toolbar"])
            pool_frame.pack(fill=tk.X, padx=8, pady=4)
            for eid, desc in TREASURE_EVENTS.items():
                short = f"0x{eid:02X} {desc[:30]}"
                rb = tk.Radiobutton(pool_frame, text=short, variable=self._event_selected_id, value=eid,
                                     font=("Consolas", 8), fg=color, bg=PAL["toolbar"], selectcolor=PAL["grid"],
                                     anchor="w", command=self._apply_selected_room_event)
                rb.pack(fill=tk.X)

    def _on_event_combo_select(self, _=None):
        val = self._event_combo_var.get()
        try:
            eid = int(val[:4], 16)
            self._event_selected_id.set(eid)
        except Exception:
            return
        self._apply_selected_room_event()

    def _sync_event_combo_to_selected_room(self):
        room_id = getattr(self, "_selected_event_room", None)
        if room_id is None:
            return
        q = self.hq_quest
        arr = q.treasure_events if self._event_mode == "treasure" else q.trap_events
        ev_val = arr[room_id] if room_id < len(arr) else 0
        if hasattr(self, "_event_selected_id"):
            self._event_selected_id.set(ev_val)
        if hasattr(self, "_event_combo_var"):
            desc = TREASURE_EVENTS.get(ev_val, "")
            self._event_combo_var.set(f"0x{ev_val:02X}  {desc}")

    def _apply_selected_room_event(self):
        room_id = getattr(self, "_selected_event_room", None)
        if room_id is None:
            return
        ev_id = getattr(self, "_event_selected_id", None)
        ev_val = ev_id.get() if ev_id else 0
        q = self.hq_quest
        arr = q.treasure_events if self._event_mode == "treasure" else q.trap_events
        self._push_undo()
        arr[room_id] = ev_val
        self._discard_last_undo_if_unchanged()
        self._render_quest_map()

    def _make_checkbutton(self, parent, text, variable, color, row, column, bg=None, **grid_opts):
        grid_opts.setdefault("sticky", "w")
        bg_color = bg if bg is not None else PAL["toolbar"]
        cb = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bg=bg_color,
            fg=color,
            selectcolor=PAL["grid"],
            activeforeground=color,
            activebackground=bg_color
        )
        cb.grid(row=row, column=column, **grid_opts)
        return cb

    def _reset_map_flags(self):
        self._flag_secret.set(False)
        self._flag_open.set(False)
        self._flag_nodraw.set(False)
        self._flag_revealed.set(False)
        self._flag_fake.set(False)

    def _build_map_tools_panel(self, parent):
        self._flag_secret = tk.BooleanVar(value=False)
        self._flag_open   = tk.BooleanVar(value=False)
        self._flag_fake   = tk.BooleanVar(value=False)
        self._flag_nodraw = tk.BooleanVar(value=False)
        self._flag_revealed = tk.BooleanVar(value=False)
        tf = tk.Frame(parent, bg=PAL["toolbar"])
        tf.pack(fill=tk.X, padx=8, pady=4)
        self._map_tool_var = tk.StringVar(value="toggle_room")
        
        tools = [
            ("toggle_room", "Tile", "#888888"),
            ("entire_room", "Room", "#888888"),
            ("wall_N",      "── Wall",  "#cc4422"),
            ("wall_W",      "│ Wall",   "#cc4422"),
            ("door_N",      "── Door",  "#ffffff"),
            ("door_W",      "│ Door",   "#ffffff"),
        ]
        pos = {
            "toggle_room": (0, 0),
            "entire_room": (0, 1),
            "wall_N":      (1, 0),
            "wall_W":      (1, 1),
            "door_N":      (2, 0),
            "door_W":      (2, 1),
        }
        row1_bg = PAL.get("toolbar_light", "#1f2536") 
        hl_frame = tk.Frame(tf, bg=row1_bg)
        hl_frame.grid(row=1, column=0, columnspan=5, sticky="nsew")
        hl_frame.lower()
        
        for val, lbl, col in tools:
            r, c = pos[val]
            bg_color = row1_bg if r == 1 else PAL["toolbar"]
            rb = tk.Radiobutton(tf, text=lbl, variable=self._map_tool_var, value=val, font=("Consolas", 8), fg=col, bg=bg_color, selectcolor=PAL["grid"],  activeforeground=col, activebackground=bg_color)
            rb.grid(row=r, column=c, padx=4, pady=2, sticky="w")
            
        self._cb_revealed = self._make_checkbutton(tf, "Revealed", self._flag_revealed, "#00ccff", row=0, column=2)
        self._cb_nodraw = self._make_checkbutton(tf, "Invisible", self._flag_nodraw, "#ffaa88", row=1, column=2, bg=row1_bg)
        self._cb_open = self._make_checkbutton(tf, "Opened", self._flag_open, "#ffffff", row=2, column=2)
        self._cb_secret = self._make_checkbutton(tf, "Secret", self._flag_secret, "#aa44cc", row=2, column=3)
        self._cb_fake = self._make_checkbutton(tf, "Fake", self._flag_fake, "#cc4422", row=2, column=4)

        def _update_states(*args):
            self._reset_map_flags()
            tval = self._map_tool_var.get()
            self._cb_revealed.config(state="normal" if tval in ("toggle_room", "entire_room") else "disabled")
            self._cb_nodraw.config(state="normal" if tval in ("wall_N", "wall_W") else "disabled")
            door_state = "normal" if tval in ("door_N", "door_W") else "disabled"
            self._cb_open.config(state=door_state)
            self._cb_secret.config(state=door_state)
            self._cb_fake.config(state=door_state)

        self._map_tool_var.trace_add("write", _update_states)
        _update_states()

    def _start_map_or_pool_drag(self, event):
        cell = self.MAP_CELL
        gx = event.x // cell
        gy = event.y // cell
        hit_idx = None
        for i, m in enumerate(self.hq_quest.monsters):
            if m["x"] == gx and m["y"] == gy:
                hit_idx = i
                break
        if hit_idx is not None:
            m = self.hq_quest.monsters[hit_idx]
            self._pool_drag_kind    = "monster"
            self._pool_drag_type_id = m["type"]
            self._pool_drag_ghost   = None
            self._pool_drag_active  = True
            self._map_drag_idx      = hit_idx

    def _start_pool_drag(self, event, kind, type_id):
        self._pool_drag_kind    = kind
        self._pool_drag_type_id = type_id
        self._pool_drag_ghost   = None
        self._pool_drag_active  = True
        self._map_drag_idx      = None

    def _pool_drag_motion(self, event):
        if not getattr(self, "_pool_drag_active", False): return
        cx = self.canvas.winfo_rootx()
        cy = self.canvas.winfo_rooty()
        mx = event.widget.winfo_rootx() + event.x - cx
        my = event.widget.winfo_rooty() + event.y - cy
        if self._pool_drag_ghost:
            self.canvas.delete(self._pool_drag_ghost)
        cell = self.MAP_CELL
        gx = mx // cell
        gy = my // cell
        tag = "ghost"

        if self._pool_drag_kind != "object":
            sym = self._get_pool_symbol(self._pool_drag_kind, self._pool_drag_type_id)
            col = self._get_pool_color(self._pool_drag_kind, self._pool_drag_type_id)
            self.canvas.create_text(gx * cell + cell//2, gy * cell + cell//2, text=sym, fill=col, font=("Segoe UI Emoji", 24), tags=tag)
            self._pool_drag_ghost = tag
            return

        tid  = self._pool_drag_type_id
        entry = OBJECT_TYPES.get(tid)
        name = entry[0] if entry else f"{tid:02X}"
        cat  = entry[1] if entry else ""
        icon = entry[2] if entry and len(entry) > 2 else ""
        col  = self._get_pool_color(self._pool_drag_kind, tid)
        MARGIN = 5

        if cat == "trap":
            px, py = gx * cell + cell//2, gy * cell + cell//2
            self.canvas.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 24), tags=tag)

        elif self._is_stairs(name):
            px, py = gx * cell + cell//2, gy * cell + cell//2
            self.canvas.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 24), tags=tag)

        elif cat == "obj":
            px, py = gx * cell + cell//2, gy * cell + cell//2
            self.canvas.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 24), tags=tag)
            if tid in self._REMOVABLE_ROCK_TIDS:
                self._draw_removable_x(self.canvas, px, py, 9, tag)

        else:
            w, h = self._get_pool_size(self._pool_drag_kind, tid)
            x1, y1 = gx * cell, gy * cell
            x2, y2 = x1 + w * cell, y1 + h * cell
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=col, width=2, tags=tag)
            self.canvas.create_text((x1+x2)//2, (y1+y2)//2, text=icon, fill=col, font=("Segoe UI Emoji", 24), tags=tag)
        self._pool_drag_ghost = tag

    def _pool_drag_drop(self, event):
        if not getattr(self, "_pool_drag_active", False): return
        self._pool_drag_active = False
        if self._pool_drag_ghost:
            self.canvas.delete(self._pool_drag_ghost)
            self._pool_drag_ghost = None
        if event.widget is self.canvas:
            mx, my = event.x, event.y
        else:
            cx = self.canvas.winfo_rootx()
            cy = self.canvas.winfo_rooty()
            mx = event.widget.winfo_rootx() + event.x - cx
            my = event.widget.winfo_rooty() + event.y - cy
        cell = self.MAP_CELL
        gx = mx // cell
        gy = my // cell
        if not (0 <= gx < QUEST_MAP_W and 0 <= gy < QUEST_MAP_H): return
        self._push_undo()
        if getattr(self, "_map_drag_idx", None) is not None:
            self.hq_quest.monsters[self._map_drag_idx]["x"] = gx
            self.hq_quest.monsters[self._map_drag_idx]["y"] = gy
            self._map_drag_idx = None
            self._render_quest_map()
            return
        kind = self._pool_drag_kind
        tid  = self._pool_drag_type_id
        if kind == "monster":
            entry = MONSTER_TABLE.get(tid, ("?", tid, 1, 0, 0, 0, 0, ""))
            self.hq_quest.monsters.append({
                "flags": 0x81, "x": gx, "y": gy,
                "room_ph": 0, "mem_ph": 0,
                "cond": 0x01, "type": tid,
                "bp_body": entry[2], "bp_mind": entry[3], "atk_dice": tid,
            })
        elif kind == "object":
            self._place_object_group(tid, gx, gy)
        self._refresh_quest_hint()
        self._update_status()
        self._render_quest_map()

    def _new_group_id(self):
        gid = getattr(self, "_next_group_id", 1)
        self._next_group_id = gid + 1
        return gid

    def _place_object_group(self, tid, ox, oy, gid=None):
        ox, oy = self._clamp_furn_anchor(tid, ox, oy)
        cells = self._furn_cells(tid, ox, oy)
        if len(cells) <= 1:
            self.hq_quest.objects.append({"type": tid, "x": ox, "y": oy})
            return
        if gid is None:
            gid = self._new_group_id()
        filler_tid = self._get_filler_id(tid)
        for i, (cx, cy) in enumerate(cells):
            if i == 0:
                self.hq_quest.objects.append({"type": tid, "x": cx, "y": cy, "group_id": gid})
            else:
                ftid = filler_tid if filler_tid is not None else tid
                self.hq_quest.objects.append({"type": ftid, "x": cx, "y": cy, "group_id": gid})

    @staticmethod
    def _is_stairs(name):
        return "STAIRS" in name.upper()

    @staticmethod
    def _stairs_orientation(name):
        n = name.upper()
        if "NW" in n: return "NW"
        if "NE" in n: return "NE"
        if "SW" in n: return "SW"
        if "SE" in n: return "SE"
        return "NW"

    @staticmethod
    def _staircase_points(x_start, y_start, x_end, y_end, n_steps):
        dx = (x_end - x_start) / n_steps
        dy = (y_end - y_start) / n_steps
        pts = [(x_start, y_start)]
        x, y = x_start, y_start
        for _ in range(n_steps):
            x += dx
            pts.append((x, y))
            y += dy
            pts.append((x, y))
        return pts

    def _draw_stairs_icon(self, c, name, x1, y1, x2, y2, col_border, col_lines, lw, tag, gap=0):
        orient = self._stairs_orientation(name)
        cell_w = x2 - x1
        cell_h = y2 - y1

        if orient == "NW":
            ox, oy = gap, gap
        elif orient == "NE":
            ox, oy = -gap, gap
        elif orient == "SW":
            ox, oy = gap, -gap
        else:  # SE
            ox, oy = -gap, -gap

        bx1, by1, bx2, by2 = x1 + ox, y1 + oy, x2 + ox, y2 + oy

        n_steps = 3

        if orient == "NW":
            x_start, y_start = 0, 0
            x_end, y_end = cell_w, cell_h / 4
            half = "top"
        elif orient == "NE":
            x_start, y_start = 0, cell_h / 4
            x_end, y_end = cell_w, cell_h / 2
            half = "top"
        elif orient == "SW":
            x_start, y_start = 0, cell_h
            x_end, y_end = cell_w, cell_h * 3 / 4
            half = "bottom"
        else:  # SE
            x_start, y_start = 0, cell_h * 3 / 4
            x_end, y_end = cell_w, cell_h / 2
            half = "bottom"

        pts = self._staircase_points(x_start, y_start, x_end, y_end, n_steps)
        abs_pts = [(bx1 + px, by1 + py) for px, py in pts]

        for i in range(len(abs_pts) - 1):
            ax, ay = abs_pts[i]
            bbx, bby = abs_pts[i + 1]
            c.create_line(ax, ay, bbx, bby, fill=col_lines, width=lw, tags=tag)

        for i in range(1, len(pts), 2):
            px, py = pts[i]
            if half == "top":
                c.create_line(bx1 + px, by1 + py, bx1 + px, by2, fill=col_lines, width=lw, tags=tag)
            else:
                c.create_line(bx1 + px, by1, bx1 + px, by1 + py, fill=col_lines, width=lw, tags=tag)
        # contorno tile
        c.create_rectangle(bx1, by1, bx2, by2, outline=col_border, width=1, tags=tag)

    def _get_pool_name(self, kind, tid):
        if kind == "monster":
            return MONSTER_TYPES.get(tid, ("?","",""))[0]
        if kind == "object":
            return OBJECT_TYPES.get(tid, ("?", "", ""))[0]
        return "?"

    def _get_pool_size(self, kind, tid):
        if kind != "object":
            return (1, 1)
        entry = OBJECT_TYPES.get(tid)
        if not entry or len(entry) < 7:
            return (1, 1)
        return entry[5], entry[6]

    def _get_pool_symbol(self, kind, tid):
        if kind == "monster":
            return MONSTER_TYPES.get(tid, ("?","?",""))[1]
        if kind == "object":
            entry = OBJECT_TYPES.get(tid)
            if entry and len(entry) > 2:
                return entry[2]
            return self._get_pool_name(kind, tid)
        return "?"

    def _get_pool_color(self, kind, tid):
        if kind == "monster":
            return MONSTER_TYPES.get(tid, ("","","#ffffff"))[2]
        if kind == "object":
            entry = OBJECT_TYPES.get(tid)
            if not entry:
                return "#ffffff"
            if len(entry) > 3:
                return entry[3]
            return "#ffaa44"
        return "#ffffff"

    def _get_filler_id(self, tid):
        entry = OBJECT_TYPES.get(tid)
        if not entry or len(entry) < 8:
            return None
        return entry[7]

    _ORIENT_CYCLES = [
        (0x38, 0x39, 0x3A, 0x3B),
        (0x30, 0x31),
        (0x32, 0x33),
        (0x5C, 0x5D),
        (0x5E, 0x5F),
        (0x4B, 0x4C),
        (0x4D, 0x4E),
        (0x4F, 0x50),
        (0x52, 0x53),
        (0x54, 0x5A),
        (0x55, 0x5B),
        (0x56, 0x58),
        (0x57, 0x59),
    ]

    @classmethod
    def _get_orient_toggle_id(cls, tid):
        for cycle in cls._ORIENT_CYCLES:
            if tid in cycle:
                i = cycle.index(tid)
                return cycle[(i + 1) % len(cycle)]
        return None

    def _toggle_object_orientation(self, oi):
        q = self.hq_quest
        o = q.objects[oi]
        new_tid = self._get_orient_toggle_id(o["type"])
        if new_tid is None:
            return False
        self._push_undo()
        gid = o.get("group_id")
        if gid is None:
            o["type"] = new_tid
            return True

        ox, oy = o["x"], o["y"]
        q.objects[:] = [ob for ob in q.objects if ob.get("group_id") != gid]
        self._place_object_group(new_tid, ox, oy, gid=gid)
        return True

    def _clamp_furn_anchor(self, tid, ox, oy):
        w, h = self._get_pool_size("object", tid)
        ox = max(0, min(ox, QUEST_MAP_W - w))
        oy = max(0, min(oy, QUEST_MAP_H - h))
        return ox, oy

    def _furn_cells(self, tid, ox, oy):
        entry = OBJECT_TYPES.get(tid)
        if not entry or len(entry) < 7:
            return [(ox, oy)]
        w, h = entry[5], entry[6]
        if (w, h) == (1, 1):
            return [(ox, oy)]
        cells = []
        for dy in range(h):
            for dx in range(w):
                x, y = ox + dx, oy + dy
                if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
                    cells.append((x, y))
        return cells

    _FACING_ARROWS = {"N": "▲", "E": "▶", "S": "▼", "W": "◀"}

    _FACING_OBJ_ARROWS = {
        0x5C: ("▼", (0, 17)),
        0x5D: ("▶", (17, 0)),
        0x5E: ("▼", (0, 17)),
        0x5F: ("▶", (17, 0)),
    }

    _REMOVABLE_ROCK_TIDS = {0x31}

    @staticmethod
    def _draw_removable_x(canvas, px, py, r, tag):
        canvas.create_line(px-r, py-r, px+r, py+r, fill="#dd2222", width=2, tags=tag)
        canvas.create_line(px-r, py+r, px+r, py-r, fill="#dd2222", width=2, tags=tag)

    def _ensure_object_groups(self, q):
        pos_index = {}
        for i, o in enumerate(q.objects):
            if o.get("group_id") is None:
                pos_index[(o["x"], o["y"])] = i
        used = set()
        for i, o in enumerate(q.objects):
            if o.get("group_id") is not None or i in used:
                continue
            entry = OBJECT_TYPES.get(o["type"])
            if not entry or len(entry) < 7:
                continue
            if (entry[5], entry[6]) == (1, 1):
                continue
            expected_filler = self._get_filler_id(o["type"])
            if expected_filler is None:
                continue
            cells = self._furn_cells(o["type"], o["x"], o["y"])
            if len(cells) <= 1:
                continue
            group_idx = [i]
            ok = True
            for cx, cy in cells[1:]:
                j = pos_index.get((cx, cy))
                if j is None or j in used:
                    ok = False
                    break
                if q.objects[j]["type"] != expected_filler:
                    ok = False
                    break
                group_idx.append(j)
            if not ok:
                continue
            gid = self._new_group_id()
            for j in group_idx:
                q.objects[j]["group_id"] = gid
                used.add(j)

    def _render_quest_map(self):
        c    = self.canvas
        cell = self.MAP_CELL
        q    = self.hq_quest
        submode = getattr(self, "_quest_submode", "map")

        c.delete("all")

        for gy in range(QUEST_MAP_H):
            for gx in range(QUEST_MAP_W):
                room_id = q.get_room_at(gx, gy)
                x1 = gx * cell; y1 = gy * cell
                fill = self._room_color(room_id) 
                c.create_rectangle(x1, y1, x1+cell, y1+cell, fill=fill, outline="", tags="rooms")

        for gy in range(QUEST_MAP_H):
            for gx in range(QUEST_MAP_W):
                wval = q.get_wall_at(gx, gy)
                if wval == 0: continue
                x1 = gx * cell; y1 = gy * cell
                secret = bool(wval & 0x08)
                opened = bool(wval & 0x04)
                nodraw = bool(wval & 0x01)
                if wval & 0x80:
                    col_w = "#ffaa88" if nodraw else "#cc4422"
                    c.create_line(x1, y1, x1+cell, y1, fill=col_w, width=3, tags="walls")
                if wval & 0x40:
                    col_w = "#ffaa88" if nodraw else "#cc4422"
                    c.create_line(x1, y1, x1, y1+cell, fill=col_w, width=3, tags="walls")
                if wval & 0x20:
                    col_d = "#cc44ff" if secret else "#ffffff"
                    mid = x1 + cell // 2
                    if opened:
                        c.create_line(mid-5, y1, mid+5, y1 + 10, fill=col_d, width=4, tags="walls")
                    else:
                        c.create_line(mid-5, y1, mid+5, y1, fill=col_d, width=4, tags="walls")
                if wval & 0x10:
                    col_d = "#cc44ff" if secret else "#ffffff"
                    mid = y1 + cell // 2
                    if opened:
                        c.create_line(x1, mid-5, x1 + 10, mid+5, fill=col_d, width=4, tags="walls")
                    else:
                        c.create_line(x1, mid-5, x1, mid+5, fill=col_d, width=4, tags="walls")

        for gy in range(QUEST_MAP_H + 1):
            c.create_line(0, gy*cell, QUEST_MAP_W*cell, gy*cell, fill="#1a2030", tags="grid")
        for gx in range(QUEST_MAP_W + 1):
            c.create_line(gx*cell, 0, gx*cell, QUEST_MAP_H*cell, fill="#1a2030", tags="grid")

        shown_rooms = set()
        for gy in range(QUEST_MAP_H):
            for gx in range(QUEST_MAP_W):
                room_id = q.get_room_at(gx, gy)
                clean_id = room_id & 0x3F
                if clean_id == 0:
                    continue
                if clean_id in shown_rooms:
                    continue
                shown_rooms.add(clean_id)
                x1 = gx * cell
                y1 = gy * cell
                col = "#ffff00" if clean_id <= 0x2B else "#ffffff"
                c.create_text(x1 + 4, y1 + 4, text=f"{clean_id:02X}", fill=col, font=("Consolas", 6), anchor="nw", tags="room_nums")

        if submode == "events":
            event_mode = getattr(self, "_event_mode", "treasure")
            arr = q.treasure_events if event_mode == "treasure" else q.trap_events
            ev_col = "#ffdd44" if event_mode == "treasure" else "#ff4488"
            for gy in range(QUEST_MAP_H):
                for gx in range(QUEST_MAP_W):
                    room_id = q.get_room_at(gx, gy)
                    clean_id = room_id & 0x3F
                    if clean_id == 0: continue
                    ev = arr[clean_id] if clean_id < len(arr) else 0
                    if ev == 0: continue
                    x2 = gx*cell + cell - 2
                    y2 = gy*cell + cell - 2
                    c.create_text(x2, y2, text=f"{ev:02X}", fill=ev_col, font=("Consolas",6,"bold"), anchor="se", tags="ev_num")
                    c.create_rectangle(gx*cell+1, gy*cell+1, gx*cell+cell-1, gy*cell+cell-1, fill="", outline=ev_col, dash=(3,3), width=1, tags="ev_border")

            sel_room = getattr(self, "_selected_event_room", None)
            if sel_room is not None:
                for gy in range(QUEST_MAP_H):
                    for gx in range(QUEST_MAP_W):
                        if (q.get_room_at(gx, gy) & 0x3F) != sel_room: continue
                        x1 = gx * cell; y1 = gy * cell
                        c.create_rectangle(x1+1, y1+1, x1+cell-1, y1+cell-1, fill="", outline="#aaaaaa", width=1, tags="ev_room_sel")

        if submode in ("map", "m&h", "objects", "events"):
            for mi, m in enumerate(q.monsters):
                mx, my = m["x"], m["y"]
                entry = MONSTER_TYPES.get(m["type"])
                if entry:
                    sym, col = entry[1], entry[2]
                else:
                    sym, col = f"{m['type']:02X}", "#ff4444"
                px = mx * cell + cell//2; py = my * cell + cell//2
                sel = getattr(self, "_selected_monster_idx", None)
                if mi == sel:
                    c.create_oval(px-13, py-13, px+13, py+13, outline="#ffff44", width=2, tags=f"mon_{mi}")
                c.create_text(px, py, text=sym, font=("TkDefaultFont",16), fill=col, tags=f"mon_{mi}")

            MARGIN = 5  # object-cell
            drawn_groups = set()
            drag_sel = getattr(self, "_map_drag_item", None)
            for oi, o in enumerate(q.objects):
                gid = o.get("group_id")
                if gid is not None:
                    if gid in drawn_groups:
                        continue
                    drawn_groups.add(gid)
                    group_items = [(i, ob) for i, ob in enumerate(q.objects) if ob.get("group_id") == gid]
                    main_idx, main_o = group_items[0]
                    for i, ob in group_items:
                        e = OBJECT_TYPES.get(ob["type"])
                        if e and e[1] != "filler":
                            main_idx, main_o = i, ob
                            break
                    xs = [ob["x"] for _, ob in group_items]
                    ys = [ob["y"] for _, ob in group_items]
                    x1 = min(xs) * cell + MARGIN; y1 = min(ys) * cell + MARGIN
                    x2 = (max(xs)+1) * cell - MARGIN; y2 = (max(ys)+1) * cell - MARGIN
                    entry = OBJECT_TYPES.get(main_o["type"])
                    icon = entry[2] if entry and len(entry) > 2 else ""
                    col  = self._get_pool_color("object", main_o["type"])
                    is_sel = bool(drag_sel) and drag_sel[0] in ("object", "object_group") and \
                             0 <= drag_sel[1] < len(q.objects) and q.objects[drag_sel[1]].get("group_id") == gid
                    c.create_rectangle(x1, y1, x2, y2, outline=col, width=2 if is_sel else 1, tags=f"obj_{main_idx}")
                    c.create_text((x1+x2)//2, (y1+y2)//2, text=icon, fill=col, font=("Segoe UI Emoji", 14), tags=f"obj_{main_idx}")
                    px_main = main_o["x"] * cell + cell // 2
                    py_main = main_o["y"] * cell + cell // 2
                    c.create_text(px_main, py_main, text="🔄", fill=col, font=("Segoe UI Emoji", 10), tags=f"obj_{main_idx}")
                else:
                    ox, oy = o["x"], o["y"]
                    entry = OBJECT_TYPES.get(o["type"])
                    name = entry[0] if entry else f"{o['type']:02X}"
                    cat  = entry[1] if entry else ""
                    icon = entry[2] if entry and len(entry) > 2 else ""
                    col  = self._get_pool_color("object", o["type"])
                    x1 = ox * cell + MARGIN; y1 = oy * cell + MARGIN
                    x2 = x1 + cell - 2*MARGIN; y2 = y1 + cell - 2*MARGIN
                    is_sel = drag_sel == ("object", oi)
                    lw = 2 if is_sel else 1
                    px, py = ox * cell + cell//2, oy * cell + cell//2

                    if cat == "trap":
                        c.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 14), tags=f"obj_{oi}")

                    elif self._is_stairs(name):
                        self._draw_stairs_icon(c, name, x1, y1, x2, y2, col_border="#999999", col_lines=col, lw=lw, tag=f"obj_{oi}", gap=4)

                    elif cat == "obj":
                        c.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 14), tags=f"obj_{oi}")
                        if o["type"] in self._REMOVABLE_ROCK_TIDS:
                            self._draw_removable_x(c, px, py, 9, f"obj_{oi}")
                        facing = self._FACING_OBJ_ARROWS.get(o["type"])
                        if facing:
                            arrow, (dx, dy) = facing
                            c.create_text(px+dx, py+dy, text=arrow, font=("Consolas", 13), fill=col, tags=f"obj_{oi}")
                    else:
                        c.create_rectangle(x1, y1, x2, y2, outline=col, width=lw, tags=f"obj_{oi}")
                        c.create_text(px, py, text=icon, fill=col, font=("Segoe UI Emoji", 14), tags=f"obj_{oi}")

            for hi, (hname, sym, col, facing_map) in enumerate(HERO_TYPES):
                hdata = q.hero_data
                off = hi * 3
                hx, hy = hdata[off], hdata[off+1]
                px = hx * cell + cell//2; py = hy * cell + cell//2
                c.create_oval(px-9, py-9, px+9, py+9, fill="#001122", outline=col, width=2, tags=f"hero_{hi}")
                c.create_text(px, py, text=sym, font=("Consolas",12), fill=col, tags=f"hero_{hi}")
                face_byte = hdata[off+2]
                face_dir  = facing_map.get(face_byte, "S")
                arrow     = self._FACING_ARROWS.get(face_dir, "▼")
                ax_off = {"N":(0,-14), "S":(0,14), "E":(14,0), "W":(-14,0)}
                dx, dy = ax_off.get(face_dir, (0,12))
                c.create_text(px+dx, py+dy, text=arrow, font=("Consolas",14), fill=col, tags=f"hero_{hi}")

    def _quest_map_click(self, ex, ey, button=1):
        cell = self.MAP_CELL
        gx = ex // cell; gy = ey // cell
        if not (0 <= gx < QUEST_MAP_W and 0 <= gy < QUEST_MAP_H): return
        self._push_undo()
        q = self.hq_quest
        submode = getattr(self, "_quest_submode", "map")

        self._map_drag_item  = None
        self._map_drag_start = (gx, gy)

        WALL_N, WALL_W = 0x80, 0x40
        DOOR_N, DOOR_W = 0x20, 0x10
        SECRET, OPEN, NODRAW = 0x08, 0x04, 0x01
        WALL_DOOR_TOOLS = {
            "wall_N": dict(bit=WALL_N, same_side_other=DOOR_N, other_side_twin=WALL_W, mods=NODRAW),
            "wall_W": dict(bit=WALL_W, same_side_other=DOOR_W, other_side_twin=WALL_N, mods=NODRAW),
            "door_N": dict(bit=DOOR_N, same_side_other=WALL_N, other_side_twin=DOOR_W, mods=SECRET | OPEN),
            "door_W": dict(bit=DOOR_W, same_side_other=WALL_W, other_side_twin=DOOR_N, mods=SECRET | OPEN),
        }

        if submode == "map":
            tool = getattr(self, "_map_tool_var", None)
            tval = tool.get() if tool else "toggle_room"

            if tval in ("toggle_room", "entire_room"):
                room_raw = q.get_room_at(gx, gy) or 0
                room_id = room_raw & 0x3F
                is_revealed = self._flag_revealed.get()
                default_room_id = DEFAULT_ROOMS[gy*QUEST_MAP_W+gx] if gy*QUEST_MAP_W+gx < len(DEFAULT_ROOMS) else 1
                
                if button == 3:
                    new_room_id = 0
                else:
                    if room_id == 0:
                        new_room_id = default_room_id
                    else:
                        new_room_id = room_id

                paint_val = (new_room_id | 0x40) if (new_room_id != 0 and is_revealed) else new_room_id
                self._map_drag_paint_val = paint_val

                if tval == "entire_room":
                    for y in range(QUEST_MAP_H):
                        for x in range(QUEST_MAP_W):
                            idx = y * QUEST_MAP_W + x
                            if idx < len(DEFAULT_ROOMS) and DEFAULT_ROOMS[idx] == default_room_id:
                                old_raw = q.get_room_at(x, y) or 0
                                q.set_room_at(x, y, paint_val)
                                adding_rev = (new_room_id != 0 and is_revealed)
                                removing_rev = (new_room_id == 0 and bool(old_raw & 0x40))
                                self._update_adjacent_revealed(q, x, y, adding_rev, removing_rev)
                else:
                    q.set_room_at(gx, gy, paint_val)
                    adding_revealed = (new_room_id != 0 and is_revealed)
                    removing_revealed = (new_room_id == 0 and bool(room_raw & 0x40))
                    self._update_adjacent_revealed(q, gx, gy, adding_revealed, removing_revealed)

                self._render_quest_map()
                return

            spec = WALL_DOOR_TOOLS.get(tval)
            if spec is None:
                self._discard_last_undo_if_unchanged()
                return
            wval = q.get_wall_at(gx, gy)

            if button == 3:
                if wval & spec["bit"]:
                    wval &= ~spec["bit"]
                    if not (wval & spec["other_side_twin"]):
                        wval &= ~spec["mods"]
                    q.set_wall_at(gx, gy, wval)
                    self._render_quest_map()
                else:
                    self._discard_last_undo_if_unchanged()
                return

            is_fake_active = hasattr(self, "_flag_fake") and self._flag_fake.get()
            if is_fake_active and tval.startswith("door_"):
                wval |= spec["bit"]
                wval |= spec["same_side_other"] 
            else:
                wval &= ~spec["same_side_other"]
                wval |= spec["bit"]
            if not (wval & spec["other_side_twin"]):
                wval &= ~spec["mods"]
            for flag_var, bit in ((self._flag_nodraw, NODRAW), (self._flag_secret, SECRET), (self._flag_open, OPEN)):
                if bit & spec["mods"]:
                    if flag_var.get(): wval |= bit
                    else: wval &= ~bit
            
            old_wval = q.get_wall_at(gx, gy)
            if wval != old_wval:
                q.set_wall_at(gx, gy, wval)
            else:
                self._discard_last_undo_if_unchanged()
                return

        elif submode == "m&h":
            if button == 3:
                removed = False
                for mi in range(len(q.monsters)-1, -1, -1):
                    m = q.monsters[mi]
                    if m["x"] == gx and m["y"] == gy:
                        q.monsters.pop(mi)
                        removed = True
                        if getattr(self, "_selected_monster_idx", None) == mi:
                            self._selected_monster_idx = None
                if removed:
                    self._build_quest_map_panel("m&h")
                else:
                    self._discard_last_undo_if_unchanged()
                    return

            if button == 1:
                hit_hero = None
                for hi, (hname,sym,col,facing_map) in enumerate(HERO_TYPES):
                    off = hi * 3
                    hx, hy = q.hero_data[off], q.hero_data[off+1]
                    if hx == gx and hy == gy:
                        hit_hero = hi
                        self._map_drag_item = ("hero", hi)
                        self._hero_toggle_candidate = hi

                hit_monster = None
                for mi, m in enumerate(q.monsters):
                    if m["x"] == gx and m["y"] == gy:
                        hit_monster = mi
                        break

                if hit_monster is not None:
                    self._map_drag_item = ("monster", hit_monster)
                    self._selected_monster_idx = hit_monster
                    if hasattr(self, "_mon_edit_frame"):
                        self._populate_monster_panel(q.monsters[hit_monster])

                if hit_hero is None and hit_monster is None:
                    self._discard_last_undo_if_unchanged()
                    return

        elif submode == "objects":
            if button == 3:
                hit_gid = None
                removed = False
                for oi in range(len(q.objects)-1, -1, -1):
                    o = q.objects[oi]
                    if o["x"] == gx and o["y"] == gy:
                        hit_gid = o.get("group_id")
                        if hit_gid is None:
                            q.objects.pop(oi)
                            removed = True
                        break
                if hit_gid is not None:
                    q.objects[:] = [o for o in q.objects if o.get("group_id") != hit_gid]
                    removed = True
                
                if removed:
                    self._refresh_quest_hint()
                    self._update_status()
                else:
                    self._discard_last_undo_if_unchanged()
                    return
            else:
                hit = None
                for oi, o in enumerate(q.objects):
                    if o["x"] == gx and o["y"] == gy:
                        hit = oi; break
                if hit is not None:
                    gid = q.objects[hit].get("group_id")
                    if gid is None:
                        is_main = True
                    else:
                        group_idxs = [i for i, o in enumerate(q.objects) if o.get("group_id") == gid]
                        main_idx = group_idxs[0]
                        for i in group_idxs:
                            e = OBJECT_TYPES.get(q.objects[i]["type"])
                            if e and e[1] != "filler":
                                main_idx = i
                                break
                        is_main = (hit == main_idx)

                    self._map_drag_item = ("object", hit)
                    self._map_toggle_candidate = hit if (is_main and self._get_orient_toggle_id(q.objects[hit]["type"]) is not None) else None

                    if gid is not None:
                        group_idxs = [i for i, o in enumerate(q.objects) if o.get("group_id") == gid]
                        ref_idx = min(group_idxs, key=lambda i: (q.objects[i]["y"], q.objects[i]["x"]))
                        self._map_drag_item  = ("object_group", ref_idx)
                        self._map_drag_group = group_idxs
                        self._map_initial_mouse = (gx, gy)
                        self._map_drag_start_coords = {i: (q.objects[i]["x"], q.objects[i]["y"]) for i in group_idxs}
                else:
                    self._map_toggle_candidate = None
                    self._discard_last_undo_if_unchanged()
                    return

        elif submode == "events":
            raw_val = q.get_room_at(gx, gy)
            ROOM_MASK = 0x3F
            room_id = raw_val & ROOM_MASK

            if room_id == 0:
                self._discard_last_undo_if_unchanged()
                return

            event_mode = getattr(self, "_event_mode", "treasure")
            arr = q.treasure_events if event_mode == "treasure" else q.trap_events
            if button == 3:
                arr[room_id] = 0
                self._selected_event_room = room_id
                self._sync_event_combo_to_selected_room()
            else:
                self._selected_event_room = room_id
                self._sync_event_combo_to_selected_room()

        self._discard_last_undo_if_unchanged()
        self._render_quest_map()

    def _quest_map_drag(self, ex, ey):
        cell = self.MAP_CELL
        gx = ex // cell; gy = ey // cell
        if not (0 <= gx < QUEST_MAP_W and 0 <= gy < QUEST_MAP_H): return
        q = self.hq_quest
        submode = getattr(self, "_quest_submode", "map")

        item = getattr(self, "_map_drag_item", None)

        if submode == "map" and item is None:
            tool = getattr(self, "_map_tool_var", None)
            if tool and tool.get() in ("toggle_room", "entire_room"):
                if getattr(self, "_last_drag_pos", None) == (gx, gy):
                    return
                self._last_drag_pos = (gx, gy)
                
                paint_val = getattr(self, "_map_drag_paint_val", 0)
                if paint_val is None: paint_val = 0

                if tool.get() == "entire_room":
                    default_room_id = DEFAULT_ROOMS[gy*QUEST_MAP_W+gx] if gy*QUEST_MAP_W+gx < len(DEFAULT_ROOMS) else 1
                    for y in range(QUEST_MAP_H):
                        for x in range(QUEST_MAP_W):
                            idx = y * QUEST_MAP_W + x
                            if idx < len(DEFAULT_ROOMS) and DEFAULT_ROOMS[idx] == default_room_id:
                                old_raw = q.get_room_at(x, y) or 0
                                q.set_room_at(x, y, paint_val)
                                adding_rev = bool(paint_val & 0x40)
                                removing_rev = (paint_val == 0 and bool(old_raw & 0x40))
                                self._update_adjacent_revealed(q, x, y, adding_rev, removing_rev)
                else:
                    old_room_raw = q.get_room_at(gx, gy) or 0
                    q.set_room_at(gx, gy, paint_val)
                    adding_revealed = bool(paint_val & 0x40)
                    removing_revealed = (paint_val == 0 and bool(old_room_raw & 0x40))
                    self._update_adjacent_revealed(q, gx, gy, adding_revealed, removing_revealed)
                
                self._render_quest_map()
            return

        if item is None: return
        kind, idx = item
        prev = getattr(self, "_map_drag_start", (gx, gy))
        if (gx, gy) == prev: return
        self._map_drag_start = (gx, gy)
        self._map_toggle_candidate = None
        self._hero_toggle_candidate = None

        if kind == "monster" and idx < len(q.monsters):
            q.monsters[idx]["x"] = gx
            q.monsters[idx]["y"] = gy
            if hasattr(self, "_mon_info_label"):
                m = q.monsters[idx]
                mname = MONSTER_TYPES.get(m["type"],("?","",""))[0]
                self._mon_info_label.config(
                    text=f"Selected: #{idx}  {mname}  @ ({gx},{gy})", fg="#aabbcc")
        elif kind == "object" and idx < len(q.objects):
            q.objects[idx]["x"] = gx
            q.objects[idx]["y"] = gy
        elif kind == "object_group":
            ref_idx = idx
            mx0, my0 = getattr(self, "_map_initial_mouse", (gx, gy))
            dx, dy = gx - mx0, gy - my0
            group_idxs = getattr(self, "_map_drag_group", [ref_idx])
            start_coords = getattr(self, "_map_drag_start_coords", {})
            xs = [start_coords.get(i, (q.objects[i]["x"], q.objects[i]["y"]))[0] for i in group_idxs]
            ys = [start_coords.get(i, (q.objects[i]["x"], q.objects[i]["y"]))[1] for i in group_idxs]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            dx = max(-min_x, min(dx, (QUEST_MAP_W - 1) - max_x))
            dy = max(-min_y, min(dy, (QUEST_MAP_H - 1) - max_y))
            for i in group_idxs:
                orig_x, orig_y = start_coords.get(i, (q.objects[i]["x"], q.objects[i]["y"]))
                q.objects[i]["x"] = orig_x + dx
                q.objects[i]["y"] = orig_y + dy
        elif kind == "hero":
            off = idx * 3
            q.hero_data[off]   = gx
            q.hero_data[off+1] = gy
        self._render_quest_map()

    def _quest_map_drag_end(self, ex, ey):
        toggle_idx = getattr(self, "_map_toggle_candidate", None)
        hero_toggle = getattr(self, "_hero_toggle_candidate", None)
        self._map_drag_item      = None
        self._map_drag_start     = None
        self._map_drag_paint_val = None
        self._map_drag_group     = None
        self._map_drag_origin    = None
        self._map_toggle_candidate = None
        self._hero_toggle_candidate = None
        if toggle_idx is not None and toggle_idx < len(self.hq_quest.objects):
            self._toggle_object_orientation(toggle_idx)
            self._render_quest_map()
        elif hero_toggle is not None:
            hi = hero_toggle
            off = hi * 3
            if hi < len(HERO_TYPES):
                _, _, _, facing_map = HERO_TYPES[hi]
                cur = self.hq_quest.hero_data[off+2]
                frames = list(facing_map.keys())
                try:   ni = (frames.index(cur) + 1) % len(frames)
                except ValueError: ni = 0
                self.hq_quest.hero_data[off+2] = frames[ni]
                self._render_quest_map()

    def _quest_map_on_motion(self, ex, ey):
        cell = self.MAP_CELL
        gx = ex // cell
        gy = ey // cell
        submode = getattr(self, "_quest_submode", "map")
        over_object = any(o["x"] == gx and o["y"] == gy for o in getattr(self.hq_quest, "objects", []))
        over_monster = any(m["x"] == gx and m["y"] == gy for m in getattr(self.hq_quest, "monsters", []))
        over_hero = False
        
        if hasattr(self.hq_quest, "hero_data"):
            for hi, _ in enumerate(HERO_TYPES):
                off = hi * 3
                if off + 1 < len(self.hq_quest.hero_data):
                    if self.hq_quest.hero_data[off] == gx and self.hq_quest.hero_data[off+1] == gy:
                        over_hero = True
                        break

        invalid_target = False
        if submode == "m&h" and over_object:
            invalid_target = True
        elif submode == "objects" and (over_monster or over_hero):
            invalid_target = True
        self.canvas.delete("invalid_target_x")

        if invalid_target:
            cx1, cy1 = gx * cell, gy * cell
            cx2, cy2 = cx1 + cell, cy1 + cell
            p = 3
            self.canvas.create_oval(cx1 + p, cy1 + p, cx2 - p, cy2 - p, outline="#ff0000", width=2, tags="invalid_target_x")
            offset = p + max(2, int(cell * 0.15))
            self.canvas.create_line(cx1 + offset, cy1 + offset, cx2 - offset, cy2 - offset, fill="#ff0000", width=2, tags="invalid_target_x")
        else:
            self.canvas.config(cursor="crosshair")

        if getattr(self, "_map_drag_item", None) is not None:
            self._quest_map_hide_tooltip()
            return

        if (gx, gy) != getattr(self, "_hover_cell", None):
            self._hover_cell = (gx, gy)
            self._quest_map_hide_tooltip()
            
            if not (0 <= gx < QUEST_MAP_W and 0 <= gy < QUEST_MAP_H):
                return
                
            tooltip_text = None
            
            if submode == "m&h":
                for hi, (hname, _, _, _) in enumerate(HERO_TYPES):
                    off = hi * 3
                    if off + 1 < len(self.hq_quest.hero_data):
                        if self.hq_quest.hero_data[off] == gx and self.hq_quest.hero_data[off+1] == gy:
                            tooltip_text = f"Hero: {hname}"
                            break
                if not tooltip_text:
                    for m in getattr(self.hq_quest, "monsters", []):
                        if m["x"] == gx and m["y"] == gy:
                            preset = m.get("atk_dice", 0)
                            entry = MONSTER_TABLE.get(preset)
                            mname = entry[0] if entry else "Unknown Monster"
                            tooltip_text = f"Monster: {mname}"
                            break
                            
            elif submode == "objects":
                for o in getattr(self.hq_quest, "objects", []):
                    if o["x"] == gx and o["y"] == gy:
                        tid = o.get("type", 0)
                        entry = OBJECT_TYPES.get(tid)
                        oname = entry[0] if entry else f"Unknown Object ({tid:02X})"
                        tooltip_text = f"Object: {oname}"
                        break
                        
            elif submode == "events":
                room_id = self.hq_quest.get_room_at(gx, gy)
                if room_id:
                    clean_id = room_id & 0x3F
                    if clean_id != 0:
                        ev_mode = getattr(self, "_event_mode", "treasure")
                        arr = self.hq_quest.treasure_events if ev_mode == "treasure" else self.hq_quest.trap_events
                        ev_val = arr[clean_id] if clean_id < len(arr) else 0
                        if ev_val != 0:
                            desc = TREASURE_EVENTS.get(ev_val, f"Unknown Event ({ev_val:02X})")
                            tooltip_text = f"Room {clean_id:02X} Event:\n{desc}"

            if tooltip_text:
                self._tooltip_after_id = self.root.after(500, lambda: self._quest_map_show_tooltip(ex, ey, tooltip_text))


    def _quest_map_show_tooltip(self, ex, ey, text):
        self._quest_map_hide_tooltip()
        cx = self.canvas.winfo_rootx() + ex + 15
        cy = self.canvas.winfo_rooty() + ey + 15
        self._tooltip_win = tk.Toplevel(self.root)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{cx}+{cy}")
        self._tooltip_win.attributes("-topmost", True)
        lbl = tk.Label(self._tooltip_win, text=text, bg="#ffffcc", fg="#000000", relief="solid", borderwidth=1, font=("Consolas", 9), justify="left")
        lbl.pack(ipadx=4, ipady=2)

    def _quest_map_hide_tooltip(self):
        if getattr(self, "_tooltip_after_id", None):
            self.root.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if getattr(self, "_tooltip_win", None):
            self._tooltip_win.destroy()
            self._tooltip_win = None