from typing import Any, Dict, Optional, TYPE_CHECKING
from ii_agent.engine.v1.tools.base import BaseAgentTool
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

class BaseSandboxTool(BaseAgentTool):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str
    metadata: Optional[Dict[str, Any]] = None
    requires_sandbox: bool = True

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if not agent.sandbox:
            raise ValueError(f"Tool {self.name} requires running sandbox before execution!")
        self.sandbox = agent.sandbox
        return
