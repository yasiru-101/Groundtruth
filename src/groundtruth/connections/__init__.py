"""Connection management: encrypted storage, URL parsing, and settings overlay."""

from groundtruth.connections.overlay import apply_connections
from groundtruth.connections.store import ConnectionStore

__all__ = ["ConnectionStore", "apply_connections"]
