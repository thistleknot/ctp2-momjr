# Unintegrated Changes & Deferred Features

This directory serves as the canonical holding area for features, SLIC scripts, CSV drafts, or dimension mappings that are **not yet fully integrated** into the MoM control plane due to current generator limitations, unresolved bugs, or architectural pivots.

## Purpose
- **Prevent Data Loss**: Ensures that partially completed work or failed integration attempts are not lost in ancient git commits or wiped by the generator's "RECONSTRUCT FROM NOTHING" nuke phase.
- **Enable Iterative Re-approach**: Provides a clear staging ground to revisit, refactor, and eventually port these features into the active control plane (`momjr_csv/`) and generator pipeline.
- **Maintain Harness Purity**: Keeps the active `ctp2_generator.py` and `momjr_csv/` directory strictly focused on what is currently working and validated, without cluttering them with broken or experimental code.

## Contents
- `mom_func.slc`, `mom_turns.slc`, `mom_city_effects.slc`: Archived SLIC modules that were previously in `_archived_slic/` but were wiped by the generator's nuke phase. These contain MoM-specific logic that needs to be re-evaluated for integration into the active SLIC pipeline.
- *(Future)*: Partial CSV drafts, experimental dimension mappings, or harness patches that require further debugging.

## Protocol
1. **Do not delete files here** without moving them to the active control plane or explicitly documenting why they are permanently abandoned.
2. **When a feature is ready**: Move the relevant files to `momjr_csv/` or the appropriate generator module, update `dimension_inventory.md`, and remove the file from this directory.
3. **Generator Safety**: The `ctp2_generator.py` nuke phase explicitly targets `default/gamedata`, `english/gamedata`, and `default/aidata`. This `_unintegrated/` directory is outside those paths and will **never** be automatically deleted by the generator.
