#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
DEMO_COMPANY = SKILL_ROOT / "assets" / "demo-company-profile.md"
DEMO_OPPORTUNITY = SKILL_ROOT / "assets" / "demo-opportunity.md"


def is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_existing_path(candidate: str | None) -> Path | None:
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BidRadar inputs and integration availability.")
    parser.add_argument("--url", help="Public opportunity URL to evaluate.")
    parser.add_argument("--file", help="Local file containing opportunity text or markdown.")
    parser.add_argument("--text", help="Inline opportunity text.")
    parser.add_argument("--company-profile", help="Optional local company profile file.")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    opportunity_source = "demo-asset"
    resolved_opportunity_file: Path | None = None
    resolved_company_profile = resolve_existing_path(args.company_profile) or DEMO_COMPANY

    if args.url:
        if not is_url(args.url):
            errors.append("The provided --url value is not a valid http/https URL.")
        opportunity_source = "url"
    elif args.file:
        resolved_opportunity_file = resolve_existing_path(args.file)
        opportunity_source = "file"
    elif args.text:
        opportunity_source = "text"
    else:
        resolved_opportunity_file = DEMO_OPPORTUNITY
        warnings.append("No opportunity input provided; using the demo opportunity asset.")

    if opportunity_source == "file":
        if not resolved_opportunity_file or not resolved_opportunity_file.exists():
            errors.append("The provided --file path does not exist.")

    if not resolved_company_profile.exists():
        errors.append(f"Company profile file not found: {resolved_company_profile}")

    apify_token = os.getenv("APIFY_TOKEN")
    apify_actor_id = os.getenv("APIFY_ACTOR_ID")
    contextual_api_key = os.getenv("CONTEXTUAL_API_KEY")
    contextual_agent_id = os.getenv("CONTEXTUAL_AGENT_ID")
    contextual_query_url = os.getenv("CONTEXTUAL_QUERY_URL")

    apify_available = bool(apify_token and apify_actor_id)
    apify_direct_fetch = opportunity_source == "url"
    contextual_available = bool(contextual_api_key and (contextual_agent_id or contextual_query_url))

    if opportunity_source == "url" and not apify_available:
        warnings.append("Apify is not fully configured; the runtime will fall back to direct URL fetch.")
    if not contextual_available:
        warnings.append("Contextual is not configured; the runtime will use the local company profile.")

    if opportunity_source == "demo-asset":
        mode = "fallback"
    elif opportunity_source in {"file", "text"}:
        mode = "partial" if contextual_available else "fallback"
    else:
        mode = "live" if (apify_available or apify_direct_fetch) and contextual_available else "partial"

    result = {
        "mode": mode,
        "input_source": opportunity_source,
        "apify": apify_available,
        "apify_actor_id": apify_actor_id,
        "direct_fetch": apify_direct_fetch,
        "contextual": contextual_available,
        "resolved_company_profile": str(resolved_company_profile),
        "resolved_opportunity_file": str(resolved_opportunity_file) if resolved_opportunity_file else None,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
