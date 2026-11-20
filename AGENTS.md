# AGENTS.md

Rules any agent reads in this repository. Details live in `.kiro/steering/`; this file is the short version.

## How we work: AI-DLC
Agents do the work between the gates. A person owns every gate.

1. **Plan.** A person picks the work.
2. **Requirements and design.** The person writes the brief as `docs/brd-<feature>.md`. The `spec` agent turns it into `.kiro/specs/<feature>/` (requirements, design, tasks). **Gate: a person approves the spec.**
3. **Build.** The `build` agent works on a branch (`feat/<name>`), with a test for every task and one commit per task.
4. **Test.** The `build` agent runs `npm test`, `npm run lint`, `npm run build` and, with the dev server running, `npm run test:browser`.
5. **Review.** After `npm run check` has run, the `reviewer` agent reads the diff and reports Critical, Warnings and Suggestions with `file:line`.
6. **Release.** **Gate: a person merges.** No agent approves, merges or pushes to `main`.

## Hard rules
- Never commit to `main`, merge, or push. Never edit code you were not asked to change.
- Never invent requirements. Anything not in the brief is out of scope until a person says otherwise.
- Never invent an API. Read the installed version first (`verify-first.md`).
- No secrets in code, prompts, steering or the repo. No real business, customer or personal data: synthetic data only.
- AWS work stays in `us-east-1`. Keep Amazon Bedrock under one request per second.

## Where things are
| What | Where |
|---|---|
| Product, stack, layout | `.kiro/steering/product.md`, `tech.md`, `structure.md` |
| Git, testing, code style | `.kiro/steering/git-workflow.md`, `testing.md`, `code-style.md` |
| Briefs | `docs/brd-*.md` |
| Specs | `.kiro/specs/<feature>/` |
| Agents | `.kiro/agents/spec.md`, `build.md`, `reviewer.md` |
| Skills | `.kiro/skills/` (`code-review` for `.ts`/`.tsx` reviews) |
| Tool connections | `.kiro/settings/mcp.json` (playwright, aws-mcp) |
| Checks | `npm run check`, `npm test`, `npm run build`, `npm run test:browser` |
