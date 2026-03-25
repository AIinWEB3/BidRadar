# BidRadar Scoring Rubric

Use this rubric to score every opportunity out of 100.

## Dimensions

- `25` points: service and technical fit
- `20` points: relevant past performance
- `20` points: mandatory requirement coverage
- `15` points: budget and attractiveness
- `10` points: timeline and delivery feasibility
- `10` points: strategic fit

## Thresholds

- `75+`: `Bid`
- `55-74`: `Review`
- `<55`: `No-Bid`

## Rules

- If a mandatory requirement is clearly unmet, cap the outcome at `Review` or `No-Bid`.
- If evidence is weak or missing, lower confidence and add a risk.
- Separate:
  - extracted opportunity facts
  - company evidence
  - inferred judgment

## Output Schema

Every report should contain:

- `verdict`
- `score`
- `confidence`
- `reasons`
- `risks`
- `matched_capabilities`
- `missing_requirements`
- `next_action`
- `sponsor_usage`

## Reason Style

Reasons should be short, concrete, and tied to evidence, for example:

- "The opportunity asks for AWS-based data modernization and the firm has two similar public-sector projects on AWS."
- "The estimated contract value is inside the preferred range."

## Risk Style

Risks should be explicit and operational, for example:

- "The deadline is in five days, which may be too short for capture preparation."
- "The requirement for active Top Secret clearance is not supported by the company profile."
