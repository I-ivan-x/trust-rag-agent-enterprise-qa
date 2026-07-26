import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, relative, resolve } from "node:path";
import { brotliCompressSync } from "node:zlib";
import { chromium } from "@playwright/test";
import { launch } from "chrome-launcher";
import lighthouse from "lighthouse";

const arguments_ = process.argv.slice(2);
if (arguments_[0] === "--") arguments_.shift();
const [buildCommit = "WORKTREE", outputDirectory = "acceptance/runtime/lighthouse"] = arguments_;
const root = resolve("dist");
const port = 4322;
const url = `http://127.0.0.1:${port}/`;
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};
const assets = await loadAssets(root);

const server = createServer((request, response) => {
  try {
    const pathname = new URL(request.url ?? "/", url).pathname;
    const assetPath = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
    const asset = assets.get(assetPath);
    if (!asset) throw new Error("not found");
    const acceptsBrotli = /(?:^|,)\s*br(?:\s*;|\s*,|$)/.test(
      String(request.headers["accept-encoding"] ?? ""),
    );
    const responseBody = acceptsBrotli ? asset.brotli : asset.body;
    response.writeHead(200, {
      "content-type": asset.contentType,
      "cache-control": "no-store",
      ...(acceptsBrotli ? { "content-encoding": "br", vary: "accept-encoding" } : {}),
    });
    response.end(responseBody);
  } catch {
    response.writeHead(404).end("not found");
  }
});

await new Promise((resolveListen) => server.listen(port, "127.0.0.1", resolveListen));
const chrome = await launch({
  chromePath: chromium.executablePath(),
  chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
});

try {
  const result = await lighthouse(url, {
    port: chrome.port,
    output: "json",
    logLevel: "error",
    onlyCategories: ["performance", "accessibility"],
    formFactor: "desktop",
    throttlingMethod: "simulate",
    screenEmulation: {
      mobile: false,
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      disabled: false,
    },
  });
  if (!result) throw new Error("Lighthouse returned no result");
  const report = typeof result.report === "string" ? result.report : result.report[0];
  const performance = Math.round(result.lhr.categories.performance.score * 100);
  const accessibility = Math.round(result.lhr.categories.accessibility.score * 100);
  const networkItems = result.lhr.audits["network-requests"]?.details?.items ?? [];
  const externalUrls = networkItems
    .map((item) => item.url)
    .filter((itemUrl) => {
      if (!itemUrl || itemUrl.startsWith("data:")) return false;
      const host = new URL(itemUrl).hostname;
      return host !== "127.0.0.1" && host !== "localhost";
    });

  await mkdir(outputDirectory, { recursive: true });
  const reportPath = join(outputDirectory, "report.json");
  await writeFile(reportPath, report, "utf8");
  const receipt = {
    schema_version: "frontend-lighthouse-receipt-v1",
    build_commit: buildCommit,
    run_mode:
      "preloaded static Astro build with precompressed Brotli; Lighthouse desktop simulated throttling",
    viewport: { width: 1440, height: 900, deviceScaleFactor: 1 },
    scores: { performance, accessibility },
    thresholds: { performance: 90, accessibility: 90 },
    external_requests: externalUrls.length,
    external_urls: externalUrls,
    report_sha256: createHash("sha256").update(report).digest("hex"),
  };
  await writeFile(
    join(outputDirectory, "receipt.json"),
    `${JSON.stringify(receipt, null, 2)}\n`,
    "utf8",
  );
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
  if (performance < 90 || accessibility < 90 || externalUrls.length > 0) process.exitCode = 1;
} finally {
  try {
    await chrome.kill();
  } catch (error) {
    if (error?.code !== "EPERM") throw error;
  }
  await new Promise((resolveClose) => server.close(resolveClose));
}

async function loadAssets(directory) {
  const loaded = new Map();
  const entries = await readdir(directory, { recursive: true, withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const filePath = join(entry.parentPath, entry.name);
    const assetPath = relative(directory, filePath).replaceAll("\\", "/");
    const body = await readFile(filePath);
    loaded.set(assetPath, {
      body,
      brotli: brotliCompressSync(body),
      contentType: contentTypes[extname(filePath)] ?? "application/octet-stream",
    });
  }
  return loaded;
}
