const statusSummary = document.querySelector("#status-summary");
const recentRuns = document.querySelector("#recent-runs");
const resultCaption = document.querySelector("#result-caption");
const resultSummary = document.querySelector("#result-summary");
const resultDetail = document.querySelector("#result-detail");
const tabs = document.querySelectorAll(".tab");
const workflows = document.querySelectorAll(".workflow");
const qualifyForm = document.querySelector("#qualify-form");
const scanForm = document.querySelector("#scan-form");
const demoRunButton = document.querySelector("#demo-run-button");
const scanEvaluateAll = document.querySelector("#scan-evaluate-all");
const scanSingleWrap = document.querySelector("#scan-single-wrap");

const state = {
  activeView: "scan",
};

const LOCAL_API_ORIGIN = "http://127.0.0.1:3008";
const apiOrigins = buildApiOrigins();

function buildApiOrigins() {
  const currentOrigin = window.location.origin && window.location.origin !== "null" ? window.location.origin : "";
  const origins = [];
  if (currentOrigin) {
    origins.push(currentOrigin);
  }
  if (!origins.includes(LOCAL_API_ORIGIN)) {
    origins.push(LOCAL_API_ORIGIN);
  }
  return origins;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatFact(item) {
  if (typeof item !== "string" || !item.includes(": ")) {
    return {
      label: "Fact",
      value: String(item ?? ""),
    };
  }
  const [label, ...rest] = item.split(": ");
  return {
    label,
    value: rest.join(": "),
  };
}

function verdictTone(verdict) {
  switch (verdict) {
    case "Bid":
      return "good";
    case "Review":
      return "warn";
    default:
      return "bad";
  }
}

function metricCard(label, value, tone = "neutral") {
  return `
    <article class="metric-card ${tone}">
      <span class="metric-label">${escapeHtml(label)}</span>
      <strong class="metric-value">${escapeHtml(value)}</strong>
    </article>
  `;
}

function multilineHtml(value) {
  return escapeHtml(value).replaceAll("\n", "<br />");
}

function listItemHtml(item) {
  const text = String(item ?? "");
  if (text.length <= 260) {
    return `<li>${multilineHtml(text)}</li>`;
  }

  const preview = `${text.slice(0, 240).trim()}...`;
  return `
    <li>
      <details class="expandable">
        <summary>${escapeHtml(preview)}</summary>
        <div class="expandable-copy">${multilineHtml(text)}</div>
      </details>
    </li>
  `;
}

const LOCAL_EVIDENCE_PREFIXES = [
  "Past performance examples:",
  "Relevant certifications",
  "Matched capabilities from the profile:",
  "Potential coverage gaps:",
  "Attachment package available",
];

function isLocalEvidenceLine(line) {
  return LOCAL_EVIDENCE_PREFIXES.some((p) => String(line).startsWith(p));
}

/** Lines in `report.evidence` that came from Contextual.ai (tagged or grounded blob). */
function extractContextualEvidenceLines(report) {
  if (!report?.evidence?.length) {
    return [];
  }
  const ev = report.evidence.filter((line) => String(line).trim() && !/^No additional evidence was available/i.test(String(line)));
  const structured = ev.filter((line) =>
    /Contextual (fit summary|service evidence|past-performance|strategic-fit):/i.test(String(line)),
  );
  if (structured.length) {
    return structured;
  }
  if (report.company_source !== "contextual") {
    return [];
  }
  if (report.sponsor_usage?.contextual_scoring) {
    return [];
  }
  return ev.filter((line) => !isLocalEvidenceLine(line));
}

function evidenceExcludingContextual(report) {
  const ctxSet = new Set(extractContextualEvidenceLines(report));
  return (report.evidence || []).filter((line) => !ctxSet.has(line));
}

function contextualModeLabel(report) {
  if (!report) {
    return { badge: "—", detail: "" };
  }
  if (report.company_source !== "contextual") {
    return {
      badge: "Not used",
      detail:
        "This qualification used only the local company markdown profile. The skill calls Contextual.ai only when `use_contextual` is on and the API returns grounded content (full SAM evaluate steps, not the fast scan preview).",
    };
  }
  if (report.sponsor_usage?.contextual_scoring) {
    return {
      badge: "Structured scoring",
      detail:
        "The skill POSTs to Contextual.ai (<code>https://api.contextual.ai/v1/agents/{agent_id}/query</code>) with a JSON-style fit rubric. Returned dimensions (service fit, past performance, strategic fit) are normalized and blended with deterministic keyword overlap scores in <code>qualify_opportunity.py</code> (<code>blend_contextual_score</code>).",
    };
  }
  return {
    badge: "Grounded retrieval",
    detail:
      "The skill queried your indexed company corpus via the same agent query endpoint and appended retrieval-grounded text to evidence (structured JSON assessment was not parsed for this run).",
  };
}

function renderContextualPanel(report, options = {}) {
  const { batchSummary } = options;
  const mode = contextualModeLabel(report);
  const lines = report ? extractContextualEvidenceLines(report) : [];

  let headline = "Contextual.ai · this run";
  let badge = mode.badge;
  let detail = mode.detail;

  if (batchSummary) {
    headline = "Contextual.ai · batch summary";
    const { total, used, structured } = batchSummary;
    badge =
      used === 0
        ? "Not used on full evaluations"
        : used === total
          ? `Used on all ${total}`
          : `Used on ${used} of ${total}`;
    detail =
      used === 0
        ? "None of the full qualifications received grounded company evidence from Contextual (local profile only)."
        : `Full qualification steps called the API where configured. ${structured} of ${used} run(s) used structured JSON scoring; others used retrieval-grounded text. Open each notice below for per-row evidence.`;
  }

  const evidenceBlock =
    lines.length > 0
      ? `
      <div class="contextual-evidence">
        <span class="contextual-evidence-label">Evidence tied to Contextual</span>
        <ul>
          ${lines.map((item) => listItemHtml(item)).join("")}
        </ul>
      </div>
    `
      : report && report.company_source === "contextual" && !batchSummary
        ? `<p class="contextual-note">See the general evidence list for retrieval text if lines are not prefixed with “Contextual …”.</p>`
        : "";

  const pillTone = batchSummary
    ? batchSummary.used > 0
      ? "good"
      : "muted"
    : report?.company_source === "contextual"
      ? "good"
      : "muted";

  return `
    <section class="detail-block contextual-panel" aria-labelledby="contextual-heading">
      <div class="contextual-panel-head">
        <h3 id="contextual-heading">${escapeHtml(headline)}</h3>
        <span class="inline-pill ${pillTone}">${escapeHtml(badge)}</span>
      </div>
      <p class="contextual-method">
        <strong>How:</strong> ${detail}
      </p>
      <p class="contextual-api-note">
        Configure <code>CONTEXTUAL_API_KEY</code> and <code>CONTEXTUAL_AGENT_ID</code> in the server environment (see <code>.env.bidradar.sh</code>). The Python script resolves non-UUID agent ids via <code>GET /v1/agents</code> when needed.
      </p>
      ${evidenceBlock}
    </section>
  `;
}

function listBlock(title, items) {
  if (!items?.length) {
    return "";
  }
  const renderedItems = items
    .map((item) => listItemHtml(item))
    .join("");
  return `
    <section class="detail-block">
      <h3>${escapeHtml(title)}</h3>
      <ul>${renderedItems}</ul>
    </section>
  `;
}

function renderFacts(facts) {
  if (!facts?.length) {
    return "";
  }
  const cards = facts
    .map((item) => {
      const fact = formatFact(item);
      return `
        <article class="fact-card">
          <span>${escapeHtml(fact.label)}</span>
          <strong>${escapeHtml(fact.value)}</strong>
        </article>
      `;
    })
    .join("");
  return `
    <section class="detail-block">
      <h3>Opportunity facts</h3>
      <div class="facts-grid">${cards}</div>
    </section>
  `;
}

function renderShortlist(shortlist) {
  if (!shortlist?.length) {
    return "";
  }
  const rows = shortlist
    .map(
      (item, idx) => `
        <tr class="${idx === 0 ? "leaderboard-row-top" : ""}" data-report-index="${idx}">
          <td>${escapeHtml(item.rank)}</td>
          <td>${escapeHtml(item.title)}</td>
          <td><span class="inline-pill ${verdictTone(item.verdict)}">${escapeHtml(item.verdict)}</span></td>
          <td>${escapeHtml(item.score)}</td>
          <td>${escapeHtml(item.deadline)}</td>
          <td>${escapeHtml(item.buyer)}</td>
        </tr>
      `,
    )
    .join("");

  return `
    <section class="detail-block leaderboard-wrap">
      <h3>Leaderboard (ranked by score)</h3>
      <div class="table-wrap leaderboard">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Opportunity</th>
              <th>Verdict</th>
              <th>Score</th>
              <th>Deadline</th>
              <th>Buyer</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <p class="leaderboard-hint">Click a row to open the matching report below.</p>
    </section>
  `;
}

function renderReportBody(report, options = {}) {
  const showShortlist = options.showShortlist !== false;
  const evidenceItems = options.excludeContextualFromEvidence ? evidenceExcludingContextual(report) : report.evidence;
  const contextualStripped =
    options.excludeContextualFromEvidence && extractContextualEvidenceLines(report).length > 0;
  const evidenceTitle = contextualStripped ? "Other evidence" : "Evidence";
  return `
    ${renderFacts(report.opportunity_facts)}
    ${showShortlist ? renderShortlist(report.scan_shortlist) : ""}
    ${listBlock("Top reasons", report.reasons)}
    ${listBlock("Top risks", report.risks)}
    ${listBlock("Matched capabilities", report.matched_capabilities)}
    ${listBlock("Missing requirements", report.missing_requirements)}
    ${listBlock(evidenceTitle, evidenceItems)}
    <section class="detail-block">
      <h3>Next action</h3>
      <p>${escapeHtml(report.next_action)}</p>
    </section>
    ${listBlock("Runtime notes", report.notes)}
  `;
}

function bindLeaderboardClicks() {
  const table = resultSummary.querySelector(".leaderboard tbody");
  if (!table) {
    return;
  }
  table.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-report-index]");
    if (!row) {
      return;
    }
    const idx = row.getAttribute("data-report-index");
    const target = document.querySelector(`#batch-report-${idx}`);
    if (target) {
      target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
}

function renderResult(payload, label) {
  if (payload.batch && Array.isArray(payload.results)) {
    renderBatchResult(payload, label);
    return;
  }

  const { summary, report } = payload;
  const verdict = report.verdict ?? summary.verdict ?? "Unknown";
  const mode = report.mode ?? summary.mode ?? "unknown";
  document.title = `${verdict} ${report.score}/100 | BidRadar Demo`;

  resultCaption.textContent = `${label} · ${mode} mode · ${report.opportunity_source}`;

  resultSummary.innerHTML = `
    <div class="metric-grid">
      ${metricCard("Verdict", verdict, verdictTone(verdict))}
      ${metricCard("Score", `${report.score}/100`)}
      ${metricCard("Confidence", report.confidence)}
      ${metricCard("Scoring", report.scoring_method === "deterministic+contextual-ai" ? "Deterministic + Contextual" : "Deterministic")}
      ${metricCard("Company evidence source", report.company_source === "contextual" ? "Contextual.ai" : "Local profile")}
      ${metricCard("Opportunity source", report.opportunity_source)}
    </div>
  `;

  resultDetail.innerHTML =
    renderContextualPanel(report) + renderReportBody(report, { showShortlist: true, excludeContextualFromEvidence: true });
}

function summarizeBatchContextual(results) {
  if (!results?.length) {
    return { total: 0, used: 0, structured: 0 };
  }
  const reports = results.map((r) => r.report);
  const used = reports.filter((r) => r.company_source === "contextual").length;
  const structured = reports.filter((r) => r.sponsor_usage?.contextual_scoring).length;
  return { total: reports.length, used, structured };
}

function renderBatchResult(payload, label) {
  const { results, scan_shortlist: scanShortlist } = payload;
  const count = results.length;
  const first = results[0]?.report;
  const modeLabel = first ? first.mode : "unknown";
  document.title = `Ranked · ${count} reports | BidRadar Demo`;
  resultCaption.textContent = `${label} · ${count} full reports · ${modeLabel} mode (aggregate)`;

  const titles = results.map((r) => r.summary.title).filter(Boolean);
  const preview = titles.slice(0, 2).join(" · ");

  const batchCtx = summarizeBatchContextual(results);

  resultSummary.innerHTML = `
    <div class="metric-grid">
      ${metricCard("Opportunities evaluated", String(count))}
      ${metricCard("Top opportunity", preview || "—")}
      ${metricCard("Best score", first ? `${first.score}/100` : "—", verdictTone(first?.verdict))}
      ${metricCard("Contextual on full evals", count ? (batchCtx.used === count ? `All ${count}` : `${batchCtx.used}/${count}`) : "—")}
      ${metricCard("Scan source", first?.opportunity_source ?? "—")}
    </div>
    ${renderShortlist(scanShortlist?.length ? scanShortlist : first?.scan_shortlist)}
  `;

  resultDetail.innerHTML =
    renderContextualPanel(first, { batchSummary: batchCtx }) +
    results
    .map((entry, index) => {
      const { summary, report } = entry;
      const verdict = report.verdict ?? summary.verdict ?? "Unknown";
      return `
        <details class="report-accordion" id="batch-report-${index}" ${index === 0 ? "open" : ""}>
          <summary>
            <span class="inline-pill ${verdictTone(verdict)}">#${summary.rank} · ${escapeHtml(verdict)}</span>
            <span>${escapeHtml(summary.title || "Opportunity")}</span>
            <span class="accordion-score">${report.score}/100</span>
          </summary>
          <div class="accordion-body">
            <p class="contextual-inline">
              <span class="inline-pill ${report.company_source === "contextual" ? "good" : "muted"}">${escapeHtml(
                report.company_source === "contextual"
                  ? report.sponsor_usage?.contextual_scoring
                    ? "Contextual · structured scoring"
                    : "Contextual · grounded retrieval"
                  : "Local profile only",
              )}</span>
              <span class="contextual-inline-meta">${escapeHtml(report.scoring_method || "deterministic")}</span>
            </p>
            <div class="metric-grid accordion-metrics">
              ${metricCard("Verdict", verdict, verdictTone(verdict))}
              ${metricCard("Score", `${report.score}/100`)}
              ${metricCard("Confidence", report.confidence)}
              ${metricCard("Mode", report.mode)}
              ${metricCard("Company evidence", report.company_source)}
            </div>
            ${renderReportBody(report, { showShortlist: false, excludeContextualFromEvidence: true })}
          </div>
        </details>
      `;
    })
    .join("");

  bindLeaderboardClicks();
}

function renderRecentReports(reports) {
  if (!reports?.length) {
    recentRuns.innerHTML = `<p class="recent-empty">No <code>*-report.json</code> files in <code>reports/</code> yet.</p>`;
    return;
  }
  recentRuns.innerHTML = `
    <div class="recent-grid">
      ${reports
        .map(
          (report) => `
            <article class="recent-card">
              <span class="inline-pill ${verdictTone(report.verdict)}">${escapeHtml(report.verdict)}</span>
              <strong>${escapeHtml(report.title)}</strong>
              <p>${escapeHtml(report.mode)} · ${escapeHtml(report.score)}/100</p>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function setLoading(label, detail = "Executing the Python skill and loading generated reports.") {
  document.title = `Running | BidRadar Demo`;
  resultCaption.textContent = `${label} · running`;
  resultSummary.innerHTML = `
    <div class="loading-state">
      <span class="loading-dot"></span>
      <p>${escapeHtml(detail)}</p>
    </div>
  `;
  resultDetail.innerHTML = "";
}

function setError(message) {
  document.title = `Error | BidRadar Demo`;
  resultCaption.textContent = "Run failed";
  resultSummary.innerHTML = `
    <div class="empty-state error">
      <h3>Request failed</h3>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
  resultDetail.innerHTML = "";
}

async function fetchJson(url, options = {}) {
  let lastError = null;

  for (const origin of apiOrigins) {
    const target = new URL(url, `${origin}/`).toString();
    try {
      const response = await fetch(target, options);
      const contentType = response.headers.get("content-type") || "";
      const raw = await response.text();
      const isJson = contentType.includes("application/json");

      if (!isJson) {
        if (origin !== apiOrigins.at(-1)) {
          continue;
        }
        const preview = raw.replace(/\s+/gu, " ").trim().slice(0, 140);
        throw new Error(
          `API returned ${contentType || "non-JSON content"} from ${origin}. ${preview || "Start the local server with npm start."}`,
        );
      }

      const payload = JSON.parse(raw);
      if (!response.ok) {
        throw new Error(payload.error || `Request failed with status ${response.status}`);
      }
      return payload;
    } catch (error) {
      lastError = error;
      if (origin === apiOrigins.at(-1)) {
        break;
      }
    }
  }

  const detail = lastError instanceof Error ? lastError.message : "Unknown request failure";
  throw new Error(`${detail} If you opened the HTML directly, keep the page open but start the API with npm start.`);
}

async function loadStatus() {
  const payload = await fetchJson("/api/status");
  const scan = payload.status?.scan_input ?? {};
  const summaryChips = [
    `<span class="status-chip ${payload.env_file_loaded ? "good" : "warn"}">${payload.env_file_loaded ? ".env loaded" : "No .env"}</span>`,
    `<span class="status-chip ${scan.apify ? "good" : "muted"}">Apify ${scan.apify ? "on" : "demo"}</span>`,
    `<span class="status-chip ${scan.contextual ? "good" : "muted"}">Contextual ${scan.contextual ? "on" : "off"}</span>`,
  ];
  statusSummary.innerHTML = summaryChips.join("");
  renderRecentReports(payload.recent_reports);
}

function switchView(nextView) {
  state.activeView = nextView;
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === nextView);
  });
  workflows.forEach((workflow) => {
    const active = workflow.id.startsWith(nextView);
    workflow.classList.toggle("active", active);
    workflow.hidden = !active;
  });
}

function syncEvaluateAllUi() {
  const on = scanEvaluateAll.checked;
  scanSingleWrap.hidden = on;
}

async function runQualify(body = {}, label = "Single opportunity") {
  setLoading(label);
  const payload = await fetchJson("/api/qualify", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  renderResult(payload, label);
  await loadStatus();
}

async function runScan(body = {}, label = "SAM scan") {
  const batch = body.evaluateAll !== false;
  setLoading(
    label,
    batch
      ? "Calling the API: Python runs SAM scan mode, then full qualification per shortlist row (demo data is often a few seconds; live SAM + contextual can take a minute)."
      : "Calling the API: Python runs SAM scan mode and one full qualification.",
  );
  const payload = await fetchJson("/api/scan", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  renderResult(payload, label);
  await loadStatus();
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});

scanEvaluateAll.addEventListener("change", syncEvaluateAllUi);
syncEvaluateAllUi();

qualifyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const companyName = document.querySelector("#qualify-company-name").value;
    await runQualify(
      {
        url: document.querySelector("#qualify-url").value,
        text: document.querySelector("#qualify-text").value,
        ...(companyName.trim() ? { companyName: companyName.trim() } : {}),
      },
      "Single opportunity",
    );
  } catch (error) {
    setError(error.message);
  }
});

scanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const companyName = document.querySelector("#scan-company-name").value.trim();
    const evaluateAll = scanEvaluateAll.checked;
    await runScan(
      {
        keywords: document.querySelector("#scan-keywords").value,
        states: document.querySelector("#scan-states").value,
        maxOpportunities: document.querySelector("#scan-max").value,
        opportunityIndex: document.querySelector("#scan-index").value,
        naicsCodes: document.querySelector("#scan-naics").value,
        setAsideTypes: document.querySelector("#scan-setaside").value,
        postedWithinDays: document.querySelector("#scan-posted-days").value,
        evaluateAll,
        ...(companyName ? { companyName } : {}),
      },
      evaluateAll ? "Scan & evaluate all" : "SAM scan (single)",
    );
  } catch (error) {
    setError(error.message);
  }
});

demoRunButton.addEventListener("click", async () => {
  document.querySelector("#qualify-url").value = "";
  document.querySelector("#qualify-text").value = "";
  try {
    await runQualify({}, "Demo opportunity");
  } catch (error) {
    setError(error.message);
  }
});

async function bootstrap() {
  try {
    await loadStatus();
  } catch (error) {
    setError(error.message);
  }
}

bootstrap();
