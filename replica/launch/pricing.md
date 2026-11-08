# Pricing

## What the market charges

Read 2026-11-08. Pricing *pages* are blocked from the build sandbox, so price figures are **to read** before you publish yours. Model and licence come from each project's README or docs on GitHub, read the same day.

| product | model (from README / docs) | source | price figures |
| --- | --- | --- | --- |
| The original | Open source, MIT licence. Paid enterprise support sold by IBM ("IBM Elite Support for Langflow"); a hosted offering exists | [LICENSE](https://github.com/langflow-ai/langflow/blob/main/LICENSE), [support docs](https://github.com/langflow-ai/langflow/blob/main/docs/docs/Support/luna-for-langflow.mdx) | to read |
| Flowise | Open source with a "Portions … licensed as follows" clause in its LICENSE; self-host or Flowise Cloud | [README](https://github.com/FlowiseAI/Flowise/blob/main/README.md), [LICENSE](https://github.com/FlowiseAI/Flowise/blob/main/LICENSE.md) | to read: flowiseai.com |
| Dify | Self-host free; Dify Cloud with plans and usage allowances | [README](https://github.com/langgenius/dify/blob/main/README.md) | to read: dify.ai/pricing |
| n8n | "Fair-code" (Sustainable Use Licence + Enterprise Licence); self-host or cloud; enterprise licences sold separately | [README](https://github.com/n8n-io/n8n/blob/master/README.md) | to read: n8n.io/pricing |

Pattern: **the builder itself is free to self-host everywhere.** Money comes from a hosted cloud, enterprise features (SSO, roles, audit), or support.

## What users said about price and billing

`feedback.md`: **0 rows** about price or billing in 225 GitHub issues. That says more about the source (bug trackers rarely carry billing complaints) than about the market. Re-check once review sites are reachable.

What the issues *do* show is where the willingness to pay is: **SSO and team access control are the two most-voted requests** (2 + 4 issues, 153 votes; `fixes.md` U2). One requester could not deploy self-hosted "without Single Sign On (SSO)" because of security review ([#2855](https://github.com/langflow-ai/langflow/issues/2855)). That is a budget-holder's problem.

## The model

Open core, sold per server, not per seat.

| tier | for | price | what's in it | status |
| --- | --- | --- | --- | --- |
| **Community** | anyone building on their own machine or server | **$0** | everything built today: canvas, agents, tools, skills, local RAG, Playground, REST API, MCP server | available |
| **Team** | a company sharing one Kelvo internally | **$49 / server / month**, or **$490 / year** (2 months free) | SSO (OIDC), roles, shared flows and projects, audit log | **not built**: waitlist only |
| **Support** | companies rolling it out on their own infrastructure | quoted | response-time commitment, deployment help | by request |

Why these numbers: they are a **starting hypothesis to test with the waitlist**, not a researched price. They could not be checked against competitors' figures from the sandbox. Flat per server avoids the surprise per-seat jumps that make self-hosted tools hard to budget. Revisit after reading the four pricing pages above and after 20 conversations with waitlist teams. Ask each team: "Would your company pay $49 a month for this?"

**Licence decision needed:** the README says MIT but the repo has no LICENSE file. Open core works with MIT (the Team features live in a separate, commercially licensed package) or with a source-available licence. Pick before launch; the landing page makes no licence claim until then.

## Billing done right (when Team ships)

- Cancel in one click from the billing page; access lasts to the end of the period.
- Renewal email 7 days before every annual renewal, with the amount and a cancel link.
- Flat price per server. Adding people never changes the bill.
- Licence key works offline (signed, checked locally) so air-gapped servers aren't punished.
- Invoices with company name and VAT number from the first payment.

## Stripe (create these when Team is real, not before)

| product | price id (suggested) | amount | interval |
| --- | --- | --- | --- |
| Kelvo Team | `team_monthly` | 4900 USD cents | month |
| Kelvo Team | `team_annual` | 49000 USD cents | year |

Use Stripe Checkout + the Customer Portal (which gives one-click cancel). Set `tax_behavior` and enable Stripe Tax if you sell to the EU/UK.
