import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

const sectionIds = [
  "hero",
  "five-questions",
  "governed-runtime",
  "reliability-turn",
  "q5-decision-frontier",
  "evaluation-infrastructure",
  "evidence-ledger",
];

const localPage = "http://127.0.0.1:4321/";

async function responsiveIntegrity(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const viewportWidth = root.clientWidth;
    const clipped = Array.from(
      document.querySelectorAll("h1,h2,h3,p,a,button,summary,dt,dd,span,strong,small,li"),
    )
      .filter((element) => {
        if (element.closest("[hidden]") || element.closest('[aria-hidden="true"]')) return false;
        const closedDetails = element.closest("details:not([open])");
        if (closedDetails && !element.closest("summary")) return false;
        if (element.clientWidth === 0 || element.clientHeight === 0) return false;
        const style = getComputedStyle(element);
        const clipsX = ["hidden", "clip"].includes(style.overflowX);
        const clipsY = ["hidden", "clip"].includes(style.overflowY);
        return (
          element.getBoundingClientRect().right > viewportWidth + 1 ||
          (clipsX && element.scrollWidth > element.clientWidth + 1) ||
          (clipsY && element.scrollHeight > element.clientHeight + 1)
        );
      })
      .map((element) => ({ tag: element.tagName, text: element.textContent?.slice(0, 80) }));
    return {
      scrollWidth: root.scrollWidth,
      clientWidth: viewportWidth,
      clipped,
    };
  });
}

async function expectResponsiveIntegrity(page) {
  const result = await responsiveIntegrity(page);
  expect(result.scrollWidth).toBeLessThanOrEqual(result.clientWidth);
  expect(result.clipped).toEqual([]);
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.locator("#q5-decision-frontier")).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
});

test("renders the exact seven-section narrative with one H1", async ({ page }) => {
  const sections = page.locator("[data-major-section]");
  await expect(sections).toHaveCount(7);
  await expect(page.locator("h1")).toHaveCount(1);
  expect(await sections.evaluateAll((nodes) => nodes.map((node) => node.id))).toEqual(sectionIds);
  for (const id of sectionIds) {
    await expect(page.locator(`#${id}`)).toBeVisible();
  }
});

test("keeps Q5 within the first three viewport heights", async ({ page }) => {
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  const top = await page.locator("#q5-decision-frontier").evaluate(
    (node) => node.getBoundingClientRect().top + window.scrollY,
  );
  expect(top).toBeLessThanOrEqual(viewport.height * 3);
});

test("has no page or meaningful-element horizontal overflow", async ({ page }) => {
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    const width = root.clientWidth;
    const candidates = Array.from(
      document.querySelectorAll("a,button,summary,h1,h2,h3,p,li,dl,article,section"),
    );
    const overflow = candidates
      .filter((element) => {
        if (element.closest("[hidden]") || element.closest('[aria-hidden="true"]')) return false;
        const rect = element.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;
        return rect.left < -1 || rect.right > width + 1;
      })
      .map((element) => ({
        tag: element.tagName,
        id: element.id,
        className: element.className,
        rect: element.getBoundingClientRect().toJSON(),
      }));
    return { scrollWidth: root.scrollWidth, clientWidth: width, overflow };
  });
  expect(result.scrollWidth).toBeLessThanOrEqual(result.clientWidth);
  expect(result.overflow).toEqual([]);
});

test("does not clip rendered text", async ({ page }) => {
  const clipped = await page.evaluate(() =>
    Array.from(
      document.querySelectorAll("h1,h2,h3,p,a,button,summary,dt,dd,span,strong,small,li"),
    )
      .filter((element) => {
        if (element.closest("[hidden]") || element.closest('[aria-hidden="true"]')) return false;
        if (element.clientWidth === 0 || element.clientHeight === 0) return false;
        const style = getComputedStyle(element);
        const clipsX = ["hidden", "clip"].includes(style.overflowX);
        const clipsY = ["hidden", "clip"].includes(style.overflowY);
        return (
          (clipsX && element.scrollWidth > element.clientWidth + 1) ||
          (clipsY && element.scrollHeight > element.clientHeight + 1)
        );
      })
      .map((element) => ({ tag: element.tagName, text: element.textContent?.slice(0, 80) })),
  );
  expect(clipped).toEqual([]);
});

test("sticky navigation leaves section headings visible", async ({ page }) => {
  const headerHeight = await page.locator("[data-sticky-header]").evaluate(
    (node) => node.getBoundingClientRect().height,
  );
  for (const id of sectionIds.slice(1)) {
    await page.locator(`#${id}`).evaluate((node) => node.scrollIntoView());
    const headingTop = await page.locator(`#${id} h2`).evaluate(
      (node) => node.getBoundingClientRect().top,
    );
    expect(headingTop, id).toBeGreaterThanOrEqual(headerHeight - 1);
  }
});

