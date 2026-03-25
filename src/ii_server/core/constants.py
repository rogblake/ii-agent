"""Central configuration constants for ii_server.

These values can be overridden via environment variables.
"""

import os

# Paths - configurable via environment variables
TOOL_CONFIG_PATH = os.getenv("TOOL_CONFIG_PATH", "/app/.tool_server_config.json")
USER_ENV_PATH = os.getenv("USER_ENV_PATH", "/app/.user_env")
USER_ENV_SH_PATH = os.getenv("USER_ENV_SH_PATH", "/app/.user_env.sh")
DEFAULT_WORKSPACE = os.getenv("DEFAULT_WORKSPACE", "/workspace")

# Default ports for development servers
DEFAULT_NEXTJS_PORT = 3000
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 3000
