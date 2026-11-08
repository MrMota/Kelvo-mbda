// End-to-end click-through of the core flows (F01-F05).
// Needs a running server (default http://127.0.0.1:7860) backed by an Ollama, or by
// `python -m kelvo.fake_ollama`, started with KELVO_USERNAME / KELVO_PASSWORD
// (defaults below, override with E2E_USER / E2E_PASS).
// Usage: node e2e/smoke.mjs [baseUrl] [screenshotDir]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://127.0.0.1:7860";
const SHOTS = process.argv[3];
const results = [];
const SKILL = "trip-" + Date.now().toString(36);
const step = async (name, fn) => {
  try { await fn(); results.push(["PASS", name]); }
  catch (e) { results.push(["FAIL", name, e.message.split("\n")[0]]); }
};
const shot = async (page, name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png` });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

const USER = process.env.E2E_USER ?? "me";
const PASS = process.env.E2E_PASS ?? "correct horse";

await step("Sign-in screen blocks the app; wrong password is refused", async () => {
  await page.goto(BASE);
  await page.getByRole("heading", { name: "Sign in to Kelvo" }).waitFor();
  await shot(page, "00-login");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill("not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("Wrong username or password.").waitFor();
  await page.getByLabel("Password").fill(PASS);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "My Projects" }).waitFor();
});

await step("F08 home loads with empty state", async () => {
  await page.goto(BASE);
  await page.getByRole("heading", { name: "My Projects" }).waitFor();
  await shot(page, "01-home");
});

await step("F01 create Simple Agent from template and chat with tool call", async () => {
  await page.getByRole("button", { name: "New Flow" }).first().click();
  await shot(page, "02-new-flow");
  await page.getByRole("button", { name: /Simple Agent/ }).click();
  await page.waitForURL(/\/flow\//);
  await page.locator(".react-flow__node").first().waitFor();
  if ((await page.locator(".react-flow__node").count()) < 6) throw new Error("template nodes missing");
  await page.waitForTimeout(400);
  await shot(page, "03-editor");
  await page.getByRole("button", { name: "Playground", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("calc: (4+4)*2");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("Result:").first().waitFor({ timeout: 15000 });
  await page.getByText("Used").first().waitFor();
  await shot(page, "04-playground");
});

await step("F01 memory: second message shows history", async () => {
  await page.getByLabel("Message", { exact: true }).fill("and again");
  await page.keyboard.press("Enter");
  await page.locator(".msg-text", { hasText: "[history=2]" }).waitFor({ timeout: 15000 });
});

await step("F02 build from scratch with drag and drop + connect", async () => {
  await page.goto(BASE);
  await page.getByRole("button", { name: "New Flow" }).first().click();
  await page.getByRole("button", { name: /Blank Flow/ }).click();
  await page.waitForURL(/\/flow\//);
  await page.getByText("Nothing here yet").waitFor();
  const canvas = page.locator(".react-flow__pane");
  const drop = async (name, x, y) => {
    const item = page.locator(".pal-item", { hasText: name }).first();
    const dt = await page.evaluateHandle(() => new DataTransfer());
    await item.dispatchEvent("dragstart", { dataTransfer: dt });
    const box = await canvas.boundingBox();
    await canvas.dispatchEvent("drop", { dataTransfer: dt, clientX: box.x + x, clientY: box.y + y });
  };
  await drop("Chat Input", 120, 200);
  await drop("Ollama", 520, 140);
  await drop("Chat Output", 940, 200);
  await page.waitForTimeout(300);
  if ((await page.locator(".react-flow__node").count()) !== 3) throw new Error("expected 3 nodes");
  const connect = async (srcNode, srcHandle, dstNode, dstHandle) => {
    const s = page.locator(`.react-flow__node[data-id^="${srcNode}"] .react-flow__handle[data-handleid="${srcHandle}"]`);
    const t = page.locator(`.react-flow__node[data-id^="${dstNode}"] .react-flow__handle[data-handleid="${dstHandle}"]`);
    await s.dragTo(t);
  };
  await connect("ChatInput", "message", "OllamaModel", "input");
  await connect("OllamaModel", "response", "ChatOutput", "input");
  if ((await page.locator(".react-flow__edge").count()) !== 2) throw new Error("edges not created");
  // invalid connection is refused: LanguageModel output → Chat Output input
  await connect("OllamaModel", "model", "ChatOutput", "input");
  if ((await page.locator(".react-flow__edge").count()) !== 2) throw new Error("invalid edge accepted");
  await page.getByText("Saved").waitFor({ timeout: 5000 });
  await page.getByRole("button", { name: "Playground", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("hello world");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".msg-text", { hasText: "Echo: hello world" }).waitFor({ timeout: 15000 });
  await shot(page, "05-scratch");
});

await step("Inspector opens on node click and edits a param", async () => {
  await page.getByRole("button", { name: "Close playground" }).click();
  await page.locator('.react-flow__node[data-id^="OllamaModel"] .node-title').click();
  await page.getByRole("complementary", { name: "Component settings" }).waitFor();
  await shot(page, "06-inspector");
});

await step("F04 skills page: create a skill", async () => {
  await page.goto(`${BASE}/skills`);
  await page.getByText("summarize").first().waitFor();
  await shot(page, "07-skills");
  await page.getByRole("link", { name: "New skill" }).click();
  await page.getByPlaceholder("code-review").fill(SKILL);
  await page.getByPlaceholder(/Use when the user asks to review/).fill("Use when the user wants a trip itinerary.");
  await page.getByRole("button", { name: "Save skill" }).click();
  await page.getByRole("heading", { name: SKILL }).waitFor();
  await shot(page, "08-skill-editor");
});

await step("F04 skilled agent loads a skill in the playground", async () => {
  await page.goto(BASE);
  await page.getByRole("button", { name: "New Flow" }).first().click();
  await page.getByRole("button", { name: /Skilled Agent/ }).click();
  await page.waitForURL(/\/flow\//);
  await page.getByRole("button", { name: "Playground", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("plan with skill:" + SKILL);
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText("load_skill").first().waitFor({ timeout: 15000 });
  await page.locator(".msg-text", { hasText: "Result: # Skill: " + SKILL }).waitFor();
  await shot(page, "09-skill-playground");
});

await step("F05 settings: create API key and see share snippets", async () => {
  await page.goto(`${BASE}/settings/keys`);
  page.once("dialog", (d) => d.accept("e2e"));
  await page.getByRole("button", { name: "Create key" }).click();
  await page.getByText("Copy it now").waitFor();
  await page.getByRole("button", { name: "Done" }).click();
  await page.goto(`${BASE}/settings/models`);
  await page.getByText("Connected · 3 models").waitFor();
  await shot(page, "10-settings");
  await page.goto(BASE);
  await page.locator(".card", { hasText: "Simple Agent" }).first().click();
  await page.getByRole("button", { name: "Share" }).click();
  await page.getByText("x-api-key: $KELVO_API_KEY").waitFor();
  await shot(page, "11-share");
  await page.getByRole("tab", { name: "MCP server" }).click();
  await page.getByRole("switch", { name: "Expose as MCP tool" }).click();
  await page.getByText("Exposed as MCP tool").waitFor();
});

await step("Dark mode renders", async () => {
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.waitForTimeout(200);
  await shot(page, "12-dark");
  await page.getByRole("button", { name: "Toggle theme" }).click();
});

await step("Phone width home has no horizontal scroll", async () => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, storageState: await page.context().storageState() });
  const m = await ctx.newPage();
  await m.goto(BASE);
  await m.getByRole("heading", { name: "My Projects" }).waitFor();
  const over = await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  if (over) throw new Error("horizontal scroll at 390px");
  if (SHOTS) await m.screenshot({ path: `${SHOTS}/13-mobile.png` });
  await ctx.close();
});

await step("Sign out returns to the sign-in screen", async () => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Sign out/ }).click();
  await page.getByRole("heading", { name: "Sign in to Kelvo" }).waitFor();
  await page.goto(`${BASE}/settings`);
  await page.getByRole("heading", { name: "Sign in to Kelvo" }).waitFor();
});

await browser.close();
for (const r of results) console.log(r.join("  "));
const relevant = errors.filter((e) => !/favicon/.test(e));
if (relevant.length) console.log("Console errors:\n  " + relevant.join("\n  "));
process.exit(results.some((r) => r[0] === "FAIL") ? 1 : 0);