test("frontier segment and state controls support keyboard operation", async ({ page }) => {
  const controlled = page.getByRole("tab", { name: "Controlled prose", exact: true });
  const open = page.getByRole("tab", { name: "Open semantics", exact: true });
  await controlled.focus();
  await controlled.press("ArrowRight");
  await expect(open).toBeFocused();
  await open.press("Enter");
  await expect(open).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#frontier-segment-panel-open_semantics")).toBeVisible();

  const realResult = page.locator("#frontier-open_semantics-real_result-tab");
  const finalDecision = page.locator("#frontier-open_semantics-final_decision-tab");
  await realResult.focus();
  await realResult.press("ArrowRight");
  await expect(finalDecision).toBeFocused();
  await finalDecision.press("Space");
  await expect(finalDecision).toHaveAttribute("aria-selected", "true");
});

test("keyboard focus is visibly styled", async ({ page }) => {
  const target = page.locator(".hero-actions a").first();
  await target.focus();
  const focusStyle = await target.evaluate((node) => {
    const style = getComputedStyle(node);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(focusStyle.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(2);
});

test("mobile touch targets remain at least 44 CSS pixels", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-390x844", "mobile interaction contract");
  const undersized = await page.locator("a,button,summary").evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0 &&
          (rect.width < 44 || rect.height < 44)
        );
      })
      .map((node) => ({
        tag: node.tagName,
        text: node.textContent?.trim().slice(0, 80),
        rect: node.getBoundingClientRect().toJSON(),
      })),
  );
  expect(undersized).toEqual([]);
});

test("375px portrait preserves core layout integrity", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-1440x900", "single supplemental viewport run");
  const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await context.newPage();
  await page.goto(localPage, { waitUntil: "networkidle" });
  await expectResponsiveIntegrity(page);
  await context.close();
});

test("phone landscape preserves core layout integrity", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-1440x900", "single supplemental viewport run");
  const context = await browser.newContext({ viewport: { width: 844, height: 390 } });
  const page = await context.newPage();
  await page.goto(localPage, { waitUntil: "networkidle" });
  await expectResponsiveIntegrity(page);
  await context.close();
});

test("125 percent text scaling preserves core layout integrity", async ({ browser }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-1440x900", "single text-scaling contract run");
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto(localPage, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: "html { font-size: 125% !important; }" });
  await expectResponsiveIntegrity(page);
  await context.close();
});

test("reduced motion preserves the complete core conclusion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload({ waitUntil: "networkidle" });
  const summary = page.locator(".frontier-summary");
  await expect(summary.locator(".frontier-summary-card")).toHaveCount(3);
  await expect(summary.getByText(/resolved 32\/32 cases/).first()).toBeVisible();
  await expect(summary.getByText(/semantic uplift was 1\/12/).first()).toBeVisible();
  await expect(summary.getByText(/Not evaluated:/).first()).toBeVisible();
  const hiddenByOpacity = await page.locator("[data-major-section]").evaluateAll((nodes) =>
    nodes.filter((node) => getComputedStyle(node).opacity === "0").map((node) => node.id),
  );
  expect(hiddenByOpacity).toEqual([]);
});

test("no-JavaScript view contains all static runtime and frontier conclusions", async ({
  browser,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-1440x900", "single no-JS contract run");
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  await page.goto(localPage, { waitUntil: "networkidle" });
  await expect(page.locator("[data-trajectory-panel]")).toHaveCount(2);
  for (const panel of await page.locator("[data-trajectory-panel]").all()) {
    await expect(panel).toBeVisible();
  }
  await expect(page.locator("[data-frontier-segment-panel]")).toHaveCount(4);
  for (const panel of await page.locator("[data-frontier-segment-panel]").all()) {
    await expect(panel).toBeVisible();
  }
  const summary = page.locator(".frontier-summary");
  await expect(summary.getByText(/resolved 32\/32 cases/).first()).toBeVisible();
  await expect(summary.getByText(/semantic uplift was 1\/12/).first()).toBeVisible();
  await expect(summary.getByText(/Not evaluated:/).first()).toBeVisible();
  await context.close();
});

test("every rendered metric reverses to a claim ledger entry", async ({ page }) => {
  const unresolved = await page.evaluate(() => {
    const ledgerIds = new Set(
      Array.from(document.querySelectorAll(".ledger-item[data-claim-id]"), (node) =>
        node.getAttribute("data-claim-id"),
      ),
    );
    return Array.from(document.querySelectorAll("[data-metric-claim]"))
      .map((node) => node.getAttribute("data-metric-claim"))
      .filter((claimId) => !claimId || !ledgerIds.has(claimId));
  });
  expect(unresolved).toEqual([]);
});

test("does not request retired hand-authored headline JSON", async ({ page }) => {
  const requested = [];
  page.on("request", (request) => requested.push(request.url()));
  await page.reload({ waitUntil: "networkidle" });
  expect(requested.filter((url) => /\/(arc|triad)\.json(?:$|\?)/.test(url))).toEqual([]);
});

test("desktop layout is at least 40 percent shorter than c583e08", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-1440x900", "baseline viewport is 1440x900");
  const baseline = JSON.parse(
    await readFile(new URL("../acceptance/layout-baseline.json", import.meta.url), "utf8"),
  );
  const current = await page.evaluate(() => document.documentElement.scrollHeight);
  const reduction = 1 - current / baseline.scrollHeight;
  expect(reduction).toBeGreaterThanOrEqual(0.4);
});
