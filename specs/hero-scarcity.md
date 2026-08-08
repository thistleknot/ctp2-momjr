# Hero Scarcity Spec

Status: ACTIVE
Created: 2026-08-07
Disposition: Implementing

## Summary

Heroes are queen-pieces: powerful, unique-feeling, summon-only. They cannot be
built from cities. The only path to a hero is through the spellbook (mana cost +
preparation time). Lose one, you can resummon — but it costs.

## Core Principles

1. **CantBuild.** All named heroes get the `CantBuild` flag in Units.txt. They
   never appear in any city's build queue.
2. **Summon-only.** Heroes come through existing spellbook summon spells. The
   mechanism already exists — this just removes the city-production bypass.
3. **Ladder-gated.** Heroes are redistributed across the sphere advance ladder
   instead of all unlocking at Mysticism. Early hero at rung 1-2, late hero at
   rung 4-5. Higher rung = more powerful hero.
4. **Not truly unique.** You CAN have two Ariels if you summon her twice. The
   cost (mana + prep time) is the scarcity, not an engine-enforced cap. Chess
   analogy: you can promote a pawn to a second queen, but it's expensive.

## Hero Distribution (ladder prereqs)

| Sphere | Early Hero (rung 1-2) | Late Hero (rung 4-5) |
|--------|----------------------|---------------------|
| Life | Serena (Life Lore / Inv) | Ariel (Life Wizard / Too) |
| Nature | Freya (Nature Lore / Plu) | Alorra (Nature Wizard / Rec) |
| Sorcery | Jafar (Sorcerous Lore / The) | — (only 1 hero) |
| Death | Rjak (Death Lore / Rfg) | Malleus (Death Master / SE) |
| Chaos | Tauron (Chaos Lore / MP) | Warrax (Chaos Wizard / Min) |

Advance codes from advances.csv:
- Life ladder: Gen → Inv → Lab → Las → Too → Mag
- Nature ladder: X1 → Plu → PT → Rad → Rec → Ref
- Sorcery ladder: Hor → The → X2 → NP → Phy → Pla
- Death ladder: U2 → Rfg → Rob → SFl → Sth → SE
- Chaos ladder: Gun → MP → Med → Met → Min → Mob

## Implementation

1. Generator adds `CantBuild` flag to hero unit blocks in Units.txt
2. Generator updates hero prereqs from Mys to their sphere ladder position
3. Death Knight is NOT a hero — it stays buildable (it's a troop type)
4. Audit and flight test

## What This Changes

- Heroes disappear from all city build queues immediately
- Heroes still appear in the Great Library (no GLHidden)
- The spellbook summon spells for heroes still work (CreateUnit via SLIC)
- AI can still get heroes via MomSpellAICast (the AI casting path)
- UnitBuildLists.txt references to heroes become dead (AI won't queue them
  from cities, but can still summon via SLIC)

## Acceptance Criteria

1. All 9 named heroes have `CantBuild` in Units.txt
2. Prereqs redistributed to sphere ladder positions
3. Heroes NOT in any UnitBuildLists.txt entry
4. Heroes still summonable via spellbook (existing summon spells)
5. Audit PASS, turnloop clean
