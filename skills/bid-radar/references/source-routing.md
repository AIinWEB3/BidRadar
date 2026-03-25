# BidRadar Source Routing

Use the lowest-risk source path first.

## Priority Order

1. Explicit local file provided by the user
2. Pasted text written to a local file
3. URL fetched directly
4. URL fetched via Apify when configured
5. Local fallback asset

## Why This Order

- Local input is the safest path and easiest to debug.
- Direct fetch is often enough for simple public pages.
- Apify should be used when it clearly improves extraction or cleanup.
- The demo must still work without external services.

## Apify Usage

Apify is optional but valuable for live extraction.

Environment variables:

- `APIFY_TOKEN`
- `APIFY_ACTOR_ID` optional, if you want to route through a specific actor

Behavior:

- If both are available, the script attempts an Apify actor run first.
- If Apify fails, the script falls back to direct fetch.
- If no URL is provided, Apify is not used.

## Contextual Usage

Contextual is used only for company knowledge retrieval.

Environment variables:

- `CONTEXTUAL_API_KEY`
- `CONTEXTUAL_AGENT_ID` preferred
- `CONTEXTUAL_QUERY_URL` optional explicit endpoint override

Behavior:

- If Contextual config is present, the script asks for evidence relevant to the opportunity.
- If Contextual fails, the script falls back to the local company profile file.

## Failure Handling

If a live path fails:

- log the failure into the report notes
- continue with the best available fallback
- keep the final report complete

Never stop the workflow just because an external integration is unavailable.
