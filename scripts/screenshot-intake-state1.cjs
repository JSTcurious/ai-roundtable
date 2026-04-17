/**
 * Automates intake through Playwright, saves a PNG when STATE 1 (prompt approval) appears.
 * Run with: PW_MODULE_DIR=/tmp/ai-roundtable-pw node scripts/screenshot-intake-state1.cjs
 */
const path = require("path");

const pwRoot = process.env.PW_MODULE_DIR || path.join(__dirname, "..", ".pw-tmp");
const { chromium } = require(path.join(pwRoot, "node_modules", "playwright"));

const OUT = process.env.SCREENSHOT_OUT || path.join(__dirname, "..", "docs", "intake-state1-live.png");
/** Use `localhost` so origin matches CRA → FastAPI CORS (`http://localhost:3000`). */
const BASE = process.env.APP_URL || "http://localhost:3000";

const APPROVAL =
  /Does this capture everything, or would you like to adjust anything\?/;

const cannedReplies = [
  "Yes — that captures it. I'm a software engineer wanting to transition into AI engineering and I want a concrete roadmap.",
  "About four years building Python backends and REST APIs; light exposure to OpenAI APIs. Target role is AI application engineer at tech companies, roughly 10 hours per week, self-funded, project-based learning.",
  "I'd like milestones, hands-on projects, and what to prioritize first. Interview-ready in about six months would be ideal.",
  "That's enough — please go ahead and frame this for the frontier models.",
];

async function waitNoTyping(page, timeoutMs) {
  await page.waitForFunction(
    () => !document.querySelector('[aria-label="Claude is typing"]'),
    null,
    { timeout: timeoutMs }
  );
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1024 } });

  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.getByLabel("What you need to figure out").fill("I want to become an AI engineer");
  await page.getByRole("button", { name: "Continue to intake" }).click();

  await page.getByRole("button", { name: "← Home" }).waitFor({ state: "visible", timeout: 120000 });

  const deadline = Date.now() + 25 * 60 * 1000;
  let replyIndex = 0;

  while (Date.now() < deadline) {
    const body = await page.textContent("body");
    if (body && APPROVAL.test(body)) {
      const tier = page.getByText("Choose roundtable depth");
      if (await tier.isVisible().catch(() => false)) {
        throw new Error("Tier selector should be hidden in STATE 1, but it was visible.");
      }
      await page.locator("text=Does this capture everything, or would you like to adjust anything?").scrollIntoViewIfNeeded();
      await page.screenshot({ path: OUT, fullPage: true });
      await browser.close();
      // eslint-disable-next-line no-console
      console.log("OK", OUT);
      return;
    }

    await waitNoTyping(page, 300000);
    await page.waitForTimeout(400);

    const chipPatterns = [/that'?s enough/i, /let'?s just go/i, /let'?s go/i, /skip the questions/i];
    let clicked = false;
    for (const re of chipPatterns) {
      const btn = page.getByRole("button", { name: re });
      if (await btn.first().isVisible().catch(() => false)) {
        await btn.first().click();
        clicked = true;
        break;
      }
    }
    if (clicked) continue;

    const reply = page.getByLabel("Your message");
    if (await reply.isVisible().catch(() => false)) {
      const text = cannedReplies[Math.min(replyIndex, cannedReplies.length - 1)];
      replyIndex += 1;
      await reply.fill(text);
      await page.getByRole("button", { name: "Send message" }).click();
      continue;
    }

    await page.waitForTimeout(1500);
  }

  await browser.close();
  throw new Error("Timed out waiting for prompt approval (STATE 1).");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
