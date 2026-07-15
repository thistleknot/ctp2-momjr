# MoM SLIC Template Catalog

## Status

MoM does **not** currently have a real bespoke SLIC translation layer. The scenario ships mostly with inherited stock/tutorial SLIC, plus one live diplomacy surface that is reusable for mod-specific translation work.

## File-role inventory

| File | Role | Treat as translation schema? |
|---|---|---|
| `Scenarios\mom\scen0000\default\gamedata\diplomacy.slc` | Live diplomacy proposal/response hooks (`NewProposal`, `Counter`, `Threaten`, `Reject`, `DesireMotivation`) | **Yes** |
| `Scenarios\mom\scen0000\default\gamedata\feats.slc` | Message-box definitions only | No |
| `Scenarios\mom\scen0000\default\gamedata\scenario.slc` | Empty override stub | No |
| `Scenarios\mom\scen0000\default\gamedata\script.slc` | Stock engine messagebox/event library | No |
| `Scenarios\mom\scen0000\default\gamedata\tut2_*.slc`, `tutorial.slc`, `test.slc` | Tutorial/demo scaffolding | No |

## Reusable template buckets

### 1. Diplomacy proposal-response template

- **Source surface:** `diplomacy.slc`
- **Core hooks:** `HandleEvent(NewProposal)`, `HandleEvent(Counter)`, `HandleEvent(Threaten)`, `HandleEvent(Reject)`, `HandleEvent(DesireMotivation)`
- **Core primitives:** `ConsiderResponse`, `ConsiderNewProposal`, `GetLastNewProposalType`, `GetNewProposalResult`, `FindCityToExtortFrom`
- **Use for MoM trailing mechanics:** wizard diplomacy, tribute demands, spell-for-gold exchanges, treaty gating by alignment/sphere power.

### 2. Per-turn state template

- **Reference surface:** `tut2_main.slc` `HandleEvent(BeginTurn|EndTurn)` only as syntax/examples
- **MoM target use:** mana upkeep, global enchantment maintenance, node-control income, overland-turn timers, plane-state checks.
- **Implementation note:** do **not** extend `tut2_main.slc`; create a MoM-owned file such as `mom_turns.slc`.

### 3. City/building side-effect template

- **Reference hooks:** `CreateBuilding`, `SellBuilding`, `CityRiot`, `GrantAdvance`, `CreateCity`
- **MoM target use:** shrine/guild/wonder side-effects, city enchantment unlocks, unrest modifiers, race-building interactions.
- **Implementation note:** treat tutorial hooks as event examples only; real MoM logic belongs in a new `mom_city_effects.slc`.

### 4. Unit-order / spell-action template

- **Reference hooks:** `CreateUnit`, `ArmySelected`, `MoveUnits`, `EntrenchUnit`, `EstablishEmbassyUnit`, `InjoinUnit`, `InciteRevolutionUnit`
- **MoM target use:** hero actions, spellcasting orders, teleport/plane-shift actions, summoned-unit behaviors, special unit commands.
- **Implementation note:** route these into a dedicated MoM action file rather than reusing tutorial handlers.

### 5. Tile-improvement / terrain-reaction template

- **Reference hooks:** `CreateImprovement`, `ImprovementComplete`, `CreatePark`, `PillageOrder`
- **MoM target use:** node/lair/tower reactions, corrupted-land cleansing, roads/outposts with magical side-effects, terrain transformation aftermath.
- **Implementation note:** pairs naturally with `tileimp.csv` gaps that are awkward to encode in static data alone.

### 6. Message/UI notification template

- **Reference surfaces:** `feats.slc`, `script.slc`
- **MoM target use:** wizard warnings, enchantment expiration notices, conquest/ritual milestone popups.
- **Implementation note:** notification-only SLIC is useful, but it is **not** the schema layer for gameplay logic.

## Translation-layer recommendation

Route the mechanics that do not fit cleanly into the generator dimensions through **new MoM-owned SLIC files**, not through the inherited tutorial files:

| Trailing MoM mechanic | Best template bucket |
|---|---|
| Wizard-to-wizard demands, bargains, tribute | Diplomacy proposal-response |
| Global enchantment upkeep / timed world effects | Per-turn state |
| City enchantments, wonder side-effects, unrest hooks | City/building side-effect |
| Hero powers, special unit orders, spell actions | Unit-order / spell-action |
| Towers, nodes, lairs, magical terrain reactions | Tile-improvement / terrain-reaction |
| Alerts, feat callouts, spell expiry warnings | Message/UI notification |

## Recommended next step

The first real MoM schema file should be a **new** `mom_turns.slc` or `mom_city_effects.slc`, because those buckets cover the largest share of trailing Master of Magic mechanics without overloading the CSV generator dimensions.
