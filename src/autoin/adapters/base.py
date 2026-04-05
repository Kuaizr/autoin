from __future__ import annotations

from abc import ABC, abstractmethod

from autoin.infrastructure.models import TaskPayload, UnifiedEvent


class BaseAdapter(ABC):
    """Adapter contract for Windows executors and platform observers."""

    adapter_name: str
    platform_name: str

    @abstractmethod
    def start_listening(self) -> None:
        """Start passive observation without requiring UI focus."""

    @abstractmethod
    def execute_action(self, task: TaskPayload) -> UnifiedEvent:
        """Perform a foreground action after the UI lock has been granted."""

    @abstractmethod
    def rollback_last_action(self) -> None:
        """Best-effort rollback, such as sending ESC or closing a blocking popup."""
