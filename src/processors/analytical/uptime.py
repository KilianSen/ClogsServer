import logging
from uuid import uuid4
from types import NoneType
from typing import Optional
from time import time

from sqlalchemy import desc
from sqlmodel import select, Field, SQLModel, Session

from src.processors import Processor
from src.models.agents import Container, ContainerState
from src.database import engine
logger = logging.getLogger(__name__)

class ContainerUptime(SQLModel, table=True):
    container_id: str = Field(primary_key=True, foreign_key="container.id")
    uptime_seconds: int = Field(default=0)
    uptime_percentage: float = Field(default=0.0)
    first_recorded: int = Field(default_factory=lambda: 0)


class UptimeSection(SQLModel, table=True):
    id: str = Field(default=None, primary_key=True)
    container_id: str = Field(foreign_key="container.id", index=True)
    start_time: int = Field(default_factory=lambda: int(time()))
    end_time: int | None = Field(default=None)
    state: str = Field(default=None)

class UptimeProcessor(Processor[Container, NoneType]):
    interval: int = 5  # Check every minute

    def on_startup(self):
        @self._router.get("/api/processors/uptime", tags=["API"])
        def get_uptime() -> list[ContainerUptime]:
            with Session(engine) as session:
                return list(session.exec(
                    select(ContainerUptime)
                ).all())

        @self._router.get("/api/processors/uptime/{container_id}", tags=["API"])
        def get_uptime_by_container(container_id: str) -> Optional[ContainerUptime]:
            with Session(engine) as session:
                return session.get(ContainerUptime, container_id)

        @self._router.get("/api/processors/uptime/sections", tags=["API"])
        def get_uptime_sections() -> list[UptimeSection]:
            with Session(engine) as session:
                return list(session.exec(
                    select(UptimeSection).order_by(UptimeSection.start_time)
                ).all())

        @self._router.get("/api/processors/uptime/sections/{container_id}", tags=["API"])
        def get_uptime_sections_by_container(container_id: str) -> list[UptimeSection]:
            with Session(engine) as session:
                return list(session.exec(
                    select(UptimeSection).where(UptimeSection.container_id == container_id).order_by(UptimeSection.start_time)
                ).all())
        pass

    def on_insert(self, data: Container) -> Optional[Container]:
        return None

    def on_get(self, data: Container) -> Optional[Container]:
        return None

    def on_delete(self, data: Container) -> Optional[Container]:
        return None

    def on_interval(self):
        pass

    def on_interval_each(self, container: Container) -> Optional[NoneType]:
        state = self.session.get(ContainerState, container.id)
        uptime_record = self.session.get(ContainerUptime, container.id)

        if not uptime_record:
            uptime_record = ContainerUptime(container_id=container.id, uptime_seconds=0, uptime_percentage=0.0,
                                            first_recorded=container.created_at)

        # We assume "running" status means it's up.
        current_time = int(time())
        if state and state.status.lower() == "running":
            last_run = getattr(self, "_last_run", None)
            if last_run:
                delta = time() - last_run
                uptime_record.uptime_seconds += int(delta)
            else:
                # First run, do not add uptime to avoid overcounting on restarts
                pass

        # Calculate percentage uptime
        total_time = current_time - uptime_record.first_recorded

        # Fix for potential overcounting
        if total_time > 0 and uptime_record.uptime_seconds > total_time:
            uptime_record.uptime_seconds = total_time

        uptime_record.uptime_percentage = round(min((uptime_record.uptime_seconds / total_time) * 100,100.0) if total_time > 0 else 0.0,4)

        self.session.add(uptime_record)

        # Check for state changes
        last_section = self.session.exec(
            select(UptimeSection).where(UptimeSection.container_id == container.id).order_by(desc(UptimeSection.start_time))
        ).first()
        current_time = int(time())
        if not last_section or last_section.state != (state.status if state else "unknown"):
            # Close previous section
            if last_section and last_section.end_time is None:
                last_section.end_time = current_time
                self.session.merge(last_section)

            # Start new section
            new_section = UptimeSection(
                id=uuid4().hex,
                container_id=container.id,
                start_time=current_time,
                state=state.status if state else "unknown"
            )
            self.session.add(new_section)

        self.session.commit()
        return None

    def on_shutdown(self):
        pass


