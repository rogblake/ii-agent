"""Shared prompt fragments for specs-first development workflows."""

FEATURE_DOCUMENT_SECTION_LIST = """\
     Required sections in every `specs/<feature-name>/document.md`:
     - Overview
     - Goals
     - Scope / non-goals
     - User flows / UX / design notes
     - Functional requirements
     - Data model / schema
     - API contracts
     - Edge cases / failure modes
     - Acceptance criteria
     - Test plan / test cases
     - Implementation notes
     - Status / open questions
"""

SPECS_FIRST_DEVELOPMENT_RULES = f"""\
- Specs-First Development (MANDATORY): Before writing any application code, you MUST clarify project requirements with the user and build a specs folder. Follow this process:
  0. FIRST, use ask_user_select to clarify all key project decisions before building specs. Ask the user about:
     - Database provider: "Which database provider would you like to use?" with options "default" (NeonDB - managed Postgres) and "supabase" (Supabase - Postgres + Auth + Storage + Realtime).
     - Any other critical choices relevant to the project (e.g., authentication method, deployment target, styling framework, etc.).
     Gather all user preferences BEFORE writing any specs or code.
  1. Create a `specs/` folder in the project root.
  2. Create `specs/spec.md` as the master spec file containing: project overview, goals, design direction, technical stack decisions (incorporating user's choices from step 0), architecture rules, and a feature list table with status (planned/in-progress/done). In that table, the `Spec` column MUST link directly to each feature document file using the form `specs/<feature-name>/document.md`, not the feature folder.
  3. For each feature, create a subfolder `specs/<feature-name>/` and create `specs/<feature-name>/document.md` as the single source of truth for that feature. Do NOT split feature specs across separate `design.md` or `test-case.md` files.
{FEATURE_DOCUMENT_SECTION_LIST}
  4. Research and complete the specs BEFORE starting any implementation. Use web search and available tools to inform technical decisions.
  5. When implementing a feature, ALWAYS read `specs/<feature-name>/document.md` first and follow it strictly. Reference `specs/spec.md` for architecture rules and overall project context.
  6. Update `specs/spec.md` status as features progress. Keep specs in sync with implementation.
  NEVER skip this step - always clarify with the user, build specs, then implement.
"""
