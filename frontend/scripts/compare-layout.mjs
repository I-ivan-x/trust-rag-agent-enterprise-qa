import { readFile, writeFile } from "node:fs/promises";

const [baselinePath, currentPath, outputPath] = process.argv.slice(2);
if (!baselinePath || !currentPath || !outputPath) {
  throw new Error("usage: node scripts/compare-layout.mjs <baseline> <current> <output>");
}

const baseline = JSON.parse(await readFile(baselinePath, "utf8"));
const current = JSON.parse(await readFile(currentPath, "utf8"));
if (
  baseline.viewport.width !== current.viewport.width ||
  baseline.viewport.height !== current.viewport.height
) {
  throw new Error("layout receipts use different viewports");
}

const reduction = 1 - current.scrollHeight / baseline.scrollHeight;
const q5ViewportHeights = current.q5Top / current.viewport.height;
const receipt = {
  schema_version: "frontend-layout-comparison-v1",
  baseline: {
    commit: baseline.commit,
    viewport: baseline.viewport,
    scrollHeight: baseline.scrollHeight,
  },
  current: {
    commit: current.commit,
    viewport: current.viewport,
    scrollHeight: current.scrollHeight,
    q5Top: current.q5Top,
  },
  reduction,
  q5ViewportHeights,
  checks: {
    scroll_height_reduction_at_least_40_percent: reduction >= 0.4,
    q5_within_three_viewport_heights: q5ViewportHeights <= 3,
    no_page_horizontal_overflow: current.scrollWidth <= current.clientWidth,
  },
};

await writeFile(outputPath, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
if (Object.values(receipt.checks).some((passed) => !passed)) process.exitCode = 1;
