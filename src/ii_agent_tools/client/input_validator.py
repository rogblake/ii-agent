from typing import Any


class ToolValidationError(ValueError):
    pass


class InputValidator:
    def validate_str(
        self,
        name: str,
        value: Any,
        min_len: int | None = None,
        max_len: int | None = None,
    ) -> None:
        if not isinstance(value, str):
            raise ToolValidationError(f"{name} must be a string")
        if min_len is not None and len(value) < min_len:
            raise ToolValidationError(f"{name} must be at least {min_len} characters")
        if max_len is not None and len(value) > max_len:
            raise ToolValidationError(f"{name} must be at most {max_len} characters")

    def validate_list(
        self,
        name: str,
        value: Any,
        min_len: int | None = None,
        max_len: int | None = None,
    ) -> None:
        if not isinstance(value, list):
            raise ToolValidationError(f"{name} must be a list")
        if min_len is not None and len(value) < min_len:
            raise ToolValidationError(f"{name} must have at least {min_len} items")
        if max_len is not None and len(value) > max_len:
            raise ToolValidationError(f"{name} must have at most {max_len} items")

    def validate_int(
        self,
        name: str,
        value: Any,
        min_val: int | None = None,
        max_val: int | None = None,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolValidationError(f"{name} must be an integer")
        if min_val is not None and value < min_val:
            raise ToolValidationError(f"{name} must be at least {min_val}")
        if max_val is not None and value > max_val:
            raise ToolValidationError(f"{name} must be at most {max_val}")

    def validate_choice(self, name: str, value: Any, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise ToolValidationError(f"{name} must be one of: {', '.join(allowed)}")

    def validate_url(self, url: Any) -> None:
        self.validate_str("url", url, min_len=1, max_len=2048)
        if not url.startswith(("http://", "https://")):
            raise ToolValidationError("Only HTTP and HTTPS URLs are allowed")
