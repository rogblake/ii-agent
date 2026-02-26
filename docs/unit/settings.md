# Unit Test Plan: `settings`

## Scope

- user LLM settings CRUD and resolution (`settings/llm/service.py`)
- MCP settings CRUD and tool-specific configuration (`settings/mcp/service.py`)
- encrypted API key behavior and fallback to system config

## Priority test suites

1. LLM setting CRUD.
- create updates existing per `(model, user)`
- update only mutates provided fields
- delete returns false for missing records

2. Encryption behavior.
- API keys are stored encrypted
- include-key paths decrypt correctly
- invalid/empty encrypted values handled safely

3. LLM config resolution.
- session with `llm_setting_id` resolves user setting first
- fallback to system model when user setting is missing
- source=`user` requires user config and errors on missing model

4. MCP setting flows.
- create deactivates previous active settings
- codex configure requires auth and builds expected server args
- claude-code auth format validation and token exchange errors
- metadata parsing resilience when stored metadata is malformed

## Fixtures / mocks

- fake LLM/MCP repositories and fake session repository
- monkeypatched encryption manager and HTTP client
- deterministic UUID/time fixtures

## Proposed test layout

- `src/tests/unit/settings/test_llm_setting_service.py`
- `src/tests/unit/settings/test_llm_resolution.py`
- `src/tests/unit/settings/test_mcp_setting_service.py`
- `src/tests/unit/settings/test_mcp_oauth_helpers.py`

## Exit criteria

- model/key resolution behavior stable across user/system fallbacks
- MCP auth/config paths covered for both success and failure
