# Spell Hand (Draw Economy)

## The Concept

Inspired by Magic: The Gathering's hand mechanic: you don't have access to your
full spellbook every turn. Instead, you **draw** spells into a hand and can only
cast from that hand.

This creates meaningful per-turn decisions. Do you cast your mediocre hand now,
or hold and hope for a better draw next turn?

## How Drawing Works

Each turn at BeginTurn:
- The system draws N spells randomly from your available spell pool
- Drawn spells go into your hand (up to hand size cap)
- Uncast spells from previous turns persist in your hand

### Draw Rate

Your draw rate (N spells per turn) is determined by:
- **Sphere rung**: higher rung = more draws per turn
- **Arcana stat**: hero stat that adds +1 draw per N arcana points

Base draw: 1 spell per turn at rung 0, increasing with research progression.

### Hand Size Cap

Maximum spells you can hold at once:

```
Hand Size = MomMagicMax / 50
```

With a Chaos wizard (max 300): hand size = 6.
With a Life wizard (max 200): hand size = 4.

Chaos has the largest hand — more options but less predictable. Life has the
smallest but most consistent.

## Strategic Implications

- **Holding spells**: Uncast spells don't vanish. Saving a powerful spell for
  the right moment is valid strategy.
- **Hand overflow**: If your hand is full when a draw happens, the new spell is
  lost. Cast or lose.
- **Deck composition**: Your "deck" is all researched spells. Researching many
  common spells dilutes your pool — you're less likely to draw a specific rare.
- **Rung investment**: Higher sphere rungs don't just unlock spells, they increase
  your draw rate. Pure research pays off in hand quality.

## The MtG Parallel

| MtG Concept | MoM Implementation |
|------------|-------------------|
| Library (deck) | All researched spells |
| Hand | Current castable set |
| Draw step | BeginTurn draw |
| Hand size limit | MomMagicMax / 50 |
| Mana to cast | MomMagicCur >= cost |
| Mulligans | None (hold between turns) |

## Interaction with Other Systems

- **Proximity casting**: Having a spell in hand isn't enough. You still need a
  mage in range to deliver offensive magic.
- **Unit bindings**: Signature spells still require their bound unit. Drawing
  Death Wish without a Death Knight in range gives only the fallback effect.
- **AI casting**: The AI draws from the same pool but uses a simpler heuristic
  (cast the first affordable spell against the nearest target).
