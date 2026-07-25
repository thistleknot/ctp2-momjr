# WIP: SLIC interactive magic-layer (stashed 2026-07-22)

## Why this is here
The last **known-working** MoM scenario is `Scenarios/mom/mom.zip` (2026-07-15). The
interactive spell/petition SLIC layer built after that zip introduced a **hard crash**
on turn 1 (no SLIC dialog, no crash dump). Per user direction, the working SLIC baseline
was restored to the live scenario and this WIP was moved aside so it isn't lost.

## What was stashed (current/broken versions)
- `mom_spells.slc` — NEW (not in working zip): spellbook popup + Flame/Demon Strike +
  `MomSpellMenuTick` BeginTurn probe ("show book every turn") + `MomOpenSpellbook`
  UI-component trigger on the ShortcutPad MagicButton.
- `mom_ritual.slc` — NEW: `MomPetitionTick` BeginTurn petition handler + petition
  messageboxes (Audience Hall).
- `mom_func.slc`, `mom_magic.slc` — modified with a `player[1] = p` assign-then-read
  rewrite of `player[p]` (this was based on an engine-source reading that `player[N]`
  indexes the event arg array). **Superseded/suspect** — see below.
- `mom_msg.slc` — added `MomMsg*` messagebox segments (SlicAlive, blessings, etc.).
- `scenario.slc` — added `#include mom_spells.slc` + `#include mom_ritual.slc`.

## Crash hypothesis (for re-integration)
The turn-1 hard crash fired in the log **immediately after** `MomMagicPower` displayed.
In BeginTurn handler order the next handler is `mom_spells`' **`MomSpellMenuTick`** — the
"TEMP PROBE: show book every turn" (`mom_spells.slc:157`) calling `MomSpellShowBook` →
`Message(g.player,'MomMsgSpellbook')`. Prime suspect for the crash. The working zip has
none of this.

CONTRADICTION to resolve before re-integrating: the working zip's `mom_turns`/`mom_func`/
`mom_magic` all use **bare `player[p]`** and (per user) worked fine — so the
"`player[p]` is out of bounds" theory that drove the `player[1] = p` rewrite is NOT the
real regression, and the rewrite may itself have introduced instability (mutating the
shared player builtin array mid-handler). Re-integration should start from the working
`player[p]` baseline and add ONE module at a time, testing each.

## Re-integration order (one module, test, next)
1. Restore `mom_msg.slc` messagebox segments only → test load + a few turns.
2. Add `mom_spells.slc` **without** the every-turn probe (delete the `MomSpellMenuTick`
   TEMP PROBE block); gate spellbook to the pool-threshold path only → test.
3. Add the `MomOpenSpellbook` UI trigger + ShortcutPad MagicButton → test the click.
4. Add `mom_ritual.slc` last → test.

Baseline to diff against: `Scenarios/mom/mom.zip` (working 2026-07-15).
