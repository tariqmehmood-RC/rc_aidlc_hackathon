# AGENTS.md

Rules for anyone (human or AI agent) working in this repo.

1. **Spec before code.** Update `docs/brd-inside-sales-copilot.md` (and any design or task docs) before writing code. No code without an agreed requirement.
2. **Small tasks with tests.** One small task at a time. Each task ships with tests and passes them before it is committed.
3. **Never commit secrets.** No keys, tokens, passwords, or `.env` files in git. Use environment variables, SSM Parameter Store, or Secrets Manager.
4. **us-east-1 only.** Every AWS resource, CDK stack, and SDK client uses `us-east-1`. Do not make the region configurable.
5. **Bedrock rate limit: 1 request per second.** Enforce it in code with a shared limiter on every Bedrock call. Do not rely on convention.
6. **Synthetic attendee data only.** Attendee names, titles, and emails are made up. Company research may use real public companies. No customer data.
7. **Infrastructure is AWS CDK**, committed to the local git repository. No console-only changes.
8. **Local git only.** Never add a remote and never push. Work on `feature/<wave>` branches with one commit per passing task. Merge into `main` locally only after the user approves. After each merge, create a backup with `git bundle create /workshop/backups/inside-sales-copilot-<wave>.bundle --all`. Reviews use the local diff (`git diff main...feature/<wave>`). Details are in `.kiro/steering/git-workflow.md`.
