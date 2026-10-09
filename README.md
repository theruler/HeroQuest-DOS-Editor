# HeroQuest Editor

**An all-in-one editor for the DOS version of *HeroQuest* (Gremlin Graphics, 1991).**
Edit text, quests, maps, monsters, furniture, graphics and sound effects of the original game files through a single graphical tool, with a live preview rendered with the game's own bitmap font.

> Current version: **v6.8** — by **TheRuler**

---

## Table of contents

- [Features](#features)
- [Supported files](#supported-files)
- [Screenshots](#screenshots)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Building a standalone executable](#building-a-standalone-executable)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Credits and legal](#credits-and-legal)

A full step-by-step guide is available in **[MANUAL.md](MANUAL.md)**.

---

## Features

### General
- **Automatic file detection**: just open (or drag & drop) a game file and the editor picks the right mode.
- **Transparent compression**: `.BIN` and `.VGA` files are decompressed on load and recompressed on save through the bundled `dec.exe` / `enc.exe`. `.UNP` (uncompressed) variants are supported too.
- **Unlimited Undo / Redo** for every editing mode.
- **Unsaved-changes protection** when opening another file or closing the program.
- **Drag & drop** loading (via `tkinterdnd2`, optional).
- Dark UI, status bar with file information, and in-context hints for each mode.

### Text editing (language `.BIN`, `EQUESTS.BIN`, `INTRO.EXE`, `QUEST.EXE`)
- **WYSIWYG preview** using the game's original bitmap font (`heroquest.fnt`) over the real in-game backgrounds.
- Edit **scrolls (text boxes)**, **plain texts** and **button labels** of the five game languages (Italian, English, Spanish, German, French).
- **Drag** text lines, buttons and whole scrolls with the mouse; **resize** scrolls with the corner handle; **double-click** a line to jump to its entry field; **add/remove** lines.
- Full support for **accented characters** (à, è, é, ì, ò, ù, ñ, ü, ö, ä, ç, ¿, ¡ …) mapped to the game's own character codes.
- **Search / filter** in the entry list.
- Byte-budget counters where the original format has hard limits (e.g. the `INTRO.EXE` text area), so you never overflow the file.
- Pointer-aware rebuilding: shared pointers are detected and shown (`×N` duplicates).

### Quest editor (`QUESTxx.BIN`)
- **Mission briefing** text editor.
- **Map editor** (26 × 19 board): paint tiles, whole rooms, walls and doors; door flags (**Opened / Secret / Fake**), wall flag (**Invisible**) and tile flag (**Revealed**).
- **Monsters & Heroes**: drag monsters from the pool onto the map, move them, and edit each monster's **type, body, mind, movement, attack, defense and reward**; choose the **wandering monster**; place the heroes' starting positions.
- **Furniture & Traps**: drag furniture (including multi-tile pieces and stairs with correct orientation) and traps onto the board; rotate/toggle orientation.
- **Room events**: assign **treasure events** and **trap events** to rooms, with a visual map and tooltips.

### Graphics editor (`.VGA`, `.UNP`)
- Full-screen **320 × 200** images and **multi-sprite** archives (monsters, heroes, furniture, sprites, …).
- Tools: **Draw** (brush 1–10 px), **Flood fill**, **Rectangle select** with **copy / paste / delete / horizontal flip / rotate 90°**.
- **Zoom** with the mouse wheel and **pan** with the middle button; right-click to **pick a color**.
- **256-color palette viewer** and selector with built-in presets: *Default, Gremlin, Text 1, Pic 1, Hero 1, 2, 3, 4, 6, 7*; palette auto-selection by file name.
- **Furniture groups** can be edited in a *composed* view; changes are applied to the right tiles.
- **Import image** (PNG, BMP, JPG, GIF — quantized to the active palette) and **Export PNG**.
- Paste images from the system **clipboard**.

### Sound effects editor (`.ALB`, `.RLD`)
- Browse the effects stored in **AdLib/OPL2 (ALB)** and **Roland MT-32 / GM (RLD)** sound banks.
- **Play** an approximate synthesized preview.
- **Extract** an effect as raw binary or as a WAV preview, and **import** a replacement effect.
- The original bank structure is preserved when saving.

---

## Supported files

| File | What you can edit |
|---|---|
| `ENGLISH.BIN`, `ITALIAN.BIN`, `SPANISH.BIN`, `GERMAN.BIN`, `FRENCH.BIN` | All game texts, scrolls and button labels (also `.UNP` versions) |
| `QUESTxx.BIN` | Quest briefing, map, monsters, heroes, furniture, traps, events |
| `EQUESTS.BIN` | Paged quest texts for all five languages |
| `INTRO.EXE` | Intro texts and fixed system strings |
| `QUEST.EXE` | Quest screen texts, position strings, DOS strings |
| `*.VGA` / `*.UNP` | Full-screen images and sprite archives (`BOOK`, `BORDERED`, `FURN`, `GRAPHICS`, `GREMLIN`, `HERO1–7`, `INVENT`, `MAPS`, `MEN`, `MONSTERS`, `ODDS&SOD`, `PIC1`, `QUESTB`, `SHOPMP`, `SHOPSP`, `SPELLIT`, `SPRITES`, `TEXT1`, `WIZBACK`) |
| `*.ALB`, `*.RLD` | Sound effect banks |

> **Always work on copies of your game files.** Keep a backup of the originals.

---

## Screenshots

<img width="1106" height="902" alt="image" src="https://github.com/user-attachments/assets/0ee83f38-0d7e-4ee8-bb5d-2e8e58f952fc" />

<img width="1097" height="901" alt="image" src="https://github.com/user-attachments/assets/9e88900e-4cb1-40aa-b82b-8361ce7bf12a" />

<img width="1101" height="900" alt="image" src="https://github.com/user-attachments/assets/2dc8fb6d-b7eb-4e12-90b3-9c397d868984" />

<img width="1100" height="902" alt="image" src="https://github.com/user-attachments/assets/118d2e22-6d71-4667-a649-93ac4872d1cf" />

<img width="1103" height="767" alt="image" src="https://github.com/user-attachments/assets/8528654d-1d73-4540-b599-c0ecad164c07" />

---

## Requirements

- **Windows** (the bundled `enc.exe` / `dec.exe` are Windows executables and are required to open/save compressed `.BIN` / `.VGA` files).
- **Python 3.8+** with Tkinter (only if running from source).
- [Pillow](https://pypi.org/project/pillow/)
- [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) *(optional, enables drag & drop)*

A pre-built single-file `HeroQuestEditor.exe` needs nothing else.

---

## Installation

### Option A — Pre-built executable
Download `HeroQuestEditor.exe` from the **Releases** page and run it. No installation required.

### Option B — Run from source
```bash
git clone https://github.com/<your-user>/heroquest-editor.git
cd heroquest-editor/data
pip install pillow tkinterdnd2
python main.py
```
If Pillow or tkinterdnd2 are missing, `main.py` tries to install them automatically when running from source.

---

## Quick start

1. Launch the editor.
2. Click **LOAD** (or press `Ctrl+O`), or **drag & drop** a game file onto the window.
3. Pick an entry from the list on the left.
4. Edit on the canvas and/or in the panel below it.
5. Click **SAVE** (or press `Ctrl+S`) and choose the destination file name.
6. Copy the modified file back into your HeroQuest folder and test it in DOSBox.

See [MANUAL.md](MANUAL.md) for details on every mode.

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save file |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+C` / `Ctrl+V` | Copy / paste selection (VGA modes) |
| `Ctrl+H` | Flip selection horizontally (VGA modes) |
| `Enter` / `Esc` | Confirm / cancel a pending paste (VGA modes) |
| `Del` | Delete selection (VGA modes) |
| Mouse wheel | Zoom (VGA) / scroll the edit panel |
| Middle button drag | Pan (VGA) |
| Right click | Pick color (VGA) · clear event (Room events) |

---

## Building a standalone executable

The project is ready for **PyInstaller `--onefile`**. All resources are located at run time through `resource_path()` (which uses `sys._MEIPASS` when frozen).

From the `data` folder just run:

```bat
build.bat
```

or manually:

```bat
python -m pip install --upgrade pyinstaller pillow tkinterdnd2
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name HeroQuestEditor ^
  --collect-all tkinterdnd2 ^
  --add-data "enc.exe;." --add-data "dec.exe;." ^
  --add-data "heroquest.fnt;." ^
  --add-data "background1.png;." --add-data "background2.png;." --add-data "background3.png;." ^
  --paths . main.py
```

The result is `dist/HeroQuestEditor.exe`.

Notes:
- `--collect-all tkinterdnd2` is required to ship the tkdnd native libraries (drag & drop).
- Some antivirus programs flag PyInstaller one-file executables as false positives. Use `--onedir` or whitelist the file if that happens.
- To see error output, rebuild without `--windowed` and start the exe from a terminal.

---

## Project structure

```
data/
├── main.py              # Entry point, dependency check, window creation
├── config.py            # Constants, palette, file lists, resource_path()
├── utils.py             # Text codec, enc/dec wrappers, font loader, helpers
├── editor.py            # Main Editor class: UI, load/save, undo/redo, mouse
├── editor_text.py       # Text modes (BIN, EQUESTS, INTRO, QUEST.EXE)
├── editor_quest_map.py  # Quest map / monsters / furniture / events editor
├── editor_vga.py        # VGA image and sprite editor
├── editor_fx.py         # Sound effects (ALB / RLD) editor
├── editor_lists.py      # Left-hand list population and status bar
├── models/
│   ├── hq_bin.py        # Language BIN files
│   ├── hq_quest.py      # QUESTxx.BIN
│   ├── hq_paged.py      # EQUESTS.BIN
│   ├── hq_intro.py      # INTRO.EXE
│   ├── hq_quest_exe.py  # QUEST.EXE
│   ├── hq_vga.py        # VGA images, sprites, palettes
│   └── hq_fx.py         # ALB / RLD sound banks
├── enc.exe / dec.exe    # Game compression tools
├── heroquest.fnt        # Original bitmap font
├── background1-3.png    # Preview backgrounds
└── build.bat            # PyInstaller build script
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Files missing" dialog at start | `enc.exe`, `dec.exe`, `heroquest.fnt` and the three `background*.png` must sit next to `main.py` (or be bundled with `--add-data`). |
| "File unsupported" / wrong mode | Make sure the file is an original, unmodified HeroQuest DOS file with its original name. |
| Drag & drop does not work | Install `tkinterdnd2`; when building, use `--collect-all tkinterdnd2`. |
| Black console window flashes | Use `--windowed` when building; the editor already hides the `enc/dec` console. |
| Game crashes after editing text | You probably exceeded a size limit: check the byte counters and keep texts within the original budget. |
| No sound in preview | Preview uses `winsound` on Windows; on other systems it needs `afplay` (macOS) or a command-line player (Linux). |

---

## Credits and legal

- Editor created by **TheRuler**.
- *HeroQuest* is a trademark of its respective owners. The DOS game was developed by Gremlin Graphics.
- This is an **unofficial fan tool**. It does **not** include any game data: you must own a legitimate copy of the game.
- Add your preferred license in a `LICENSE` file (e.g. MIT) before publishing.
