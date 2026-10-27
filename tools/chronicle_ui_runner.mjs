import { chromium } from "@playwright/test";

let browser;

function fail(message, details = {}) {
  return { status: "failed", failure: { code: "ui_driver_failed", message, details } };
}

function valueFrom(input, key) {
  if (!(key in input)) throw new Error(`Scenario input is missing ${key}.`);
  return input[key];
}

function roleLocator(page, action, input) {
  const locator = page.getByRole(action.role, action.name ? { name: action.name } : undefined);
  return action.textFrom ? locator.filter({ hasText: String(valueFrom(input, action.textFrom)) }) : locator;
}

async function inspectPage(page, url, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(url, { waitUntil: "domcontentloaded" });
  const viewportFacts = await page.evaluate(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
    documentWidth: document.documentElement.scrollWidth,
    documentHeight: document.documentElement.scrollHeight,
  }));
  return {
    status: "observed",
    proof: false,
    page: {
      url: page.url(),
      title: await page.title(),
      browser: "chromium",
      browserVersion: browser.version(),
      viewport: viewportFacts,
      horizontalOverflow: viewportFacts.documentWidth > viewportFacts.width,
      accessibleTree: (await page.locator("body").ariaSnapshot()).slice(0, 12000),
    },
  };
}

async function runScenario(request) {
  const { scenario, input, url, viewport, operation } = request;
  const context = await browser.newContext({ viewport, locale: "zh-CN" });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const observedResponses = [];
  const targetQuery = new URLSearchParams({ q: String(input.query) }).get("q");
  page.on("response", (response) => {
    const request = response.request();
    const target = new URL(operation.path, url);
    const actual = new URL(response.url());
    if (request.method() === operation.method
      && actual.pathname === target.pathname
      && actual.searchParams.get("q") === targetQuery) {
      observedResponses.push(response.json().then((payload) => ({
        operationId: operation.operationId,
        method: request.method(),
        path: actual.pathname,
        status: response.status(),
        payload,
      })).catch(() => ({
        operationId: operation.operationId,
        method: request.method(),
        path: actual.pathname,
        status: response.status(),
        payload: null,
      })));
    }
  });

  try {
    const startedAt = performance.now();
    await page.goto(url, { waitUntil: "domcontentloaded" });
    const pageReadyAt = performance.now();
    const stepResults = [];
    for (const action of scenario.actions) {
      if (action.action === "press") {
        await page.keyboard.press(action.key);
      } else if (action.action === "fill") {
        const locator = page.getByRole(action.role, { name: action.name });
        await locator.fill(String(valueFrom(input, action.valueFrom)));
      } else if (action.action === "expect-focused") {
        const locator = page.getByRole(action.role, { name: action.name });
        await locator.waitFor({ state: "visible" });
        const focused = await locator.evaluate((element) => element === document.activeElement);
        if (!focused) throw new Error(`The ${action.role} control did not receive keyboard focus.`);
      } else if (action.action === "expect-visible") {
        await roleLocator(page, action, input).waitFor({ state: "visible" });
      } else {
        throw new Error(`Unsupported registered UI action ${action.action}.`);
      }
      stepResults.push({
        action: action.action,
        ...(action.role ? { targetRole: action.role } : {}),
        status: "asserted",
      });
    }

    const checks = [];
    for (const assertion of scenario.assertions) {
      if (assertion.kind === "operation-observed") {
        const responses = await Promise.all(observedResponses);
        const observed = responses.find((item) => item.operationId === assertion.operationId
          && item.status >= 200
          && item.status < 300
          && Array.isArray(item.payload)
          && item.payload.some((entry) => entry.id === input.expectedNoteId && entry.headline === input.expectedHeadline));
        if (!observed) {
          throw new Error(`Browser operation ${assertion.operationId} did not return the expected note identity.`);
        }
        checks.push({
          kind: assertion.kind,
          status: "passed",
          operation: {
            operationId: observed.operationId,
            method: observed.method,
            path: observed.path,
            status: observed.status,
            matchedNoteId: input.expectedNoteId,
          },
        });
      } else if (assertion.kind === "no-horizontal-overflow") {
        const dimensions = await page.evaluate(() => ({
          viewportWidth: window.innerWidth,
          documentWidth: document.documentElement.scrollWidth,
        }));
        if (dimensions.documentWidth > dimensions.viewportWidth) {
          throw new Error(`Page overflows horizontally by ${dimensions.documentWidth - dimensions.viewportWidth}px.`);
        }
        checks.push({ kind: assertion.kind, status: "passed", ...dimensions });
      } else {
        throw new Error(`Unsupported registered UI assertion ${assertion.kind}.`);
      }
    }

    const result = roleLocator(page, { role: "option", textFrom: "expectedHeadline" }, input);
    const interactionFinishedAt = performance.now();
    return {
      status: "asserted",
      viewport,
      variantId: request.variantId,
      timings: {
        pageReadyMs: Math.round((pageReadyAt - startedAt) * 100) / 100,
        interactionMs: Math.round((interactionFinishedAt - pageReadyAt) * 100) / 100,
        totalMs: Math.round((interactionFinishedAt - startedAt) * 100) / 100,
      },
      steps: stepResults,
      assertions: checks,
      visibleResult: { role: "option", textMatched: await result.isVisible() },
    };
  } finally {
    await context.close();
  }
}

function percentile(values, fraction) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(sorted.length * fraction) - 1)];
}

async function measureScenario(request) {
  const repeat = Number(request.repeat);
  if (!Number.isInteger(repeat) || repeat < 2 || repeat > 30) {
    throw new Error("UI measurement repeat must be an integer from 2 to 30.");
  }
  const samples = [];
  let last = null;
  for (let index = 0; index < repeat; index += 1) {
    last = await runScenario(request);
    samples.push(last.timings);
  }
  const totalSamples = samples.map((sample) => sample.totalMs);
  return {
    status: "measured",
    browser: "chromium",
    browserVersion: browser.version(),
    platform: process.platform,
    runMode: request.runMode,
    runModeSource: "caller-reported",
    viewport: last.viewport,
    variantId: request.variantId,
    repeat,
    datasetSize: request.datasetSize ?? null,
    datasetSizeSource: "caller-reported",
    metric: "navigation-to-visible-result",
    samples,
    samplesMs: totalSamples,
    p50Ms: percentile(totalSamples, 0.5),
    p95Ms: percentile(totalSamples, 0.95),
    assertions: last.assertions,
    visibleResult: last.visibleResult,
  };
}

async function main() {
  const request = JSON.parse(await readStdin());
  browser = await chromium.launch({ headless: true });
  if (request.mode === "inspect") {
    const context = await browser.newContext({ viewport: request.viewport, locale: "zh-CN" });
    try {
      const page = await context.newPage();
      return await inspectPage(page, request.url, request.viewport);
    } finally {
      await context.close();
    }
  }
  if (request.mode === "scenario") return await runScenario(request);
  if (request.mode === "measure") return await measureScenario(request);
  return fail("Unsupported UI runner mode.", { mode: request.mode });
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

try {
  const result = await main();
  process.stdout.write(`${JSON.stringify(result)}\n`);
  if (result.status === "failed") process.exitCode = 1;
} catch (error) {
  process.stdout.write(`${JSON.stringify(fail(error.message || String(error)))}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close();
}
