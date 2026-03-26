import { execFile } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const currentFile = fileURLToPath(import.meta.url);
const demoRoot = dirname(currentFile);
const repoRoot = resolve(demoRoot, "..");
const publicRoot = join(demoRoot, "public");
const reportsRoot = join(repoRoot, "reports");
const envFilePath = join(repoRoot, ".env.bidradar.sh");
const qualifyScript = join(repoRoot, "skills", "bid-radar", "scripts", "qualify_opportunity.py");
const validateScript = join(repoRoot, "skills", "bid-radar", "scripts", "validate_inputs.py");
const runtimeEnv = {
  ...process.env,
  ...loadShellExports(envFilePath),
};
const port = normalizeInteger(process.env.PORT, 3000, { min: 1, max: 65535 });
const host = nonEmptyString(process.env.HOST) || "127.0.0.1";

function loadShellExports(filePath) {
  if (!existsSync(filePath)) {
    return {};
  }

  const exports = {};
  const content = readFileSync(filePath, "utf8");
  for (const rawLine of content.split(/\r?\n/u)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.startsWith("export ")) {
      continue;
    }

    const match = line.match(/^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$/u);
    if (!match) {
      continue;
    }

    const [, key, rawValue] = match;
    let value = rawValue.trim();
    const quote = value[0];
    if ((quote === '"' || quote === "'") && value.endsWith(quote)) {
      value = value.slice(1, -1);
    }
    exports[key] = value;
  }
  return exports;
}

