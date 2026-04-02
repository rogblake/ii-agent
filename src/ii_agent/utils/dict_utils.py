"""Dictionary utility functions."""

from typing import Any, Dict


def drop_none(d: Dict[str, Any], recursive: bool = True) -> Dict[str, Any]:
    """
    Drop None values from dictionary.

    Args:
        d: Dictionary to filter
        recursive: If True, recursively drop None from nested dicts

    Returns:
        New dictionary with None values removed

    Examples:
        >>> drop_none({'a': 1, 'b': None, 'c': 3})
        {'a': 1, 'c': 3}

        >>> drop_none({'a': {'b': None, 'c': 1}}, recursive=True)
        {'a': {'c': 1}}
    """
    if not recursive:
        return {k: v for k, v in d.items() if v is not None}

    result = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            nested = drop_none(v, recursive=True)
            if nested:  # Only add non-empty dicts
                result[k] = nested
        else:
            result[k] = v
    return result