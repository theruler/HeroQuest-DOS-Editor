# Sezione 6: Formato QUESTXX.BIN, tabelle mostri/oggetti
import struct
from utils import decode_text, encode_text

QUEST_MAP_SIZE      = 0x200
QUEST_HERO_OFFSET   = 0x400
QUEST_HERO_SIZE     = 12
QUEST_TREAS_OFFSET  = 0x40C
QUEST_TRAPS_OFFSET  = 0x437
QUEST_EVENTS_SIZE   = 43
QUEST_POP_OFFSET    = 0x462
QUEST_POP_HDR_SIZE  = 12

QUEST_MAP_W = 26
QUEST_MAP_H = 19

# ── Monster types (Graphic & Colors) ───────────────────────────────────────────
MONSTER_TYPES = {
    0x00: ("Goblin",            "👹", "#4ade80"),
    0x01: ("Orc",               "👺", "#6a3a1a"),
    0x02: ("Fimir",             "👾", "#3a7a2a"),    
    0x03: ("Chaos Warrior",     "⚔", "#0044cc"),
    0x04: ("Skeleton",          "💀", "#aaaaaa"),
    0x05: ("Zombie",            "🧟", "#4a6a3a"),
    0x06: ("Mummy",             "🧛", "#9a7a3a"),
    0x07: ("Gargoyle",          "🗿", "#6a6a8a"),
    0x08: ("Orc Warlord Ulag",  "👺", "#bb9900"),
    0x09: ("Orc Lord Grak",     "👺", "#bb9900"),
    0x0A: ("Balur the Fire Mage","🦹", "#bb9900"),
    0x0B: ("Stone Chaos Warrior","⚔", "#aaaaaa"),
    0x1A: ("The Witch Lord",    "🗿", "#bb9900"),
    0x14: ("Spirit Rider",      "💀", "#aa8a4a"),
    0x15: ("Death Myst",        "🌀", "#aaaaaa"),
    0x16: ("Bellthor",          "🦹", "#bb9900"),
    0x17: ("Skulmar",           "🦹", "#bb9900"),
    0x18: ("Doom Guard",        "⚔", "#cc2222"),
    0x19: ("Witch Kessandria",  "🦹", "#bb9900"),
    0x1A: ("The Witch Lord",    "🧙", "#bb9900"),
    0x1B: ("Stone Statue",      "🗿", "#aaaaaa"),
}

# ── Monster Table (Stats & Defaults) ───────────────────────────────────────────
MONSTER_TABLE = {
    # atk_dice: (name, mtype, bp_body, bp_mind, movement, attack, defense, reward)
    0x00: ("Goblin",                  0x00, 1, 1, 10, 2, 1, "—"),
    0x01: ("Orc",                     0x01, 1, 2,  8, 3, 2, "—"),
    0x02: ("Fimir",                   0x02, 2, 3,  6, 3, 3, "—"),
    0x03: ("Chaos Warrior",           0x03, 3, 3,  6, 3, 4, "—"),
    0x04: ("Skeleton",                0x04, 1, 0,  6, 2, 2, "—"),
    0x05: ("Zombie",                  0x05, 1, 0,  4, 2, 3, "—"),
    0x06: ("Mummy",                   0x06, 2, 0,  4, 3, 4, "—"),
    0x07: ("Gargoyle",                0x07, 3, 4,  6, 4, 4, "—"),
    0x08: ("Orc Warlord Ulag",        0x01, 2, 3, 10, 4, 5, "100 gold"),
    0x09: ("Orc Lord Grak",           0x01, 3, 3,  8, 4, 4, "—"),
    0x0A: ("Balur the Fire Mage",     0x07, 3, 7,  8, 2, 5, "Message"),
    0x0B: ("Stone Chaos Warrior",     0x07, 1, 1,  1, 2, 6, "—"),
    0x0C: ("The Witch Lord",          0x07, 4, 6, 10, 5, 6, "—"),
    0x0D: ("Awakened Witch Lord",     0x07, 4, 6,  1, 3, 5, "—"),
    0x0E: ("Goblin 💰",              0x00, 1, 1, 10, 2, 1, "10 gold"),
    0x0F: ("Orc 💰",                 0x01, 1, 2,  8, 3, 2, "20 gold"),
    0x10: ("Fimir 💰",               0x02, 2, 3,  6, 3, 3, "30 gold"),
    0x11: ("Chaos Warrior 💰",       0x03, 3, 3,  6, 3, 4, "40 gold"),  
    0x12: ("Chaos Warrior",           0x03, 3, 3,  6, 3, 4, "Orc's bane"),
    0x13: ("Zombie 💰",              0x05, 1, 0,  4, 2, 3, "20 gold"),
    0x14: ("Spirit Rider",            0x03, 3, 3,  8, 4, 3, "—"),
    0x15: ("Death Mist",              0x00, 1, 0,  6, 4, 3, "—"),
    0x16: ("Bellthor",                0x07, 3, 3,  6, 4, 6, "Message"),
    0x17: ("Skulmar",                 0x07, 3, 4,  8, 5, 6, "—"),
    0x18: ("Doomguard",               0x07, 3, 3,  6, 4, 6, "—"),
    0x19: ("Witch Kessandria",        0x07, 3, 4,  6, 4, 6, "—"),
    0x1A: ("The Witch Lord (Return)", 0x07, 4, 5, 10, 5, 6, "Message"),
    0x1B: ("Stone Statue",            0x01, 1, 0,  8, 3, 2, "—"),
}

