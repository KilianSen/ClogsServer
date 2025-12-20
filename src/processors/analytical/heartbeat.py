import logging
from types import NoneType
from typing import Optional
from time import time

from sqlmodel import select

from src.processors import Processor
from src.models.agents import Agent, ContainerState, Heartbeat, Container

logger = logging.getLogger(__name__)

class HeartbeatProcessor(Processor[Heartbeat, NoneType]):
    interval: int = 5

    def on_startup(self):
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


