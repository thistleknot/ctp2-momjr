# ctp2-momjr — Master of Magic total conversion for Call to Power 2

**v7.0.1** — CTP2 port of the Civ2 **MoM Junior** scenario (Master of Magic),
built on the Apolyton Edition.

> **What 7.0.1 fixes — sprite wiring and spellbook usability.**
> 20 faction units now have their own art (extracted from HoMM2 + custom
> Treant/Drow). Icon TGAs no longer show magenta Civ2 backgrounds. Spellbook
> pages render button numbers 1-2-3 left-to-right (was reversed). Generator
> reads the CSV `sprite` column directly instead of re-deriving from the unit
> name.

> **What 7.0.0 adds — cross-paradigm features.** MtG-style spell hand (draw
> from deck, rarity-gated), D&D-style hero stats (STR/DEX/CON/INT/WIS/CHA on
> named heroes), HoMM-style morale (army composition bonus/penalty), LotR-style
> fellowship (heroes adjacent to each other gain stacking buffs), and enchantment
> stacking (multiple enchants on one unit, diminishing returns).

> **What 6.0.0 adds — new spell proxy patterns.** Subversion (flip enemy city
> building), City Curse (reduce production), Raise Dead (resurrect killed unit
> as undead). Three new effect_kind implementations that expand what the
> spellbook can express without engine patches.

> **What 5.0.0 adds — magic combat system + 80 units.** 135 spells with wiki
> descriptions and confirmation pages. Selectable summon menu (per-rung creature
> picker, player chooses). 15 new faction units (Priest, Crusader, Templar,
> Treant, Druid, Apprentice, Crystal Golem, Djinn, Vampire, Bone Golem, Goblin,
> Orc, Ogre, Troll, Drow). 3 neutral dwarves. War Mage + Arch Mage casters.
> Heroes CantBuild (summon-only). Proximity-gated casting. 5-sphere resistance
> matrix.

> **What 3.8 fixes — a dragon is finally tougher than a peasant.** Unit stats
> were rescaled from civ2 with flat multipliers, which let the top run away, and
> `MaxHP` was written as the literal 10 on every single unit — civ2's own
> durability axis (1h Spearmen to 6h Great Wyrm) was parsed and thrown away.
> Stats are now **rank-cast**: each unit keeps its position in the source
> ordering and is re-cast onto stock CTP2's range through an S-curve that
> saturates at the top. Great Wyrm 100/87/60, Spearmen 10/10/10 — and War Troll,
> a unit you *build*, comes out 54/43/35. See `CHANGELOG.md`.

> **What 3.7 fixes — summoning no longer skips the tech tree.** A Warbears cost
> 1970 science to *build* and 0 science to *summon*, because the summon roll
> floored the sphere rung at 1. Every tribe had rung-1 summoning from turn one, so
> the units you met at a border were creatures that tribe could never have built —
> three identical bears, forever. A tribe must now research its sphere's magic
> before it can summon anything at all. See `CHANGELOG.md`.

> **What 3.6 adds — summoning takes preparation.** A summon used to resolve next
> turn no matter what it was, so a Great Wyrm and a Warbears arrived on the same
> schedule. Committing one now debits the mana, rolls the creature, and starts a
> countdown equal to its sphere rung: a rung-1 Warbears still arrives next turn,
> a rung-5 Great Wyrm takes five. One at a time, and no cancel. **Upkeep bounds
> how many creatures you can keep; preparation bounds how fast you can get
> them.** See `CHANGELOG.md`.

> **What 3.5 does — mana became an economy instead of a deposit box.** Summoning
> cost 75 mana *once* and nothing afterwards, so mana had exactly one sink, the
> sink was repeatable, and nothing bounded it — a tribe with no other use for the
> pool piled up identical creatures, and at sphere rung 1 Nature's pool is one
> creature. Now a summoned creature costs mana **every turn it lives**, scaled by
> the rung it was rolled at; the sphere's own buildings generate mana so you can
> invest in income; and the `j` panel shows the whole ledger — income, upkeep,
> net. Over-summon and one creature evaporates, chosen by a draw **weighted by
> its own upkeep**, so the hungriest is the likeliest to go. The AI checks
> whether it can *feed* a creature, not just afford it — so its army goes back to
> being mostly city-built troops, with summons as the parlor trick they were
> meant to be. Saves load unchanged. See `CHANGELOG.md`.

