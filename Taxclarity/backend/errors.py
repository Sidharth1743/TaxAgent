"""Custom error types for memory and persistence layers."""


class SqlPersistenceError(RuntimeError):
    """Raised when SQL persistence fails."""


class VertexMemoryError(RuntimeError):
    """Raised when Vertex Memory Bank operations fail."""


class MemoryJobDlqError(RuntimeError):
    """Raised when a memory job fails and cannot be enqueued to the DLQ."""
