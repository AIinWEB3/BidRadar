# BidRadar Source Routing

Use the lowest-risk source path first.

## Priority Order

1. SAM scan via the Apify `sam-gov-scraper` actor when the user asks to search opportunities
2. Explicit local file provided by the user
3. Pasted text written to a local file
4. URL fetched directly
5. URL fetched via Apify content extraction when configured for that purpose
6. Local fallback asset

## Why This Order

- Local input is the safest path and easiest to debug.
- SAM scanning is better done through a purpose-built actor than a generic page crawler.
- Direct fetch is often enough for simple public detail pages.
- Apify should be used when it clearly improves discovery or cleanup.
- The demo must still work without external services.

## Apify Usage

Apify is the preferred live discovery layer for SAM scan mode.

Environment variables:

- `APIFY_TOKEN`
- `APIFY_ACTOR_ID` for the SAM scan actor
- `APIFY_CONTENT_ACTOR_ID` optional, if you want a separate content-extraction actor for URL mode

Behavior:

- In SAM scan mode, the script uses `fortuitous_pirate/sam-gov-scraper` by default.
- In URL mode, the script prefers direct fetch and only uses Apify content extraction if a content actor is configured.
- If Apify fails, the script falls back to direct fetch or local demo assets.

## Contextual Usage

Contextual is used for grounded company knowledge retrieval and conservative semantic scoring support.

Environment variables:

- `CONTEXTUAL_API_KEY`
- `CONTEXTUAL_AGENT_ID` preferred
- `CONTEXTUAL_QUERY_URL` optional explicit endpoint override

Behavior:

- If Contextual config is present, the script asks for both evidence and a structured fit assessment relevant to the opportunity.
- The runtime blends Contextual semantic fit into service, past-performance, and strategic-fit scoring, while keeping budget, timeline, mandatory requirements, and hard blockers deterministic.
- If Contextual fails, the script falls back to the local company profile file.

## Failure Handling

If a live path fails:

- log the failure into the report notes
- continue with the best available fallback
- keep the final report complete

Never stop the workflow just because an external integration is unavailable.