> **What 3.4 does — the sentinel wonders are gone.** Five "wonders" whose names
> literally began with the civ2 disabled marker — `Xlighthouse`, `Xapollo
> Program`, `Xstatue Of Liberty`, `Xwomens Suffrage`, `Xcure For Cancer` — were
> being shown to players in the Great Library. They were never buildable and are
> now culled: **28 → 23 wonders**. The MAGIC STATUS panel also tells you your
> sphere rung, since that decides which creatures a summon can roll.

> **What 3.3 fixed — a tribe can finally build its own troops.** Every sphere
> unit had been locked behind the magic ladder, so a Nature city's build list was
> literally two items, `Spearmen` and `Peasants`, and stayed that way until 1865
> science. MoM splits racial troops (built, the mainstay) from fantastic
> creatures (summoned) — and MOMJR always encoded which is which. 23 units move
> back onto the mundane advance the source specified: Centaurs at 455 science
> instead of 1865, **Minotaur on turn one**. They stay faction-walled, so only
> Nature fields Elven Archers. See `CHANGELOG.md`.

> **What 3.2 added — the ladder starts mattering, and the AI starts casting.** The
> 75-mana summon used to be five constants: Nature always got Warbears, the
> cheapest of its 13 units, at every rung of a six-rung ladder. It now rolls,
> weighted, over everything you have unlocked. And the AI, which had been accruing
> mana every turn since 1.0 and could never spend a point of it — the only thing
> that authorises a summon sat in a button body, which only a human click reaches
> — now has a magic brain of its own, paying the same prices you do. Saves load
> unchanged. See `CHANGELOG.md`.

> **What 3.1.1 fixed — every wonder message printed its name twice.** The
> rival-wonder warning read `Bardic CollegeBardic College`. `#ARTICLE` turns out
> to be an ident-suffix lookup, not a computed article: the engine reads
> `<IDENT>_ARTICLE` from `gl_str.txt` and falls back to the *name* when it is
> missing, so the eleven messages written as `{name#ARTICLE}{name}` doubled it.
> MoM's string file overrides the base one and shipped none of those keys — two
> separate lanes, one deleting the inherited keys and one never writing our own.
> Saves are unaffected. See `CHANGELOG.md`.

> **What 3.1.0 fixed — the victory nobody could reach.** Every one of the AI's
> seven wonder build lists shipped empty, so no AI player could build any of the
> 23 MoM wonders — including `WONDER_RUNE_OF_RULERSHIP`, which
> `EndGameObjects.txt` makes the scenario's win condition. An AI-only game
> therefore had no reachable ending except the year 2300 (turn 1000). The lists
> are now derived from the scenario's own wonder database. Saves are unaffected.
> The same release fixes a diplomatic-proposal modal that froze the headless
> turn loop, and adds the first balance audit. See `CHANGELOG.md`.

> **What 3.0.1 fixes — the diplomacy screen every tribe could not open.** All
> five tribes pointed at a parchment image that does not exist, and because the
> engine builds that filename at runtime, nothing in the database dangled and no
> gate could see it. The symptom was a frozen frame with an empty console,
> because the missing-art modal *is* the freeze. Saves are unaffected. The same
> release took the harness from a 40-turn ceiling to a full **200-turn**
> playthrough. See `CHANGELOG.md`.

> **What's new in 3.0 — the Renaissance cap actually applies.** 2.0 announced
> that mundane tech ends at the Renaissance; the code that enforced it asked the
> wrong question ("did MoM author this advance?" — MoM authored nearly all of
> them) and so enforced nothing. Ages 5–7 are now magic-only: every one of the 19
> advances above AGE_FOUR is a sphere-ladder rung or transitively requires one,
> confirmed in-game. See `CHANGELOG.md`.

> **What 2.0 brought — the tribes became real.** Faction identity used to live
> only in SLIC's player index; now it is in the data. Every unit, building and
> wonder carries a `sphere`, four engine `mod_Can*` hooks fence what each tribe
> may research and build, and mundane tech ends at the Renaissance so Ages 5–10
> belong entirely to the magic ladder. That cap deleted 113 advances, which in
> turn exposed and closed the whole DB-Error crash class. Full detail in
> [`CHANGELOG.md`](CHANGELOG.md).