# ── Object types ───────────────────────────────────────────────────────────────
# Formato: (Nome, Categoria, Icona, Colore, TestoAlternativo, Larghezza, Altezza, Filler_ID)
OBJECT_TYPES = {
    0x30: ("Rock",                  "obj",    "🪨", "#888888", "Rock",          1, 1, None),
    0x31: ("Rock(Removable)",       "obj",    "🪨", "#888888", "Rock",          1, 1, None),
    0x32: ("Pit (Hidden)",          "trap",   "▣", "#cc2222", "Pit",            1, 1, None),
    0x33: ("Pit (Opened)",          "trap",   "▣", "#888888", "Pit",            1, 1, None),
    0x34: ("Falling Rock",          "trap",   "⬇", "#cc4422", "Falling Rock",   1, 1, None),
    0x36: ("Spear",                 "trap",   "🔱", "#cc4422", "Spear",         1, 1, None),
    0x37: ("Teleport",              "trap",   "🌀", "#3366ff", "Teleport",      1, 1, None),
    0x38: ("Stairs (NW)",           "obj",    "🪜", "#777777", "Stairs",        1, 1, None),
    0x39: ("Stairs (SW)",           "obj",    "🪜", "#777777", "Stairs",        1, 1, None),
    0x3A: ("Stairs (NE)",           "obj",    "🪜", "#555555", "Stairs",        1, 1, None),
    0x3B: ("Stairs (SE)",           "obj",    "🪜", "#555555", "Stairs",        1, 1, None),
    0x42: ("Table",                 "filler", "",  "#996633", "Table",         1, 1, None),
    0x44: ("Torture Table",         "filler", "",  "#996633", "Torture Table", 1, 1, None),
    0x45: ("Tomb",                  "filler", "",  "#888888", "Tomb",          1, 1, None),
    0x46: ("Alchemy Table",         "filler", "",  "#996633", "Alchemy Table", 1, 1, None),
    0x47: ("Fireplace",             "filler", "",  "#888888", "Fireplace",     1, 1, None),
    0x48: ("Closet",                "filler", "",  "#996633", "Closet",        1, 1, None),
    0x49: ("Library",               "filler", "",  "#996633", "Library",       1, 1, None),
    0x4A: ("Armour Rack",           "filler", "",  "#888888", "Armour Rack",   1, 1, None),
    0x4B: ("Table 2x3",             "furn",   "🪑", "#996633", "Table",         2, 3, 0x42),
    0x4C: ("Table 3x2",             "furn",   "🪑", "#996633", "Table",         3, 2, 0x42),
    0x4D: ("Torture Table 3x2",     "furn",   "🔗", "#996633", "Torture Table", 3, 2, 0x44),
    0x4E: ("Torture Table 2x3",     "furn",   "🔗", "#996633", "Torture Table", 2, 3, 0x44),
    0x4F: ("Alchemy Table 2x3",     "furn",   "🧪", "#996633", "Alchemy Table", 2, 3, 0x46),
    0x50: ("Alchemy Table 3x2",     "furn",   "🧪", "#996633", "Alchemy Table", 3, 2, 0x46),
    0x52: ("Tomb 2x3",              "furn",   "⚰", "#888888", "Tomb",          2, 3, 0x45),
    0x53: ("Tomb 3x2",              "furn",   "⚰", "#888888", "Tomb",          3, 2, 0x45),
    0x54: ("Closet 1x3",            "furn",   "🚪", "#996633", "Closet",        1, 3, 0x48),
    0x55: ("Armour Rack 3x1",       "furn",   "🛡", "#888888", "Armour Rack",   3, 1, 0x4A),
    0x56: ("Library 1x3",           "furn",   "📚", "#996633", "Library",       1, 3, 0x49),
    0x57: ("Fireplace 3x1",         "furn",   "🔥", "#888888", "Fireplace",     3, 1, 0x47),
    0x58: ("Library 3x1",           "furn",   "📚", "#996633", "Library",       3, 1, 0x49),
    0x59: ("Fireplace 1x3",         "furn",   "🔥", "#888888", "Fireplace",     1, 3, 0x47),
    0x5A: ("Closet 3x1",            "furn",   "🚪", "#996633", "Closet",        3, 1, 0x48),
    0x5B: ("Armour Rack 1x3",       "furn",   "🛡", "#888888", "Armour Rack",   1, 3, 0x4A),
    0x5C: ("Chest (S)",             "obj",    "💰", "#ccaa00", "Chest",         1, 1, None),
    0x5D: ("Chest (E)",             "obj",    "💰", "#ccaa00", "Chest",         1, 1, None),
    0x5E: ("Throne (S)",            "obj",    "👑", "#ccaa00", "Throne",        1, 1, None),
    0x5F: ("Throne (E)",            "obj",    "👑", "#ccaa00", "Throne",        1, 1, None),
}

