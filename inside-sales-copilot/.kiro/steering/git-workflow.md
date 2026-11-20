# Git workflow

Local git only. There is no remote and no hosting service.

## Rules
- Never add a remote (`git remote add` is not allowed). Never push, fetch, or pull.
- Work on branches named `feature/<wave>` (for example `feature/wave-1`, `feature/wave-2`).
- One commit per passing task. Run the tests for the task before committing.
- Never commit directly to `main`.
- Merge into `main` locally, and only after the user approves the wave.
- Never commit secrets, `.env` files, or `cdk.out/`. Check `git status` before each commit.
- Stage files by name, not with `git add -A`.
- Commit messages: short, in the imperative (for example "Add attendee verifier").

## Review
Reviews happen on the local diff:

```
git diff main...feature/<wave>
git log --oneline main..feature/<wave>
```

## Merge and backup
After the user approves a wave:

1. `git checkout main`
2. `git merge --no-ff feature/<wave>`
3. Create a backup bundle (create `/workshop/backups` first if it does not exist):

```
mkdir -p /workshop/backups
git bundle create /workshop/backups/inside-sales-copilot-<wave>.bundle --all
```

4. Check the backup: `git bundle verify /workshop/backups/inside-sales-copilot-<wave>.bundle`

Do not delete the feature branch until the backup is verified. Backup bundles are stored outside the repository and are never committed.