![MoM running in CTP2: the MAGIC STATUS panel with a live mana pool and a
Summon Creature arm, beside a Life Tribe city](docs/img/mom_magic_status_ingame.png)

![The mod in play at 3775BC: two tribe cities, Eudoria and Silvermere, on an
isometric map with a mana node visible, and Knights queued in the unit
panel](docs/img/mom_ingame_3775bc.png)

*3775BC. Tribe cities Eudoria and Silvermere with Spearmen garrisons; a mana
node east of the ridge; Knights — a neutral unit every tribe may field — in the
build panel. Captured headlessly through `tools/uiwalk/uiwalk.py`.*

## Playing it — where the magic lives

![The MAGIC STATUS hub open at 2975BC over the Chaos cities Darkstone and
Hellrock: mana 200/200, income 37 minus upkeep 2 for 35 per turn, sphere rung 1
of 5, a summon priced at 69, and three arms — Cast a Working, Summon Creature,
Close](docs/img/mom_magic_menu_hub.png)

*2975BC, playing Chaos. The panel is the whole magic economy in five lines.*

**Launch `ctp2_program/ctp/ctp2.exe`.** Not `ctp2-dbg.exe` — the `j` key is a
bespoke engine patch and the debug build does not carry it, so on that binary
the menus appear not to exist.

**New Game → Scenario → Master of Magic**, then choose your tribe from the
**EMPIRE** selector. That selector decides your sphere and therefore your entire
spellbook; the default is Tribes of Nature.

**Press `j` in game** to open the hub:

```
MAGIC STATUS  (the Hub)          mana / income - upkeep = net / rung / price
├─ Artifacts ───────→ what you bear, its Boon and its Bane
│     ├─ Wishes ────→ the genie's three, enumerated
│     │     ├─ Riches            500 gold
│     │     ├─ Power             fill your pool
│     │     ├─ Servant           an efreet answers
│     │     ├─ Back
│     │     └─ Close
│     ├─ Back
│     └─ Close
├─ Cast a Working ──→ Workings, the spellbook for your sphere
│     ├─ Flame Strike (50)
│     ├─ Demon Strike (100)       Chaos only
│     ├─ Store Power              bank toward the next rung
│     ├─ Back                     returns to the Hub
│     └─ Close
├─ Summon Creature                places an order; resolves next turn
└─ Close
```

**Everything in that tree is built and has been walked in game** — arms pressed
headlessly, panels captured and read. What is NOT built, and is specified in
[`specs/earned-powers-and-counterplay.md`](specs/earned-powers-and-counterplay.md),
is the rest of the artifact system: sites and huts to find vessels in, major
wishes from a captured avatar, heroes, lichdom, and the persistent-hazard
counterplay. If it is not in the tree above, it is not in the game.

**The Lamp** is the one vessel that exists. It is *anchored* (`MaxMovePoints 0`,
`Attack 0`, `Defense 0`, `Civilian`) and can never be built, so it is found
rather than made — today it comes from destroying an efreet, which frees the
vessel its servant was bound into. Holding it raises your pool from 200 to 250
and drains 4 mana every turn, and you cannot put it down. That pairing is the
design: **the same resource is raised and lowered**, so an artifact is a
decision rather than a pickup.

A vessel **cannot change hands.** CTP2 has no unit-ownership transfer — the
engine captures cities, never units — so an enemy who reaches your lamp destroys
it and takes your capacity boon and unspent wishes with it. The contest over an
artifact is denial, not seizure.

A hard engine limit shapes that tree: **a segment renders at most five arms and
silently drops the overflow from the tail** — measured, eight declared and five
drawn, with `Close` among the casualties. So `Close` is always declared first,
arms paint right-to-left from declaration order (which is why `Close` sits
rightmost on screen), and affordance-gating is a necessity rather than polish —
the Artifacts and Wishes arms can only appear when they are relevant because
there is no room for them otherwise.

