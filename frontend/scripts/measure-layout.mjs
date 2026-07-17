import { writeFile } from "node:fs/promises";
import { chromium } from "@playwright/test";

const [url, commit, outputPath, widthArg, heightArg] = process.argv.slice(2);

if (!url || !commit) {
  throw new Error(
    "usage: node scripts/measure-layout.mjs <url> <commit> [output.json]",
  );
}

const viewport = {
  width: widthArg ? Number(widthArg) : 1440,
  height: heightArg ? Number(heightArg) : 900,
};
if (!Number.isInteger(viewport.width) || !Number.isInteger(viewport.height)) {
  throw new Error("viewport width and height must be integers");
}
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage({ viewport });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);

  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    const q5 = document.querySelector("#q5-decision-frontier");
    const majorSections = Array.from(
      document.querySelectorAll("[data-major-section]"),
    ).map((section) => ({
      id: section.id,
      top: Math.round(section.getBoundingClientRect().top + window.scrollY),
      height: Math.round(section.getBoundingClientRect().height),
    }));

    return {
      scrollHeight: root.scrollHeight,
      scrollWidth: root.scrollWidth,
      clientWidth: root.clientWidth,
      q5Top: q5
        ? Math.round(q5.getBoundingClientRect().top + window.scrollY)
        : null,
      majorSections,
    };
  });

  const receipt = {
    schema_version: "frontend-layout-measurement-v1",
    url,
    commit,
    viewport,
    ...layout,
  };

  const serialized = `${JSON.stringify(receipt, null, 2)}\n`;
  if (outputPath) {
    await writeFile(outputPath, serialized, "utf8");
  }
  process.stdout.write(serialized);
} finally {
  await browser.close();
}
