# Repository structure

```
frontend/                 React app (Vite, TypeScript, Tailwind)
backend/
  src/
    handlers/             Lambda entry points (thin, no business logic)
      briefs_read         create_brief, get_brief, list_briefs
      briefs_write        update_brief, confirm_brief, approve_brief, retry_brief
      rules_cases         rules (keep or discard, list, delete) and list_case_studies
      worker              SQS consumer, the only handler that calls Bedrock
    services/             Business logic, no AWS event parsing
      invite_parser
      research
      case_study_matcher
      brief_writer
      rules
      pipeline            worker jobs: parse, pipeline, extract_rules
      offline_model       deterministic stand-in for Bedrock (tests, --fake-bedrock)
    lib/                  Shared helpers
      bedrock_client      Converse wrapper, rate limiter, retries
      http fetch          Safe HTTP fetch for research
      models              Shared data types
      brief_store         Briefs table access, conditional transitions
      api                 claims, body parsing, errors, job queue
      observability       redacting logger, metrics
  tests/                  pytest + moto (fixtures/ holds recorded research)
  local_run.py            run the backend locally on one invite
data/
  case_studies.json       Seed library
  sample_invites/         Synthetic sample invites
scripts/                  seed-demo-users (post-deploy, password from command line)
infra/                    AWS CDK v2 (TypeScript)
docs/
  brd-inside-sales-copilot.md
  architecture.md
  cost-estimate.md
  demo-script.md
README.md
AGENTS.md
```

## Conventions
- Handlers are thin: parse the event, validate input, call a service, return the response.
- Services hold the logic and take their dependencies (Bedrock client, research provider, tables) as arguments, so tests can replace them.
- Only `lib/bedrock_client` talks to Bedrock.
- Tests for a module live in `backend/tests/`, named after the module (for example `test_case_study_matcher.py`).
- Sample invites in `data/sample_invites/` use synthetic attendees only.
- Do not add top-level folders without updating this file.