Three things the panel is telling you, using the capture above as the worked
example. **The summon price is yours alone** — 69 there, from Chaos's 92% civ
rate against `45 + 30 × rung`; a Sorcery or Death player at the same rung pays
54. **`Preparing: 0 turns left` means nothing is on the way**; a summon is an
order, not an instant, so end a turn before expecting the creature. And **income
minus upkeep is what actually accrues** — 37 − 2 = 35 above, and a large standing
summoned army drives that toward zero and stalls the pool where it sits.

The arms paint right-to-left from the order they are declared in, which is why
`Close` sits last on screen despite being declared first. That ordering is
load-bearing rather than cosmetic: the box renders at most five arms and drops
overflow silently from the tail, so `Close` is declared first to guarantee it
survives.

## What this mod adds

- **Interactive SLIC, per civ.** The magic system is a real modal the player
  acts on, not a notification stream: `MAGIC STATUS` shows the mana pool and
  income, and its `Summon Creature` arm places an order that survives the
  turn boundary and resolves next `BeginTurn`. The creature is chosen from the
  **caster's own sphere** — a Life tribe summons a Guardian Spirit and *cannot*
  raise Death's zombies. Each of the five spheres (Life, Nature, Sorcery, Death,
  Chaos) has its own predicates, buildings, income, blessings, spellbook and
  result popups.
- **Mana is a real resource, and the pool is the one fixed anchor.** Every tribe
  gets the same **200**-point pool, deliberately: it is the constant the rest of
  the numbers are expressed against, so a player always knows the ceiling and
  the edge lives in price, income and rung instead. Income comes from cities and
  owned mana nodes; summons and spells compete for the same pool rather than
  being free. Summon price varies **by sphere** — Chaos pays 92% of the base
  ladder, Sorcery and Death 54%.
- **Centred unit art.** MoM's units are rebuilt into CTP2 sprites whose draw
  anchor matches the vanilla convention, so they stand on their tile instead of
  drifting off it. Extent and anchor are derived together from the measured
  envelope of all 95 shipped `GU0*.SPR` — see `lessons_learned.md`, which is the
  project wiki.
- **A control plane you can edit in Excel.** `mom_dimension_inventory.xlsx` is
  the artifact the mod is based on. **Each tab is one dimension** — units,
  advances, improvements, terrain, players, wonders, tileimp, sprite pick rules,
  cost bands, atlas geometry, and **slic** — so changing the mod means editing a
  spreadsheet, not hand-patching game text files.

## The control plane

`mom_dimension_inventory.xlsx` — 35 tabs, one per dimension. A **cell is a file,
and/or a set of constants, classes and/or functions** — the actual content, not
a description of it.

### Why SLIC flows the other way

Every other dimension is **forward-generated**: a Civ2 mod is encoded into the
workbook, and the generator turns that into scenario files.

SLIC is the exception, and has to be. Civ2 has no equivalent to it — there is
nothing upstream to encode *from*. SLIC is authored directly against CTP2, which
is precisely why it is **backcast** into the workbook by
`tools/backcast_slic.py`:

```
Civ2 RULES.TXT ---encode--> [ mom_dimension_inventory.xlsx ] ---generate--> scenario
                                          ^
scenario *.slc  ---backcast---------------+
```

The workbook stays the single place to see what the mod *is*; the `.slc` files
stay the source of truth for what it *does*. The backcast never writes SLIC — a
spreadsheet that could regenerate SLIC would be strictly worse than text files
that are diffable, commentable and compilable.

### The `slic` tab

One row per module, and the content columns carry real source:

| column | holds |
|---|---|
| `constants` | module-scope declarations (the per-player arrays) |
| `functions` | every `int_f` / `void_f`, whole, with its leading comment |
| `handlers` | every `HandleEvent` block, whole |
| `triggers` | every UI trigger block, whole |
| `segments` | every `alertbox` / `messagebox`, whole |
| `source` | the entire file, verbatim |

plus `phase` and `include_order` (read from `scenario.slc`'s `#include` list,
not hardcoded). `slic_index` is the flat companion — one row per declaration
with its signature — for scanning and filtering rather than reading.

