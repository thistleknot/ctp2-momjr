---
inclusion: fileMatch
fileMatchPattern: "**/lessons_learned*"
---

# Lessons Learned Conventions

Included when reading or writing lessons_learned files.

## Format

Each entry is dated and titled with a one-line summary of the insight:

```markdown
## YYYY-MM-DD — One-sentence takeaway

**Context/trigger:** what happened that produced this lesson.

**What is actually true, measured:** the corrected understanding with evidence.

**The transferable principle:** the general law, not specific to this instance.
```

## Principles Captured So Far

- When two spends share one resource, the cheaper one starves the dearer unless gated
- When two hypotheses predict the same observation, add the column that splits them
- SHRINK THE RIG, NOT THE QUESTION — keep tests under 15 minutes
- A workaround that works is the thing most likely to stop you finding the fix
- A memory with a CORRECTED section is a trap if you read it top-down — put the fix at the TOP
- Do not restore files, run multiple partial fixes, or loop through hypotheses without user test results

## Hypothesis Discipline

Every diagnostic change MUST be preceded by a written, falsifiable hypothesis:
1. **Hypothesis** — what you believe is wrong (cite evidence, not hunches)
2. **Test** — single change, one variable isolated
3. **Prediction** — observable outcome if TRUE vs FALSE
4. **Confirmation bar** — how you'll know (intermittent bugs need multiple trials)

Document BEFORE making changes. Record result against prediction. Only then move
to the next hypothesis.
