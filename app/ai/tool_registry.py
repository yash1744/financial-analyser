"""Registry between the agent and the existing finance tools.

Wraps FinanceToolset (app/llm/tools.py) — the tools themselves are not
redefined here. The registry's job is the error contract: expected
failures become error tool-results the model can read and recover from,
instead of exceptions that abort the whole chat turn.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm.tools import FinanceToolset, UnknownToolError
from app.services.exceptions import ConflictError, NotFoundError

logger = logging.getLogger(__name__)


class ToolExecution(BaseModel):
    content: str  # JSON result, or error text when is_error
    is_error: bool = False


class ToolRegistry:
    def __init__(self, toolset: FinanceToolset) -> None:
        self._toolset = toolset

    def definitions(self) -> list[dict[str, Any]]:
        """Tool definitions in provider format ({name, description, input_schema})."""
        return self._toolset.definitions()

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        """Run one tool call; failures become readable error results."""
        try:
            result = await self._toolset.execute(name, arguments)
            return ToolExecution(content=json.dumps(result))
        except UnknownToolError:
            return ToolExecution(
                content=f"Unknown tool '{name}'. Use one of the provided tools.",
                is_error=True,
            )
        except ValidationError as exc:
            issues = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            return ToolExecution(
                content=f"Invalid arguments for {name}: {issues}", is_error=True
            )
        except (NotFoundError, ConflictError) as exc:
            return ToolExecution(content=f"Error from {name}: {exc}", is_error=True)
        except Exception:
            # unexpected — log with traceback, tell the model only that it failed
            logger.exception("tool %s failed", name)
            return ToolExecution(
                content=f"Internal error executing {name}.", is_error=True
            )
