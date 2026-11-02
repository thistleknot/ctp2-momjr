# Excel-Controlled SLIC Proposal Flow

## Objective

Let an LLM propose MoM SLIC changes from the same reviewed Civ2-to-CTP2 control plane that carries mappings and formulas, then accept those changes only after isolated static and headless game checks.

## Pipeline

`Civ2 source -> encoder -> reviewed mapping/formula workbook -> LLM SLIC proposal cell -> isolated candidate .slc -> static symbol and scenario checks -> headless fresh-game battery -> reviewed acceptance -> canonical .slc -> workbook backcast`

## Requirements

- R1. The workbook shall keep the current `slic` tab as a read-only backcast receipt and store proposed SLIC in a separate `slic_proposals` tab.
- R2. Each proposal shall identify the module, base-file SHA-256, source/target mapping IDs, workbook formula rows it consumes, proposal ID, LLM/model provenance, rationale, and review status.
- R3. Initial LLM proposals shall be retained unchanged; revisions shall append a new proposal with `supersedes` pointing to the prior proposal.
- R4. An unchanged reviewed mapping fingerprint shall be reused; disambiguation shall run only for missing, changed, or explicitly reopened mappings.
- R5. The staging tool shall reject a proposal when its base-file fingerprint is stale, its module is not included, or any referenced CTP2 symbol is absent.
- R6. Candidate SLIC shall be written only into an isolated scenario copy; the generator and live scenario shall remain untouched during proposal evaluation.
- R7. Static checks shall include `mom_audit.py`, `validate_all_surfaces.py`, and the applicable scenario validator against the isolated candidate.
- R8. A candidate shall pass a fresh-game headless battery of at least three varied inputs with zero SLIC compile/runtime errors and explicit assertions for the proposed behavior.
- R9. Every headless case shall be bounded to a total disposition under 15 minutes; use the smallest scenario and turn count that can distinguish the proposed behavior.
- R10. Only an accepted proposal that passes all static and headless gates may replace canonical `.slc` source; the backcast then refreshes the workbook receipt.
- R11. Failed proposals and their logs shall remain available for review and shall not change canonical `.slc`, generated scenario data, or the published mod.

## Decision provenance

- The initial proposal is immutable provenance; acceptance is a separate disposition.
- A replacement proposal is appended and linked to the decision it supersedes; prior choices are not erased.
- Existing MoM source is imported as legacy code. Missing historical LLM records remain unknown and are not reconstructed as if they existed.
- A coverage fingerprint includes source rows, target structures, formula rows, and the SLIC module base hash. Matching coverage does not trigger another LLM proposal.

## Closed

- `backcast_slic.py` remains a receipt generator and never writes source SLIC. Proposed code enters through a separate isolated candidate path.
- Workbook formulas do not substitute for engine execution. A formula receipt proves expected data values; headless game checks prove script loading and behavior.
- A successful parse or zero-error launch alone is insufficient; the proposal-specific assertion must also pass.

## Preconditions and failure modes

- Preconditions: Excel workbook, source mapping/formula rows, staged scenario, CTP2 executable, headless harness, and input fixtures are available.
- Missing mappings, stale fingerprints, unresolved symbols, static-check failures, timeouts, SLIC errors, or failed behavior assertions reject the candidate and preserve canonical files.
