# Tech

## Stack
- React 19 (`react`, `react-dom` ^19.3) with function components and hooks
- TypeScript ~6.0, ESM (`"type": "module"`)
- Vite 8 with `@vitejs/plugin-react`
- ESLint 10 flat config: `@eslint/js`, `typescript-eslint` recommended, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- npm (`package-lock.json`)
- Plain CSS (`src/index.css`, `src/App.css`). No CSS framework or state library is installed.

## Commands
| Task | Command |
|---|---|
| Dev server | `npm run dev` (port 5173) |
| Type-check and build | `npm run build` (`tsc -b && vite build`, output in `dist/`) |
| Lint | `npm run lint` |
| Preview build | `npm run preview` |
| Unit tests | `npm test` (Vitest, `vitest run`) |
| Secret scan | `npm run scan:secrets` (gitleaks 8.30.1, config `.gitleaks.toml`) |
| Static analysis | `npm run scan:sast` (Semgrep 1.186.0, metrics off in the script) |
| All pre-review checks | `npm run check` (lint, secrets, SAST) |

Do not start the dev server from the agent shell. Ask the user to run it, or check whether it is already running on 5173.

## TypeScript rules (tsconfig.app.json)
- `verbatimModuleSyntax`: use `import type { ... }` for type-only imports.
- `erasableSyntaxOnly`: no `enum`, `namespace`, or constructor parameter properties. Use union types and `as const` objects.
- `noUnusedLocals` and `noUnusedParameters` are errors.
- `allowImportingTsExtensions`: relative imports may include `.tsx`, as `main.tsx` does.
- Target ES2023, `moduleResolution: bundler`, `jsx: react-jsx`.

## Dev server behind the IDE proxy (important)
The app is viewed through the IDE's code-server and CloudFront proxy, and `vite.config.ts` is set up for that:
- `base: command === 'serve' ? '/absproxy/5173/' : '/'`, so only the dev server uses the prefix and production builds are unaffected. code-server's `/absproxy/<port>/` route keeps the path prefix. The `/proxy/<port>/` route strips it, which leaves root-absolute asset URLs unresolvable and the page blank.
- `server.allowedHosts: ['.cloudfront.net']`. Vite 8 rejects unknown `Host` headers with 403 "Blocked request". The leading dot allows `cloudfront.net` and all its subdomains.
- URL to open: `https://<cloudfront-host>/absproxy/5173/` (trailing slash required). The host is in the `VSCODE_PROXY_URI` env var.
- Consequences of `base`: reference public files as `${import.meta.env.BASE_URL}file.svg`, not `/file.svg`. `App.tsx` currently uses `/icons.svg#...` in `<use href>`. Fix these when touching that code, because hardcoded root paths bypass `base`.
- `base` is `/` for builds, so no change is needed for a production deploy.

## Conventions
- Follow the ESLint config. Run `npm run lint` and `npm run build` before reporting work as done.
- Do not add dependencies without a reason. Prefer the platform and React built-ins first.
- Testing rules are in `testing.md`. Vitest is the runner (`npm test`); add it with the first spec that needs it.
