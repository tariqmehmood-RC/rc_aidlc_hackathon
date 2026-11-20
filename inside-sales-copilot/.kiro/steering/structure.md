# Repository structure

```
frontend/                 React app (Vite, TypeScript, Tailwind)
backend/
  src/
    handlers/             Lambda handlers
      create_brief
      get_brief
      list_briefs
      update_brief
      confirm_brief
      approve_brief
      retry_brief
      list_case_studies
      rules              (list and delete saved rules, keep or discard proposals)
      worker             (SQS consumer, the only handler that calls Bedrock)
    services/             Business logic, no AWS event parsing
      invite_parser
      research
      attendee_verifier
      case_study_matcher
      brief_writer
      rules
    lib/                  Shared helpers
      bedrock_client      Converse wrapper, rate limiter, retries
      http fetch          Safe HTTP fetch for research
      models              Shared data types
  tests/                  pytest + moto
data/
  case_studies.json       Seed library
  attendee_profiles.json  Synthetic attendee directory
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
- Tests for a module live in `backend/tests/`, named after the module (for example `test_attendee_verifier.py`).
- Sample invites in `data/sample_invites/` use synthetic attendees only.
- Do not add top-level folders without updating this file.
