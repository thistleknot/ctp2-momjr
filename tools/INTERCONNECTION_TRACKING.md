# CTEdit Integration Plan: Interconnection-Aware Masking
## Auto-Notify User When Record is Masked for Removal

### Goal
When a user selects a record (unit, advance, improvement, etc.) in the ctpedit.py UI dropdown for removal/masking, the tool should:
1. **Auto-detect all interconnections** (icon refs, GL sections, text links, prerequisites)
2. **Display findings to user** before confirming the mask
3. **Offer option to auto-clean** all found interconnections
4. **Track mask state** in persistent database

### Interconnections to Track (by dimension)

#### Units (UNIT_*)
- Icon definition in `uniticon.txt`
- GL sections: `[UNIT_X_GAMEPLAY]`, `[UNIT_X_HISTORICAL]`, `[UNIT_X_PREREQ]`, `[UNIT_X_STATISTICS]`, `[UNIT_X_SUMMARY]`
- Text references in GL: `<L:DATABASE_UNITS,UNIT_X>`
- References in advance descriptions
- References in improvement descriptions
- References in wonder descriptions

#### Advances (ADVANCE_*)
- GL sections: `[ADVANCE_X_GAMEPLAY]`, `[ADVANCE_X_HISTORICAL]`, `[ADVANCE_X_PREREQ]`, `[ADVANCE_X_STATISTICS]`
- Text references in GL: `<L:DATABASE_ADVANCES,ADVANCE_X>`
- Prerequisites in other records (units, advances, improvements, wonders)

#### Improvements (IMPROVE_*)
- Icon definition in `uniticon.txt`
- GL sections: `[IMPROVE_X_GAMEPLAY]`, `[IMPROVE_X_HISTORICAL]`, `[IMPROVE_X_PREREQ]`, `[IMPROVE_X_STATISTICS]`, `[IMPROVE_X_SUMMARY]`
- Prerequisites in other records

#### Wonders (WONDER_*)
- Icon definition in `uniticon.txt`
- GL sections: `[WONDER_X_GAMEPLAY]`, `[WONDER_X_HISTORICAL]`, `[WONDER_X_PREREQ]`, `[WONDER_X_STATISTICS]`
- Text references in GL

#### Tile Improvements (TILEIMP_*)
- Icon definition in `uniticon.txt`
- GL sections: `[TILEIMP_X_GAMEPLAY]`, `[TILEIMP_X_HISTORICAL]`, `[TILEIMP_X_PREREQ]`, `[TILEIMP_X_STATISTICS]`

### UI/CLI Integration Points

#### 1. CLI (mask_manager.py)
```
python mask_manager.py mask units UNIT_BOMBER
[MASK] units: UNIT_BOMBER

⚠ INTERCONNECTIONS DETECTED:
  Icon Refs: uniticon.txt
  GL Sections: Great_Library.txt
  GL Text Refs: Great_Library.txt

💡 Tip: Run 'python apply_masks.py --apply' to auto-remove all references
```

#### 2. ctpedit.py UI (Proposed)
When user selects "Remove/Mask" from dropdown:
```
┌─────────────────────────────────────────┐
│ REMOVE UNIT: UNIT_BOMBER                │
├─────────────────────────────────────────┤
│ This action will affect:                 │
│  ✗ Icon definition (uniticon.txt)       │
│  ✗ GL Gameplay section                   │
│  ✗ GL Historical section                 │
│  ✗ References in Jet Propulsion advance │
│  ✗ References in Aircraft Carrier advance
│  ✗ References in 2 improvements         │
│                                          │
│ ☑ Auto-remove all interconnections      │
│                                          │
│ [Cancel]  [Mask & Clean Up]             │
└─────────────────────────────────────────┘
```

#### 3. API for ctpedit.py
```python
from scan_interconnections import InterconnectionScanner

scanner = InterconnectionScanner("units", "UNIT_BOMBER")
interconnections = scanner.scan_all()

# Returns dict with keys:
# - icon_refs: [files]
# - gl_sections: [files]
# - gl_text_refs: [files]
# - prerequisite_refs: [files]
# - unit_refs: [files]
# - advance_refs: [files]
# - improve_refs: [files]
# - wonder_refs: [files]

if interconnections:
    print(f"Found interconnections in {len(interconnections)} categories")
    for category, files in interconnections.items():
        print(f"  {category}: {files}")
```

### Implementation Steps

1. **Extend scan_interconnections.py**
   - Add method to return structured interconnection data
   - Add method to return human-readable summary
   - Support quiet mode for programmatic use

2. **Create mask_api.py** (optional wrapper)
   - Provide high-level API for ctpedit.py integration
   - Methods: `get_interconnections()`, `mask_and_cleanup()`, `preview_cleanup()`

3. **Integrate with ctpedit.py**
   - Import `InterconnectionScanner` or `mask_api`
   - Call when user selects "Mask for Removal"
   - Display interconnection warnings in UI
   - Execute `apply_masks.py --apply` to clean up

### Current State

- ✓ `mask_manager.py`: CLI tool to track masks
- ✓ `scan_interconnections.py`: CLI tool to detect interconnections
- ✓ `apply_masks.py`: CLI tool to remove masked records
- ✓ Auto-scan integrated into mask_manager.py
- ⚠ ctpedit.py UI integration: Proposed, not yet implemented
