import logging
from types import NoneType
from typing import Optional
from time import time

from fastapi import APIRouter
from sqlmodel import select

from src.processors import Processor
from src.models.agents import Container, ContainerState
from src.models.uptime import ContainerUptime

logger = logging.getLogger(__name__)

class UptimeProcessor(Processor[Container, NoneType]):
    interval: int = 5  # Check every minute

    def on_startup(self):
        @self._router.get("/api/processors/uptime")
        def get_uptime():
            uptimes = self.session.exec(
                select(ContainerUptime)
            ).all()
            return uptimes
        pass

    def on_insert(self, data: Container) -> Optional[Container]:
        return None

    def on_get(self, data: Container) -> Optional[Container]:
        return None

    def on_delete(self, data: Container) -> Optional[Container]:
        return None

    def on_interval(self):
        pass

    def on_interval_each(self, container: Container) -> Optional[Container]:
        state = self.session.get(ContainerState, container.id)
        uptime_record = self.session.get(ContainerUptime, container.id)

        if not uptime_record:
            uptime_record = ContainerUptime(container_id=container.id, uptime_seconds=0, uptime_percentage=0.0,
                                            first_recorded=container.created_at)

        # We assume "running" status means it's up.
        if state and state.status.lower() == "running":
            uptime_record.uptime_seconds += self.interval

        # Calculate percentage uptime
        total_time = int(time()) - uptime_record.first_recorded
        uptime_record.uptime_percentage = round(min((uptime_record.uptime_seconds / total_time) * 100,100.0) if total_time > 0 else 0.0,4)

        self.session.add(uptime_record)
        self.session.commit()
        return None

    def on_shutdown(self):
        pass


