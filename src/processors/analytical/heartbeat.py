from enum import Enum
import logging
from types import NoneType
from typing import Optional
from time import time

from sqlmodel import select, SQLModel, Field

from src.processors import Processor
from src.models.agents import Agent, ContainerState, Heartbeat, Container

logger = logging.getLogger(__name__)

class AliveState(Enum):
    active = "active"
    inactive = "inactive"

class AliveAgent(SQLModel, table=True):
    agent_id: str = Field(primary_key=True, foreign_key="agent.id")
    state: AliveState

class HeartbeatProcessor(Processor[Heartbeat, NoneType]):
    interval: int = 5

    def on_startup(self):

        @self._router.get("/api/processors/active")
        def get_active_agents() -> dict[str, bool]:
            agents: list[AliveAgent] = list(self.session.exec(
                select(AliveAgent)
            ).all())
            return {a.agent_id: a.state == AliveState.active for a in agents}

        pass

    def on_insert(self, data: Heartbeat) -> Optional[Heartbeat]:
        return None

    def on_get(self, data: Heartbeat) -> Optional[Heartbeat]:
        return None

    def on_delete(self, data: Heartbeat) -> Optional[Heartbeat]:
        return None

    def on_interval(self):
        # For each agent, check if we have received a heartbeat recently (its heartbeat_interval + leniency)
        # If heartbeats are missing, set all containers to 'unknown' state
        logger.debug("Running heartbeat interval check.")
        agents: list[Agent] = list(self.session.exec(
            select(Agent)
        ).all())

        current_time = time()

        for agent in agents:
            iv = agent.heartbeat_interval * 2 # Consider missing if no heartbeat in double the interval
            leniency = 1.05  # 5% leniency

            time_threshold = current_time -(iv * leniency)
            heartbeats = self.session.exec(
                select(Heartbeat).where(
                    (Heartbeat.agent_id == agent.id) &
                    (Heartbeat.timestamp >= time_threshold * 10**9)
                )
            ).all()

            active: AliveAgent | None = self.session.get(AliveAgent, agent.id)
            if not active:
                active = AliveAgent(agent_id=agent.id, state=AliveState.active if heartbeats else AliveState.inactive)
                self.session.add(active)
                self.session.commit()
            else:
                if heartbeats and active.state == AliveState.inactive:
                    active.state = AliveState.active
                    self.session.add(active)
                    self.session.commit()
                elif not heartbeats and active.state == AliveState.active:
                    active.state = AliveState.inactive
                    self.session.add(active)
                    self.session.commit()

            if not heartbeats:
                logger.warning(f"Agent {agent.id} is missing heartbeats. Marking its containers as 'unknown'.")
                containers = self.session.exec(
                    select(Container).where(
                        Container.agent_id == agent.id
                    )
                ).all()

                for container in containers:
                    state = self.session.get(ContainerState, container.id)
                    if state:
                        state.status = "unknown"
                        self.session.add(state)

                self.session.commit()

    def on_interval_each(self, heartbeat: Heartbeat) -> Optional[Heartbeat]:
        pass

    def on_shutdown(self):
        pass


