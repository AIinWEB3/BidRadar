#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
DEMO_COMPANY = SKILL_ROOT / "assets" / "demo-company-profile.md"
DEMO_OPPORTUNITY = SKILL_ROOT / "assets" / "demo-opportunity.md"


def fetch_text(url: str, data: dict | None = None, headers: dict | None = None, timeout: int = 30) -> str:
    payload = None
    request_headers = headers or {}
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_path(candidate: str | None, default: Path | None = None) -> Path:
    if candidate:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path
    if default is None:
        raise ValueError("No path candidate or default was provided.")
    return default


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_html_markup(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_markdown_sections(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    metadata: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            current_section = line[3:].strip().lower()
            sections.setdefault(current_section, [])
            continue
        if current_section is None and ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip()
            continue
        if current_section is not None:
            if line.startswith("- "):
                sections[current_section].append(line[2:].strip())
            else:
                sections[current_section].append(line)

    return metadata, sections


def normalize_list(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


def extract_money_amount(text: str | None) -> int | None:
    if not text:
        return None
    matches = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})", text)
    if not matches:
        return None
    try:
        return int(matches[0].replace(",", ""))
    except ValueError:
        return None


def extract_min_max_range(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    matches = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})", text)
    numbers: list[int] = []
    for match in matches:
        try:
            numbers.append(int(match.replace(",", "")))
        except ValueError:
            continue
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers), max(numbers)


def extract_deadline_days(deadline_text: str | None) -> int | None:
    if not deadline_text:
        return None
    try:
        deadline = dt.date.fromisoformat(deadline_text.strip())
    except ValueError:
        return None
    return (deadline - dt.date.today()).days


def text_contains_phrase(text: str, phrase: str) -> bool:
    cleaned = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    phrase_clean = " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))
    return bool(phrase_clean) and phrase_clean in cleaned


def score_overlap(candidates: list[str], haystack: str, weight: int) -> tuple[int, list[str]]:
    matched = [candidate for candidate in candidates if text_contains_phrase(haystack, candidate)]
    if not candidates:
        return weight // 2, []
    ratio = len(matched) / len(candidates)
    return round(weight * min(1.0, ratio)), matched


def fetch_via_apify(url: str, notes: list[str]) -> str | None:
    token = os.getenv("APIFY_TOKEN")
    actor_id = os.getenv("APIFY_ACTOR_ID")
    if not token or not actor_id:
        return None

    endpoint = f"https://api.apify.com/v2/acts/{urllib.parse.quote(actor_id, safe='')}/run-sync-get-dataset-items?token={urllib.parse.quote(token)}"
    payload = {
        "startUrls": [{"url": url}],
        "start_urls": [{"url": url}],
        "maxCrawlPages": 1,
        "max_crawl_pages": 1,
        "proxyConfiguration": {"useApifyProxy": True},
    }

    try:
        raw = fetch_text(endpoint, data=payload, headers={"Accept": "application/json"}, timeout=60)
        items = json.loads(raw)
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            notes.append("Apify returned no dataset items; falling back to direct fetch.")
            return None
        first = items[0]
        if isinstance(first, dict):
            for key in ("text", "markdown", "content", "html", "body", "description"):
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    notes.append("Used Apify for live opportunity extraction.")
                    return strip_html_markup(value) if key in {"html", "body"} else value.strip()
        notes.append("Apify response did not contain a usable text field; falling back to direct fetch.")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Apify fetch failed: {exc}. Falling back to direct fetch.")
    return None


def fetch_direct(url: str, notes: list[str]) -> str | None:
    try:
        text = fetch_text(url, headers={"User-Agent": "BidRadar/0.1"})
        notes.append("Used direct URL fetch for live opportunity content.")
        return strip_html_markup(text)
    except urllib.error.URLError as exc:
        notes.append(f"Direct fetch failed: {exc}.")
        return None


def query_contextual(question: str, notes: list[str]) -> str | None:
    api_key = os.getenv("CONTEXTUAL_API_KEY")
    query_url = os.getenv("CONTEXTUAL_QUERY_URL")
    agent_id = os.getenv("CONTEXTUAL_AGENT_ID")
    if not api_key:
        return None
    if not query_url and agent_id:
        query_url = f"https://api.contextual.ai/v1/agents/{agent_id}/query"
    if not query_url:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    payload = {
        "query": question,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
    }

    try:
        raw = fetch_text(query_url, data=payload, headers=headers, timeout=60)
        parsed = json.loads(raw)
        notes.append("Used Contextual for grounded company evidence.")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Contextual query failed: {exc}. Falling back to local company profile.")
        return None

    def pull_strings(value: object) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, dict):
            out: list[str] = []
            for nested in value.values():
                out.extend(pull_strings(nested))
            return out
        if isinstance(value, list):
            out: list[str] = []
            for nested in value:
                out.extend(pull_strings(nested))
            return out
        return []

    strings = pull_strings(parsed)
    if not strings:
        return None
    unique_strings: list[str] = []
    for item in strings:
        if item not in unique_strings:
            unique_strings.append(item)
    return "\n".join(unique_strings[:5])