Structure is re-derived on every run. The `purpose` and `status` prose is merged
forward by name and kept in `tools/momjr_csv/slic_purpose.json`, so a
declaration added in code shows up with an empty `purpose` — a visible TODO —
and human- or LLM-written intent text is never clobbered. That is the second
process: propose a feature in the sheet, implement it in SLIC, and let the
backcast reconcile the two.

```
python tools/export_mod_workbook.py   # rebuilds the forward-generated tabs
python tools/backcast_slic.py         # then adds slic + slic_index
python tools/backcast_slic.py --check # exits 1 if the tab drifted from the code
```

Run the backcast **after** the export — the export rebuilds the workbook from
the forward dimensions and does not know about SLIC.

## Player's Guide (MkDocs)

The mod ships a browsable player's guide built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).
It serves as the human-review control plane — every dimension, unit, spell, and
advance is rendered with its in-game art inline.

```
cd Scenarios\mom
mkdocs serve
```

Opens at `http://127.0.0.1:8000`. Structure:

- **Getting Started** — installation, first game walkthrough, sphere overview
- **Magic System** — spellbook, spell hand, proximity targeting, resistance, bindings, stacking, cataclysm
- **Dimensions** — units (with per-row icon), advances, buildings, spells, terrain (all generated from CSVs)
- **Factions** — full roster per sphere with stats and matchups
- **Systems** — hero stats, fellowship, summoning, mana economy, artifacts

Reference tables are generated by `docs/gen_reference.py` from the same CSVs
that feed `mom_dimension_inventory.xlsx`. Unit icons are cropped from the observer
contact sheet by `docs/extract_unit_icons.py`. To regenerate after CSV changes:

```
python docs/extract_unit_icons.py   # re-crop unit icons from observer sheet
python docs/gen_reference.py        # regenerate all reference tables
mkdocs build --strict               # verify
```

## The two artifacts

The mod and the code, kept separate on purpose:

## 1. `mom.zip` — the mod

What a player installs. Unzip into `Scenarios\` and the scenario is there.

It carries **only** what the engine loads — `packicon.tga`, `packlist.txt` and
`scen0000/`, the same shape as the scenarios that ship with the game — under a
top-level `mom/` prefix. No tooling, no control plane, no docs: **the repo holds
the code, the zip holds the mod.** Rebuilt from the tree, never hand-maintained:

```
python tools\ctp2_generator.py    # control plane -> scenario
python tools\mom_audit.py         # validate
python tools\build_mod_zip.py     # package
```

## 2. The repo tree — the control-plane version

The same scenario, restructured so everything regenerates from data:

- `scen0000/` — the generated CTP2 scenario (gamedata, graphics, aidata)
- `tools/` — the universal mod encoder pipeline:
  - `encode_civ2_mod.py` — Civ2 `RULES.TXT` → per-dimension CSVs (+ xlsx workbook)
  - `tools/momjr_csv/` — **the control plane**: dimension CSVs + per-mod policy
    (`mod_policy.json`, masks, GL rewrites, sprite pick rules, unit block overrides,
    advance code map, cost bands, atlas geometry)
  - `ctp2_generator.py` — control plane → scenario files (engine only; all MoM
    decisions live in the policy files)
  - `export_mod_workbook.py` / `sync_excel_to_csv.py` — xlsx ⇄ csv round-trip
  - `mom_audit.py` — post-generation validation
- `specs/` — design specs, including the engine/policy inventory that drove the split
- `lessons_learned.md` — the project wiki (newest entries first)

### Regeneration

```
set CTP2_GENERATOR_SCENARIO_DIR=<scenario dir>   # optional; defaults to Scenarios\mom\scen0000
python tools\ctp2_generator.py
python tools\mom_audit.py
```

The generator is deterministic: two runs from the same control plane produce
byte-identical output (this is the pipeline's regression gate).

### Converting a different Civ2 mod

```
python tools\encode_civ2_mod.py --mod-dir <civ2 mod dir> --out <new csv dir>
# hand-curate the csv dir (wonders block_text, players ctp2 columns, policy, atlas)
set CTP2_GENERATOR_CSV_DIR=<new csv dir>
python tools\ctp2_generator.py
```

Source game content © Activision / Firaxis / the original MoMJR scenario
authors; this repo contains only mod data and tooling.
