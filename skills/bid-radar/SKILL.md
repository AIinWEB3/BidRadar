---
name: bid-radar
description: Discover and qualify public-sector procurement opportunities for a consulting or services firm from SAM.gov scans, public notice URLs, local files, or pasted text, then return a Bid, Review, or No-Bid recommendation with score, reasons, risks, matched capabilities, evidence source, and next action. Use when the user asks to search for opportunities, shortlist notices, evaluate an RFP, compare an opportunity to company capabilities or past performance, or make a bid/no-bid decision.
---

# BidRadar

## Inputs

- Accept exactly one primary opportunity source: `--scan-sam`, `--url`, `--file`, or `--text`.
- Accept `--company-profile` when the user provides company-specific materials.
- Prefer `--text` for pasted content instead of creating a temporary file unless a file is explicitly needed.
- Resolve relative file paths from the workspace root; accept absolute paths as-is.
- Fall back to `assets/demo-company-profile.md`, `assets/demo-opportunity.md`, or `assets/demo-sam-opportunities.json` only when user input or live integrations are missing.

## Workflow

1. Run `scripts/validate_inputs.py` first when input resolution, live integration availability, or fallback behavior is unclear.
2. Read the preflight JSON for source resolution, integration availability, resolved files, warnings, and errors.
3. Run `scripts/qualify_opportunity.py` as the primary execution step.
4. Use `--scan-sam` for discovery and shortlisting requests. Pass filters such as `--keywords`, `--states`, `--naics-codes`, `--set-aside-types`, `--posted-within-days`, `--max-opportunities`, and `--opportunity-index` when needed.
5. Use `--url`, `--file`, or `--text` for single-opportunity qualification.
6. Pass `--company-profile` when the user gives firm-specific materials. Otherwise let the script use the demo profile.
7. Read the JSON summary printed to stdout. Open the generated Markdown or JSON report only when you need the full evidence trail.
8. Return a concise answer with the verdict, score, top reasons, top risks, next action, and scan shortlist summary when scan mode was used.
9. State whether the run ended in `live`, `partial`, or `fallback` mode, and mention whether Apify, direct fetch, Contextual, or demo/local assets were used.

## Commands

From the workspace root:

```bash
python3 skills/bid-radar/scripts/validate_inputs.py --url "<opportunity-url>"
python3 skills/bid-radar/scripts/qualify_opportunity.py --url "<opportunity-url>"
```

For SAM scanning:

```bash
python3 skills/bid-radar/scripts/validate_inputs.py --scan-sam --keywords "data modernization" --states CA --max-opportunities 10
python3 skills/bid-radar/scripts/qualify_opportunity.py --scan-sam --keywords "data modernization" --states CA --max-opportunities 10
```

For pasted text:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --text "Opportunity text goes here"
```

For local input:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --file /path/to/opportunity.md
```

For an explicit company profile:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --file /path/to/opportunity.md --company-profile /path/to/company-profile.md
```

To send reports to a temporary directory:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --file /path/to/opportunity.md --report-dir /tmp/bid-radar-reports
```

## References

- Read `references/scoring-rubric.md` when you need the scoring weights, thresholds, or expected report schema.
- Read `references/source-routing.md` when you need to reason about source selection, live integrations, or fallback order.
- Keep reference loading selective. Do not pull reference files into context unless the current task needs them.

## Response Rules

- Keep the recommendation grounded in the opportunity text and company evidence returned by the script.
- Prefer the script's deterministic score and verdict over freeform judgment.
- Treat missing mandatory requirements, no-go criteria, or attachment-only requirements as real risks. Do not override them with optimistic language.
- Report the evidence source clearly: live fetch, SAM scan, Contextual, local company profile, or demo asset.
- Surface shortlist results in scan mode instead of discussing only the selected opportunity.
- Continue in fallback mode when Apify or Contextual is unavailable. Fail soft and still return a complete answer.