# ── Hero info ──────────────────────────────────────────────────────────────────
HERO_TYPES = [
    ("Barbarian", "B", "#cc3333", {0x23:"N", 0x1D:"E", 0x20:"S", 0x26:"W"}),
    ("Dwarf",     "D", "#aa6622", {0x2F:"N", 0x29:"E", 0x2C:"S", 0x32:"W"}),
    ("Elf",       "E", "#33aa33", {0x3B:"N", 0x35:"E", 0x38:"S", 0x3E:"W"}),
    ("Wizard",    "W", "#4488cc", {0x47:"N", 0x41:"E", 0x44:"S", 0x4A:"W"}),
]

# ── Treasure/Trap events ───────────────────────────────────────────────────────
TREASURE_EVENTS = {
    0x00: "None",
    0x01: "Chest: Trapped, disarm it",
    0x02: "Chest: Trapped, -1 BP",
    0x03: "Cupboard: 30 coins + healing",
    0x04: "Chest: -1 BP +100 coins",
    0x05: "Weapon rack: Spear",
    0x06: "Chest: 50 coins + healing",
    0x07: "Chest: 250 coins (heavy)",
    0x08: "Throne: Melar's key",
    0x09: "Talisman of lore",
    0x0A: "Borin's armour",
    0x0B: "Chest: Karlen's 200 coins",
    0x0C: "Chest: 150 coins + wand",
    0x0D: "Chest: 100 coins (vanish)",
    0x0E: "Shield",
    0x0F: "Chest: Trapped, beware",
    0x10: "Chest: Gargoyle awakes",
    0x11: "Spirit blade",
    0x12: "Chest: 200 coins",
    0x13: "Chest: 200 coins",
    0x14: "Chest: 300 coins",
    0x15: "Chest: 100 coins + healing",
    0x16: "Chest: Trapped, -1 BP",
    0x17: "Chest: Trapped, disarm",
    0x18: "Table: Agrain's keys",
    0x19: "2 Chests: 200 coins x2",
    0x1A: "Chest: 350 coins",
    0x1B: "Chest: 250 coins",
    0x1C: "Throne: 500 coins",
    0x1D: "Chest: Potion of healing",
    0x1E: "Mine entrance + 5000 coins",
    0xFF: "Room already searched",
}

