"""Subdomain domain exceptions."""

from ii_agent.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError


class SubdomainNotFoundError(NotFoundError):
    """Raised when a subdomain is not found."""

    pass


class SubdomainNotAvailableError(ConflictError):
    """Raised when a subdomain is not available for claiming."""

    def __init__(self, subdomain: str, reason: str | None = None):
        self.subdomain = subdomain
        self.reason = reason or f"Subdomain '{subdomain}' is not available"
        super().__init__(self.reason)


class SubdomainServiceUnavailableError(ServiceUnavailableError):
    """Raised when the Cloudflare KV service is not configured."""

    pass
