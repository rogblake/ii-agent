"""Conftest for unit/integrations tests.

Pre-stubs broken import chains before any test module is collected.
This prevents import errors from modules that have optional or missing
dependencies (e.g. engine.v1.agent_controller, ii_tool, etc.).
"""
from __future__ import annotations

import sys
import types

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_src_root = __file__.replace("/src/tests/unit/integrations/conftest.py", "/src")


def _pkg_stub(name: str) -> types.ModuleType:
    """Create a minimal package stub that allows sub-module imports."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    mod.__path__ = [f"{_src_root}/{name.replace('.', '/')}"]
    mod.__package__ = name
    sys.modules[name] = mod
    return mod


def _mod_stub(name: str, **attrs) -> types.ModuleType:
    """Create a simple module stub with optional attributes."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stub ii_agent.integrations.mcp_sse package (broken __init__.py)
# ---------------------------------------------------------------------------

# Must stub parent packages first
_pkg_stub("ii_agent.integrations")
_pkg_stub("ii_agent.integrations.mcp_sse")

# Ensure ii_agent.integrations is reachable as attribute
import ii_agent as _ii_agent_root  # noqa: E402

if not hasattr(_ii_agent_root, "integrations"):
    _ii_agent_root.integrations = sys.modules["ii_agent.integrations"]

# Attach mcp_sse sub-package attribute to already-stubbed ii_agent.integrations
_integrations_pkg = sys.modules["ii_agent.integrations"]
if not hasattr(_integrations_pkg, "mcp_sse"):
    _integrations_pkg.mcp_sse = sys.modules["ii_agent.integrations.mcp_sse"]

# ---------------------------------------------------------------------------
# Stub missing engine modules
# ---------------------------------------------------------------------------

_mod_stub(
    "ii_agent.engine.v1.agent_controller",
    AgentController=type("AgentController", (), {}),
)

_mod_stub(
    "ii_agent.engine.agents.beta",
    register_default_session_hooks=lambda *a, **kw: None,
)
_mod_stub(
    "ii_agent.engine.agents.beta.hooks",
    register_default_session_hooks=lambda *a, **kw: None,
)
_mod_stub(
    "ii_agent.engine.agents.beta.hooks.session_hooks",
    register_default_session_hooks=lambda *a, **kw: None,
)

_mod_stub(
    "ii_agent.utils.workspace_manager",
    WorkspaceManager=type("WorkspaceManager", (), {}),
)

# ---------------------------------------------------------------------------
# Stub optional external dependencies
# ---------------------------------------------------------------------------

_mod_stub("ii_tool")
_mod_stub("ii_tool.mcp")
_mod_stub("ii_tool.mcp.client", MCPClient=type("MCPClient", (), {}))

# ---------------------------------------------------------------------------
# Stub ii_agent.integrations.a2a package (broken import chain via as_server)
#
# as_server.py -> engine.v1.factory -> engine.v1.models.google.interactions
#              -> google.genai.interactions (missing InteractionEvent etc.)
# ---------------------------------------------------------------------------

# Stub the google.genai.interactions module with all names that are imported
# in engine.v1.models.google.interactions.  We must do this BEFORE any a2a
# module is imported so the stub is in sys.modules and the real import is
# never attempted.
import google.genai as _google_genai  # real package – already loadable

_google_genai_interactions_stub = _mod_stub(
    "google.genai.interactions",
    InteractionEvent=type("InteractionEvent", (), {}),
    InteractionSSEEvent=type("InteractionSSEEvent", (), {}),
    ContentStart=type("ContentStart", (), {}),
    ContentDelta=type("ContentDelta", (), {}),
    ContentStop=type("ContentStop", (), {}),
    Usage=type("Usage", (), {}),
    Interaction=type("Interaction", (), {}),
)
# Also set as attribute on the package object so `from google.genai import interactions` works
if not hasattr(_google_genai, "interactions"):
    _google_genai.interactions = _google_genai_interactions_stub

# Stub engine.v1.models.google so its __init__ (which imports .interactions) is bypassed
_pkg_stub("ii_agent.engine.v1.models")
_pkg_stub("ii_agent.engine.v1.models.google")
_mod_stub(
    "ii_agent.engine.v1.models.google.interactions",
    GeminiInteractions=type("GeminiInteractions", (), {}),
)

# Stub the factory package and its submodules referenced by as_server.py
# and engine.agents.agent_service
_factory_pkg = _pkg_stub("ii_agent.engine.v1.factory")
_factory_pkg.AgentFactory = type("AgentFactory", (), {})
_mod_stub(
    "ii_agent.engine.v1.factory.factory",
    AgentFactory=type("AgentFactory", (), {}),
)
_mod_stub(
    "ii_agent.engine.v1.factory.converter",
    convert_agent_event_to_realtime=lambda *a, **kw: None,
)

# Stub ii_agent.integrations.a2a package so its __init__.py is not executed
_pkg_stub("ii_agent.integrations.a2a")

# Attach a2a sub-package attribute to already-stubbed ii_agent.integrations
_integrations_stub = sys.modules.get("ii_agent.integrations")
if _integrations_stub is not None and not hasattr(_integrations_stub, "a2a"):
    _integrations_stub.a2a = sys.modules["ii_agent.integrations.a2a"]
