class ResearchSignalError(RuntimeError):
    """Base exception for a failed, non-reproducible run."""


class ConfigurationError(ResearchSignalError):
    """Raised when the run configuration violates the contract."""


class OpenAlexError(ResearchSignalError):
    """Raised when OpenAlex cannot provide a valid response."""


class OpenCitationsError(ResearchSignalError):
    """Raised when OpenCitations cannot provide a valid response."""


class PaginationError(OpenAlexError):
    """Raised when cursor pagination is incomplete or loops."""


class InvariantError(ResearchSignalError):
    """Raised when a collection invariant is violated."""
