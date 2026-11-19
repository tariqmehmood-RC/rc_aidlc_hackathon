# Structure

## Layout
```
idea-board/
├── .kiro/steering/        Steering docs (product, tech, structure)
├── index.html             Vite entry. Mounts #root, loads /src/main.tsx
├── vite.config.ts         Vite config (react plugin, proxy base, allowedHosts)
├── eslint.config.js       ESLint flat config
├── tsconfig.json          Solution file referencing the two below
├── tsconfig.app.json      Compiler options for src/ (browser code)
├── tsconfig.node.json     Compiler options for Node-side config files
├── package.json
├── public/                Static files served as-is (favicon.svg, icons.svg)
└── src/
    ├── main.tsx           React root. Renders <App /> in StrictMode
    ├── App.tsx            Root component (still the template demo)
    ├── App.css            Styles for App
    ├── index.css          Global styles
    └── assets/            Imported images (hero.png, react.svg, vite.svg)
```
Generated and ignored by git: `node_modules/`, `dist/`, `*.local`, `*.log`.

## Conventions
- All application code goes in `src/`. Config files stay at the repo root.
- Entry flow: `index.html` → `src/main.tsx` → `src/App.tsx`.
- Components are function components in `.tsx` files. Name the file after the component in PascalCase (`IdeaCard.tsx`), with its styles beside it (`IdeaCard.css`) when it has any.
- When `src/` grows, group by feature (e.g. `src/features/ideas/`) rather than by file type. Put shared pieces in `src/components/`, `src/hooks/` and `src/lib/` only when more than one feature uses them. Don't create these folders ahead of need.
- Import images and other bundled assets from `src/assets/` through JS imports. Files in `public/` are referenced by URL and must use `import.meta.env.BASE_URL` (see `tech.md`).
- `.vscode/` is gitignored except `extensions.json`.
