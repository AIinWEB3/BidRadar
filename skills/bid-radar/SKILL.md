---
name: bid-radar
description: Scan and rank public procurement opportunities, or evaluate a single RFP or SAM.gov notice, and return Bid, Review, or No-Bid with reasons, risks, matched capabilities, and next steps. Use when the user wants discovery, qualification, or bid/no-bid guidance against company capabilities or past work.
---

# BidRadar

Use this skill when the user wants to discover, scan, shortlist, or qualify public opportunities for a consulting or services firm.

Typical trigger requests:

- "Should we bid on this RFP?"
- "Evaluate this SAM.gov opportunity for our firm."
- "Compare this procurement notice to our company capabilities."
- "Review this opportunity and tell me if we should bid."
- "Scan SAM.gov for opportunities we should bid on."
- "Find public-sector data modernization opportunities and rank them."

## Inputs

Preferred inputs:

- a SAM.gov scan request with keywords or filters
- a public opportunity URL
- a local file with pasted opportunity text
- pasted opportunity text written to a temp file if needed

Optional input:

- a company profile file

If no company profile is provided, use `assets/demo-company-profile.md`.
If no opportunity is provided, use `assets/demo-opportunity.md`.

## Workflow

1. Run `scripts/validate_inputs.py` to detect the execution mode.
2. If the user wants discovery, run `scripts/qualify_opportunity.py --scan-sam ...` with the desired filters.
3. Otherwise, run `scripts/qualify_opportunity.py` with the resolved input.
4. Read the generated report.
5. Return a concise answer with:
   - verdict
   - score
   - top reasons
   - top risks
   - next action
   - shortlist summary when scan mode is used
6. Tell the user whether the run used:
   - Apify live extraction
   - Contextual company evidence
   - local fallback assets

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

For local input:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --file /path/to/opportunity.md
```

For an explicit company profile:

```bash
python3 skills/bid-radar/scripts/qualify_opportunity.py --file /path/to/opportunity.md --company-profile /path/to/company-profile.md
```

## Decision Rules

- Keep the output grounded in the opportunity text and company materials.
- Prefer deterministic scoring over freeform judgment.
- Use `references/scoring-rubric.md` for the score and thresholds.
- Use `references/source-routing.md` for when to use the SAM scraper, direct fetch, or local fallback.
- If a mandatory requirement is clearly unmet, do not override that risk with optimistic language.
- If live integrations fail, continue in fallback mode instead of stopping.

## Output Expectations

The report should always include:

- `Bid / Review / No-Bid`
- total score
- matched capabilities
- top reasons
- top risks
- evidence source
- next action
- shortlist results in scan mode

## Fallback Behavior

If Apify or Contextual is unavailable:

- use local opportunity content
- use local company profile content
- still produce a complete report

The skill should fail soft, not fail closed.
