# Advance Tree

Complete advance/research tree generated from `advances.csv`.

## All Advances

| Advance | Code | Prereq 1 | Prereq 2 | Category | Epoch |
|---------|------|----------|----------|----------|-------|
| User Def Tech A | Aut | — | — | Military | 0 |
| Chivalry | Chi | Feu | — | Military | 0 |
| Extra Advance 4 | Cmn | — | — | Military | 0 |
| Tactics | Exp | Tac | Uni | Military | 0 |
| Feudalism | Feu | War | — | Military | 0 |
| Holy Warriors | Ldr | Chi | The | Military | 0 |
| Grand Mastery | NF | Exp | Fli | Military | 0 |
| Leadership | Tac | Chi | Uni | Military | 0 |
| Warrior Code | War | — | — | Military | 0 |
| Ceremonial Burial | Cer | — | — | Religious | 0 |
| Code of Laws | CoL | Alp | — | Religious | 0 |
| Monarchy | Mon | Cer | CoL | Religious | 0 |
| Theology | MT | Phi | Feu | Religious | 0 |
| Mysticism | Mys | Cer | — | Religious | 0 |
| Philosophy | Phi | Mys | Lit | Religious | 0 |
| The Republic | Rep | Lit | — | Religious | 0 |
| Banking | Ban | Rep | Tra | Economic | 0 |
| Currency | Cur | Bro | — | Economic | 0 |
| Map Making | Map | Alp | — | Economic | 0 |
| Navigation | Nav | Sea | Ast | Economic | 0 |
| Pottery | Pot | — | — | Economic | 0 |
| Sanitation | San | CA | — | Economic | 0 |
| Seafaring | Sea | Map | Pot | Economic | 0 |
| Trade | Tra | Cur | CoL | Economic | 0 |
| Ecognomics | Eco | Uni | Ban | Economic | 0 |
| Bridge Building | Bri | Iro | Cst | Engineering | 0 |
| Bronze Working | Bro | — | — | Engineering | 0 |
| Construction | Cst | Mas | Cur | Engineering | 0 |
| Iron Working | Iro | Bro | War | Engineering | 0 |
| Masonry | Mas | — | — | Engineering | 0 |
| Nature Lore | Plu | X1 | Ato | Economic | 1 |
| Nature Adept | PT | Plu | — | Economic | 1 |
| Nature Mage | Rad | PT | — | Economic | 1 |
| Nature Wizard | Rec | Rad | — | Economic | 1 |
| Nature Master | Ref | Rec | — | Economic | 1 |
| Nature Magic | X1 | NF | — | Economic | 1 |
| Alchemy | AFl | Cmp | — | Academic | 0 |
| Alphabet | Alp | — | — | Academic | 0 |
| Animism | Amp | Uni | — | Academic | 0 |
| Astrology | Ast | Mys | Mat | Academic | 0 |
| Eldritch Lore | Ato | Ast | — | Academic | 0 |
| Greater Fauna Lore | Che | X4 | — | Academic | 0 |
| Healing | CA | Ast | Phi | Academic | 0 |
| Lesser Enchanments | Cmb | Mys | — | Academic | 0 |
| Metamorphosis | Cmp | E1 | Cst | Academic | 0 |
| Pantheism | Cor | Cer | Env | Academic | 0 |
| Rune Lore | E1 | X6 | Lit | Academic | 0 |
| Sea Mastery | Eng | Iro | U3 | Academic | 0 |
| Shamanism | Env | — | — | Academic | 0 |
| Thaumaturgy | Esp | The | X6 | Academic | 0 |
| Wizardry | Fli | AFl | — | Academic | 0 |
| Glyphs | FP | — | — | Academic | 0 |
| Literacy | Lit | Wri | CoL | Academic | 0 |
| Mathematics | Mat | Alp | Mas | Academic | 0 |
| Greater Enchantments | RR | Cmb | — | Academic | 0 |
| University | Uni | Mat | Phi | Academic | 0 |
| Writing | Wri | Alp | — | Academic | 0 |
| Forces of Nature | U1 | Amp | — | Academic | 0 |
| Sea Lore | U3 | Nav | — | Academic | 0 |
| Artificing | X3 | Esp | — | Academic | 0 |
| Lesser Fauna Lore | X4 | Amp | — | Academic | 0 |
| Pyrotechnics | X5 | Ato | — | Academic | 0 |
| Occult Studies | X6 | Env | — | Academic | 0 |
| Life Magic | Gen | NF | — | Religious | 1 |
| Life Lore | Inv | Gen | Ato | Religious | 1 |
| Life Adept | Lab | Inv | — | Religious | 1 |
| Life Mage | Las | Lab | — | Religious | 1 |
| Life Wizard | Too | Las | — | Religious | 1 |
| Life Master | Mag | Too | — | Religious | 1 |
| Death Lore | Rfg | U2 | Ato | Academic | 1 |
| Death Adept | Rob | Rfg | — | Academic | 1 |
| Death Mage | SFl | Rob | — | Academic | 1 |
| Death Wizard | Sth | SFl | — | Academic | 1 |
| Death Master | SE | Sth | — | Academic | 1 |
| Death Magic | U2 | NF | — | Academic | 1 |
| Sorcery | Hor | NF | — | Engineering | 1 |
| Sorcery Mage | NP | X2 | — | Engineering | 1 |
| Sorcery Wizard | Phy | NP | — | Engineering | 1 |
| Sorcery Master | Pla | Phy | — | Engineering | 1 |
| Sorcerous Lore | The | Hor | Ato | Engineering | 1 |
| Sorcery Adept | X2 | The | — | Engineering | 1 |
| Chaos Magic | Gun | NF | — | Military | 1 |
| Chaos Lore | MP | Gun | Ato | Military | 1 |
| Chaos Adept | Med | MP | — | Military | 1 |
| Chaos Mage | Met | Med | — | Military | 1 |
| Chaos Wizard | Min | Met | — | Military | 1 |
| Chaos Master | Mob | Min | — | Military | 1 |
| Future Technology | ... | Sth | MP | Academic | 3 |

## Sphere Magic Ladders

Each sphere has a 6-rung research chain:

### Life

```
Life Magic (Gen) → Life Lore (Inv) → Life Adept (Lab) → Life Mage (Las) → Life Wizard (Too) → Life Master (Mag)
```

### Nature

```
Nature Magic (X1) → Nature Lore (Plu) → Nature Adept (PT) → Nature Mage (Rad) → Nature Wizard (Rec) → Nature Master (Ref)
```

### Sorcery

```
Sorcery (Hor) → Sorcerous Lore (The) → Sorcery Adept (X2) → Sorcery Mage (NP) → Sorcery Wizard (Phy) → Sorcery Master (Pla)
```

### Death

```
Death Magic (U2) → Death Lore (Rfg) → Death Adept (Rob) → Death Mage (SFl) → Death Wizard (Sth) → Death Master (SE)
```

### Chaos

```
Chaos Magic (Gun) → Chaos Lore (MP) → Chaos Adept (Med) → Chaos Mage (Met) → Chaos Wizard (Min) → Chaos Master (Mob)
```


**Total: 88 advances**
