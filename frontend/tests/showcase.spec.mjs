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

test("runtime paths and technical disclosure support keyboard operation", async ({ page }) => {
  const approval = page.getByRole("tab", { name: "正确路径：等待审批", exact: true });
  const blocked = page.getByRole("tab", { name: "危险路径：尝试绕过审批", exact: true });
  await approval.focus();
  await approval.press("ArrowRight");
  await expect(blocked).toBeFocused();
  await blocked.press("Enter");
  await expect(blocked).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#trajectory-panel-blocked_path")).toBeVisible();

  const disclosure = page.locator(".frontier-technical summary");
  await disclosure.focus();
  await disclosure.press("Enter");
  await expect(page.locator(".frontier-technical")).toHaveAttribute("open", "");
});

test("Q5 workbench follows the four-route and three-state demo script", async ({ page }) => {
  const segmentTabs = page.locator("[data-frontier-segment-tabs]");
  const grammar = segmentTabs.getByRole("tab", { name: /Grammar/ });
  const controlled = segmentTabs.getByRole("tab", { name: /Controlled prose/ });
  const openSemantics = segmentTabs.getByRole("tab", { name: /Open semantics/ });
  const unsafe = segmentTabs.getByRole("tab", { name: /Unsafe/ });

  await expect(controlled).toHaveAttribute("aria-selected", "true");
  const controlledPanel = page.locator("#frontier-segment-panel-controlled_prose");
  await expect(controlledPanel).toContainText("原未覆盖案例已全部解决");
  await expect(controlledPanel).toContainText("不调用");

  const stateTabs = controlledPanel.locator(".state-tabs");
  const hypothesis = stateTabs.getByRole("tab", { name: /Hypothesis/ });
  const realResult = stateTabs.getByRole("tab", { name: /Real result/ });
  const finalDecision = stateTabs.getByRole("tab", { name: /Final decision/ });
  await expect(finalDecision).toHaveAttribute("aria-selected", "true");
  await hypothesis.click();
  await expect(controlledPanel.getByText("待验证假设")).toBeVisible();
  await realResult.click();
  await expect(controlledPanel).toContainText("32/32");
  await finalDecision.click();
  await expect(controlledPanel.getByText("最终工程决策")).toBeVisible();

  await openSemantics.click();
  await expect(page.locator("#frontier-segment-panel-open_semantics")).toContainText(
    "开放世界价值继续标记为未评估",
  );
  await unsafe.click();
  await expect(page.locator("#frontier-segment-panel-unsafe")).toContainText(
    "拒绝或安全升级",
  );

  await grammar.focus();
  await grammar.press("ArrowDown");
  await expect(controlled).toBeFocused();
  await expect(controlled).toHaveAttribute("aria-selected", "true");
  await controlled.press("End");
  await expect(unsafe).toBeFocused();
  await expect(unsafe).toHaveAttribute("aria-selected", "true");
  await unsafe.press("Home");
  await expect(grammar).toBeFocused();
  await expect(grammar).toHaveAttribute("aria-selected", "true");
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
          !node.closest("details:not([open])") &&
          !node.closest("[hidden]") &&
          !node.closest('[aria-hidden="true"]') &&
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
  const mobileStory = page.locator(".hero-mobile-story");
  await expect(mobileStory).toContainText("现实任务");
  await expect(mobileStory).toContainText("治理动作");
  await expect(mobileStory).toContainText("当前结果");
  const storyBottom = await mobileStory.evaluate((node) => node.getBoundingClientRect().bottom);
  expect(storyBottom).toBeLessThanOrEqual(812);
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
  await expect(summary.getByText(/解决了 32\/32 条案例/).first()).toBeVisible();
  await expect(summary.getByText(/语义提升为 1\/12/).first()).toBeVisible();
  await expect(summary.getByText(/尚未评估：/).first()).toBeVisible();
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
  await expect(page.locator(".trajectory-tabs")).toBeHidden();
  await expect(page.locator("[data-frontier-segment-panel]")).toHaveCount(4);
  for (const panel of await page.locator("[data-frontier-segment-panel]").all()) {
    await expect(panel).toBeVisible();
  }
  await expect(page.locator("[data-frontier-state-panel]")).toHaveCount(12);
  for (const panel of await page.locator("[data-frontier-state-panel]").all()) {
    await expect(panel).toBeVisible();
  }
  await expect(page.locator("[data-frontier-segment-tabs]")).toBeHidden();
  await expect(page.locator(".state-tabs")).toHaveCount(4);
  for (const tablist of await page.locator(".state-tabs").all()) {
    await expect(tablist).toBeHidden();
  }
  const summary = page.locator(".frontier-summary");
  await expect(summary.getByText(/解决了 32\/32 条案例/).first()).toBeVisible();
  await expect(summary.getByText(/语义提升为 1\/12/).first()).toBeVisible();
  await expect(summary.getByText(/尚未评估：/).first()).toBeVisible();
  await context.close();
});

