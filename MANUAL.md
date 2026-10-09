# HeroQuest Editor — User Manual

Version 6.8 · by TheRuler

This manual explains how to use every part of the editor. For installation and build instructions, see [README.md](README.md).

---

## Contents

1. [Before you start](#1-before-you-start)
2. [The interface](#2-the-interface)
3. [Opening and saving files](#3-opening-and-saving-files)
4. [Undo / Redo](#4-undo--redo)
5. [Editing texts (language BIN files)](#5-editing-texts-language-bin-files)
6. [EQUESTS.BIN (paged texts)](#6-equestsbin-paged-texts)
7. [INTRO.EXE](#7-introexe)
8. [QUEST.EXE](#8-questexe)
9. [Editing quests (QUESTxx.BIN)](#9-editing-quests-questxxbin)
10. [Editing graphics (VGA / UNP)](#10-editing-graphics-vga--unp)
11. [Editing sound effects (ALB / RLD)](#11-editing-sound-effects-alb--rld)
12. [Typical workflows](#12-typical-workflows)
13. [Tips and good practices](#13-tips-and-good-practices)
14. [Keyboard and mouse reference](#14-keyboard-and-mouse-reference)
15. [FAQ](#15-faq)

---

## 1. Before you start

- **Back up your game folder.** Always edit copies, never your only original files.
- You need a legitimate copy of HeroQuest for DOS. The editor contains no game data.
- The editor needs `enc.exe`, `dec.exe`, `heroquest.fnt` and `background1.png`, `background2.png`, `background3.png`. They are included in the executable build. If you run from source they must stay in the same folder as `main.py`; otherwise a **"Files missing"** message lists what is absent.
- Test your changes in DOSBox (or your preferred DOS environment) after saving.

---

## 2. The interface

```
┌──────────────────────────────────────────────────────────────┐
│ [LOAD] [SAVE] [UNDO] [REDO]            hint        status    │  ← Toolbar
├──────────────┬───────────────────────────────────────────────┤
│ SEARCH: ...  │                                               │
│              │                CANVAS                         │
│  Entry list  │        (live preview / map / image)           │
│              ├───────────────────────────────────────────────┤
│              │              EDIT PANEL                       │
│              │   (text fields, tools, palettes, options)     │
└──────────────┴───────────────────────────────────────────────┘
```

- **Toolbar**: LOAD, SAVE, UNDO, REDO. On the right, a *hint* explains how to interact with the current mode and the *status* shows information about the open file.
- **Entry list (left)**: the contents of the file (texts, quest sections, images, sprites, effects). A **SEARCH** box appears for text files and multi-sprite VGA files.
- **Canvas (top right)**: the live preview. In text modes it shows the game's original font over the real background; in quest modes it shows the board; in VGA modes it shows the pixel image.
- **Edit panel (below the canvas)**: changes with the mode. It scrolls with the mouse wheel when it is taller than the window.

The window minimum size is 1100 × 660.

---

## 3. Opening and saving files

### Opening
- Click **LOAD**, press `Ctrl+O`, or **drag & drop** a file onto the window.
- The editor **detects the type automatically** from the file content and name (INTRO.EXE, QUEST.EXE, quest, paged, VGA, multi-VGA, sound bank, language BIN).
- Compressed files (`.BIN`, `.VGA`) are decompressed automatically with `dec.exe`.
- If you have unsaved changes, you are asked before they are discarded.
- If the file is not recognized you will get an error message.

### Saving
- Click **SAVE** or press `Ctrl+S`, then choose the file name.
- Language `.BIN` files are rebuilt and **recompressed** automatically with `enc.exe` when the target name is a known compressed game file.
- Save with the **original file name** if you want to drop it straight into the game folder.
- After saving, a message confirms the new size in bytes (or the number of sprites/effects).

> The status line and the window ask for confirmation when closing with unsaved changes.

---

## 4. Undo / Redo

- **UNDO**: `Ctrl+Z`. **REDO**: `Ctrl+Y` or `Ctrl+Shift+Z`.
- Every drag, text edit, paint stroke, paste and placement creates an undo step.
- History is cleared when you open another file.

---

## 5. Editing texts (language BIN files)

Files: `ENGLISH.BIN`, `ITALIAN.BIN`, `SPANISH.BIN`, `GERMAN.BIN`, `FRENCH.BIN` (and their `.UNP` versions).

### The entry list
Each entry has an offset label and a type tag:

| Tag | Meaning |
|---|---|
| `[scroll]` | A parchment text box with one or more lines and optional buttons |
| `[text]` | Plain text placed on the screen |
| `[button]` | A button label |
| `×N` | The entry's pointer is shared by *N* places in the game |
| `↳` | Orphan entry (referenced from another block) |

Use **SEARCH** to filter entries by their text.

### Editing a scroll
1. Select a `[scroll]` in the list. The canvas shows it on the parchment background.
2. **Move the whole scroll**: drag it by its top or bottom roll.
3. **Resize**: drag the small triangle (◢) in the bottom-right corner.
4. **Move a line**: click and drag it.
5. **Edit a line**: double-click it. The cursor jumps to its entry field in the panel below; type your text and press `Enter` (or the ✔ button) to apply.
6. **Move a button**: drag the button label. **Double-click** a button to jump to its own entry in the list.
7. **Add a line** with the *Add line* button, and **delete** a line with the *−* button next to it.

### Special characters
Accented letters and symbols (`à è é ì ò ù ñ ü ö ä á ç ¿ ¡ ú í ó`) are automatically converted to the game's internal codes. Characters that the game font cannot represent are replaced with `?`.

### Limits
Each file has fixed size limits. If a text becomes too long the editor will refuse or warn when saving. Keep modified text within the original space, shortening other strings if necessary.

---

## 6. EQUESTS.BIN (paged texts)

- The list shows **languages** (English, French, Spanish, German, Italian) with their **Page 1 / Page 2**.
- Select a page; the canvas shows it over a background.
- Edit as in section 5: **drag** lines, **double-click** to edit, **Add line** to append.
- The *search* box filters pages that contain a given text.

---

## 7. INTRO.EXE

- The list shows the intro **pages** and the **fixed system strings** (`SYSTEM STRING`).
- **Pages**: edit them like normal text pages. A counter shows `used / max bytes`; the total text of all pages cannot exceed the maximum area of the original executable.
- **System strings**: select one and edit it in the text area; the counter shows the number of bytes used versus the fixed length available. Press ✔ to apply.

---

## 8. QUEST.EXE

- Contains several kinds of strings: **position strings**, **page blocks**, **plain strings** and **DOS strings** (terminated with `$` in the original).
- Select an item and edit it in the panel. Page blocks and position strings can also be dragged on the canvas.
- Counters show bytes used vs. the maximum available.
- Only printable ASCII is shown for DOS strings; internal control bytes are preserved automatically.

---

## 9. Editing quests (QUESTxx.BIN)

When you open a quest file, the list shows the quest name and five sections:

| Section | Purpose |
|---|---|
| **MISSION BRIEFING** | The quest's introduction text |
| **MAP EDITOR** | Rooms, corridors, walls and doors |
| **MONSTERS & HEROES** | Monster placement and stats, wandering monster, heroes' start |
| **FURNITURES & TRAPS** | Furniture and trap placement |
| **ROOM EVENTS** | Treasure and trap events assigned to rooms |

The board is **26 × 19** tiles.

### 9.1 Mission briefing
Works like the text editor: drag lines, double-click to edit, *Add line* for more text.

### 9.2 Map editor
Select a tool in the panel:

| Tool | Use |
|---|---|
| **Tile** | Click to toggle a single floor tile on/off |
| **Room** | Click to toggle an entire room |
| **── Wall / │ Wall** | Draw horizontal / vertical walls |
| **── Door / │ Door** | Place horizontal / vertical doors |

Flags (enabled only for the relevant tool):

- **Revealed** (Tile/Room): the area is visible from the start.
- **Invisible** (Walls): the wall exists but is not drawn.
- **Opened**, **Secret**, **Fake** (Doors): initial state and door behavior.

Hover the map for tooltips.

### 9.3 Monsters & Heroes
- The **monster pool** (Goblin, Orc, Fimir, Chaos Warrior, Skeleton, Zombie, Mummy, Gargoyle) is at the top. **Drag** a monster onto the board to place it.
- **Drag** a placed monster to move it.
- Click a monster to select it, then edit it in **✎ Edit Selected Monster**:
  - **Monster type** (a preset fills in the default stats)
  - **Body**, **Mind**, **Movement**, **Attack**, **Defense**, **Reward**
- Use the **Wandering Monster** drop-down (top right) to choose the roaming monster of the quest.
- Hero starting positions are also shown on the board and can be moved.

### 9.4 Furniture & Traps
- Drag items from the **OBJECT POOL** (furniture, stairs, doors-related objects, traps) onto the board.
- Multi-tile furniture is drawn with its real footprint and snaps to the grid; stairs are drawn with correct orientation.
- Use the orientation toggle to rotate an object where the game supports it.
- Objects that cannot be placed in a position are clamped to the nearest valid anchor.
- A small **✕** appears on removable objects.

### 9.5 Room events
- Click a room to select it.
- Choose **Treasure Events** or **Trap Events**, and pick the event from the **Select type / Event** list.
- **Right-click** a room to clear its event.
- The map shows marker symbols for rooms that already have events (✔ / 🔄 as appropriate).

---

## 10. Editing graphics (VGA / UNP)

### 10.1 File types
- **Single image** (e.g. `BOOK.VGA`, `PIC1.VGA`): one 320 × 200 picture, 256 colors.
- **Sprite archives** (e.g. `MONSTERS.VGA`, `HERO1–7.VGA`, `SPRITES.VGA`, `FURN.VGA`): many small images listed on the left and grouped by block. `FURN.VGA` additionally offers **furniture groups** that you can edit in a *composed* view.

### 10.2 Canvas controls
| Action | How |
|---|---|
| Zoom | Mouse wheel (current zoom shown in the info box) |
| Pan | Hold the **middle mouse button** and drag |
| Pick a color | **Right-click** on a pixel |
| Paint | Left-click / drag with **Draw** |

### 10.3 Tools
- **✎ Draw** — paints with the selected color; the **Brush** size ranges from 1 to 10.
- **🫗 Fill** — flood-fills a connected area.
- **▭ Select ➜** — drag a rectangle to select a region. Then:
  - `Ctrl+C` to copy, `Ctrl+V` to paste. After pasting, **drag** the pasted image to position it and press **Enter** to apply (or **Esc** to cancel).
  - **Delete** (button or `Del`) clears the selection.
  - **H flip** (button or `Ctrl+H`) mirrors it horizontally.
  - **↷ 90°** rotates it by 90°.

Images from the **system clipboard** can also be pasted.

### 10.4 Palette
- The 16 × 16 swatch grid shows the active palette. **Click** a swatch to choose your drawing color.
- The editor selects a palette automatically from the file name (Gremlin, Text 1, Pic 1, Hero 1–7). You can switch preset palettes (*Default, Gremlin, Text 1, Pic 1, Hero 1, 2, 3, 4, 6, 7*) or load a palette file.
- The info box shows zoom, palette name, image size, number of colors used and the current color.

### 10.5 Import / Export
- **Export PNG**: saves the current image as a PNG using the active palette.
- **Import image**: loads PNG, BMP, JPG or GIF and converts it to the active palette (nearest colors). For best results prepare images with the exact size and palette of the original.

### 10.6 Saving
Save with `Ctrl+S`. Compressed `.VGA` files are re-encoded automatically; `.UNP` files are saved uncompressed.

---

## 11. Editing sound effects (ALB / RLD)

- Open a sound bank (`GAME_FX.ALB` for AdLib, `GAME_FX.RLD` for Roland).
- The list shows all defined effects. The panel shows bank type, reference ID and data size, plus a visual summary.
- **▶ Play** — plays an approximate **synthesized preview** (not the true OPL2 / MT-32 sound).
- **⇩ Extract (bin)** — saves the raw effect data.
- **⇩ Extract preview (wav)** — saves the preview as a WAV file.
- **⇧ Import** — replaces the selected effect with a raw binary file.
- When saving, the original structure and tables are preserved and pointers are updated.

> Some of the labels in the sound panel are currently in Italian.

---

## 12. Typical workflows

### Translate or fix a game text
1. Open `ENGLISH.BIN` (or the language you want).
2. Use **SEARCH** to find the text.
3. Double-click the line, edit, press `Enter`.
4. Adjust the scroll size if needed.
5. Save with the same file name and copy it into the game folder.

### Create a new quest layout
1. Open a `QUESTxx.BIN`.
2. In **MAP EDITOR**, clear and redraw rooms/walls/doors.
3. In **MONSTERS & HEROES**, populate the board and tweak stats.
4. In **FURNITURES & TRAPS**, add furniture.
5. In **ROOM EVENTS**, assign treasure/trap events.
6. Edit the **MISSION BRIEFING** and save.

### Replace a picture
1. Open the VGA file.
2. Press **Export PNG** to get a starting template.
3. Edit it in your favorite pixel editor, keeping size and palette.
4. **Import image**, touch up with Draw/Fill, then save.

---

## 13. Tips and good practices

- Save often under **different file names** while experimenting.
- Keep the original game files untouched in a separate folder.
- When editing text, stay within the original length: the game has strict memory limits.
- Use the *×N* marker: changing an entry with several references changes **all** places that use it.
- For graphics, zoom in with the wheel for precise work and use the select tool to copy common parts.
- If something looks wrong after saving, reload the saved file in the editor to verify its contents.

---

## 14. Keyboard and mouse reference

| Input | Action |
|---|---|
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save file |
| `Ctrl+Z` | Undo |
| `Ctrl+Y`, `Ctrl+Shift+Z` | Redo |
| `Ctrl+C` / `Ctrl+V` | Copy / paste (VGA) |
| `Ctrl+H` | Horizontal flip of selection (VGA) |
| `Enter` / `Esc` | Apply / cancel paste (VGA) |
| `Del` | Delete selection (VGA) |
| Left click / drag | Select, move, paint, place |
| Double click | Edit a text line / jump to a button's entry |
| Right click | Color picker (VGA), clear event (Room events) |
| Middle drag | Pan image (VGA) |
| Mouse wheel | Zoom (VGA) or scroll the edit panel |

---

## 15. FAQ

**The editor says my file is unsupported.**
Use unmodified original DOS HeroQuest files with their original names.

**Where do I find the compressed/uncompressed versions?**
Compressed files (`.BIN`, `.VGA`) are the ones used by the game. `.UNP` files are their uncompressed equivalents and can be edited too.

**Can I use it on Linux or macOS?**
The Python code is cross-platform, but compressed files need `enc.exe` / `dec.exe`, which are Windows programs (they could work through Wine).

**My modified text crashes the game.**
You probably exceeded a length or memory limit. Shorten the text or free space in other entries.

**Drag & drop does not work.**
Install `tkinterdnd2` (or build the exe with `--collect-all tkinterdnd2`).

**The sound preview does not sound like the game.**
It is a simplified synthesis; the real sound comes from the OPL2 / MT-32 hardware emulation in DOSBox.

---

*HeroQuest is a trademark of its respective owners. This is an unofficial fan tool.*
