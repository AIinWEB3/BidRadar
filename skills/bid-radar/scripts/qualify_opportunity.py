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
DEMO_SAM_SCAN = SKILL_ROOT / "assets" / "demo-sam-opportunities.json"
DEFAULT_SAM_SCAN_ACTOR = "fortuitous_pirate~sam-gov-scraper"
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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


def load_json_file(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


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


def normalize_list(items: list[str] | None) -> list[str]:
    if not items:
        return []
    return [item.strip() for item in items if item and item.strip()]


def unique_strings(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique


def clean_contextual_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\[\d+\]\(\)", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -\n\t")


def as_sentence(text: str | None) -> str:
    cleaned = clean_contextual_text(text)
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


def parse_csv_argument(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_date(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def is_uuid(value: str | None) -> bool:
    return bool(value and UUID_PATTERN.fullmatch(value.strip()))


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
    normalized = normalize_date(deadline_text)
    if not normalized:
        return None
    try:
        deadline = dt.date.fromisoformat(normalized)
    except ValueError:
        return None
    return (deadline - dt.date.today()).days


def clamp_score(value: object, max_score: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(max_score, score))


def blend_contextual_score(local_score: int, contextual_score: int | None, max_score: int) -> int:
    if contextual_score is None:
        return local_score
    blended = round((local_score + contextual_score) / 2)
    return max(0, min(max_score, max(local_score, blended)))


def append_query_params(url: str, params: dict[str, object]) -> str:
    parsed = urllib.parse.urlparse(url)
    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            serialized = "true" if value else "false"
        else:
            serialized = str(value)
        query_items.append((key, serialized))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query_items)))


def parse_json_object_from_text(text: str | None) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()
    candidates = [cleaned]
    first_brace = cleaned.find("{")
    if first_brace != -1:
        candidates.append(cleaned[first_brace:])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def text_contains_phrase(text: str, phrase: str) -> bool:
    cleaned = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    phrase_clean = " ".join(re.findall(r"[a-z0-9]+", phrase.lower()))
    return bool(phrase_clean) and phrase_clean in cleaned


def score_overlap(candidates: list[str], haystack: str, weight: int) -> tuple[int, list[str]]:
    matched = [candidate for candidate in candidates if text_contains_phrase(haystack, candidate)]
    if not candidates:
        return weight // 2, []
    denominator = max(1, min(len(candidates), 4))
    ratio = len(matched) / denominator
    return round(weight * min(1.0, ratio)), matched


def normalize_actor_id(actor_id: str | None) -> str | None:
    if not actor_id:
        return None
    return actor_id.strip().replace("/", "~")


