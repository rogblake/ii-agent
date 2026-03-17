# Product Specifications Index

## Platform

| Spec | Status | Description |
|------|--------|-------------|
| [platform-overview.md](platform-overview.md) | Active | What II-Agent is, user personas, key journeys |

## Feature Domains

| Domain | Spec Location | Description |
|--------|--------------|-------------|
| Agent execution | `CLAUDE.md` > Billing & Credit System | Agent runtime with per-call billing |
| Chat | `docs/FRONTEND.md` > Chat Runtime | Multi-model chat with SSE streaming |
| Slides | `content/slides/` (code) | HTML slide generation + PDF export |
| Storybook | `content/storybook/` (code) | Visual storybook generation with versioning |
| Projects | `projects/` (code) | Full-stack deployment to Cloud Run |
| Skills | `content/skills/` (code) | Custom skill management (builtin/github/custom) |

## Adding a Product Spec

1. Create the spec in `docs/product-specs/`.
2. Add an entry to this index.
3. Include: problem statement, user journey, acceptance criteria, technical notes.
