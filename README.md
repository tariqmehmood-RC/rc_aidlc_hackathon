# Idea board

A small React and TypeScript app (Vite) for capturing short ideas. Add an idea, see the list newest first, delete one. Ideas are kept in the browser's `localStorage`; there is no backend.

The repository is also set up for working with Kiro agents the AI-DLC way. Read [`AGENTS.md`](AGENTS.md) before you start.

## Quick start

Requires Node.js 22.22 or later (or 24.15+), and npm. The test tools (Vitest, jsdom) need it.

```sh
git clone https://github.com/tariqmehmood-RC/rc_aidlc_hackathon.git
cd rc_aidlc_hackathon
npm install
npm run dev
```

Open **http://localhost:5173/absproxy/5173/**. The `/absproxy/5173/` path is required: the dev server is configured for the workshop IDE's proxy (see "Running behind the workshop IDE").

## Checks

| Command | What it does |
|---|---|
| `npm test` | Unit and component tests (Vitest, jsdom, Testing Library) |
| `npm run lint` | ESLint |
| `npm run build` | Type check (`tsc -b`) and production build |
| `npm run check` | Lint, secret scan (gitleaks) and static analysis (Semgrep) |
| `npm run test:browser` | End-to-end check in headless Chrome through the Playwright MCP server. Needs `npm run dev` running |

`npm run check` and `npm run test:browser` need three machine-level tools: gitleaks 8.30.1, Semgrep 1.186.0 and Google Chrome.
- On the workshop machine (Amazon Linux 2023): `npm run setup:tools` installs all three at pinned versions. It is safe to re-run.
- Elsewhere: install [gitleaks](https://github.com/gitleaks/gitleaks#installing), [Semgrep](https://semgrep.dev/docs/getting-started/) (`pipx install semgrep==1.186.0` or `uv tool install semgrep==1.186.0`) and Google Chrome yourself.

## How we work with agents (AI-DLC)

A person owns the gates. Agents do the work between them. The full rules are in [`AGENTS.md`](AGENTS.md).

1. Write a brief in `docs/brd-<feature>.md`.
2. Switch to the **spec** agent. It writes `.kiro/specs/<feature>/`. You approve the spec.
3. Switch to the **build** agent. It builds on a `feat/<name>` branch, with a test and a commit per task, then checks the flow in a browser.
4. Run `npm run check`, then switch to the **reviewer** agent. It reports findings with file and line.
5. A person merges.

The agents live in `.kiro/agents/`. Pick one in the chat panel's agent selector, beside the model picker.

## Kiro setup in this repo

| Path | Purpose |
|---|---|
| `AGENTS.md` | Rules any agent reads |
| `.kiro/steering/` | Standing rules: product, tech, structure, git workflow, testing, code style, verify-first |
| `.kiro/specs/` | Specs, one folder per feature |
| `.kiro/agents/` | `spec`, `build`, `reviewer` |
| `.kiro/skills/` | `code-review` (reviews `.ts`/`.tsx` files), `skill-creator`, and AWS Agent Toolkit skills |
| `.kiro/hooks/lint-on-save.json` | Runs `npm run lint` when a `.ts`/`.tsx` file is saved |
| `.kiro/settings/mcp.json` | MCP servers: `playwright` (needs Chrome) and `aws-mcp` (needs `uv`) |

After cloning, open the folder in Kiro and trust it when asked, so Kiro loads the steering, agents, hooks and MCP servers.

## Project layout

See [`.kiro/steering/structure.md`](.kiro/steering/structure.md). App code is in `src/ideas/`, with tests beside each file.

## Running behind the workshop IDE

The workshop IDE runs on a lab machine behind CloudFront, so `vite.config.ts` sets two things for the dev server only:
- `base: '/absproxy/5173/'`, because the IDE's `/absproxy/<port>/` route keeps the path prefix. Do not use `/proxy/5173/`: it strips the prefix, and the page loads blank.
- `server.allowedHosts: ['.cloudfront.net']`, so Vite answers to the proxy's hostname. Do not use `allowedHosts: true`: it turns the host check off.

Through the IDE, open `https://<your-cloudfront-host>/absproxy/5173/`. Production builds use `base: '/'` and are unaffected.

## Rules for this project
- Synthetic data only. No business, customer or personal data.
- No secrets in code, prompts, steering or the repo.
- AWS work stays in `us-east-1`. Keep Amazon Bedrock under one request per second.
