# Phase 4b: Paper and Video Packaging

## Codex Prompt Contract

Implement the paper and video packaging documents only. Do not change experimental results in this phase. Before stopping, prove that every planned section or video segment maps to a real artifact and that the submission checklist reflects the actual course requirements.

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
   - related work plan
   - methodology details
   - performance evaluation figures and tables
   - conclusion points
   - references plan
2. Map each required paper section to specific artifacts so no claim is left unsupported.
3. Create a figure and table inventory for the paper with real captions, not caption placeholders.
4. Create a video flow that follows the paper structure and identifies:
   - slide sequence
   - demo segments if any
   - which figure or table appears where
   - who presents what if the group needs speaking assignments
5. Create a submission checklist covering:
   - paper completeness
   - video completeness
   - file formats
    - paper constraints: PDF, Overleaf, Springer LNCS, max 15 pages
    - video constraints: MP4 or MOV, max 10 minutes, max 200MB
   - submission targets: EasyChair for the paper, Canvas for the video
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
rg -n "Title|Abstract|Introduction|Background|Related Work|Methodology|Performance Evaluation|Conclusion|References" markdown reports
```

Expected result:
- every required paper section from the course brief is present in the outline or report scaffolding

```bash
find artifacts/report/figures -maxdepth 1 -type f | wc -l
find artifacts/report/tables -maxdepth 1 -type f | wc -l
```

Expected result:
- the inventory can point to real generated assets

```bash
uv run python -c "from pathlib import Path; import re; pattern=re.compile(r'TBD|TODO|placeholder|insert later'); paths=[p for root in ['markdown','reports'] for p in ([Path(root)] if Path(root).is_file() else Path(root).rglob('*')) if p.is_file()]; matches=[]; [matches.append(f'{p}:{i}:{line}') for p in paths for i, line in enumerate(p.read_text().splitlines(), 1) if pattern.search(line)]; assert not matches, '\\n'.join(matches)"
```

Expected result:
- no unresolved placeholders remain in final packaging docs

```bash
rg -n "PDF|Overleaf|Springer|15 pages|MP4|MOV|10 minutes|200MB|EasyChair|Canvas" markdown reports
```

Expected result:
- the submission checklist captures the paper, video, and submission-target constraints from the course brief

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
