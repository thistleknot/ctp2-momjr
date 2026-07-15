import csv, re, os

MOMJR_CSV = os.path.join(os.path.dirname(__file__), 'momjr_csv')

def make_key(name):
    key = name.strip()
    key = re.sub(r"'", '', key)
    stripped = re.sub(r'x\([^)]+\)', '', key)
    if stripped.strip():
        key = stripped
    key = re.sub(r'^x(?=[A-Z])', '', key)
    key = re.sub(r'[^A-Za-z0-9 ]', '_', key)
    key = re.sub(r'_+', '_', key)
    key = re.sub(r'^_|_$', '', key)
    key = re.sub(r' +', '_', key)
    key = key.upper()
    return key

# === UNITS ===
raw_units = [
 ['Peasants','0','1.','0a','1d','2h','1f','4','nil'],
 ['Zombies','0','1.','2a','2d','2h','1f','4','Rfg'],
 ['Spearmen','0','1.','1a','1d','1h','1f','1','nil'],
 ['Swordsmen','0','1.','2a','2d','1h','1f','2','Bro'],
 ['Phantom Warriors','0','2.','3a','1d','1h','2f','3','The'],
 ['Hell Hounds','0','1.','4a','2d','1h','1f','6','MP'],
 ['Warbears','0','1.','3a','3d','2h','1f','4','Plu'],
 ['Warlock','0','2.','12a','2d','2h','2f','12','AFl'],
 ['Ariel','0','2.','3a','8d','2h','2f','4','no'],
 ['Jafar','0','4.','6a','4d','2h','2f','6','no'],
 ['Rjak','0','2.','6a','6d','2h','2f','8','no'],
 ['Tauron','0','2.','8a','3d','2h','3f','5','no'],
 ['Serena','0','2.','3a','4d','2h','1f','6','no'],
 ['Freya','0','3.','4a','5d','2h','2f','4','no'],
 ['Alorra','0','2.','6a','2d','2h','1f','10','no'],
 ['Centaurs','0','2.','2a','1d','1h','1f','2','Env'],
 ['Elven Archers','0','1.','3a','1d','1h','1f','3','Cor'],
 ['Mage','0','1.','3a','1d','1h','1f','4','X6'],
 ['Wyvern','1','3.','8a','4d','2h','2f','12','Che'],
 ['Knights','0','2.','4a','2d','1h','1f','4','Chi'],
 ['Paladins','0','2.','6a','2d','2h','1f','5','Ldr'],
 ['Unicorn','0','3.','3a','6d','2h','1f','6','Lab'],
 ['Iron Golem','0','1.','8a','5d','4h','1f','9','Esp'],
 ['Catapult','0','1.','6a','1d','1h','1f','4','Mat'],
 ['Steam Cannon','0','1.','10a','2d','2h','2f','12','X3'],
 ['B6','0','1.','5a','4d','4h','1f','9','no'],
 ['B3','0','1.','5a','4d','4h','1f','9','no'],
 ['B9','0','1.','5a','4d','4h','1f','9','no'],
 ['Efreet','0','1.','7a','3d','2h','2f','9','Met'],
 ['Wraith','0','2.','4a','3d','2h','1f','6','Rob'],
 ['Griffin','1','4.','4a','4d','2h','1f','6','X4'],
 ['Pegasus','1','5.','5a','2d','2h','2f','8','Las'],
 ['Galley','2','3.','1a','1d','1h','1f','4','Map'],
 ['Warship','2','4.','7a','3d','2h','1f','8','Eng'],
 ['Hydra','0','1.','12a','3d','3h','2f','12','Mob'],
 ['Airship','1','6.','5a','1d','1h','1f','4','X3'],
 ['Minotaur','0','1.','1a','2d','2h','1f','3','War'],
 ['War Troll','0','1.','7a','5d','3h','1f','7','Tac'],
 ['Gargoyle','1','2.','2a','4d','2h','1f','6','Med'],
 ['Guardian Spirit','0','2.','1a','5d','3h','1f','4','Inv'],
 ['Cockatrice','1','2.','6a','1d','1h','3f','6','PT'],
 ['B7','0','1.','5a','4d','4h','1f','9','no'],
 ['B8','0','1.','5a','4d','4h','1f','9','no'],
 ['B3','0','1.','5a','4d','4h','1f','9','no'],
 ['Salamander','0','2.','10a','3d','2h','1f','10','X5'],
 ['Infernal Device','1','10.','99a','0d','1h','1f','16','NF'],
 ['Minion','0','2.','0a','0d','1h','1f','3','Wri'],
 ['Demon','1','2.','4a','5d','2h','1f','7','SFl'],
 ['Caravan','0','1.','0a','1d','1h','1f','5','Tra'],
 ['B5','0','1.','5a','4d','4h','1f','9','no'],
 ['B4','0','1.','5a','4d','4h','1f','9','no'],
 ['War Mammoth','0','2.','10a','5d','3h','1f','8','Exp'],
 ['Storm Giant','0','2.','8a','4d','2h','1f','9','NP'],
 ['Air Elemental','1','8.','6a','3d','1h','1f','5','X2'],
 ['Storm Drake','1','5.','12a','6d','3h','2f','14','Pla'],
 ['Warrax','0','2.','8a','3d','2h','2f','12','no'],
 ['Undead Dragon','1','3.','12a','6d','4h','2f','3','SE'],
 ['Great Wyrm','0','2.','15a','9d','6h','2f','12','Ref'],
 ['Behemoth','0','1.','5a','4d','4h','1f','9','Rad'],
 ['Malleus','0','2.','8a','2d','2h','1f','10','no'],
 ['Merfolk','2','4.','4a','3d','2h','1f','5','U3'],
 ['Archangel','1','4.','12a','12d','2h','2f','12','Mag'],
]
h_units = ['name','domain','move','attack','defense','hp','firepower','cost','prereq','icon','sprite','sound_select1','sound_move','sound_attack']
with open(os.path.join(MOMJR_CSV,'units.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(h_units)
    for r in raw_units:
        k = make_key(r[0])
        r += [f'ICON_UNIT_{k}', f'SPRITE_{k}', f'SOUND_SELECT1_{k}', f'SOUND_MOVE_{k}', f'SOUND_ATTACK_{k}']
        w.writerow(r)
print(f'[OK] units.csv: {len(raw_units)} rows')

# === IMPROVEMENTS ===
raw_impr = [
 ['Nothing','1','0','nil'],
 ["Wizard's Fortress",'10','0','Mas'],
 ['Barracks','4','1','nil'],
 ['Granary','6','1','Pot'],
 ['Temple','4','1','Cer'],
 ['MarketPlace','8','1','Cur'],
 ['Library','8','1','Wri'],
 ['Courthouse','8','1','CoL'],
 ['City Walls','8','0','Mas'],
 ['Aqueduct','8','2','Cst'],
 ['Bank','12','3','Ban'],
 ['Cathedral','12','3','MT'],
 ['University','16','3','Uni'],
 ['xMass Transit','16','4','no'],
 ['Colosseum','10','4','Cst'],
 ["Mechanician's Guild",'20','4','X3'],
 ['xManufacturing Plant','32','6','no'],
 ['xSDI Defense','20','4','no'],
 ['xRecycling Center','20','2','no'],
 ['xPower Plant','16','4','no'],
 ['xHydro Plant','24','4','no'],
 ['Primal Source','16','2','U1'],
 ["Merchant's Guild",'16','4','Eco'],
 ['Sewer System','12','2','San'],
 ['xSupermarket','8','3','no'],
 ['xSuperhighways','20','5','no'],
 ['Beacon of Wisdom','16','3','Fli'],
 ['SAM Missile Battery','10','2','no'],
 ['Coastal Fortress','8','1','no'],
 ['Solar Harness','32','4','Rec'],
 ['Harbor','6','1','Sea'],
 ['Sea Mines','16','3','Eng'],
 ['Fantastic Stable','16','3','X4'],
 ['xPolice Station','6','2','no'],
 ['Port','8','3','U3'],
 ['Transporter','0','0','no'],
 ['xSS Structural','8','0','no'],
 ['xSS Component','16','0','no'],
 ['xSS Module','32','0','no'],
 ['x(Capitalization)','60','0','no'],
 ["Gaia's Shrine",'20','0','PT'],
 ['Pleasure Dome','20','0','The'],
 ['Font of Bounty','20','0','Plu'],
 ['xLighthouse','20','0','no'],
 ['Great Library','30','0','Lit'],
 ['Oracle','30','0','Mys'],
 ['Wall of Bone','30','0','Rob'],
 ['Guild of Legends','30','0','Feu'],
 ['Rune of Rulership','30','0','E1'],
 ['Bardic College','20','0','Tra'],
 ['The Parthenon','40','0','MT'],
 ["Mystic X's Tower",'30','0','Ast'],
 ["Gunthar's Voyage",'40','0','Nav'],
 ["Prospero's Conservatory",'30','0','CA'],
 ['Elixir of Metamorphosis','40','0','Cmp'],
 ['Enchanted Grotto','40','0','Inv'],
 ['Eldritch College','40','0','Ato'],
 ['Gnome Treasury','40','0','Eco'],
 ["Reywind's Discovery",'40','0','RR'],
 ['xStatue of Liberty','40','0','no'],
 ["Mesmer's Tower",'30','0','Cmb'],
 ["xWomen's Suffrage",'60','0','no'],
 ['Forge of Chaos','60','0','Min'],
 ['Entropy Engine','60','0','NF'],
 ['League of Wizards','60','0','Phy'],
 ['xApollo Program','60','0','no'],
 ['Celestial Beacon','60','0','Too'],
 ['xCure for Cancer','60','0','no'],
]
h_impr = ['name','cost','upkeep','prereq','icon']
with open(os.path.join(MOMJR_CSV,'improvements.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(h_impr)
    for r in raw_impr:
        k = make_key(r[0])
        r.append(f'ICON_IMPROVE_{k}')
        w.writerow(r)
print(f'[OK] improvements.csv: {len(raw_impr)} rows')

# === ADVANCES ===
raw_adv = [
 ['Alchemy','','Cmp','nil','0','3    ; AFl'],
 ['Alphabet','','nil','nil','0','3    ; Alp'],
 ['Animism','','Uni','no','0','3    ; Amp'],
 ['Astrology','','Mys','Mat','0','3    ; Ast'],
 ['Eldritch Lore','','Ast','nil','0','3    ; Ato'],
 ['User Def Tech A','','no','no','0','0    ; Aut'],
 ['Banking','','Rep','Tra','0','1    ; Ban'],
 ['Bridge Building','','Iro','Cst','0','4    ; Bri'],
 ['Bronze Working','','nil','nil','0','4    ; Bro'],
 ['Ceremonial Burial','','nil','nil','0','2    ; Cer'],
 ['Greater Fauna Lore','','X4','nil','0','3    ; Che'],
 ['Chivalry','','Feu','nil','0','0    ; Chi'],
 ['Code of Laws','','Alp','nil','0','2    ; CoL'],
 ['Healing','','Ast','Phi','0','3    ; CA'],
 ['Lesser Enchanments','','no','nil','0','3    ; Cmb'],
 ['Extra Advance 4','','no','no','0','0    ; Cmn'],
 ['Metamorphosis','','E1','Cst','0','3    ; Cmp'],
 ['Extra Advance 6','','no','no','0','0    ; Csc'],
 ['Construction','','Mas','Cur','0','4    ; Cst'],
 ['Pantheism','','Cer','Env','0','3    ; Cor'],
 ['Currency','','Bro','nil','0','1    ; Cur'],
 ['Extra Advance 5','','no','no','0','0    ; Dem'],
 ['Ecognomics','','Uni','Ban','0','1    ; Eco'],
 ['Rune Lore','','X6','Lit','0','3    ; E1'],
 ['User Def Tech C','','no','no','0','0    ; E2'],
 ['Sea Mastery','','Iro','U3','0','3    ; Eng'],
 ['Shamanism','','nil','nil','0','3    ; Env'],
 ['Thaumaturgy','','The','X6','0','3    ; Esp'],
 ['Tactics','','Tac','Uni','0','0    ; Exp'],
 ['Feudalism','','War','nil','0','0    ; Feu'],
 ['Wizardry','','AFl','nil','0','3    ; Fli'],
 ['Extra Advance 3','','no','no','0','0    ; Fun'],
 ['Glyphs','','no','no','0','3    ; FP'],
 ['Life Magic','','NF','nil','1','2    ; Gen'],
 ['User Def Tech B','','no','no','0','0    ; Gue'],
 ['Chaos Magic','','NF','nil','1','0    ; Gun'],
 ['Sorcery','','NF','nil','1','4    ; Hor'],
 ['Extra Advance 1','','no','no','0','0    ; Ind'],
 ['Life Lore','','Gen','Ato','1','2    ; Inv'],
 ['Iron Working','','Bro','War','0','4    ; Iro'],
 ['Life Adept','','Inv','nil','1','2    ; Lab'],
 ['Life Mage','','Lab','nil','1','2    ; Las'],
 ['Holy Warriors','','Chi','The','0','0    ; Ldr'],
 ['Literacy','','Wri','CoL','0','3    ; Lit'],
 ['Life Wizard','','Las','nil','1','2    ; Too'],
 ['Life Master','','Too','nil','1','2    ; Mag'],
 ['Map Making','','Alp','nil','0','1    ; Map'],
 ['Masonry','','nil','nil','0','4    ; Mas'],
 ['Chaos Lore','','Gun','Ato','1','0    ; MP'],
 ['Mathematics','','Alp','Mas','0','3    ; Mat'],
 ['Chaos Adept','','MP','nil','1','0    ; Med'],
 ['Chaos Mage','','Med','nil','1','0    ; Met'],
 ['Chaos Wizard','','Met','nil','1','0    ; Min'],
 ['Chaos Master','','Min','nil','1','0    ; Mob'],
 ['Monarchy','','Cer','CoL','0','2    ; Mon'],
 ['Theology','','Phi','Feu','0','2    ; MT'],
 ['Mysticism','','Cer','nil','0','2    ; Mys'],
 ['Navigation','','Sea','Ast','0','1    ; Nav'],
 ['Grand Mastery','','Exp','Fli','0','0    ; NF'],
 ['Sorcery Mage','','X2','nil','1','4    ; NP'],
 ['Philosophy','','Mys','Lit','0','2    ; Phi'],
 ['Sorcery Wizard','','NP','nil','1','4    ; Phy'],
 ['Sorcery Master','','Phy','nil','1','4    ; Pla'],
 ['Nature Lore','','X1','Ato','1','1    ; Plu'],
 ['Nature Adept','','Plu','nil','1','1    ; PT'],
 ['Pottery','','nil','nil','0','1    ; Pot'],
 ['Nature Mage','','PT','nil','1','1    ; Rad'],
 ['Greater Enchantments','','no','nil','0','3    ; RR'],
 ['Nature Wizard','','Rad','nil','1','1    ; Rec'],
 ['Nature Master','','Rec','nil','1','1    ; Ref'],
 ['Death Lore','','U2','Ato','1','3    ; Rfg'],
 ['The Republic','','Lit','nil','0','2    ; Rep'],
 ['Death Adept','','Rfg','nil','1','3    ; Rob'],
 ['Extra Advance 2','','no','no','0','0    ; Roc'],
 ['Sanitation','','CA','nil','0','1    ; San'],
 ['Seafaring','','Map','Pot','0','1    ; Sea'],
 ['Death Mage','','Rob','nil','1','3    ; SFl'],
 ['Death Wizard','','SFl','nil','1','3    ; Sth'],
 ['Death Master','','Sth','nil','1','3    ; SE'],
 ['blah','','no','no','0','4    ; Stl'],
 ['blah','','no','no','0','3    ; Sup'],
 ['Leadership','','Chi','Uni','0','0    ; Tac'],
 ['Sorcerous Lore','','Hor','Ato','1','4    ; The'],
 ['Blah','','no','no','0','3    ; ToG'],
 ['Trade','','Cur','CoL','0','1    ; Tra'],
 ['University','','Mat','Phi','0','3    ; Uni'],
 ['Warrior Code','','nil','nil','0','0    ; War'],
 ['blah','','no','no','0','4    ; Whe'],
 ['Writing','','Alp','nil','0','3    ; Wri'],
 ['Future Technology','','Sth','MP','3','3    ; ...'],
 ['Forces of Nature','','Amp','nil','0','3    ; U1'],
 ['Death Magic','','NF','nil','1','3    ; U2'],
 ['Sea Lore','','Nav','nil','0','3    ; U3'],
 ['Nature Magic','','NF','nil','1','1    ; X1'],
 ['Sorcery Adept','','The','nil','1','4    ; X2'],
 ['Artificing','','Esp','nil','0','3    ; X3'],
 ['Lesser Fauna Lore','','Amp','nil','0','3    ; X4'],
 ['Pyrotechnics','','Ato','nil','0','3    ; X5'],
 ['Occult Studies','','Env','nil','0','3    ; X6'],
 ['Extra Advance 7','','no','no','0','0    ; X7'],
]
h_adv = ['name','code','prereq1','prereq2','epoch','category','icon','gameplay_str','historical_str','prereq_str','vari_str','stattext_str']
with open(os.path.join(MOMJR_CSV,'advances.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(h_adv)
    for r in raw_adv:
        k = make_key(r[0])
        r += [f'ICON_ADVANCE_{k}', f'ADVANCE_{k}_GAMEPLAY', f'ADVANCE_{k}_HISTORICAL', f'ADVANCE_{k}_PREREQ', f'ADVANCE_{k}_STATISTICS', f'ADVANCE_{k}_PREREQ']
        w.writerow(r)
print(f'[OK] advances.csv: {len(raw_adv)} rows')

print('All 3 CSVs regenerated clean with image schema columns.')