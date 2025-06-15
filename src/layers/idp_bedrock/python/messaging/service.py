"""
Copyright © Amazon.com and Affiliates
"""

from typing import Any

from messaging.publishers.base import BasePublisher


class MessageDeliveryService:
    def __init__(self) -> None:
        self._publishers = []

    def attach(self, publisher: BasePublisher) -> None:
        self._publishers.append(publisher)

    def detach(self, publisher: BasePublisher) -> None:
        self._publishers.remove(publisher)

    def post(self, payload: Any) -> None:
        for publisher in self._publishers:
            publisher.publish(payload)
