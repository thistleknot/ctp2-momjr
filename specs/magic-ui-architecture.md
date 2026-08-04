---
description: 'Where each magic menu lives and why. One hub reached by the j hotkey, spokes reached from its arms, and the control-panel button as a shortcut INTO a spoke rather than a second system. Placement follows trigger semantics: a key that means "show me my state" opens the hub; a button that means "I want to act" jumps to the action. This is the v4 plan.'
---

***definitions***

- :Hub: is the segment the `j` hotkey opens — player state plus navigation, no
  irreversible action of its own.
- :Spoke: is a segment reached from a :Hub: arm, owning one kind of action.
- :Shortcut: is a control-panel trigger that opens a :Spoke: directly, skipping
  the :Hub:. It is an accelerator, never the only way in.
- :NavArm: is a button whose whole job is to open another segment.
- :ActArm: is a button that spends, casts or commits.
- :Affordance: is an arm shown only when its precondition holds — you do not see
  Wishes without a lamp.

***requirements***

**Placement SHALL follow trigger semantics.** `j` reads as "show me my magic", so
it opens the :Hub:. The control-panel Magic button reads as "I want to cast", so
it is a :Shortcut: into the Workings :Spoke:.

> The defect this repairs is TWO DISCONNECTED SYSTEMS. Today `j` gives status and
> Summon while the control-panel button gives a spellbook, and a player who finds
> one has no reason to suspect the other. Same tree, two doors, one of which each
> player never discovers.

**A :Shortcut: SHALL open a :Spoke: that is ALSO reachable from the :Hub:.** No
segment may be reachable only by a route the player has to be told about.

**There SHALL be no new hotkeys.**

> `j` is not a SLIC binding, it is a bespoke engine patch
> (`keypress.cpp:410`), hardcoded to one key and one segment name, and the stock
> keyboard machinery it works around is dead — `RunKeyboardTrigger` iterates
> `m_triggerKey[]` into `TRIGGER_LIST_KEY_PRESSED`, which has zero subscribers.
> So every additional hotkey costs an engine patch and a rebuild, while a
> control-panel trigger costs nothing. Grow the tree, not the keymap.

**A :NavArm: SHALL `Kill()` its own box before opening the next.**

> Boxes STACK; they do not replace. A stacked pair freezes the turn loop, and the
> dismiss path aims at the last-declared arm — which is how clearing a box once
> re-fired Summon instead of closing it. Chaining is base-verified
> (`tut2_msg.slc`: `TMTurn0` -> `TMTurn0B` -> `TMGoodPlaces`, and back), so the
> pattern is proven; the ordering is the part that bites.

**Every :Spoke: SHALL carry a way back to the :Hub:.** A tree the player can only
descend is a trap.

**An :ActArm: SHALL state its price in its label** and SHALL be hidden or refused
when unaffordable — never silently inert.

**A label SHALL NOT interpolate.** Costs that vary at runtime belong in the body.

> MEASURED: `"Summon Creature ({MomSummonCostDisp})"` printed the braces
> verbatim while the body beside it substituted correctly. Static costs
> (`Flame Strike (50)`) are fine in a label because they are literals in the
> cast; the rung-scaled summon price is not.

**An :Affordance: SHALL be driven by state the player can see.**

**A segment SHALL declare AT MOST FIVE arms, and `Close` SHALL be declared
FIRST.**

> MEASURED 2026-08-03, eight arms declared, five rendered:
> `[ARM 4] [ARM 3] [ARM 2] [ARM 1] [Summon Creature]`. Two facts, and the second
> is a trap. Render order is REVERSED against declaration order. Overflow is
> dropped from the TAIL of the declaration list, silently — so ARM 5, ARM 6 and
> **`Close` itself** all disappeared. A sixth arm deletes your close button and
> nothing says so.
>
> Hence the ordering rule: declaring `Close` first is what guarantees it
> survives, and it lands rightmost on screen because of the reversal. The tree
> below fits with one slot spare at every node.

***decisions***

Three questions were left open when this tree was first drafted. Settled:

