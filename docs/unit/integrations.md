# Unit Test Plan: `integrations`

## Scope

- A2A integration server/session adaptation (`integrations/a2a/*`)
- connector token services (`integrations/connectors/*`)
- MCP SSE app mounting and route composition (`integrations/mcp_sse/*`)

## Priority test suites

1. Connector token lifecycle.
- `save_mcp_token()` create vs update path
- `get_user_by_mcp_token()` handles expiry and metadata defaults

2. A2A request adaptation.
- context/task/session ID mapping rules
- tool arg deep-merge behavior across turns
- default user identity resolution/fallback behavior

3. Sandbox reuse behavior in A2A.
- preferred sandbox connect success path
- reuse failure fallback to new sandbox
- extension context updated for reuse metadata

4. Event/adaptor conversions.
- outbound A2A status/result formatting from internal events
- error path emits failed task event with metadata

5. MCP SSE mounting.
- wrapper app mounts OAuth + MCP routes at expected paths
- middleware insertion failures degrade gracefully

## Fixtures / mocks

- fake event queue and fake A2A context object
- monkeypatched sandbox manager/resource pool
- fake FastAPI/Starlette app for mount assertions

## Proposed test layout

- `src/tests/unit/integrations/test_connector_service.py`
- `src/tests/unit/integrations/test_a2a_server.py`
- `src/tests/unit/integrations/test_a2a_adapters.py`
- `src/tests/unit/integrations/test_mcp_sse_mount.py`

## Exit criteria

- protocol adaptation behavior is stable under partial failures
- token/session handling paths are regression-protected
