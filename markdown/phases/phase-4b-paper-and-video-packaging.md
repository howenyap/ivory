# Phase 4b: Paper and Video Packaging

## Objective

Translate the completed experiment outputs into submission-ready paper and video materials. This phase should not invent new results. It should map existing artifacts into the report structure, the video flow, and the final submission checklist so the project can be presented coherently and defensibly.

## Inputs / Dependencies

- [`phase-4a-reproducibility-and-report-assets.md`](./phase-4a-reproducibility-and-report-assets.md) is complete.
- Final figures and tables exist under `artifacts/report/`.
- The course submission requirements in [`../project outlines.md`](../project%20outlines.md) are understood.

## Implementation Steps

1. Create a paper-outline document that maps:
   - title and abstract intent
   - introduction claims
   - background topics
   - methodology details
   - performance evaluation figures and tables
   - conclusion points
2. Map each required paper section to specific artifacts so no claim is left unsupported.
3. Create a figure and table inventory for the paper with captions or caption placeholders.
4. Create a video flow that follows the paper structure and identifies:
   - slide sequence
   - demo segments if any
   - which figure or table appears where
   - who presents what if the group needs speaking assignments
5. Create a submission checklist covering:
   - paper completeness
   - video completeness
   - file formats
   - final artifact locations
   - deadline readiness
6. Keep all deliverables grounded in already-generated project outputs.

## Deliverables

- paper outline document
- section-to-artifact mapping
- figure and table inventory
- video flow or script outline
- submission checklist

## Verification

Run these checks from the repository root:

```bash
rg -n "^## " markdown reports
```

Expected result:
- section structure exists for the outline or report scaffolding

```bash
find artifacts/report/figures -maxdepth 1 -type f | wc -l
find artifacts/report/tables -maxdepth 1 -type f | wc -l
```

Expected result:
- the inventory can point to real generated assets

```bash
rg -n "TBD|TODO|placeholder|insert later" markdown reports
```

Expected result:
- no unresolved placeholders remain in final packaging docs unless explicitly accepted

## Definition of Done

- Every paper section has a mapped supporting artifact.
- The video flow is grounded in concrete outputs from the project.
- Submission requirements are captured in a checklist.
- No new experimental claims are introduced without artifact support.
- The team can use these packaging docs directly to assemble the submission.

## Common Failure Modes

- Writing conclusions that are not backed by saved evaluation artifacts.
- Planning a video around demos or visuals that do not exist.
- Forgetting to map figures and tables to specific sections.
- Leaving placeholder text in the final packaging docs.
- Treating this phase as a fresh research phase instead of a packaging phase.

## Codex Prompt Contract

Implement the paper and video packaging documents only. Do not change experimental results in this phase. Before stopping, prove that every planned section or video segment maps to a real artifact and that the submission checklist reflects the actual course requirements.
