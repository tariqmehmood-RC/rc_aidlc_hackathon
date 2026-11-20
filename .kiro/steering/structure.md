# Structure

## Layout
```
idea-board/
├── AGENTS.md              Rules any agent reads; the AI-DLC workflow and gates
├── README.md              How to set up, run and check the project
├── .kiro/
│   ├── steering/          Standing rules (product, tech, structure, git, testing, code style, verify-first)
│   ├── specs/<feature>/   requirements.md, design.md, tasks.md, one folder per feature
│   ├── agents/            spec.md, build.md, reviewer.md (roles with their own tools and permissions)
│   ├── skills/            code-review, skill-creator, and vendored AWS Agent Toolkit skills
│   ├── hooks/             lint-on-save.json
│   └── settings/mcp.json  MCP servers: playwright, aws-mcp
├── docs/
│   ├── brd-<feature>.md   Briefs a person writes before a spec
│   ├── reviews/           Code-review skill output
│   └── screenshots/       Browser-check screenshots
├── scripts/               setup-dev-tools.sh, browser-check.mjs, mcp-client.mjs
├── index.html             Vite entry. Mounts #root, loads /src/main.tsx
├── vite.config.ts         Vite and Vitest config (proxy base, allowedHosts, jsdom)
├── eslint.config.js       ESLint flat config
├── tsconfig*.json         TypeScript config (app and Node)
├── .gitleaks.toml         Secret-scan config
├── public/                Static files served as-is (favicon.svg)
└── src/
    ├── main.tsx           React root. Renders <App /> in StrictMode
    ├── App.tsx            Renders the IdeaBoard
    ├── App.css            Board styles
    ├── index.css          Global styles and colour tokens
    ├── ideas/             The idea board feature: types, validation, storage, hook, components, tests
    └── test/setup.ts      Vitest setup (jest-dom matchers, localStorage reset)
```
Generated and ignored by git: `node_modules/`, `dist/`, `.playwright-mcp/`, `*.local`, `*.log`.

## Conventions
- All application code goes in `src/`. Config files stay at the repo root.
- Entry flow: `index.html` → `src/main.tsx` → `src/App.tsx` → `src/ideas/IdeaBoard.tsx`.
- Group code by feature (`src/ideas/`). Put shared pieces in `src/components/`, `src/hooks/` and `src/lib/` only when more than one feature uses them. Do not create these folders ahead of need.
- Components are function components in `.tsx` files, named after the component in PascalCase (`IdeaList.tsx`). Tests sit beside the code as `<name>.test.ts(x)`.
- Import bundled assets through JS imports. Files in `public/` are referenced by URL and must use `import.meta.env.BASE_URL` (see `tech.md`).
- Briefs go in `docs/`, specs in `.kiro/specs/`. Agents never write app code outside the task they were given.
- `.vscode/` is gitignored except `extensions.json`.
