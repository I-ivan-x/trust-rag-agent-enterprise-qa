import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const [url, outputDirectory = "acceptance/screenshots"] = process.argv.slice(2);
if (!url) {
  throw new Error("usage: node scripts/capture-viewports.mjs <url> [output-directory]");
}

const viewports = [
  { name: "desktop-1440x900", width: 1440, height: 900 },
  { name: "laptop-1280x720", width: 1280, height: 720 },
  { name: "mobile-390x844", width: 390, height: 844 },
];

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ headless: true });

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto(url, { waitUntil: "networkidle" });
    await page.screenshot({
      path: join(outputDirectory, `${viewport.name}.png`),
      fullPage: true,
    });
    await page.close();
  }
} finally {
  await browser.close();
}
