# CIV2 RULES.TXT → CTP2 Dimension Map
## MoMJR Port Reference

Derived from `H:\Games\civ2\SCENARIO\MOMJR\RULES.TXT` analysis.
Cross-mod SLIC schema analysis (AE × Cradle × Ages of Man × LOTR) lives in `dimension_inventory.md` (repo root).

---

## Patch Tool

Use `ctpedit.py` to port dimensions with all cascade effects pre-wired:

```
python Scenarios/mom/tools/ctpedit.py status
python Scenarios/mom/tools/ctpedit.py show   <dimension>
python Scenarios/mom/tools/ctpedit.py patch  <dimension>   [--dry-run]
python Scenarios/mom/tools/ctpedit.py patch  all
```

Dimensions: `advances`, `units`, `improvements`, `wonders`

Each `patch` run calls `ctp2_generator.py` (idempotent) then `mom_audit.py`.
Cascade effects for each dimension are documented in the tool and below.

**Key lessons wired in:**
- Unit block removal uses `UnitsFile.remove_unit()` — never regex (nested sub-blocks)
- `unit_mask.csv` lists stock CTP2 / test units to remove at generation time
- `building_uniticon.csv` is the canonical proxy TGA path for CTP2-only improvements
- `dimension_inventory.md` is 1st-class source of truth for what belongs in the mod

---

## How to Read This Document

Each section is one CIV2 `@SECTION` block.  For each:

- **CIV2 schema** — field-by-field breakdown of what the section encodes
- **CTP2 files** — which gamedata files carry the equivalent data
- **Interconnections** — what other dimensions this one cross-references (by abbreviation, slot index, or string key)
- **MoMJR notes** — mod-specific content, disabled slots, and porting risks

---

## 1. @COSMIC — Global game constants