DEFAULT_ROOMS = bytes([
    0x01,0x01,0x01,0x01,0x02,0x02,0x02,0x02,0x02,0x02,0x03,0x03,0x03,0x03,0x03,0x03,0x04,0x04,0x04,0x04,0x04,0x04,0x05,0x05,0x05,0x05,
    0x01,0x15,0x15,0x15,0x15,0x16,0x16,0x16,0x16,0x17,0x17,0x17,0x03,0x03,0x18,0x18,0x18,0x19,0x19,0x19,0x19,0x1A,0x1A,0x1A,0x1A,0x05,
    0x01,0x15,0x15,0x15,0x15,0x16,0x16,0x16,0x16,0x17,0x17,0x17,0x03,0x03,0x18,0x18,0x18,0x19,0x19,0x19,0x19,0x1A,0x1A,0x1A,0x1A,0x05,
    0x01,0x15,0x15,0x15,0x15,0x16,0x16,0x16,0x16,0x17,0x17,0x17,0x03,0x03,0x18,0x18,0x18,0x19,0x19,0x19,0x19,0x1A,0x1A,0x1A,0x1A,0x05,
    0x01,0x1B,0x1B,0x1B,0x1B,0x1C,0x1C,0x1C,0x1C,0x17,0x17,0x17,0x03,0x03,0x18,0x18,0x18,0x19,0x19,0x19,0x19,0x1A,0x1A,0x1A,0x1A,0x05,
    0x06,0x1B,0x1B,0x1B,0x1B,0x1C,0x1C,0x1C,0x1C,0x17,0x17,0x17,0x08,0x08,0x18,0x18,0x18,0x1D,0x1D,0x1D,0x1D,0x1E,0x1E,0x1E,0x1E,0x0A,
    0x06,0x1B,0x1B,0x1B,0x1B,0x1C,0x1C,0x1C,0x1C,0x07,0x08,0x08,0x08,0x08,0x08,0x08,0x09,0x1D,0x1D,0x1D,0x1D,0x1E,0x1E,0x1E,0x1E,0x0A,
    0x06,0x1B,0x1B,0x1B,0x1B,0x1C,0x1C,0x1C,0x1C,0x07,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x09,0x1D,0x1D,0x1D,0x1D,0x1E,0x1E,0x1E,0x1E,0x0A,
    0x06,0x1B,0x1B,0x1B,0x1B,0x1C,0x1C,0x1C,0x1C,0x07,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x09,0x1D,0x1D,0x1D,0x1D,0x1E,0x1E,0x1E,0x1E,0x0A,
    0x06,0x06,0x06,0x06,0x07,0x07,0x07,0x07,0x07,0x07,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x09,0x09,0x09,0x09,0x09,0x09,0x0A,0x0A,0x0A,0x0A,
    0x0B,0x20,0x20,0x20,0x20,0x21,0x21,0x22,0x22,0x0C,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x0E,0x23,0x23,0x23,0x23,0x24,0x24,0x24,0x24,0x0F,
    0x0B,0x20,0x20,0x20,0x20,0x21,0x21,0x22,0x22,0x0C,0x1F,0x1F,0x1F,0x1F,0x1F,0x1F,0x0E,0x23,0x23,0x23,0x23,0x24,0x24,0x24,0x24,0x0F,
    0x0B,0x20,0x20,0x20,0x20,0x21,0x21,0x22,0x22,0x0C,0x0D,0x0D,0x0D,0x0D,0x0D,0x0D,0x0E,0x23,0x23,0x23,0x23,0x24,0x24,0x24,0x24,0x0F,
    0x0B,0x20,0x20,0x20,0x20,0x26,0x26,0x26,0x26,0x27,0x27,0x27,0x0D,0x0D,0x28,0x28,0x28,0x28,0x23,0x23,0x23,0x24,0x24,0x24,0x24,0x0F,
    0x0B,0x25,0x25,0x25,0x25,0x26,0x26,0x26,0x26,0x27,0x27,0x27,0x0D,0x0D,0x28,0x28,0x28,0x28,0x29,0x29,0x29,0x2A,0x2A,0x2A,0x2A,0x0F,
    0x10,0x25,0x25,0x25,0x25,0x26,0x26,0x26,0x26,0x27,0x27,0x27,0x12,0x12,0x28,0x28,0x28,0x28,0x29,0x29,0x29,0x2A,0x2A,0x2A,0x2A,0x14,
    0x10,0x25,0x25,0x25,0x25,0x26,0x26,0x26,0x26,0x27,0x27,0x27,0x12,0x12,0x28,0x28,0x28,0x28,0x29,0x29,0x29,0x2A,0x2A,0x2A,0x2A,0x14,
    0x10,0x25,0x25,0x25,0x25,0x26,0x26,0x26,0x26,0x27,0x27,0x27,0x12,0x12,0x28,0x28,0x28,0x28,0x29,0x29,0x29,0x2A,0x2A,0x2A,0x2A,0x14,
    0x10,0x10,0x10,0x10,0x11,0x11,0x11,0x11,0x11,0x11,0x12,0x12,0x12,0x12,0x12,0x12,0x13,0x13,0x13,0x13,0x13,0x13,0x14,0x14,0x14,0x14,
])