def extract_apify_items(parsed: object) -> list[dict]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("items", "data", "results", "opportunities"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [parsed]
    return []


def run_apify_actor(actor_id: str, payload: dict, notes: list[str], success_note: str) -> list[dict]:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return []
    endpoint = (
        "https://api.apify.com/v2/acts/"
        f"{urllib.parse.quote(actor_id, safe='')}/run-sync-get-dataset-items?token={urllib.parse.quote(token)}"
    )
    try:
        raw = fetch_text(endpoint, data=payload, headers={"Accept": "application/json"}, timeout=90)
        items = extract_apify_items(json.loads(raw))
        if items:
            notes.append(success_note)
        else:
            notes.append(f"Apify actor {actor_id} returned no usable dataset items.")
        return items
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Apify actor {actor_id} failed: {exc}.")
        return []


def fetch_via_apify_content(url: str, notes: list[str]) -> str | None:
    actor_id = normalize_actor_id(os.getenv("APIFY_CONTENT_ACTOR_ID"))
    if not actor_id or not os.getenv("APIFY_TOKEN"):
        return None
    payload = {
        "startUrls": [{"url": url}],
        "start_urls": [{"url": url}],
        "maxCrawlPages": 1,
        "max_crawl_pages": 1,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    items = run_apify_actor(actor_id, payload, notes, "Used Apify content extraction for live opportunity content.")
    if not items:
        return None
    first = items[0]
    for key in ("text", "markdown", "content", "html", "body", "description"):
        value = first.get(key)
        if isinstance(value, str) and value.strip():
            return strip_html_markup(value) if key in {"html", "body"} else value.strip()
    notes.append("Apify content actor did not return a usable text field.")
    return None


def fetch_direct(url: str, notes: list[str]) -> str | None:
    try:
        text = fetch_text(url, headers={"User-Agent": "BidRadar/0.2"})
        notes.append("Used direct URL fetch for live opportunity content.")
        return strip_html_markup(text)
    except urllib.error.URLError as exc:
        notes.append(f"Direct fetch failed: {exc}.")
        return None


def scan_sam_via_apify(args: argparse.Namespace, notes: list[str]) -> list[dict]:
    actor_id = normalize_actor_id(os.getenv("APIFY_ACTOR_ID") or os.getenv("APIFY_SAM_ACTOR_ID") or DEFAULT_SAM_SCAN_ACTOR)
    if not os.getenv("APIFY_TOKEN"):
        return []

    payload: dict[str, object] = {
        "postedWithinDays": args.posted_within_days,
        "maxOpportunities": args.max_opportunities,
        "includeAttachmentUrls": True,
    }
    if args.keywords:
        payload["keywords"] = args.keywords
    if args.naics_codes:
        payload["naicsCodes"] = parse_csv_argument(args.naics_codes)
    if args.states:
        payload["states"] = parse_csv_argument(args.states)
    if args.set_aside_types:
        payload["setAsideTypes"] = parse_csv_argument(args.set_aside_types)

    return run_apify_actor(actor_id, payload, notes, f"Used Apify SAM scanner actor {actor_id} for opportunity discovery.")


def list_contextual_agents(api_key: str) -> list[dict]:
    raw = fetch_text(
        "https://api.contextual.ai/v1/agents",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        agents = parsed.get("agents")
        if isinstance(agents, list):
            return [item for item in agents if isinstance(item, dict)]
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def resolve_contextual_agent_id(agent_id: str, api_key: str, notes: list[str]) -> str | None:
    cleaned = agent_id.strip()
    if is_uuid(cleaned):
        return cleaned

    try:
        agents = list_contextual_agents(api_key)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Could not resolve Contextual agent ID fragment '{cleaned}': {exc}.")
        return cleaned

    id_matches: list[str] = []
    name_matches: list[str] = []
    for agent in agents:
        candidate_id = agent.get("id") or agent.get("agent_id")
        candidate_name = agent.get("name")
        if isinstance(candidate_id, str):
            normalized_id = candidate_id.strip()
            if normalized_id == cleaned or normalized_id.startswith(cleaned):
                id_matches.append(normalized_id)
        if isinstance(candidate_name, str) and candidate_name.strip() == cleaned and isinstance(candidate_id, str):
            name_matches.append(candidate_id.strip())

    matches = id_matches or name_matches
    unique_matches = sorted(set(match for match in matches if match))
    if len(unique_matches) == 1:
        notes.append(f"Resolved Contextual agent ID fragment '{cleaned}' to the full agent UUID via /v1/agents.")
        return unique_matches[0]
    if len(unique_matches) > 1:
        notes.append(f"Contextual agent ID fragment '{cleaned}' matched multiple agents. Falling back to the local company profile.")
        return None

    notes.append(f"Contextual agent ID fragment '{cleaned}' did not match any available agents. Falling back to the local company profile.")
    return None


def contextual_query_urls(
    query_url: str | None,
    resolved_agent_id: str | None,
    *,
    retrievals_only: bool = False,
    include_retrieval_content_text: bool = False,
) -> list[str]:
    params: dict[str, object] = {}
    if retrievals_only:
        params["retrievals_only"] = True
    if include_retrieval_content_text:
        params["include_retrieval_content_text"] = True

    candidate_urls: list[str] = []

    def add_candidate(url: str | None) -> None:
        if not url:
            return
        final_url = append_query_params(url, params) if params else url
        if final_url not in candidate_urls:
            candidate_urls.append(final_url)

    if query_url:
        add_candidate(query_url)
    if resolved_agent_id:
        add_candidate(f"https://api.contextual.ai/v1/agents/{resolved_agent_id}/query")
        add_candidate(f"https://api.contextual.ai/v1/agents/{resolved_agent_id}/query/acl")

    return candidate_urls


def run_contextual_query(
    prompt: str,
    notes: list[str],
    success_label: str,
    *,
    retrievals_only: bool = False,
    include_retrieval_content_text: bool = False,
) -> dict | None:
    api_key = os.getenv("CONTEXTUAL_API_KEY")
    query_url = os.getenv("CONTEXTUAL_QUERY_URL")
    agent_id = os.getenv("CONTEXTUAL_AGENT_ID")
    if not api_key:
        return None

    resolved_agent_id = resolve_contextual_agent_id(agent_id, api_key, notes) if agent_id else None
    candidate_urls = contextual_query_urls(
        query_url,
        resolved_agent_id,
        retrievals_only=retrievals_only,
        include_retrieval_content_text=include_retrieval_content_text,
    )
    if not candidate_urls:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    parsed: dict | None = None
    last_error: Exception | None = None
    for target_url in candidate_urls:
        try:
            raw = fetch_text(target_url, data=payload, headers=headers, timeout=60)
            parsed_candidate = json.loads(raw)
            if isinstance(parsed_candidate, dict):
                parsed = parsed_candidate
                notes.append(f"{success_label} via {target_url}.")
                break
            last_error = ValueError("Contextual response was not a JSON object.")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if parsed is None:
        notes.append(f"Contextual query failed: {last_error}. Falling back to local company profile.")
        return None

    return parsed


def extract_contextual_retrieval_text(parsed: dict) -> str | None:
    retrieval_contents = parsed.get("retrieval_contents")
    if not isinstance(retrieval_contents, list):
        return None

    evidence_chunks: list[str] = []
    for item in retrieval_contents:
        if not isinstance(item, dict):
            continue
        content_text = item.get("content_text")
        if isinstance(content_text, str):
            cleaned = clean_contextual_text(content_text)
            if cleaned and cleaned not in evidence_chunks:
                evidence_chunks.append(cleaned)
    if evidence_chunks:
        return "\n".join(evidence_chunks[:5])
    return None


def extract_contextual_message_text(parsed: dict) -> str | None:
    message = parsed.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content

    def pull_strings(value: object) -> list[str]:
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
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
    return "\n".join(unique_strings(strings[:5])) if strings else None


def normalize_contextual_dimension(value: object, max_score: int) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}
    matched_capabilities = unique_strings(
        [clean_contextual_text(item) for item in normalize_list(raw.get("matched_capabilities"))]
    )
    evidence = unique_strings([clean_contextual_text(item) for item in normalize_list(raw.get("evidence"))])
    gaps = unique_strings([clean_contextual_text(item) for item in normalize_list(raw.get("gaps"))])
    if not matched_capabilities:
        matched_capabilities = evidence[:3]
    return {
        "score": clamp_score(raw.get("score"), max_score),
        "matched_capabilities": matched_capabilities,
        "evidence": evidence,
        "gaps": gaps,
    }


def build_contextual_assessment_prompt(opportunity_text: str) -> str:
    trimmed = re.sub(r"\s+", " ", opportunity_text).strip()
    if len(trimmed) > 2200:
        trimmed = trimmed[:2200] + "..."
    return (
        "Using only the uploaded company documents, assess company fit for the opportunity below. "
        "Return JSON only using this schema: "
        "{\"service_fit\":{\"score\":0-25,\"matched_capabilities\":[string],\"evidence\":[string],\"gaps\":[string]},"
        "\"past_performance\":{\"score\":0-20,\"evidence\":[string],\"gaps\":[string]},"
        "\"strategic_fit\":{\"score\":0-10,\"evidence\":[string],\"gaps\":[string]},"
        "\"no_go\":[string],\"summary\":string}. "
        "Rules: be conservative; generic capability claims should not receive maximum scores without specific support; "
        "`no_go` must stay empty unless the opportunity text clearly contains a blocker that conflicts with the company documents; "
        "do not invent requirements or past performance; keep each string under 18 words.\n\n"
        f"Opportunity:\n{trimmed}"
    )


def query_contextual_assessment(opportunity_text: str, notes: list[str]) -> dict | None:
    parsed = run_contextual_query(
        build_contextual_assessment_prompt(opportunity_text),
        notes,
        "Used Contextual AI fit assessment",
    )
    if not parsed:
        return None

    raw_assessment = parse_json_object_from_text(extract_contextual_message_text(parsed))
    if not raw_assessment:
        notes.append("Contextual assessment response was not valid JSON. Falling back to deterministic scoring.")
        return None

    service_fit = normalize_contextual_dimension(raw_assessment.get("service_fit"), 25)
    past_performance = normalize_contextual_dimension(raw_assessment.get("past_performance"), 20)
    strategic_fit = normalize_contextual_dimension(raw_assessment.get("strategic_fit"), 10)
    no_go = unique_strings([clean_contextual_text(item) for item in normalize_list(raw_assessment.get("no_go"))])
    summary = clean_contextual_text(str(raw_assessment.get("summary") or ""))

    if not any(
        [
            service_fit["score"],
            past_performance["score"],
            strategic_fit["score"],
            service_fit["evidence"],
            past_performance["evidence"],
            strategic_fit["evidence"],
            no_go,
            summary,
        ]
    ):
        notes.append("Contextual assessment returned no usable scoring details. Falling back to deterministic scoring.")
        return None

    return {
        "service_fit": service_fit,
        "past_performance": past_performance,
        "strategic_fit": strategic_fit,
        "no_go": no_go,
        "summary": summary,
    }


def query_contextual(question: str, notes: list[str]) -> str | None:
    parsed = run_contextual_query(
        question,
        notes,
        "Used Contextual for grounded company evidence",
        retrievals_only=True,
        include_retrieval_content_text=True,
    )
    if not parsed:
        return None

    retrieval_text = extract_contextual_retrieval_text(parsed)
    if retrieval_text:
        return retrieval_text

    fallback_text = extract_contextual_message_text(parsed)
    return clean_contextual_text(fallback_text)


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


def build_opportunity_from_scan_item(item: dict) -> tuple[str, dict[str, str], dict[str, list[str]]]:
    attachments = [attachment for attachment in item.get("attachments", []) if isinstance(attachment, dict)]
    attachment_lines = []
    for attachment in attachments[:5]:
        filename = attachment.get("filename", "Unnamed attachment")
        download_url = attachment.get("downloadUrl", "")
        line = filename if not download_url else f"{filename} ({download_url})"
        attachment_lines.append(line)

    place = item.get("placeOfPerformance") or {}
    city = place.get("city") if isinstance(place, dict) else None
    state = place.get("stateCode") if isinstance(place, dict) else None
    location = ", ".join(part for part in [city, state] if part)

    buyer = " / ".join(
        part for part in [item.get("agencyName"), item.get("officeName")] if isinstance(part, str) and part.strip()
    )

    opp_meta = {
        "title": item.get("title") or item.get("solicitationNumber") or item.get("opportunityId") or "Unknown opportunity",
        "buyer": buyer or "Unknown buyer",
        "estimated value": str(item.get("estimatedValue") or item.get("awardAmount") or "Not provided"),
        "deadline": normalize_date(item.get("responseDeadline")) or "Not provided",
        "delivery model": str(item.get("deliveryModel") or "Not provided"),
        "notice id": str(item.get("solicitationNumber") or item.get("opportunityId") or "Not provided"),
        "naics code": str(item.get("naicsCode") or "Not provided"),
        "set aside": str(item.get("setAsideType") or "Not provided"),
        "source link": str(item.get("samGovLink") or "Not provided"),
        "place of performance": location or "Not provided",
    }

    sections = {
        "mandatory requirements": normalize_list(item.get("mandatoryRequirements")),
        "preferred requirements": normalize_list(item.get("preferredRequirements")),
        "attachments": attachment_lines,
    }

    description = str(item.get("description") or "")
    contacts = [contact for contact in item.get("contacts", []) if isinstance(contact, dict)]
    contact_lines = [
        " / ".join(part for part in [contact.get("name"), contact.get("email"), contact.get("phone")] if part) for contact in contacts
    ]
    text_parts = [
        f"Title: {opp_meta['title']}",
        f"Description: {description}",
        f"NAICS: {opp_meta['naics code']}",
        f"Set Aside: {opp_meta['set aside']}",
        f"Buyer: {opp_meta['buyer']}",
        f"Place of Performance: {opp_meta['place of performance']}",
        f"Attachments: {'; '.join(attachment_lines) if attachment_lines else 'None listed'}",
        f"Contacts: {'; '.join(contact_lines) if contact_lines else 'None listed'}",
    ]
    return "\n".join(text_parts), opp_meta, sections


def build_opportunity_facts(opp_meta: dict[str, str], opp_sections: dict[str, list[str]]) -> list[str]:
    facts = [
        f"Title: {opp_meta.get('title', 'Unknown opportunity')}",
        f"Buyer: {opp_meta.get('buyer', 'Unknown buyer')}",
        f"Estimated Value: {opp_meta.get('estimated value', 'Not provided')}",
        f"Deadline: {opp_meta.get('deadline', 'Not provided')}",
        f"Delivery Model: {opp_meta.get('delivery model', 'Not provided')}",
    ]
    if opp_meta.get("notice id"):
        facts.append(f"Notice ID: {opp_meta['notice id']}")
    if opp_meta.get("naics code"):
        facts.append(f"NAICS Code: {opp_meta['naics code']}")
    if opp_meta.get("set aside"):
        facts.append(f"Set Aside: {opp_meta['set aside']}")
    if opp_meta.get("place of performance"):
        facts.append(f"Place of Performance: {opp_meta['place of performance']}")
    attachments = normalize_list(opp_sections.get("attachments"))
    if attachments:
        facts.append(f"Attachments: {len(attachments)}")
    if opp_meta.get("source link"):
        facts.append(f"Source Link: {opp_meta['source link']}")
    return facts


def evaluate_opportunity(
    opportunity_text: str,
    opp_meta: dict[str, str],
    opp_sections: dict[str, list[str]],
    company_text: str,
    company_meta: dict[str, str],
    company_sections: dict[str, list[str]],
    notes: list[str],
    opportunity_source: str,
    use_contextual: bool,
) -> dict:
    opportunity_lower = opportunity_text.lower()
    services = normalize_list(company_sections.get("services"))
    past_performance = normalize_list(company_sections.get("past performance"))
    preferred_sectors = normalize_list(company_sections.get("preferred sectors"))
    no_go_criteria = normalize_list(company_sections.get("no-go criteria"))
    mandatory_reqs = normalize_list(opp_sections.get("mandatory requirements"))
    attachments = normalize_list(opp_sections.get("attachments"))

    contextual_assessment = query_contextual_assessment(opportunity_text, notes) if use_contextual else None

    local_service_score, matched_services = score_overlap(services, opportunity_lower, 25)
    local_past_score, matched_past = score_overlap(past_performance + preferred_sectors, opportunity_lower, 20)
    local_sector_score, matched_sectors = score_overlap(preferred_sectors, opportunity_lower, 10)

    contextual_service = contextual_assessment["service_fit"] if contextual_assessment else None
    contextual_past = contextual_assessment["past_performance"] if contextual_assessment else None
    contextual_strategic = contextual_assessment["strategic_fit"] if contextual_assessment else None

    service_score = blend_contextual_score(
        local_service_score,
        contextual_service["score"] if contextual_service else None,
        25,
    )
    past_score = blend_contextual_score(
        local_past_score,
        contextual_past["score"] if contextual_past else None,
        20,
    )
    sector_score = blend_contextual_score(
        local_sector_score,
        contextual_strategic["score"] if contextual_strategic else None,
        10,
    )

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

    score = service_score + past_score + mandatory_score + budget_score + timeline_score + sector_score

    no_go_hits = [rule for rule in no_go_criteria if text_contains_phrase(opportunity_lower, rule)]
    if contextual_assessment:
        no_go_hits = unique_strings(no_go_hits + contextual_assessment["no_go"])
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

    attachment_review_needed = opportunity_source.startswith("sam-scan") and attachments and not mandatory_reqs
    if attachment_review_needed and verdict == "Bid":
        verdict = "Review"

    if score >= 80:
        confidence = "High"
    elif score >= 60:
        confidence = "Medium"
    else:
        confidence = "Low"

    contextual_matched_capabilities = []
    if contextual_service:
        contextual_matched_capabilities = normalize_list(contextual_service.get("matched_capabilities"))
    matched_capabilities = unique_strings(matched_services + matched_sectors + contextual_matched_capabilities)

    reasons: list[str] = []
    if matched_services:
        reasons.append(f"Service overlap is strong: {', '.join(matched_services[:4])}.")
    elif contextual_matched_capabilities:
        reasons.append(f"Contextual evidence supports technical fit: {', '.join(contextual_matched_capabilities[:3])}.")
    if matched_past:
        reasons.append("The company profile includes relevant past performance or sector experience.")
    elif contextual_past and contextual_past["evidence"]:
        reasons.append(f"Contextual evidence suggests related delivery experience: {as_sentence(contextual_past['evidence'][0])}")
    if not mandatory_missing and mandatory_reqs:
        reasons.append("The mandatory requirements appear covered by the current company profile.")
    if contextual_strategic and local_sector_score == 0 and contextual_strategic["evidence"]:
        reasons.append(f"Contextual evidence supports strategic fit: {as_sentence(contextual_strategic['evidence'][0])}")
    if budget_score >= 10 and value is not None:
        reasons.append(f"The estimated value of ${value:,} is within or near the preferred contract range.")
    if timeline_score >= 8 and days_left is not None:
        reasons.append(f"The deadline is {days_left} days away, which leaves workable response time.")
    if attachments:
        reasons.append(f"The listing includes {len(attachments)} downloadable attachment(s) for deeper review.")
    reasons = unique_strings([reason for reason in reasons if reason])
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
    if contextual_service and contextual_service["gaps"]:
        risks.append(f"Contextual evidence gap: {as_sentence(contextual_service['gaps'][0])}")
    if contextual_past and contextual_past["gaps"]:
        risks.append(f"Contextual evidence gap: {as_sentence(contextual_past['gaps'][0])}")
    if attachment_review_needed:
        risks.append("Detailed requirements appear to live in the attachment package and still need review before a firm Bid decision.")
    risks = unique_strings([risk for risk in risks if risk])
    if not risks and verdict == "Review":
        risks.append("The fit is promising, but the available evidence is not yet strong enough for an automatic Bid recommendation.")
    elif not risks:
        risks.append("No major blockers were detected from the available inputs.")

    evidence: list[str] = []
    company_source = "local-profile"
    contextual_text = None
    if contextual_assessment:
        company_source = "contextual"
        if contextual_assessment["summary"]:
            evidence.append(f"Contextual fit summary: {contextual_assessment['summary']}")
        for item in contextual_service["evidence"][:2] if contextual_service else []:
            evidence.append(f"Contextual service evidence: {clean_contextual_text(item)}")
        for item in contextual_past["evidence"][:2] if contextual_past else []:
            evidence.append(f"Contextual past-performance evidence: {clean_contextual_text(item)}")
        for item in contextual_strategic["evidence"][:1] if contextual_strategic else []:
            evidence.append(f"Contextual strategic-fit evidence: {clean_contextual_text(item)}")
    elif use_contextual:
        contextual_text = query_contextual(build_contextual_question(opportunity_text), notes)
        if contextual_text:
            company_source = "contextual"
            evidence.append(contextual_text)
    evidence.extend(build_local_evidence(company_sections, matched_capabilities, mandatory_missing))

    if attachments:
        evidence.append(f"Attachment package available for download: {attachments[0]}")
    evidence = unique_strings([item for item in evidence if item])

    if attachment_review_needed:
        next_action = "Open the leading attachment package and confirm hard requirements before moving from Review to Bid."
    else:
        next_action = {
            "Bid": "Confirm staffing assumptions and prepare a short capture brief within 24 hours.",
            "Review": "Have the BD lead review the missing requirements and decide whether to pursue a clarification path.",
            "No-Bid": "Log the disqualifying factors and move on to a better-fit opportunity.",
        }[verdict]

    return {
        "verdict": verdict,
        "score": score,
        "confidence": confidence,
        "scoring_method": "deterministic+contextual-ai" if contextual_assessment else "deterministic",
        "score_breakdown": {
            "service_fit": service_score,
            "past_performance": past_score,
            "mandatory_requirements": mandatory_score,
            "budget": budget_score,
            "timeline": timeline_score,
            "strategic_fit": sector_score,
        },
        "opportunity_source": opportunity_source,
        "company_source": company_source,
        "opportunity_facts": build_opportunity_facts(opp_meta, opp_sections),
        "reasons": reasons,
        "risks": risks,
        "matched_capabilities": matched_capabilities,
        "missing_requirements": mandatory_missing or ["None identified from the available inputs."],
        "evidence": evidence or ["No additional evidence was available."],
        "next_action": next_action,
        "notes": notes,
        "sponsor_usage": {
            "apify": any(note.startswith("Used Apify") for note in notes),
            "contextual": company_source == "contextual",
            "contextual_scoring": bool(contextual_assessment),
        },
    }


def build_scan_shortlist(candidates: list[dict], limit: int = 25) -> list[dict]:
    shortlist = []
    for rank, candidate in enumerate(candidates[:limit], start=1):
        opp_meta = candidate["opp_meta"]
        shortlist.append(
            {
                "rank": rank,
                "title": opp_meta.get("title", "Unknown opportunity"),
                "verdict": candidate["verdict"],
                "score": candidate["score"],
                "deadline": opp_meta.get("deadline", "Not provided"),
                "buyer": opp_meta.get("buyer", "Unknown buyer"),
                "link": opp_meta.get("source link", "Not provided"),
            }
        )
    return shortlist


def filter_scan_items(items: list[dict], args: argparse.Namespace) -> list[dict]:
    filtered = items

    if args.keywords:
        keyword_tokens = [token for token in re.findall(r"[a-z0-9]+", args.keywords.lower()) if token]
        if keyword_tokens:
            filtered = [
                item
                for item in filtered
                if all(
                    token in " ".join(
                        re.findall(r"[a-z0-9]+", f"{item.get('title', '')} {item.get('description', '')}".lower())
                    )
                    for token in keyword_tokens
                )
            ]

    states = {state.upper() for state in parse_csv_argument(args.states)}
    if states:
        filtered = [
            item
            for item in filtered
            if isinstance(item.get("placeOfPerformance"), dict)
            and str(item["placeOfPerformance"].get("stateCode", "")).upper() in states
        ]

    naics_codes = {code for code in parse_csv_argument(args.naics_codes)}
    if naics_codes:
        filtered = [item for item in filtered if str(item.get("naicsCode", "")) in naics_codes]

    set_aside_types = {value.lower() for value in parse_csv_argument(args.set_aside_types)}
    if set_aside_types:
        filtered = [item for item in filtered if str(item.get("setAsideType", "")).lower() in set_aside_types]

    return filtered


def generate_report_markdown(result: dict) -> str:
    lines = [
        "# BidRadar Qualification Report",
        "",
        f"- Verdict: {result['verdict']}",
        f"- Score: {result['score']}/100",
        f"- Confidence: {result['confidence']}",
        f"- Scoring Method: {result.get('scoring_method', 'deterministic')}",
        f"- Mode: {result['mode']}",
        f"- Opportunity Source: {result['opportunity_source']}",
        f"- Company Evidence Source: {result['company_source']}",
        "",
        "## Opportunity Facts",
    ]
    for item in result["opportunity_facts"]:
        lines.append(f"- {item}")
    if result.get("score_breakdown"):
        lines.extend(["", "## Score Breakdown"])
        for label, value in result["score_breakdown"].items():
            lines.append(f"- {label.replace('_', ' ').title()}: {value}")
    if result.get("scan_shortlist"):
        lines.extend(["", "## Scan Shortlist"])
        for item in result["scan_shortlist"]:
            lines.append(
                f"- #{item['rank']} {item['title']} — {item['verdict']} ({item['score']}/100), "
                f"deadline {item['deadline']}, buyer {item['buyer']}, link {item['link']}"
            )
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


def load_company_profile(path: Path) -> tuple[str, dict[str, str], dict[str, list[str]]]:
    company_text = load_text_file(path)
    company_meta, company_sections = parse_markdown_sections(company_text)
    return company_text, company_meta, company_sections


def apply_company_name_override(company_text: str, company_name: str | None) -> str:
    if not company_name or not str(company_name).strip():
        return company_text
    name = str(company_name).strip()
    lines = company_text.splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().lower().startswith("name:"):
            out.append(f"Name: {name}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if lines and lines[0].startswith("#"):
            return lines[0] + "\n\nName: " + name + "\n\n" + "\n".join(lines[1:])
        return f"Name: {name}\n\n{company_text}"
    return "\n".join(out)


def compute_qualification_mode(result: dict) -> str:
    mode = "live" if result["sponsor_usage"]["apify"] and result["company_source"] == "contextual" else "partial"
    if result["opportunity_source"] in {"demo-asset", "sam-scan-demo"} and result["company_source"] == "local-profile":
        mode = "fallback"
    return mode


def select_scan_candidate(candidates: list[dict], requested_index: int) -> dict:
    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
    if 0 <= requested_index < len(ranked):
        return ranked[requested_index]
    return ranked[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan and qualify public opportunities for a consulting firm.")
    parser.add_argument("--scan-sam", action="store_true", help="Scan SAM-style opportunities through the Apify actor.")
    parser.add_argument("--keywords", help="Search keywords for SAM scan mode.")
    parser.add_argument("--naics-codes", help="Comma-separated NAICS codes for SAM scan mode.")
    parser.add_argument("--states", help="Comma-separated state codes for SAM scan mode.")
    parser.add_argument("--set-aside-types", help="Comma-separated set-aside types for SAM scan mode.")
    parser.add_argument("--posted-within-days", type=int, default=30, help="Posted-within-days filter for SAM scan mode.")
    parser.add_argument("--max-opportunities", type=int, default=10, help="Maximum opportunities to scan in SAM mode.")
    parser.add_argument("--opportunity-index", type=int, default=0, help="Ranked shortlist index to fully evaluate in SAM scan mode.")
    parser.add_argument("--url", help="Public opportunity URL.")
    parser.add_argument("--file", help="Local file containing opportunity text or markdown.")
    parser.add_argument("--text", help="Inline opportunity text.")
    parser.add_argument("--company-profile", help="Optional local company profile file.")
    parser.add_argument("--company-name", help="Override the Name field in the company profile without editing the file.")
    parser.add_argument(
        "--evaluate-all",
        action="store_true",
        help="With --scan-sam, run full contextual qualification for each shortlisted opportunity and emit ranked reports.",
    )
    parser.add_argument("--report-dir", help="Directory for generated reports.")
    args = parser.parse_args()

    notes: list[str] = []
    company_profile_path = resolve_path(args.company_profile, DEMO_COMPANY)
    company_text, company_meta, company_sections = load_company_profile(company_profile_path)
    if args.company_name:
        company_text = apply_company_name_override(company_text, args.company_name)
        company_meta, company_sections = parse_markdown_sections(company_text)

    opportunity_source = "demo-asset"
    scan_shortlist: list[dict] = []
    batch_mode = False
    batch_pairs: list[tuple[dict, dict]] | None = None

    if args.scan_sam:
        opportunity_source = "sam-scan"
        scan_items = scan_sam_via_apify(args, notes)
        if not scan_items:
            scan_items = load_json_file(DEMO_SAM_SCAN)
            opportunity_source = "sam-scan-demo"
            notes.append("Used demo SAM scan results because live Apify scanning was unavailable.")
        if not isinstance(scan_items, list) or not scan_items:
            raise SystemExit("No SAM opportunities were available to evaluate.")
        filtered_scan_items = filter_scan_items(scan_items, args)
        if filtered_scan_items:
            scan_items = filtered_scan_items
        elif args.keywords or args.states or args.naics_codes or args.set_aside_types:
            notes.append("No scan results matched the requested filters exactly; using the unfiltered opportunity set instead.")

        # Cap per-run work: preview + optional full eval each row (align with --max-opportunities upper bound).
        preview_limit = max(1, min(args.max_opportunities, 25))
        preview_candidates: list[dict] = []
        for item in scan_items[:preview_limit]:
            if not isinstance(item, dict):
                continue
            candidate_text, candidate_meta, candidate_sections = build_opportunity_from_scan_item(item)
            preview_result = evaluate_opportunity(
                candidate_text,
                candidate_meta,
                candidate_sections,
                company_text,
                company_meta,
                company_sections,
                notes=[],
                opportunity_source=opportunity_source,
                use_contextual=False,
            )
            preview_candidates.append(
                {
                    "item": item,
                    "opportunity_text": candidate_text,
                    "opp_meta": candidate_meta,
                    "opp_sections": candidate_sections,
                    "verdict": preview_result["verdict"],
                    "score": preview_result["score"],
                }
            )

        if not preview_candidates:
            raise SystemExit("No SAM opportunities could be normalized into preview candidates.")

        scan_shortlist = build_scan_shortlist(sorted(preview_candidates, key=lambda item: item["score"], reverse=True))

        if args.evaluate_all:
            batch_mode = True
            ranked_preview = sorted(preview_candidates, key=lambda item: item["score"], reverse=True)
            batch_results: list[dict] = []
            base_notes = list(notes)
            for i, selected in enumerate(ranked_preview):
                item_notes = base_notes + [
                    f"Full qualification {i + 1}/{len(ranked_preview)}: "
                    f"{selected['opp_meta'].get('title', 'Unknown opportunity')}."
                ]
                res = evaluate_opportunity(
                    selected["opportunity_text"],
                    selected["opp_meta"],
                    selected["opp_sections"],
                    company_text,
                    company_meta,
                    company_sections,
                    notes=item_notes,
                    opportunity_source=opportunity_source,
                    use_contextual=True,
                )
                batch_results.append(res)
            pairs = list(zip(ranked_preview, batch_results))
            pairs.sort(key=lambda pair: pair[1]["score"], reverse=True)
            batch_pairs = pairs
            reranked_candidates = [
                {
                    "opp_meta": prev["opp_meta"],
                    "verdict": full["verdict"],
                    "score": full["score"],
                }
                for prev, full in pairs
            ]
            scan_shortlist = build_scan_shortlist(reranked_candidates)
            for _, res in pairs:
                res["scan_shortlist"] = scan_shortlist
            result = pairs[0][1]
            notes.append(f"Scanned {len(scan_items)} SAM opportunities; full qualification batch size {len(pairs)}.")
        else:
            selected = select_scan_candidate(preview_candidates, args.opportunity_index)
            notes.append(
                f"Scanned {len(scan_items)} SAM opportunities and selected '{selected['opp_meta'].get('title', 'Unknown opportunity')}' for full qualification."
            )

            result = evaluate_opportunity(
                selected["opportunity_text"],
                selected["opp_meta"],
                selected["opp_sections"],
                company_text,
                company_meta,
                company_sections,
                notes=notes,
                opportunity_source=opportunity_source,
                use_contextual=True,
            )
            result["scan_shortlist"] = scan_shortlist
    else:
        opportunity_text = ""
        opp_meta: dict[str, str]
        opp_sections: dict[str, list[str]]

        if args.text:
            opportunity_source = "text"
            opportunity_text = args.text
            opp_meta, opp_sections = parse_markdown_sections(opportunity_text)
        elif args.file:
            opportunity_source = "file"
            opportunity_text = load_text_file(resolve_path(args.file))
            opp_meta, opp_sections = parse_markdown_sections(opportunity_text)
        elif args.url and is_url(args.url):
            opportunity_source = "url"
            opportunity_text = fetch_via_apify_content(args.url, notes) or fetch_direct(args.url, notes) or ""
            opp_meta = {
                "title": "Live opportunity page",
                "buyer": "Unknown buyer",
                "estimated value": "Not provided",
                "deadline": "Not provided",
                "delivery model": "Not provided",
                "notice id": "Not provided",
                "naics code": "Not provided",
                "set aside": "Not provided",
                "source link": args.url,
                "place of performance": "Not provided",
            }
            opp_sections = {"mandatory requirements": [], "preferred requirements": [], "attachments": []}
        else:
            opportunity_text = load_text_file(DEMO_OPPORTUNITY)
            opp_meta, opp_sections = parse_markdown_sections(opportunity_text)
            notes.append("Used demo opportunity asset because no URL, file, or inline text was provided.")

        if not opportunity_text.strip():
            opportunity_source = "demo-asset"
            opportunity_text = load_text_file(DEMO_OPPORTUNITY)
            opp_meta, opp_sections = parse_markdown_sections(opportunity_text)
            notes.append("Falling back to demo opportunity asset because no live opportunity content was available.")

        result = evaluate_opportunity(
            opportunity_text,
            opp_meta,
            opp_sections,
            company_text,
            company_meta,
            company_sections,
            notes=notes,
            opportunity_source=opportunity_source,
            use_contextual=True,
        )

    report_dir = resolve_path(args.report_dir, REPO_ROOT / "reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    base_timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    if batch_mode and batch_pairs:
        summaries: list[dict] = []
        for rank_index, (_prev, res) in enumerate(batch_pairs):
            ts = f"{base_timestamp}-{rank_index:02d}"
            res["timestamp"] = ts
            res["mode"] = compute_qualification_mode(res)
            markdown_path = report_dir / f"{ts}-report.md"
            json_path = report_dir / f"{ts}-report.json"
            markdown_path.write_text(generate_report_markdown(res), encoding="utf-8")
            json_path.write_text(json.dumps(res, indent=2), encoding="utf-8")
            title = "Unknown opportunity"
            if res.get("opportunity_facts"):
                title = res["opportunity_facts"][0].replace("Title: ", "", 1)
            summaries.append(
                {
                    "rank": rank_index + 1,
                    "verdict": res["verdict"],
                    "score": res["score"],
                    "confidence": res["confidence"],
                    "mode": res["mode"],
                    "top_reason": res["reasons"][0],
                    "top_risk": res["risks"][0],
                    "report_markdown": str(markdown_path),
                    "report_json": str(json_path),
                    "title": title,
                }
            )
        batch_payload: dict = {"batch": True, "items": summaries, "scan_shortlist": scan_shortlist}
        if scan_shortlist:
            batch_payload["shortlist_count"] = len(scan_shortlist)
        print(json.dumps(batch_payload, indent=2))
        return 0

    mode = compute_qualification_mode(result)

    result["timestamp"] = base_timestamp
    result["mode"] = mode

    markdown_report = generate_report_markdown(result)
    markdown_path = report_dir / f"{base_timestamp}-report.md"
    json_path = report_dir / f"{base_timestamp}-report.json"
    markdown_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary = {
        "verdict": result["verdict"],
        "score": result["score"],
        "confidence": result["confidence"],
        "mode": mode,
        "top_reason": result["reasons"][0],
        "top_risk": result["risks"][0],
        "report_markdown": str(markdown_path),
        "report_json": str(json_path),
    }
    if result.get("scan_shortlist"):
        summary["shortlist_count"] = len(result["scan_shortlist"])
        summary["selected_opportunity"] = result["opportunity_facts"][0].replace("Title: ", "", 1)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