- **Summon stays a single roll; it does NOT become a spoke with rung choice.**
  Letting a player pick the rung collapses the ladder into one decision — always
  take the dearest you can afford — and it deletes the gamble that makes a
  summon feel like magic rather than a purchase. The caster chooses WHETHER to
  call and pays a known price; the void chooses what answers.
- **An artifact is a UNIT, not a building or a player flag.** This is decided by
  the hero requirement, not by convenience: a hero must be able to BEAR an
  artifact, which means the artifact has to be portable, co-locatable and
  losable. A player flag cannot be taken from you, and a building cannot travel.
  A unit can be carried, captured, killed and banished — which is also exactly
  what the :Binding: loop needs.
- **Bearing is CO-LOCATION, not an equipment slot.** CTP2 has no inventory. A
  hero bears an artifact while they share a tile or army, so "equipping" is
  moving, and losing the hero in the field risks the artifact with them.

***the tree***

```
MAGIC  (j -- the Hub)
   status: mana / income - upkeep = net / sphere rung / preparation
   |
   +-- Summon a Creature ......... Spoke: the existing commit path
   +-- Cast a Working ............ Spoke: Workings   <-- control-panel Shortcut
   |      +-- Flame Strike (50)
   |      +-- Demon Strike (100)      [Chaos only]
   |      +-- Store Power             <-- MOM_MSG_BTN_STORE, authored, unbound
   |      +-- Back
   +-- Artifacts ................. Spoke: only while holding one
   |      +-- <lamp, gem, ...>
   |      +-- Wishes .............. Spoke: only while holding a lamp
   |      +-- Back
   +-- Close
```

Every leaf already exists in some form. `MOM_MSG_BTN_STORE` ("Store Power") was
authored and never bound; it belongs here, as the honest third option beside
spend-50 and spend-100, and it makes the body's promise — *"or store your power
for later"* — true. `MomMsgSlicAlive` is dead PoC scaffolding and is deleted.

***scenarios***

**Given** a player pressing `j`, **when** the :Hub: opens, **then** it SHALL show
state and navigation and SHALL spend nothing.

**Given** the control-panel Magic button, **when** it is fired, **then** the
Workings :Spoke: SHALL open directly, and that same :Spoke: SHALL also be
reachable from the :Hub:.

**Given** a :NavArm:, **when** it is clicked, **then** exactly one box SHALL be
on screen afterwards.

**Given** a player with no lamp, **when** the :Hub: opens, **then** no Wishes arm
SHALL appear.

**Given** a working the player cannot afford, **when** the Workings :Spoke:
opens, **then** that arm SHALL be absent or SHALL refuse with a stated reason.

***acceptance***

**Assertions** — these fail the build:

1. Every segment defined in `mom_*.slc` is reachable: shown by `Message()`,
   opened by a `trigger`, or named by the engine. The orphan check that found
   `MagicMenu`, `MomMsgSlicAlive` and `MOM_MSG_BTN_STORE` becomes a gate.
2. Every authored `MOM_MSG_BTN_*` key is bound to a `Button(ID_...)`.
3. No `Button` uses a stock `ID_BUTTON_*` string — that is what made a finished
   spellbook read as "Research" and "Goal".
4. Every :NavArm: body contains a `Kill()`.
5. No new engine hotkey: `keypress.cpp` names exactly one segment.

**Diagnostics**:

6. The reachable tree, printed from the segment graph, so a spoke that falls off
   is visible without a playthrough.

***rejected***

- **A second hotkey per menu.** Each one is an engine patch; the tree is free.
- **A menu reachable only by the control-panel button.** That is the current
  defect, not a design.
- **Opening a box without killing the caller.** Stacks, then freezes the turn.

***open***

- **What happens at exactly five arms plus a Back arm.** The tree fits today,
  but Artifacts is a list whose length is the player's, not the designer's. A
  list longer than four entries needs paging, and paging costs two arms.
- **The panel quotes the UNDISCOUNTED price before the sphere-root grant lands.**
  At rung 0 it reads "a summon costs 45 mana" — the lazy 100% default, before
  the civ percentage is assigned. Cosmetic, and only visible on turn 1.