### CIV2 fields (54 scalar values, lines 20–73)
| Value | Meaning | CTP2 analog |
|---|---|---|
| Road movement multiplier | Roads multiply move allowance | `Const.txt` → `MOVE_POINTS_*` |
| Trireme loss chance | Sea hazard | not directly ported |
| Food per citizen | Population consumption | `Pop.txt` food coefficients |
| Food box rows | Population growth rate | `Pop.txt` / `citysize*.txt` |
| Shield box rows | Production accumulation | `Const.txt` production constants |
| Settlers eat (Monarchy / Communism) | Worker maintenance | `Units.txt` SlaveFood / upkeep |
| City size for 1st unhappiness | Happiness threshold | `Const.txt` CITY_CONTENT_POP |
| Riot factor (# cities) | Corruption analog | `govern.txt` CrimeCoef |
| Aqueduct / Sewer size caps | Building-gated growth | `buildings.txt` CityCapSize |
| Tech paradigm | Science slowdown multiplier | `Advance.txt` / `Const.txt` |
| Engineer transform time | Tile improvement speed | `tileimp.txt` TurnsToComplete |
| Govt support thresholds | Free unit slots by govt | `govern.txt` FreeUnits |
| Communism palace dist. | Corruption override | `govern.txt` CorruptionCoef |
| Fundamentalism science % | Science penalty | `govern.txt` ScienceCoef |
| Shield penalty for production change | Rush/switch penalty | `Const.txt` |
| Paradrop range | Air unit special range | `Units.txt` MaxMovePoints / SpecialAttack |
| Mass/Thrust paradigm | Spaceship (N/A for MoM) | not ported |

**Key porting risk:** Many COSMIC values have no direct CTP2 equivalent — they are baked into CTP2's `Const.txt` and `govern.txt`. Each must be mapped individually and verified against the AE baseline, since AE's `Const.txt` is our closest calibrated starting point.

---

## 2. @CIVILIZE — Advances (100 slots)

### CIV2 schema
```
name, AI_value, civilized_modifier, prereq1, prereq2, epoch, category
```
- `prereq` = 3-char abbreviation code from the `;comment` on each line
- `nil` = no prerequisite (root advance)
- `no` = blocked / impossible (disabled slot)
- **Epoch**: 0=Ancient, 1=Renaissance, 2=Industrial, 3=Modern
- **Category**: 0=Military, 1=Economic, 2=Social, 3=Academic, 4=Applied

### CTP2 files
| File | Role |
|---|---|
| `Advance.txt` | Advance database: cost, prereqs, flags, era |
| `uniticon.txt` | `ICON_ADVANCE_<NAME>` → TGA path mapping |
| `concept.txt` | Great Library text body (gameplay_str, historical_str, etc.) |
| `concepticon.txt` | GL icon references per advance |
| `branchID.txt` | Tech tree branch groupings |

### Interconnections
- **→ @IMPROVE**: every building/wonder has a `prereq` advance abbreviation
- **→ @UNITS**: every unit has a `preq` advance abbreviation (unlocks it)
- **→ @IMPROVE (@ENDWONDER)**: expiration advances end wonders when researched
- **→ @LEADERS**: AI value + civilized modifier feed leader personality-weighted tech valuation
- **Self-referential**: prereq1/prereq2 form the tech tree DAG

### MoMJR structure
Five magic paths, each with a root (value=100, epoch=1) and 5 chained advances:

| Path | Root | Chain |
|---|---|---|
| Life | Life Magic | Life Lore → Life Adept → Life Mage → Life Wizard → Life Master |
| Chaos | Chaos Magic | Chaos Lore → Chaos Adept → Chaos Mage → Chaos Wizard → Chaos Master |
| Sorcery | Sorcery | Sorcery Mage → Sorcery Wizard → Sorcery Master (3 only) |
| Nature | (via X1 prereq) | Nature Lore → Nature Adept → Nature Mage → Nature Wizard → Nature Master |
| Death | (via U2 prereq) | Death Lore → Death Adept → Death Mage → Death Wizard → Death Master |

`Grand Mastery` (prereq: Exp + Fli) = capstone military advance.  
`NF` = Grand Mastery abbreviation — used as prereq for the magic-path root advances (`Life Magic NF nil`, `Chaos Magic NF nil`, `Sorcery NF nil`). Magic paths only open after Grand Mastery.

**Disabled slots** (name=`blah` or `Extra Advance N` or `User Def Tech X`): 14 slots total — inherited from base Civ2 template, not used by MoM. These have `no,no` prereqs. Do NOT generate TGA or GL entries for these.

**Skip rules in generator:**
- name.lower() == 'blah'
- name starts with 'x' (case-insensitive)
- name contains 'Extra Advance'
- name contains 'User Def Tech'

---

## 3. @IMPROVE — Buildings and Wonders (68 entries)

### CIV2 schema
```
name, cost(shields), maintenance(gold/turn), prereq_advance
```
- `maintenance == 0` → Wonder (one-per-world)
- `maintenance > 0` → City improvement (repeatable)
- `x` prefix on name → disabled (not buildable, treated as placeholder)

### Split: improvements vs wonders
Looking at the `@IMPROVE` list:

**City improvements** (maintenance > 0, ~34 entries): Wizard's Fortress, Barracks, Granary, Temple, MarketPlace, Library, Courthouse, City Walls, Aqueduct, Bank, Cathedral, University, Colosseum, Mechanician's Guild, Primal Source, Merchant's Guild, Sewer System, Beacon of Wisdom, SAM Missile Battery, Coastal Fortress, Solar Harness, Harbor, Sea Mines, Fantastic Stable, Port, Gaia's Shrine, Pleasure Dome, Font of Bounty — plus `x`-prefixed disabled entries.

**Wonders** (maintenance == 0, ~30 entries): Great Library, Oracle, Wall of Bone, Guild of Legends, Rune of Rulership, Bardic College, The Parthenon, Mystic X's Tower, Gunthar's Voyage, Prospero's Conservatory, Elixir of Metamorphosis, Enchanted Grotto, Eldritch College, Gnome Treasury, Reywind's Discovery, Mesmer's Tower, Forge of Chaos, Entropy Engine, League of Wizards, Celestial Beacon, and `x`-prefixed disabled wonders.

### ⚠️ DISCOVERY: Improvements.bmp is a shared grid (improvements + wonders)

`Improvements.bmp` contains **both** city improvement icons **and** wonder icons in a single flat grid. The slot index in the BMP grid directly equals the `@IMPROVE` line index (0-based, row-major).

**For MoMJR (68 @IMPROVE entries, 8-col × 9-row = 72 cell grid):**
- Cells 0–39 → city improvements → extract as `ICON_IMPROVE_*.TGA` → `improveicon.txt`
- Cells 40–67 → wonders → extract as `ICON_WONDER_*.TGA` → `wondericon.txt`
- Cells 68–71 → unused padding (beyond end of `@IMPROVE`)

**Rules for any CIV2 mod:**
1. **Never use pixel content** to determine whether a cell is "used" — inherited base-game cells look non-empty even if the mod doesn't override them.
2. **Always count `@IMPROVE` entries** from `RULES.TXT` to find the total slot count.
3. **Find the wonder split** by counting from the end of `@IMPROVE`: the last N entries where `maintenance == 0` are wonders (matching `@ENDWONDER` slot order).
4. The BMP grid may have extra padding cells beyond the `@IMPROVE` count — these are unreferenced and should be skipped.
5. `improveicon.csv` (for CTP2 generator) should only include slots 0 to (split−1). `wondericon.csv` / `wonders.csv` use `cell_index = row_index + split_offset`.

### CTP2 files
| File | Role |
|---|---|
| `buildings.txt` / `Improve.txt` | Building database: cost, upkeep, prereq flags, effects |
| `Wonder.txt` | Wonder database: cost, effects, GL text keys |
| `uniticon.txt` | `ICON_IMPROVE_<NAME>` and `ICON_WONDER_<NAME>` → TGA paths |
| `wondericon.txt` | Wonder icon bindings |
| `improveicon.txt` | Building icon bindings |
| `concept.txt` | GL text: gameplay_str, historical_str |
| `wondermovie.txt` | Wonder completion movie (N/A if no custom movies) |

### Interconnections
- **← @CIVILIZE**: prereq advance abbreviation unlocks each building/wonder
- **→ @ENDWONDER**: each wonder slot (1–28) has a paired expiration advance in @ENDWONDER (all `nil` in MoMJR = never expire)
- **→ @COSMIC**: Aqueduct and Sewer System size-cap values reference COSMIC city size thresholds
- **→ @TERRAIN** (indirect): Harbor / Port enable sea trade that connects to trade-good terrain specials
- **→ @CARAVAN** (indirect): some wonders boost trade route value — trade goods are @CARAVAN

### MoMJR notes
- `Wizard's Fortress` replaces base Civ2 Palace — this is the core city building, cost=10, no prereq. Likely needs `PALACE` flag in CTP2 `buildings.txt`.
- `Primal Source` (prereq U1 = unknown abbreviation — check abbreviation table) is MoM's mana source building.
- All `x`-prefixed entries (xMass Transit, xManufacturing Plant, xSDI Defense, etc.) = base Civ2 buildings that MoMJR disabled. Do NOT port these — skip rules cover them.
- Wonders are in `dimension_inventory.md` lines 1565+ (30 wonders).
- Buildings are in `dimension_inventory.md` lines 1208+ (68 improvements).

---

## 4. @ENDWONDER — Wonder expiration advances (28 slots)

### CIV2 schema
One advance abbreviation per line, matching the 28 standard Civ2 wonders by slot index.  
`nil` = never expires.

### MoMJR: all 28 entries are `nil`
No wonder expires. Safe to set all CTP2 wonder `Obsolete` fields to `ADVANCE_NONE` or leave unset.

### CTP2 files
- `Wonder.txt` — `Obsolete ADVANCE_NAME` field per wonder

---

## 5. @UNITS — Unit types (62 active + ~9 placeholder B-slots)

### CIV2 schema
```
name, obsolete_advance, domain, move, range, att, def, hits, firepwr, cost, holds, role, prereq, flags(15-bit)
```

| Field | Values | CTP2 analog |
|---|---|---|
| obsolete_advance | advance abbrev / `nil` | `Units.txt` Obsolete |
| domain | 0=Ground, 1=Air, 2=Sea | `Units.txt` DomainType |
| move | movement points | `Units.txt` MaxMovePoints |
| range | fuel turns (air only) | `Units.txt` Fuel |
| att / def | combat factors | `Units.txt` Attack / Defense |
| hits | hit points ×10 | `Units.txt` HP |
| firepwr | damage per hit | `Units.txt` Firepower |
| cost | shield rows to build | `Units.txt` ProductionCost |
| holds | cargo capacity (sea) | `Units.txt` CargoVolume |
| role | AI behavior | `Units.txt` |
| prereq | advance to unlock | `Units.txt` EnableAdvance |
| flags | 15-bit special abilities | `Units.txt` CanXxx flags |

### Flag bits → CTP2 abilities
```
000000000000001 = Two space visibility      → rangeVis / ZOC
000000000000010 = Ignore ZOC                → IgnoresZOC
000000000000100 = Amphibious assault        → CanAssaultCity / amphibious
000000001000000 = Negates city walls        → IgnoresCityWalls (howitzer-type)
000000010000000 = Carries air units         → CargoAir
000000100000000 = Paradrop                  → Paradrop
000001000000000 = Missile (1-shot nuke type)→ SpecialAttack
000010000000000 = Stealth fighter           → Stealth
010000000000000 = AEGIS / AA defense        → AntiAir / CanBombard
100000000000000 = Spy                       → CanBeExpelled / diplomat flags
```

### CTP2 files
| File | Role |
|---|---|
| `Units.txt` | Unit database: all stats, flags, GL keys |
| `uniticon.txt` | `ICON_UNIT_<NAME>` → TGA path |
| `Units.bmp` (source) | Sprite sheet — 64×48 cells, sequential slot order |
| `spriteID.txt` | Sprite animation bindings |
| `newsprite.txt` | New-format sprite references |
| `concept.txt` | GL text per unit |

### Role → CTP2 AI behavior
| CIV2 role | CTP2 approximate |
|---|---|
| 0 = Attack | Attack / CanAttack |
| 1 = Defend | Defend / CityDefense |
| 2 = Naval Superiority | Sea combat |
| 3 = Air Superiority | Air combat |
| 4 = Sea Transport | CanTransport |
| 5 = Settle | CanSettle / Settler |
| 6 = Diplomacy | Diplomat / CanBeExpelled |
| 7 = Trade | CanEstablishTradeRoute (Caravan) |

### Interconnections
- **← @CIVILIZE**: prereq advance abbreviation
- **→ @TERRAIN**: domain determines which terrain types the unit can traverse
- **→ @ORDERS**: unit orders (Fortify, Build Road, etc.) only available to certain roles/domains
- **→ @LEADERS**: AI personality (attack/expand/civilize) determines which unit roles are prioritized
- **→ @GOVERNMENTS**: government type affects free unit support slots (COSMIC)
- **← @COSMIC**: paradrop range constant

### MoMJR notes
- All `nil` in `obsolete_advance` → no unit ever becomes obsolete. This is intentional for MoM's static fantasy setting.
- B3/B4/B5/B6/B7/B8/B9 = blank placeholder units (same stats: 5a/4d/4h/1f, cost 9, no prereq). Skip these.
- `Caravan` (role 7, prereq Tra) = trade unit. In CTP2: `CanEstablishTradeRoute`.
- `Minion` (role 6, prereq Wri) = diplomat. In CTP2: diplomat / spy class.
- `Infernal Device` = nuclear analog (att 99, air domain, fuel 1, 1-shot missile, prereq NF). Maps to CTP2 nuclear or special attack unit.
- `Archangel` has `100000100010001` flags = spy + carrier + air-capable + 2-space vis. Highest-tier Life path unit.
- `Air Elemental` has `010000000010011` = AEGIS-like air defense + ignore ZOC + 2-space vis.

---

## 6. @TERRAIN — Terrain types and specials (33 entries)

### CIV2 schema (base terrain, first 11 entries)
```
name, move_cost, defense_bonus, food, shields, trade,
road?, road_food_bonus, road_extra_trade, 
irrigation_result, irrigation_turns, irrigation_food_bonus,
mining_result, 
transform_result
```

### Specials (entries 12–33)
Terrain special resources overlaid on base terrain. Format same as base terrain.

### MoMJR-specific specials
| Special | Trade value col 6 | Meaning |
|---|---|---|
| Nature Node | 5 | Mana income — Nature magic |
| Chaos Node | 5 | Mana income — Chaos magic |
| Sorcery Node | 5 | Mana income — Sorcery magic |

**Note**: Life Node and Death Node not present in terrain — probably because Life and Death magic paths use units/buildings rather than map nodes as their income source (Ariel = Life leader, Rjak = Death leader).

### CTP2 files
| File | Role |
|---|---|
| `terrain.txt` | Terrain database: movement, defense, yields |
| `tileimp.txt` | Tile improvements: roads, irrigation, mines, fortresses |
| `tileimpicon.txt` | Terrain improvement icons |
| `terrainicon.txt` | Terrain type icons |
| `goods.txt` | Terrain-linked trade goods (Node specials → mana goods) |
| `goodsicon.txt` | Good icons |
| `Terrain1.bmp`, `Terrain2.bmp` | Source terrain graphics (CIV2) |

### Interconnections
- **← @ORDERS**: Build Road / Irrigation / Mine / Transform / Clean Pollution / Build Fortress / Build Airbase all operate on terrain
- **→ @UNITS**: domain determines which terrain is passable; terrain modifies defense bonus
- **→ @CARAVAN**: terrain specials produce commodities that fuel trade routes
- **→ @COSMIC**: transform time multiplier; irrigation/mining yields
- **→ @IMPROVE**: Harbor enables sea trade tiles; Port boosts coastal trade

### Porting note: Node terrain → CTP2 goods
CIV2 nodes produce raw trade points. CTP2 uses `goods.txt` with terrain-linked goods (e.g., `TERRAIN_X_GOOD_ONE`). The three MoM nodes should map to custom mana-type goods (Nature Mana, Chaos Mana, Sorcery Mana) with `Gold` yield reflecting the mana income. These goods need entries in `goods.txt`, `goodsicon.txt`, and `goodsID.txt`.

---

## 7. @GOVERNMENTS — Government types (7 entries)

### CIV2 schema
```
name, male_title, female_title
```
Standard Civ2 progression: Anarchy → Despotism → Monarchy → Communism → Fundamentalism → Republic → Democracy

### CTP2 files
| File | Role |
|---|---|
| `govern.txt` | Government database: all economic/military/happiness coefficients |
| `governicon.txt` | Government icons |
| `DiffDB.txt` | Difficulty modifiers interact with government |

### Government → CTP2 govern.txt fields (key ones)
| CIV2 concept | CTP2 govern.txt field |
|---|---|
| Free unit slots | FreeUnits |
| Corruption formula | CrimeCoef, CorruptionCoef |
| Science penalty (Fundamentalism) | ScienceCoef |
| Happiness/riot threshold | RationsExpectation, WagesExpectation |
| Rush-buy availability | GoldBuyFactor |

### Interconnections
- **← @COSMIC**: free unit support values are per-government in COSMIC
- **→ @LEADERS**: each leader has an optional per-government title override
- **→ @UNITS**: government type affects unit upkeep cost
- **→ @CIVILIZE**: Monarchy, Communism, Republic, Democracy are also advance names (unlocking the government)

### MoMJR note
MoMJR keeps all 7 standard governments. The 5 MoM-faction leaders (Ariel, Freya, Jafar, Rjak, Tauron) have no per-government title overrides — they use the default titles from @GOVERNMENTS.

---

## 8. @LEADERS — Civilization leaders (23 entries in MoMJR)

### CIV2 schema
```
male_leader, female_leader, female(0/1), color(1-7), style(0-3),
civ_name_plural, civ_adjective, attack(-1/0/1), expand(-1/0/1), civilize(-1/0/1),
[govt_id, male_title, female_title, ...]   ← optional, repeatable
```

- **Style**: 0=Bronze Age, 1=Classical, 2=Far East, 3=Medieval → city sprite family
- **Personality axes**: attack (militaristic↔rational), expand (expansionist↔perfectionist), civilize (civilized↔militaristic)

### MoM faction leaders (first 5)
| Leader | Faction | Color | Style | Personality |
|---|---|---|---|---|
| Ariel (f) | Tribes of Life | 1 | Classical | rational, perfectionist, civilized |
| Freya (f) | Tribes of Nature | 2 | Medieval | neutral, expansionist, neutral |
| Jafar (m) | Tribes of Sorcery | 3 | Medieval | rational, neutral, neutral |
| Rjak (m) | Tribes of Death | 7 | Bronze Age | aggressive, expansionist, militaristic |
| Tauron (m) | Tribes of Chaos | 6 | Far East | aggressive, neutral, militaristic |

### Standard Civ2 civs (entries 6–22)
Greeks, Indians, Russians, Zulus, French, Aztecs, Chinese, English, Mongols, Celts, Japanese, Vikings, Spanish, Persians, Carthaginians, Sioux + 2 partial entries (Arabs, Incas — missing some fields, porting risk).

### CTP2 files
| File | Role |
|---|---|
| `civilisation.txt` | Civilization/leader database |
| `citystyle.txt` | City style families (0–3 styles) |
| `agecitystyle.txt` | City style by age/era |
| `Colors00-05.txt` | Civ color palettes |
| `profile.txt` | AI personality profiles |
| `diplomacy.slc` | Diplomatic interaction scripts |

### Interconnections
- **→ @GOVERNMENTS**: leader titles per government
- **→ @CIVILIZE**: AI advance valuations driven by attack/expand/civilize personality
- **→ @UNITS**: aggressive leaders prefer attack-role units
- **→ @TERRAIN** (indirect): city style determines which city BMP family is rendered on terrain

### MoMJR porting note
The 5 MoM faction leaders are the priority. The 17 standard Civ2 civs can use AE's existing `civilisation.txt` entries as a baseline — only the 5 MoM factions need custom entries. Leaders `Ariel` and `Freya` are female-primary (field 3=1); CTP2's `civilisation.txt` needs `Female 1` flag and female leader name.

---

## 9. @CARAVAN — Trading commodities (16 entries)

### CIV2 entries (slot order)
Hides, Wool, Beads, Cloth, Salt, Coal, Copper, Dye, Wine, Silk, Silver, Spice, Gems, Gold, Oil, Uranium

### CTP2 files
| File | Role |
|---|---|
| `goods.txt` | Goods database: yield (Gold/Food/Production), terrain binding, probability |
| `goodsicon.txt` | Good icon TGA bindings |
| `goodsID.txt` | Integer ID ↔ good name registry |

### CTP2 goods schema (from `goods.txt` probe)
```
GOOD_NAME {
   SpriteID  <n>
   Sound     SOUND_ID_<GOOD>
   Gold      <n>
   Food      <n>
   Production <n>
   Probability <0-1>
   Icon      ICON_GOOD_<TERRAIN_FAMILY>_<SLOT>
}
```

### Interconnections
- **← @TERRAIN**: terrain specials produce specific goods (the slot index in @CARAVAN matches the terrain special trade column)
- **→ @IMPROVE**: some buildings boost trade route income (Harbor, Port, MarketPlace, Merchant's Guild)
- **→ @UNITS**: Caravan unit (role 7) establishes trade routes between cities

### MoMJR porting note
CIV2's @CARAVAN is a flat list of names only — CTP2 requires full economic data per good (yield, sound, sprite, terrain binding). The 16 CIV2 commodities need mapping to CTP2's terrain-family goods system. The three MoM magic node specials (Nature Node, Chaos Node, Sorcery Node) require *new* goods entries not present in AE baseline — these are the highest-value porting risk in the goods dimension.

---

## 10. @ORDERS — Unit orders (10 entries)

### CIV2 entries
Fortify, Sleep, Build Fortress, Build Road, Build Irrigation, Build Mine, Transform, Clean Pollution, Build Airbase, Go to

### CTP2 files
| File | Role |
|---|---|
| `Orders.txt` | Order database (CTP2 has many more orders than Civ2) |
| `order.txt` | Order ID registry |
| `tileimp.txt` | Tile improvement actions (Road, Irrigation, Mine, Fortress, Airbase) |
| `tileimpicon.txt` | Improvement icons |

### Interconnections
- **→ @TERRAIN**: each build order produces a terrain improvement that changes tile yields
- **→ @UNITS**: only certain unit types (role 5 = Settler, domain 0 = ground) can execute terrain-modifying orders
- **← @COSMIC**: transform time controlled by COSMIC "base time for engineers to transform terrain"
- **→ @ADVANCE** (indirect): some orders become available only after specific advances (Road → Bronze Working era, Airbase → Flight-era equivalent)

### MoMJR note
CTP2 has a much richer order system (many unit specials, ranged attacks, etc.). The 10 Civ2 orders are all subsets of standard CTP2 orders. No custom orders needed for MoM — use CTP2 defaults. Magic abilities (unit specials) go through `specattack.txt` and `SpecialAttack` unit flags, not @ORDERS.

---

## 11. @EVENTS → SLIC

CIV2's `@EVENTS` / `EVENTS.TXT` section does not exist in `RULES.TXT` — it lives in a separate `EVENTS.TXT` file per scenario. All scripted scenario logic (triggered events, unit spawns, city takeovers, diplomatic incidents, wonder effects, advance-gated events) maps to CTP2 **SLIC** scripting.

### CTP2 SLIC files in mom gamedata
| File | Role |
|---|---|
| `scenario.slc` | Main scenario event script |
| `script.slc` | General game script hooks |
| `diplomacy.slc` | Diplomatic event handlers |
| `feats.slc` | Feat (achievement) triggers |
| `test.slc` | Debug/test hooks |
| `tut2_*.slc` | Tutorial scripts (not needed for MoM) |

**Cross-mod SLIC comparison** (AE × Cradle × Ages of Man × LOTR) is fully documented in `dimension_inventory.md`. Use that as the schema authority before writing any MoM SLIC.

---

## 12. @DIFFICULTY / @ATTITUDES — Ancillary

### @DIFFICULTY (6 levels: Chieftain → Deity)
→ `DiffDB.txt`: per-difficulty AI bonuses, production multipliers, happiness offsets

### @ATTITUDES (9 levels: Worshipful → Enraged)
→ `diplomacy.slc` + `civilisation.txt` attitude thresholds
→ Diplomatic text strings in `concept.txt` or string tables

---

## Cross-Dimensional Interconnection Map

```
@CIVILIZE ──prereq──► @IMPROVE (unlocks buildings/wonders)
@CIVILIZE ──prereq──► @UNITS   (unlocks units)
@CIVILIZE ◄──expire── @ENDWONDER (wonder expiration)
@CIVILIZE ──prereq──► @GOVERNMENTS (Monarchy, Republic, etc.)

@IMPROVE ──Harbor/Port──► @TERRAIN (sea trade tiles)
@IMPROVE ──MarketPlace──► @CARAVAN (trade route value boost)

@UNITS ──domain──► @TERRAIN (passability, movement cost)
@UNITS ──role:Trade──► @CARAVAN (Caravan unit creates trade routes)
@UNITS ──role:Settle──► @ORDERS (build orders)

@TERRAIN ──specials──► @CARAVAN (nodes/resources produce goods)
@TERRAIN ──defense bonus──► @UNITS (combat modifier)

@LEADERS ──personality──► @CIVILIZE (AI tech priority)
@LEADERS ──personality──► @UNITS (AI unit preference)
@LEADERS ──govt titles──► @GOVERNMENTS

@GOVERNMENTS ──support slots──► @UNITS (free units COSMIC)
@GOVERNMENTS ──science coef──► @CIVILIZE (research rate)

@ORDERS ──build──► @TERRAIN (tile improvements)
@ORDERS ──domain restriction──► @UNITS (who can build what)

@COSMIC ──global constants──► ALL dimensions
@EVENTS/SLIC ──triggers──► ALL dimensions (scripted overrides)
```

---

## CTP2 Files Not Covered by RULES.TXT (CTP2-only dimensions)

These have no CIV2 analog and must be populated from AE baseline:

| File | Purpose |
|---|---|
| `age.txt` | Historical ages (Bronze → Information) |
| `agecitystyle.txt` | City style by age |
| `cityid.txt` / `citysize*.txt` | City size thresholds and building slot counts |
| `citystyle.txt` | City sprite families |
| `concept.txt` | Great Library text (all dimensions feed here) |
| `endgame.txt` / `EndGameObjects.txt` | Victory conditions |
| `feat.txt` / `feats.slc` | In-game achievements |
| `gw.txt` | Global warming model |
| `hscore.txt` | High score table |
| `map.txt` | Map generation parameters |
| `newsprite.txt` / `spriteID.txt` | Sprite animation registry |
| `ozone.txt` | Ozone depletion model |
| `playlist.txt` | Music playlist |
| `pollution.txt` | Pollution model |
| `Pop.txt` | Population growth model |
| `profile.txt` | AI personality profiles |
| `risks.txt` | Random event risks |
| `sounds.txt` | Sound event bindings |
| `specattack.txt` | Special attack definitions (magic spells map here) |
| `throne.txt` | Throne room / palace upgrades |
| `victorymovie.txt` | End-game movie bindings |
| `wondermovie.txt` | Wonder completion movies |

---

## Scenario Art

| File | Location | Purpose |
|---|---|---|
| `scenicon.tga` | `Scenarios/mom/scen0000/scenicon.tga` | 160×120 scenario chooser preview |
| `packicon.tga` | `Scenarios/mom/packicon.tga` | 160×120 pack-level icon |

Source: `TITLE.GIF` (640×480) downscaled via LANCZOS. Generated 2026-05-24.

---

## Porting Priority Order

1. **@CIVILIZE** → `Advance.txt` + `uniticon.txt` + `concept.txt` ← *advances images currently broken*
2. **@IMPROVE** (buildings only) → `buildings.txt` / `Improve.txt` + `uniticon.txt` ← *improvement images currently broken*
3. **@IMPROVE** (wonders) → `Wonder.txt` ← *already working (icons correct)*
4. **@UNITS** → `Units.txt` ← *already working (icons correct)*
5. **@LEADERS** → `civilisation.txt` ← *5 MoM factions are the priority*
6. **@TERRAIN** nodes → `goods.txt` ← *mana income system*
7. **@CARAVAN** → `goods.txt` full mapping
8. **@EVENTS** → `scenario.slc` ← *last, after all data dimensions are correct*