test("plain interview narrative answers the three core questions", async ({ page }) => {
  await expect(page.locator("h1")).toContainText("不能越权执行");
  for (const label of [
    "项目价值",
    "一次事故",
    "怎么变可靠",
    "何时需要模型",
    "如何验真",
    "完整证据",
  ]) {
    await expect(page.locator(".desktop-nav")).toContainText(label);
  }
  await expect(page.locator("#governed-runtime")).toContainText("执行前必须审批");
  await expect(page.locator("#governed-runtime")).toContainText("等待人工审批");
  await expect(page.locator("#q5-decision-frontier")).toContainText(
    "确定性解析器解决了 32/32",
  );
  await expect(page.locator("#q5-decision-frontier")).toContainText("开放语义场景尚未评估");
  await expect(page.locator("#five-questions")).toContainText("当前实验没有证明它比简单规则带来额外收益");
  await expect(page.locator("#evaluation-infrastructure")).toContainText(
    "这个项目实际实现了什么",
  );
});

test("hero presents three distinct canonical outcomes", async ({ page }) => {
  const metrics = page.locator(".hero-metric");
  await expect(metrics).toHaveCount(3);
  await expect(metrics.nth(0)).toContainText("冻结评测复验：未授权动作全部阻断");
  await expect(metrics.nth(1)).toContainText("冻结受控文本：确定性解析器解决");
  await expect(metrics.nth(2)).toContainText("当前开发范围：模型增益未达到门槛");
  expect(await metrics.evaluateAll((nodes) => nodes.map((node) => node.dataset.metricName))).toEqual([
    "unauthorized_action_blocked",
    "previously_uncovered_cases_resolved",
    "semantic_uplift",
  ]);
});

test("specialist abbreviations stay out of the default interview path", async ({ page }) => {
  const visibleText = await page.locator("body").evaluate((node) => node.innerText);
  for (const forbidden of [
    "F11",
    "F13",
    "F17",
    "K1",
    "Boundary G",
    "headline eligibility",
    "real-dev",
    "parser-uncovered",
    "anti-gaming triad",
  ]) {
    expect(visibleText).not.toContain(forbidden);
  }
});

test("demonstration corpus never enters the formal claim ledger", async ({ page }) => {
  await expect(page.locator("[data-trajectory-player]")).toHaveAttribute(
    "data-corpus-id",
    "interview-v1",
  );
  const ledgerText = await page.locator("#evidence-ledger").textContent();
  expect(ledgerText).not.toContain("interview-v1");
  expect(ledgerText).not.toContain("data/showcase/");
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

test("interactive controls and evidence links preserve exact lineage", async ({ page }) => {
  const controlErrors = await page.evaluate(() => {
    const controls = Array.from(document.querySelectorAll("[aria-controls]"));
    const ids = controls.map((node) => node.getAttribute("aria-controls"));
    return {
      missing: ids.filter((id) => !id || !document.getElementById(id)),
      duplicates: ids.filter((id, index) => ids.indexOf(id) !== index),
    };
  });
  expect(controlErrors).toEqual({ missing: [], duplicates: [] });

  const questions = JSON.parse(
    await readFile(new URL("../src/data/questions.json", import.meta.url), "utf8"),
  );
  const firstClaim = questions.questions.flatMap((question) => question.claims)[0];
  const source = firstClaim.source_artifacts[0];
  const claim = page.locator(`[data-claim-id="${firstClaim.claim_id}"].ledger-item`);
  await claim.locator("summary").click();
  const sourceLink = claim.getByRole("link", { name: new RegExp(source.path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  await expect(sourceLink).toHaveAttribute(
    "href",
    `https://github.com/I-ivan-x/agent-reliability-lab/blob/${source.artifact_commit}/${source.path}`,
  );
});

test("mobile chapter navigation closes after selection", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-390x844", "mobile navigation contract");
  const navigation = page.locator(".mobile-nav");
  await navigation.locator("summary").click();
  await expect(navigation).toHaveAttribute("open", "");
  await navigation.getByRole("link", { name: "项目价值" }).click();
  await expect(navigation).not.toHaveAttribute("open", "");
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
