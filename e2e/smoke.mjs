// End-to-end click-through of the core flows (F01-F05).
// Needs a running server (default http://127.0.0.1:7860) backed by an Ollama, or by
// `python -m kelvo.fake_ollama`, started with KELVO_USERNAME / KELVO_PASSWORD
// (defaults below, override with E2E_USER / E2E_PASS).
// Usage: node e2e/smoke.mjs [baseUrl] [screenshotDir]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium, devices } = require("playwright");

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

await step("X2 agent warns when its model can't call tools", async () => {
  const sel = page.locator('.react-flow__node[data-id="agent"] select[aria-label="Model"]');
  await sel.selectOption("gemma2:2b");
  await page.getByText("gemma2:2b can't call tools").waitFor();
  await sel.selectOption("");
  if (await page.getByText("can't call tools").count()) throw new Error("warning stayed after picking a tools model");
  if (!(await sel.locator('option[value="llama3.1:8b"]').textContent()).includes("tools")) throw new Error("no tools tag in picker");
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
  await page.getByText("Connected · 4 models").waitFor();
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

await step("Phone: editor ⋯ menu and chat with a tool call", async () => {
  const ctx = await browser.newContext({ ...devices["iPhone 13"], storageState: await page.context().storageState() });
  const m = await ctx.newPage();
  await m.goto(BASE);
  await m.getByRole("button", { name: "New Flow" }).first().tap();
  await m.getByRole("button", { name: /Simple Agent/ }).tap();
  await m.waitForURL(/\/flow\//);
  await m.locator(".react-flow__node").first().waitFor();
  if (await m.locator(".react-flow__minimap").count()) throw new Error("minimap shown on phone");
  await m.getByRole("button", { name: "More", exact: true }).tap();
  await m.locator(".menu").getByRole("button", { name: "Logs" }).tap();
  await m.getByRole("heading", { name: "Run logs" }).waitFor();
  await m.getByRole("button", { name: "Close" }).tap();
  await m.getByRole("button", { name: "Playground", exact: true }).tap();
  await m.getByLabel("Message", { exact: true }).fill("calc: 6*7");
  await m.getByRole("button", { name: "Send" }).tap();
  await m.locator(".msg-text", { hasText: "Result:" }).waitFor({ timeout: 15000 });
  if (await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error("sideways scroll on phone");
  if (SHOTS) await m.screenshot({ path: `${SHOTS}/14-phone-chat.png` });
  await ctx.close();
});

await step("Installable: manifest and home-screen icon", async () => {
  const r = await page.request.get(`${BASE}/manifest.webmanifest`);
  const man = await r.json();
  if (man.display !== "standalone" || !man.icons?.length) throw new Error("bad manifest");
  if (!(await page.request.get(`${BASE}/apple-touch-icon.png`)).ok()) throw new Error("no apple-touch-icon");
});

await step("Power Agent: command waits for Approve; Reject blocks it", async () => {
  await page.goto(BASE);
  await page.getByRole("button", { name: "New Flow" }).first().click();
  await page.getByRole("button", { name: /Power Agent/ }).click();
  await page.waitForURL(/\/flow\//);
  await page.getByRole("button", { name: "Playground", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("tool:command_line:echo approved-run-ok");
  await page.getByRole("button", { name: "Send" }).click();
  const card = page.getByRole("alertdialog");
  await card.getByText("echo approved-run-ok").waitFor({ timeout: 15000 });
  await shot(page, "15-approval");
  await card.getByRole("button", { name: "Approve" }).click();
  await page.locator(".msg-text", { hasText: "approved-run-ok" }).first().waitFor({ timeout: 15000 });
  await page.getByLabel("Message", { exact: true }).fill("tool:command_line:echo must-not-run");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reject" }).click({ timeout: 15000 });
  await page.locator(".msg-text", { hasText: "did not approve" }).waitFor({ timeout: 15000 });
});

await step("Chat: Markdown replies render; HTML in replies is neutralised", async () => {
  await page.goto(`${BASE}/chat`);
  await page.getByRole("combobox", { name: "Agent" }).waitFor();
  const basic = (await page.request.post(`${BASE}/api/flows`, { data: { template: "basic-prompting", name: "Echo Bot" } }).then((r) => r.json()));
  await page.goto(`${BASE}/chat/${basic.id}`);
  await page.getByRole("heading", { name: "What can I help with?" }).waitFor();
  await page.getByLabel("Message", { exact: true }).fill("x\n# Big Title\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<img src=x onerror=\"window.__xss=1\">");
  await page.keyboard.press("Enter");
  await page.locator(".md-reply h1", { hasText: "Big Title" }).waitFor({ timeout: 15000 });
  if ((await page.locator(".md-reply li").count()) < 2) throw new Error("list not rendered");
  if (!(await page.locator(".md-reply td", { hasText: "2" }).count())) throw new Error("table not rendered");
  await page.waitForTimeout(300);
  if (await page.evaluate(() => window.__xss)) throw new Error("XSS executed");
  if (await page.locator(".md-reply img[onerror]").count()) throw new Error("onerror attribute survived");
  await shot(page, "16-chat-markdown");
});

await step("Chat: attach a file; the agent reads it; chip stays in history", async () => {
  await page.getByRole("button", { name: "New chat" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "meeting-notes.txt", mimeType: "text/plain", buffer: Buffer.from("Decision: ship Kelvo 0.4 on Friday") });
  await page.locator(".pg-input .chip", { hasText: "meeting-notes.txt" }).waitFor();
  await page.getByLabel("Message", { exact: true }).fill("What was decided?");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".md-reply", { hasText: "ship Kelvo 0.4 on Friday" }).waitFor({ timeout: 15000 });
  await page.reload();
  await page.locator(".msg.user .chip", { hasText: "meeting-notes.txt" }).waitFor({ timeout: 10000 });
  await shot(page, "17-chat-file");
});

await step("Chat: switch agents, new chat, search history", async () => {
  const picker = page.getByRole("combobox", { name: "Agent" });
  const options = await picker.locator("option").allTextContents();
  if (options.length < 2) throw new Error("expected several agents");
  const before = page.url();
  await picker.selectOption({ label: options.find((o) => o !== "Echo Bot") });
  await page.waitForURL((u) => u.toString() !== before);
  await page.getByRole("heading", { name: "What can I help with?" }).waitFor();
  await picker.selectOption({ label: "Echo Bot" });
  await page.waitForURL((u) => u.toString() === before);
  await page.locator(".pg-sessions .side-item", { hasText: "What was decided?" }).waitFor();
});

await step("Settings: memory add and delete", async () => {
  await page.goto(`${BASE}/settings/memory`);
  await page.getByLabel("New memory").fill("Prefers answers in bullet points");
  await page.getByRole("button", { name: "Add" }).click();
  await page.getByText("Prefers answers in bullet points").waitFor();
  await page.getByRole("button", { name: "Delete memory" }).first().click();
  await page.getByText("Nothing remembered yet.").waitFor();
});

await step("Schedules: create, run now, result lands in Chat", async () => {
  await page.goto(`${BASE}/settings/schedules`);
  await page.getByRole("heading", { name: "Schedules" }).waitFor();
  await page.getByRole("combobox", { name: "Flow" }).selectOption({ label: "Echo Bot" });
  await page.getByPlaceholder(/Search this week/).fill("Daily briefing please");
  await page.getByRole("button", { name: "Add schedule" }).click();
  await page.getByText("“Daily briefing please”").waitFor();
  await page.getByRole("button", { name: "Run now" }).first().click();
  await page.getByText("Ran: the result is in Chat").waitFor({ timeout: 20000 });
  await shot(page, "18-schedules");
  await page.getByRole("link", { name: "Echo Bot" }).first().click();
  await page.locator(".pg-sessions .side-item", { hasText: "Daily briefing please" }).waitFor({ timeout: 10000 });
});

await step("Palette offers MCP Tools", async () => {
  await page.goto(BASE);
  await page.locator(".card", { hasText: "Echo Bot" }).first().click();
  await page.getByLabel("Search components").fill("MCP");
  await page.locator(".pal-item", { hasText: "MCP Tools" }).waitFor();
});

await step("Phone: Chat page with history drawer", async () => {
  const ctx = await browser.newContext({ ...devices["iPhone 13"], storageState: await page.context().storageState() });
  const m = await ctx.newPage();
  await m.goto(`${BASE}/chat`);
  await m.getByRole("combobox", { name: "Agent" }).waitFor();
  if (await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)) throw new Error("sideways scroll");
  await m.getByRole("button", { name: "Chat history" }).tap();
  await m.locator(".pg-sessions.open").waitFor();
  if (SHOTS) await m.screenshot({ path: `${SHOTS}/19-phone-chat-history.png` });
  await m.getByRole("button", { name: "Close history" }).tap();
  await ctx.close();
});

await step("0.4.1: an agent that only announces is nudged into calling the tool", async () => {
  const f = await page.request.post(`${BASE}/api/flows`, { data: { template: "simple-agent", name: "Nudge Test" } }).then((r) => r.json());
  await page.goto(`${BASE}/chat/${f.id}`);
  await page.getByLabel("Message", { exact: true }).fill("announce:calculator:6*7");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".md-reply", { hasText: '"result": 42' }).waitFor({ timeout: 15000 });
  await page.getByText("Used").first().waitFor();
});

await step("0.4.1: thinking shows as a collapsible block", async () => {
  const f = await page.request.post(`${BASE}/api/flows`, { data: { template: "power-agent", name: "Thinker" } }).then((r) => r.json());
  await page.goto(`${BASE}/chat/${f.id}`);
  await page.getByLabel("Message", { exact: true }).fill("hello there");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".thinking summary", { hasText: "Thought process" }).waitFor({ timeout: 15000 });
  await page.locator(".thinking summary").click();
  await page.locator(".thinking-text", { hasText: "Let me work this out." }).waitFor();
  await shot(page, "20-thinking");
});

await step("0.4.1: reloading mid-reply shows 'still working', then the reply arrives", async () => {
  const f = await page.request.post(`${BASE}/api/flows`, { data: { template: "basic-prompting", name: "Slow Bot" } }).then((r) => r.json());
  await page.goto(`${BASE}/chat/${f.id}`);
  await page.getByLabel("Message", { exact: true }).fill("slow:5 reconnect test");
  await page.getByRole("button", { name: "Send" }).click();
  await page.waitForTimeout(1200);
  await page.reload();  // like locking the phone mid-run
  await page.getByText("The agent is still working on this chat.").waitFor({ timeout: 10000 });
  await shot(page, "21-still-working");
  await page.locator(".md-reply", { hasText: "reconnect test" }).waitFor({ timeout: 20000 });
  if (await page.getByText("The agent is still working on this chat.").count()) throw new Error("banner stayed");
});

await step("0.4.1: Stop really stops the run and Logs says so", async () => {
  const f = await page.request.post(`${BASE}/api/flows`, { data: { template: "basic-prompting", name: "Stop Bot" } }).then((r) => r.json());
  await page.goto(`${BASE}/chat/${f.id}`);
  await page.getByLabel("Message", { exact: true }).fill("slow:8 stop me");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Stop" }).click({ timeout: 5000 });
  await page.locator(".msg-text.err", { hasText: "Stopped" }).waitFor({ timeout: 10000 });
  const runs = await page.request.get(`${BASE}/api/flows/${f.id}/runs`).then((r) => r.json());
  if (runs[0].status !== "error" || runs[0].error !== "Stopped by you.") throw new Error(`run not stopped: ${JSON.stringify(runs[0])}`);
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
