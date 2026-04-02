from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

from ii_agent.core.logger import logger

# Keys that should be deep copied for background hooks to prevent race conditions
BACKGROUND_HOOK_COPY_KEYS = frozenset(
    {
        "run_input",
        "run_context",
        "run_output",
        "metadata",
    }
)


def copy_args_for_background(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a copy of hook arguments for background execution.

    This deep copies run_input, run_context, run_output, session_state, dependencies,
    and metadata to prevent race conditions when hooks run in the background.

    Args:
        args: The original arguments dictionary

    Returns:
        A new dictionary with copied values for sensitive keys
    """
    copied_args = {}
    for key, value in args.items():
        if key in BACKGROUND_HOOK_COPY_KEYS and value is not None:
            try:
                copied_args[key] = deepcopy(value)
            except Exception:
                # If deepcopy fails (e.g., for non-copyable objects), use the original
                logger.warning(
                    f"Could not deepcopy {key} for background hook, using original reference"
                )
                copied_args[key] = value
        else:
            copied_args[key] = value
    return copied_args


def normalize_hooks(
    hooks: Optional[List[Callable[..., Any]]],
    async_mode: bool = False,
) -> Optional[List[Callable[..., Any]]]:
    """Normalize hooks to a list format

    Args:
        hooks: List of hook functions or hook instances
        async_mode: Whether to use async versions of methods
    """

    result_hooks: List[Callable[..., Any]] = []

    if hooks is not None:
        for hook in hooks:
            # Check if the hook is async and used within sync methods
            if not async_mode:
                import asyncio

                if asyncio.iscoroutinefunction(hook):
                    raise ValueError(
                        f"Cannot use {hook.__name__} (an async hook) with `run()`. Use `arun()` instead."
                    )

                result_hooks.append(hook)
    return result_hooks if result_hooks else None


def filter_hook_args(hook: Callable[..., Any], all_args: Dict[str, Any]) -> Dict[str, Any]:
    """Filter arguments to only include those that the hook function accepts."""
    import inspect

    try:
        sig = inspect.signature(hook)
        accepted_params = set(sig.parameters.keys())

        has_var_keyword = any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
        )

        # If the function has **kwargs, pass all arguments
        if has_var_keyword:
            return all_args

        # Otherwise, filter to only include accepted parameters
        filtered_args = {key: value for key, value in all_args.items() if key in accepted_params}

        return filtered_args

    except Exception as e:
        logger.warning(f"Could not inspect hook signature, passing all arguments: {e}")
        # If signature inspection fails, pass all arguments as fallback
        return all_args
