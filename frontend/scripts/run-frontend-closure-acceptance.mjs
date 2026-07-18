import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { chromium } from "@playwright/test";

const root = resolve("dist");
const acceptanceRoot = resolve("acceptance/frontend-closure");
const lighthouseRoot = resolve("acceptance/runtime/frontend-closure-lighthouse");
const testedCommit = git("rev-parse", "HEAD");
const testedTree = git("rev-parse", "HEAD^{tree}");
if (git("status", "--porcelain", "--untracked-files=all")) {
  throw new Error("frontend closure acceptance requires a clean worktree");
}

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
execFileSync(npmCommand, ["run", "build"], { stdio: "inherit" });

const lighthouseRuns = [];
for (let index = 1; index <= 3; index += 1) {
  const outputDirectory = join(lighthouseRoot, `run-${index}`);
  execFileSync(
    process.execPath,
    ["scripts/run-lighthouse.mjs", testedCommit, outputDirectory],
    { stdio: "inherit" },
  );
  const receipt = JSON.parse(await readFile(join(outputDirectory, "receipt.json"), "utf8"));
  lighthouseRuns.push({
    run_index: index,
    performance: receipt.scores.performance,
    accessibility: receipt.scores.accessibility,
    external_requests: receipt.external_requests,
    report_path: `frontend/acceptance/runtime/frontend-closure-lighthouse/run-${index}/report.json`,
    report_sha256: receipt.report_sha256,
  });
}

const screenshotResults = await captureScreenshots();
const performanceScores = lighthouseRuns.map((run) => run.performance).sort((a, b) => a - b);
const performanceMedian = performanceScores[1];
const hardThresholdsPassed = lighthouseRuns.every(
  (run) => run.performance >= 90 && run.accessibility >= 90 && run.external_requests === 0,
);
const receipt = {
  schema_version: "frontend-closure-acceptance-v1",
  tested_commit: testedCommit,
  tested_tree: testedTree,
  package_name: "agent-reliability-lab-showcase",
  browser: "playwright-chromium",
  lighthouse_run_count: lighthouseRuns.length,
  lighthouse_runs: lighthouseRuns,
  thresholds: {
    performance_each_minimum: 90,
    accessibility_each_minimum: 90,
    performance_median_recommended: 95,
  },
  performance_median: performanceMedian,
  performance_median_recommendation_met: performanceMedian >= 95,
  screenshots: screenshotResults,
  model_requests: 0,
  external_requests: lighthouseRuns.reduce((total, run) => total + run.external_requests, 0),
  best_run_selection_allowed: false,
  hard_thresholds_passed: hardThresholdsPassed,
};
if (!hardThresholdsPassed) throw new Error("frontend closure Lighthouse threshold failed");
await mkdir(acceptanceRoot, { recursive: true });
const serialized = `${JSON.stringify(receipt, null, 2)}\n`;
await writeFile(join(acceptanceRoot, "receipt.json"), serialized, "utf8");
process.stdout.write(serialized);

async function captureScreenshots() {
  const port = 4323;
  const url = `http://127.0.0.1:${port}/`;
  const server = createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url ?? "/", url).pathname;
      const relative = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
      const filePath = normalize(join(root, relative));
      if (!filePath.startsWith(root)) throw new Error("invalid path");
      const body = await readFile(filePath);
      const contentTypes = {
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
      };
      response.writeHead(200, {
        "content-type": contentTypes[extname(filePath)] ?? "application/octet-stream",
        "cache-control": "no-store",
      });
      response.end(body);
    } catch {
      response.writeHead(404).end("not found");
    }
  });
  await new Promise((resolveListen) => server.listen(port, "127.0.0.1", resolveListen));
  const browser = await chromium.launch({ headless: true });
  const results = [];
  const viewports = [
    { name: "desktop-1440x900", width: 1440, height: 900 },
    { name: "laptop-1280x720", width: 1280, height: 720 },
    { name: "mobile-390x844", width: 390, height: 844 },
  ];
  try {
    await mkdir(acceptanceRoot, { recursive: true });
    for (const viewport of viewports) {
      const page = await browser.newPage({ viewport });
      const externalUrls = [];
      page.on("request", (request) => {
        const requestUrl = new URL(request.url());
        if (!new Set(["127.0.0.1", "localhost"]).has(requestUrl.hostname)) {
          externalUrls.push(request.url());
        }
      });
      await page.goto(url, { waitUntil: "networkidle" });
      const path = join(acceptanceRoot, `${viewport.name}.png`);
      await page.screenshot({ path, fullPage: true });
      if (externalUrls.length) throw new Error(`external screenshot requests: ${externalUrls}`);
      const bytes = await readFile(path);
      results.push({
        viewport: { width: viewport.width, height: viewport.height },
        path: `frontend/acceptance/frontend-closure/${viewport.name}.png`,
        sha256: createHash("sha256").update(bytes).digest("hex"),
      });
      await page.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolveClose) => server.close(resolveClose));
  }
  return results;
}

function git(...args) {
  return execFileSync("git", args, { encoding: "utf8" }).trim();
}
