"""
Copyright © Amazon.com and Affiliates
"""

from abc import ABC, abstractmethod
from typing import Any


class BasePublisher(ABC):
    @abstractmethod
    def publish(self, payload: Any) -> None:
        pass