def _is_quest_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            raw = f.read()
            
        if len(raw) < QUEST_POP_OFFSET + QUEST_POP_HDR_SIZE:
            return False

        for b in raw[:0x200]:
            room_id = b & 0x3F 
            if room_id > 0x2A: 
                return False
                
        mon_start = struct.unpack_from('<H', raw, QUEST_POP_OFFSET + 0x04)[0]
        return mon_start == 0x000C
    except Exception:
        return False

class HQQuestFile:
    def __init__(self):
        self.raw             = b""
        self.rooms_layer     = bytearray(DEFAULT_ROOMS) + bytearray(0x200 - len(DEFAULT_ROOMS))
        self.walls_layer     = bytearray(0x200)
        self.hero_data       = bytearray(QUEST_HERO_SIZE)
        self.treasure_events = bytearray(QUEST_EVENTS_SIZE)
        self.trap_events     = bytearray(QUEST_EVENTS_SIZE)
        self._pop_raw_prefix = b""
        self.text_lines      = []
        self._trailing       = b""
        self.monsters        = []
        self.wandering_monster = None
        self.objects         = []

    def load(self, path: str):
        self.raw = open(path, "rb").read()
        raw = self.raw

        self.rooms_layer     = bytearray(raw[0x000:0x200])
        self.walls_layer     = bytearray(raw[0x200:0x400])
        self.hero_data       = bytearray(raw[QUEST_HERO_OFFSET : QUEST_HERO_OFFSET + QUEST_HERO_SIZE])
        self.treasure_events = bytearray(raw[QUEST_TREAS_OFFSET : QUEST_TREAS_OFFSET + QUEST_EVENTS_SIZE])
        self.trap_events     = bytearray(raw[QUEST_TRAPS_OFFSET : QUEST_TRAPS_OFFSET + QUEST_EVENTS_SIZE])

        base = QUEST_POP_OFFSET
        text_start     = struct.unpack_from('<H', raw, base + 0x00)[0]
        text_size      = struct.unpack_from('<H', raw, base + 0x02)[0]
        mon_block_start= struct.unpack_from('<H', raw, base + 0x04)[0]
        mon_block_size = struct.unpack_from('<H', raw, base + 0x06)[0]
        obj_block_start= struct.unpack_from('<H', raw, base + 0x08)[0]
        nr_objects     = struct.unpack_from('<H', raw, base + 0x0A)[0]

        self.monsters = []
        self.wandering_monster = None
        if mon_block_size > 0:
            mp = base + mon_block_start
            count = mon_block_size // 10
            for i in range(count):
                off = mp + i * 10
                if off + 10 > len(raw): break
                flags    = raw[off + 0]
                x        = raw[off + 1]
                y        = raw[off + 2]
                room_ph  = raw[off + 3]
                mem_ph   = struct.unpack_from('<H', raw, off + 4)[0]
                cond     = raw[off + 6]
                bp_byte  = raw[off + 7]
                mtype    = raw[off + 8]
                atk_dice = raw[off + 9]
                entry = {
                    "flags":    flags,
                    "x":        x,
                    "y":        y,
                    "room_ph":  room_ph,
                    "mem_ph":   mem_ph,
                    "cond":     cond,
                    "bp_body":  (bp_byte >> 4) & 0xF,
                    "bp_mind":  bp_byte & 0xF,
                    "type":     mtype,
                    "atk_dice": atk_dice,
                }
                if i == 0:
                    self.wandering_monster = entry
                else:
                    self.monsters.append(entry)

        self.objects = []
        if nr_objects > 0:
            op = base + obj_block_start
            for i in range(nr_objects):
                off = op + i * 3
                if off + 3 > len(raw): break
                x     = raw[off + 0]
                y     = raw[off + 1]
                otype = raw[off + 2]
                self.objects.append({
                    "type": otype,
                    "x":    x,
                    "y":    y,
                })

        self._pop_raw_prefix = raw[base : base + text_start]

        abs_text = base + text_start
        self.text_lines = []
        pos = abs_text
        end = abs_text + text_size

        while pos < end:
            if raw[pos] != 0x11: break
            if pos + 2 >= end: break
            y, x = raw[pos + 1], raw[pos + 2]
            pos += 3
            s = pos
            while pos < end and raw[pos] != 0x11 and raw[pos] != 0x00:
                pos += 1
            self.text_lines.append({"row": y, "col": x, "text": decode_text(raw[s:pos])})
            if pos < end and raw[pos] == 0x00:
                pos += 1
                break

        self._trailing = raw[base + text_start + text_size :]

    def rebuild(self) -> bytes:
        if len(self.monsters) > 31:
            raise Exception(f"Too many monsters: {len(self.monsters)} > 31. Save aborted.")

        mon_block = bytearray()
        mon_entries = []
        if self.wandering_monster is not None:
            mon_entries.append(self.wandering_monster)
        mon_entries.extend(self.monsters)
        for m in mon_entries:
            bp_byte = ((m.get("bp_body", 1) & 0xF) << 4) | (m.get("bp_mind", 0) & 0xF)
            mon_block += bytes([m["flags"], m["x"], m["y"], m["room_ph"]])
            mon_block += struct.pack('<H', m["mem_ph"])
            mon_block += bytes([m["cond"], bp_byte, m["type"], m["atk_dice"]])

        obj_block = bytearray()
        for o in self.objects:
            obj_block += bytes([o["x"], o["y"], o["type"]])

        text_body = bytearray()
        for l in self.text_lines:
            text_body += bytes([0x11, l["row"], l["col"]])
            text_body += encode_text(l["text"])
        text_size = len(text_body)

        mon_start = 0x0C
        mon_size  = len(mon_block)
        obj_start = mon_start + mon_size
        nr_obj    = len(self.objects)
        text_off  = obj_start + len(obj_block)

        pop_hdr = struct.pack('<HHHHHH',
            text_off, text_size,
            mon_start, mon_size,
            obj_start, nr_obj)

        result = bytearray()
        result += bytes(self.rooms_layer[:0x200]).ljust(0x200, b'\x00')
        result += bytes(self.walls_layer[:0x200]).ljust(0x200, b'\x00')
        result += bytes(self.hero_data[:QUEST_HERO_SIZE]).ljust(QUEST_HERO_SIZE, b'\x00')
        result += bytes(self.treasure_events[:QUEST_EVENTS_SIZE]).ljust(QUEST_EVENTS_SIZE, b'\x00')
        result += bytes(self.trap_events[:QUEST_EVENTS_SIZE]).ljust(QUEST_EVENTS_SIZE, b'\x00')
        result += pop_hdr
        result += mon_block
        result += obj_block
        result += text_body
        result += b'\x00'
        return bytes(result)

    def get_room_at(self, x, y):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            return self.rooms_layer[y * QUEST_MAP_W + x]
        return 0

    def set_room_at(self, x, y, val):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            self.rooms_layer[y * QUEST_MAP_W + x] = val & 0xFF

    def get_wall_at(self, x, y):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            return self.walls_layer[y * QUEST_MAP_W + x]
        return 0

    def set_wall_at(self, x, y, val):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            self.walls_layer[y * QUEST_MAP_W + x] = val & 0xFF

    def get_room_properties(self, x, y):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            val = self.rooms_layer[y * QUEST_MAP_W + x]
            room_id   = val & 0x3F
            show_tile = bool(val & 0x80)
            show_walls = bool(val & 0x40)
            return room_id, show_tile, show_walls
        return 0, False, False

    def set_room_properties(self, x, y, room_id, show_tile, show_walls):
        if 0 <= x < QUEST_MAP_W and 0 <= y < QUEST_MAP_H:
            new_val = room_id & 0x3F
            if show_tile:  new_val |= 0x80
            if show_walls: new_val |= 0x40
            self.rooms_layer[y * QUEST_MAP_W + x] = new_val