function normalizeInteger(value, fallback, options = {}) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  const min = options.min ?? Number.MIN_SAFE_INTEGER;
  const max = options.max ?? Number.MAX_SAFE_INTEGER;
  return Math.min(max, Math.max(min, parsed));
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function parseJson(text, label) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Failed to parse ${label}: ${error.message}`);
  }
}

function extractFactValue(facts, label) {
  const prefix = `${label}: `;
  if (!Array.isArray(facts)) {
    return null;
  }
  const match = facts.find((item) => typeof item === "string" && item.startsWith(prefix));
  return match ? match.slice(prefix.length) : null;
}

async function readRecentReports(limit = 6) {
  if (!existsSync(reportsRoot)) {
    return [];
  }

  const names = (await readdir(reportsRoot))
    .filter((name) => name.endsWith("-report.json"))
    .sort()
    .reverse()
    .slice(0, limit);

  const reports = [];
  for (const name of names) {
    const filePath = join(reportsRoot, name);
    const report = parseJson(await readFile(filePath, "utf8"), name);
    reports.push({
      file_name: name,
      timestamp: report.timestamp ?? null,
      verdict: report.verdict ?? "Unknown",
      score: report.score ?? null,
      mode: report.mode ?? "unknown",
      title: extractFactValue(report.opportunity_facts, "Title") ?? "Unknown opportunity",
    });
  }
  return reports;
}

async function runPythonJson(scriptPath, args = []) {
  const result = await execFileAsync("python3", [scriptPath, ...args], {
    cwd: repoRoot,
    env: runtimeEnv,
    maxBuffer: 10 * 1024 * 1024,
  });
  return parseJson(result.stdout, scriptPath);
}

async function runQualification(args = []) {
  const result = await execFileAsync("python3", [qualifyScript, ...args], {
    cwd: repoRoot,
    env: runtimeEnv,
    maxBuffer: 10 * 1024 * 1024,
  });
  const summary = parseJson(result.stdout, "qualification summary");
  if (summary.batch && Array.isArray(summary.items)) {
    const results = [];
    for (const item of summary.items) {
      if (!item.report_json) {
        throw new Error("Batch qualification item did not return report_json.");
      }
      const reportPath = resolve(item.report_json);
      const report = parseJson(await readFile(reportPath, "utf8"), "qualification report");
      results.push({
        summary: item,
        report,
      });
    }
    return {
      batch: true,
      results,
      scan_shortlist: summary.scan_shortlist ?? [],
      shortlist_count: summary.shortlist_count ?? results.length,
    };
  }
  if (!summary.report_json) {
    throw new Error("Qualification run did not return a report_json path.");
  }

  const reportPath = resolve(summary.report_json);
  const report = parseJson(await readFile(reportPath, "utf8"), "qualification report");
  return {
    summary,
    report,
  };
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw.trim()) {
    return {};
  }
  return parseJson(raw, "request body");
}

function appendArg(target, flag, value) {
  const normalized = nonEmptyString(value);
  if (normalized) {
    target.push(flag, normalized);
  }
}

function appendFlag(target, flag, condition) {
  if (condition) {
    target.push(flag);
  }
}

function buildQualifyArgs(body) {
  const args = [];
  appendArg(args, "--url", body.url);
  appendArg(args, "--text", body.text);
  appendArg(args, "--file", body.file);
  appendArg(args, "--company-profile", body.companyProfile);
  appendArg(args, "--company-name", body.companyName);
  appendArg(args, "--report-dir", "reports");
  return args;
}

function buildScanArgs(body) {
  const args = ["--scan-sam"];
  appendArg(args, "--keywords", body.keywords);
  appendArg(args, "--states", body.states);
  appendArg(args, "--naics-codes", body.naicsCodes);
  appendArg(args, "--set-aside-types", body.setAsideTypes);
  appendArg(args, "--company-profile", body.companyProfile);
  appendArg(args, "--company-name", body.companyName);
  args.push("--posted-within-days", String(normalizeInteger(body.postedWithinDays, 30, { min: 1, max: 365 })));
  args.push("--max-opportunities", String(normalizeInteger(body.maxOpportunities, 5, { min: 1, max: 25 })));
  if (body.evaluateAll !== false) {
    appendFlag(args, "--evaluate-all", true);
  } else {
    args.push("--opportunity-index", String(normalizeInteger(body.opportunityIndex, 0, { min: 0, max: 24 })));
  }
  args.push("--report-dir", "reports");
  return args;
}

function mimeType(filePath) {
  switch (extname(filePath)) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    case ".js":
      return "application/javascript; charset=utf-8";
    case ".json":
      return "application/json; charset=utf-8";
    default:
      return "text/plain; charset=utf-8";
  }
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  response.end(body);
}

async function serveStatic(response, pathname) {
  const relativePath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = resolve(publicRoot, relativePath);
  if (!filePath.startsWith(publicRoot)) {
    sendJson(response, 404, { error: "Not found" });
    return;
  }

  try {
    const fileStats = await stat(filePath);
    if (!fileStats.isFile()) {
      sendJson(response, 404, { error: "Not found" });
      return;
    }
    const content = await readFile(filePath);
    response.writeHead(200, {
      "Content-Type": mimeType(filePath),
      "Content-Length": content.byteLength,
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
    });
    response.end(content);
  } catch {
    sendJson(response, 404, { error: "Not found" });
  }
}

const server = createServer(async (request, response) => {
  const baseUrl = `http://${request.headers.host || "localhost"}`;
  const url = new URL(request.url || "/", baseUrl);

  try {
    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-store",
      });
      response.end();
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/status") {
      const [singleInput, scanInput, recentReports] = await Promise.all([
        runPythonJson(validateScript),
        runPythonJson(validateScript, ["--scan-sam", "--max-opportunities", "5"]),
        readRecentReports(),
      ]);

      sendJson(response, 200, {
        env_file_loaded: existsSync(envFilePath),
        status: {
          single_input: singleInput,
          scan_input: scanInput,
        },
        recent_reports: recentReports,
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/qualify") {
      const body = await readBody(request);
      const args = buildQualifyArgs(body);
      const started = Date.now();
      console.log(`[bidradar] POST /api/qualify → python3 qualify_opportunity.py ${args.join(" ")}`);
      const result = await runQualification(args);
      console.log(`[bidradar] qualify finished in ${Date.now() - started}ms`);
      sendJson(response, 200, result);
      return;
    }

    if (request.method === "POST" && url.pathname === "/api/scan") {
      const body = await readBody(request);
      const args = buildScanArgs(body);
      const started = Date.now();
      console.log(`[bidradar] POST /api/scan → python3 qualify_opportunity.py ${args.join(" ")}`);
      const result = await runQualification(args);
      console.log(`[bidradar] scan finished in ${Date.now() - started}ms`);
      sendJson(response, 200, result);
      return;
    }

    if (request.method === "GET" && url.pathname === "/api/recent-reports") {
      sendJson(response, 200, {
        recent_reports: await readRecentReports(),
      });
      return;
    }

    if (request.method === "GET") {
      await serveStatic(response, url.pathname);
      return;
    }

    sendJson(response, 405, { error: "Method not allowed" });
  } catch (error) {
    sendJson(response, 500, {
      error: error instanceof Error ? error.message : "Unknown server error",
    });
  }
});

server.listen(port, host, () => {
  console.log(`BidRadar demo running at http://${host}:${port}`);
});