def build_contextual_question(opportunity_text: str) -> str:
    trimmed = re.sub(r"\s+", " ", opportunity_text).strip()
    if len(trimmed) > 2200:
        trimmed = trimmed[:2200] + "..."
    return (
        "Using only the uploaded company documents, list the strongest evidence for whether this company "
        "should bid on the following opportunity. Return concise bullet points with both strengths and gaps.\n\n"
        f"Opportunity:\n{trimmed}"
    )


def build_local_evidence(company_sections: dict[str, list[str]], matched_capabilities: list[str], missing: list[str]) -> list[str]:
    evidence: list[str] = []
    past_performance = company_sections.get("past performance", [])
    if past_performance:
        evidence.append(f"Past performance examples: {past_performance[0]}")
    certifications = company_sections.get("certifications", [])
    if certifications:
        evidence.append(f"Relevant certifications or differentiators: {', '.join(certifications[:3])}")
    if matched_capabilities:
        evidence.append(f"Matched capabilities from the profile: {', '.join(matched_capabilities[:5])}")
    if missing:
        evidence.append(f"Potential coverage gaps: {', '.join(missing[:3])}")
    return evidence


def generate_report_markdown(result: dict) -> str:
    lines = [
        "# BidRadar Qualification Report",
        "",
        f"- Verdict: {result['verdict']}",
        f"- Score: {result['score']}/100",
        f"- Confidence: {result['confidence']}",
        f"- Mode: {result['mode']}",
        f"- Opportunity Source: {result['opportunity_source']}",
        f"- Company Evidence Source: {result['company_source']}",
        "",
        "## Opportunity Facts",
    ]
    for item in result["opportunity_facts"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Top Reasons"])
    for item in result["reasons"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Top Risks"])
    for item in result["risks"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Matched Capabilities"])
    for item in result["matched_capabilities"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Missing Requirements"])
    for item in result["missing_requirements"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Evidence"])
    for item in result["evidence"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Next Action", result["next_action"], "", "## Notes"])
    for item in result["notes"]:
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify a public opportunity for a consulting firm.")
    parser.add_argument("--url", help="Public opportunity URL.")
    parser.add_argument("--file", help="Local file containing opportunity text or markdown.")
    parser.add_argument("--text", help="Inline opportunity text.")
    parser.add_argument("--company-profile", help="Optional local company profile file.")
    parser.add_argument("--report-dir", help="Directory for generated reports.")
    args = parser.parse_args()

    notes: list[str] = []

    company_profile_path = resolve_path(args.company_profile, DEMO_COMPANY)
    company_text = load_text_file(company_profile_path)
    company_meta, company_sections = parse_markdown_sections(company_text)

    opportunity_source = "demo-asset"
    opportunity_text = ""
    if args.text:
        opportunity_source = "text"
        opportunity_text = args.text
    elif args.file:
        opportunity_source = "file"
        opportunity_text = load_text_file(resolve_path(args.file))
    elif args.url and is_url(args.url):
        opportunity_source = "url"
        opportunity_text = fetch_via_apify(args.url, notes) or fetch_direct(args.url, notes) or ""
    else:
        opportunity_text = load_text_file(DEMO_OPPORTUNITY)
        notes.append("Used demo opportunity asset because no URL, file, or inline text was provided.")

    if not opportunity_text.strip():
        opportunity_source = "demo-asset"
        opportunity_text = load_text_file(DEMO_OPPORTUNITY)
        notes.append("Falling back to demo opportunity asset because no live opportunity content was available.")

    opp_meta, opp_sections = parse_markdown_sections(opportunity_text)
    opportunity_lower = opportunity_text.lower()

    services = normalize_list(company_sections.get("services", []))
    past_performance = normalize_list(company_sections.get("past performance", []))
    certifications = normalize_list(company_sections.get("certifications", []))
    preferred_sectors = normalize_list(company_sections.get("preferred sectors", []))
    no_go_criteria = normalize_list(company_sections.get("no-go criteria", []))
    mandatory_reqs = normalize_list(opp_sections.get("mandatory requirements", []))
    preferred_reqs = normalize_list(opp_sections.get("preferred requirements", []))

    service_score, matched_services = score_overlap(services, opportunity_lower, 25)
    past_score, matched_past = score_overlap(past_performance + preferred_sectors, opportunity_lower, 20)

    mandatory_matched = [req for req in mandatory_reqs if text_contains_phrase(company_text.lower(), req) or text_contains_phrase(opportunity_lower, req)]
    mandatory_missing = [req for req in mandatory_reqs if req not in mandatory_matched]
    mandatory_score = 20 if not mandatory_reqs else round(20 * (len(mandatory_matched) / len(mandatory_reqs)))

    value = extract_money_amount(opp_meta.get("estimated value"))
    min_value, max_value = extract_min_max_range(company_meta.get("preferred contract size"))
    if value is None or min_value is None:
        budget_score = 8
    elif min_value <= value <= (max_value or value):
        budget_score = 15
    elif value < min_value:
        budget_score = 4
    else:
        budget_score = 10

    days_left = extract_deadline_days(opp_meta.get("deadline"))
    if days_left is None:
        timeline_score = 7
    elif days_left < 5:
        timeline_score = 2
    elif days_left < 14:
        timeline_score = 6
    else:
        timeline_score = 10

    sector_score, matched_sectors = score_overlap(preferred_sectors, opportunity_lower, 10)

    score = service_score + past_score + mandatory_score + budget_score + timeline_score + sector_score

    no_go_hits = [rule for rule in no_go_criteria if text_contains_phrase(opportunity_lower, rule)]
    delivery_model = opp_meta.get("delivery model", "")
    if "onsite-only" in delivery_model.lower() and "onsite-only delivery" not in no_go_hits:
        no_go_hits.append("onsite-only delivery")

    if no_go_hits:
        verdict = "No-Bid"
    elif mandatory_missing:
        verdict = "Review" if score >= 55 else "No-Bid"
    elif score >= 75:
        verdict = "Bid"
    elif score >= 55:
        verdict = "Review"
    else:
        verdict = "No-Bid"

    if score >= 80:
        confidence = "High"
    elif score >= 60:
        confidence = "Medium"
    else:
        confidence = "Low"

    reasons: list[str] = []
    if matched_services:
        reasons.append(f"Service overlap is strong: {', '.join(matched_services[:4])}.")
    if matched_past:
        reasons.append("The company profile includes relevant past performance or sector experience.")
    if not mandatory_missing:
        reasons.append("The mandatory requirements appear covered by the current company profile.")
    if budget_score >= 10 and value is not None:
        reasons.append(f"The estimated value of ${value:,} is within or near the preferred contract range.")
    if timeline_score >= 8 and days_left is not None:
        reasons.append(f"The deadline is {days_left} days away, which leaves workable response time.")
    if not reasons:
        reasons.append("The opportunity has some alignment, but the evidence is limited.")

    risks: list[str] = []
    if mandatory_missing:
        risks.append(f"Missing or weak evidence for mandatory requirements: {', '.join(mandatory_missing[:3])}.")
    if value is not None and min_value is not None and value < min_value:
        risks.append(f"The estimated value of ${value:,} is below the preferred contract floor of ${min_value:,}.")
    if days_left is not None and days_left < 14:
        risks.append(f"The deadline is in {days_left} days, which compresses response preparation time.")
    if no_go_hits:
        risks.append(f"No-go criteria were triggered: {', '.join(no_go_hits[:3])}.")
    if not risks and verdict == "Review":
        risks.append("The fit is promising, but the available evidence is not yet strong enough for an automatic Bid recommendation.")
    elif not risks:
        risks.append("No major blockers were detected from the available inputs.")

    contextual_text = query_contextual(build_contextual_question(opportunity_text), notes)
    company_source = "contextual" if contextual_text else "local-profile"
    evidence = []
    if contextual_text:
        evidence.append(contextual_text)
    evidence.extend(
        build_local_evidence(
            company_sections,
            matched_services + matched_sectors,
            mandatory_missing,
        )
    )

    next_action = {
        "Bid": "Confirm staffing assumptions and prepare a short capture brief within 24 hours.",
        "Review": "Have the BD lead review the missing requirements and decide whether to pursue a clarification path.",
        "No-Bid": "Log the disqualifying factors and move on to a better-fit opportunity.",
    }[verdict]

    opportunity_facts = [
        f"Title: {opp_meta.get('title', 'Unknown opportunity')}",
        f"Buyer: {opp_meta.get('buyer', 'Unknown buyer')}",
        f"Estimated Value: {opp_meta.get('estimated value', 'Not provided')}",
        f"Deadline: {opp_meta.get('deadline', 'Not provided')}",
        f"Delivery Model: {opp_meta.get('delivery model', 'Not provided')}",
    ]

    report_dir = resolve_path(args.report_dir, REPO_ROOT / "reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    mode = "live" if opportunity_source == "url" and company_source == "contextual" else "partial"
    if opportunity_source == "demo-asset" and company_source == "local-profile":
        mode = "fallback"

    result = {
        "timestamp": timestamp,
        "verdict": verdict,
        "score": score,
        "confidence": confidence,
        "mode": mode,
        "opportunity_source": opportunity_source,
        "company_source": company_source,
        "opportunity_facts": opportunity_facts,
        "reasons": reasons,
        "risks": risks,
        "matched_capabilities": matched_services + matched_sectors,
        "missing_requirements": mandatory_missing or ["None identified from the available inputs."],
        "evidence": evidence or ["No additional evidence was available."],
        "next_action": next_action,
        "notes": notes,
        "sponsor_usage": {
            "apify": any("Apify" in note for note in notes),
            "contextual": company_source == "contextual",
        },
    }

    markdown_report = generate_report_markdown(result)
    markdown_path = report_dir / f"{timestamp}-report.md"
    json_path = report_dir / f"{timestamp}-report.json"
    markdown_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary = {
        "verdict": verdict,
        "score": score,
        "confidence": confidence,
        "mode": mode,
        "top_reason": reasons[0],
        "top_risk": risks[0],
        "report_markdown": str(markdown_path),
        "report_json": str(json_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
