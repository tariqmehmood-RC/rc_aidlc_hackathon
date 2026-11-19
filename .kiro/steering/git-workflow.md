# Git workflow

Rules for the agent. Each line is binding.

## Branches
- NEVER commit to `main`. NEVER run `git push`, `git merge`, `git rebase`, `git reset --hard`, or `git push --force`.
- MUST do feature work on a branch named `feat/<kebab-case-name>`, `fix/<kebab-case-name>` or `chore/<kebab-case-name>`.
- MUST run `git status` before creating a branch. If the tree is dirty, STOP and ask the user.
- NEVER delete a branch or discard changes you did not make.

## Commits
- MUST commit with format `<type>: <imperative summary>`, summary at most 72 characters, no trailing period.
- `<type>` MUST be one of: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
- MUST make one commit per spec task. NEVER bundle two tasks in one commit.
- MUST stage files by name. NEVER use `git add -A` or `git add .`.
- NEVER use `--no-verify` or `--amend`. After a failed hook or check, fix it and make a new commit.
- NEVER commit `node_modules/`, `dist/`, `.env*`, or any file containing a secret.

## Exceptions (user-run only)
- The user makes the lab checkpoint commits on `main` in their own terminal. The agent MUST NOT make those.
- MUST run `npm run lint` and `npm run build` before every commit. NEVER commit if either fails.
