"""Exceptions of dtool-dserver."""


class DServerStorageBrokerError(Exception):
    """Base exception for DServerStorageBroker errors."""
    pass


class DServerAuthenticationError(DServerStorageBrokerError):
    """Authentication error with dserver."""
    pass


class DServerDatasetNotFoundError(DServerStorageBrokerError):
    """Dataset not found on dserver."""
    pass


class DServerNotImplementedError(DServerStorageBrokerError):
    """Feature not implemented on dserver or storage backend."""
    pass
