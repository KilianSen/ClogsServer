from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import uuid4

from sqlmodel import SQLModel, Field
from pydantic import BaseModel

from src.database import SessionDep


class Agent(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True)
    hostname: str | None = Field(nullable=True)
    heartbeat_interval: int = Field(default=30, nullable=False)
    discovery_interval: int = Field(default=30, nullable=False)
    on_host: bool = Field(nullable=False)


class Heartbeat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    agent_id: str = Field(foreign_key="agent.id", index=True, nullable=False)
    timestamp: int = Field(nullable=False)


### Context ###
class ContextType(str, Enum):
    compose = "compose"
    swarm = "swarm"


class Context(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    agent_id: str | None = Field(default=None, nullable=False, foreign_key="agent.id", index=True)
    name: str = Field(nullable=False)
    type: ContextType = Field(nullable=False)


### Container Models ###

class Container(SQLModel, table=True):
    """
    Represents a container being monitored by an agent.
    """
    id: str | None = Field(default=None, primary_key=True)
    agent_id: str = Field(nullable=False, foreign_key="agent.id", index=True)
    context: int | None = Field(default=None, foreign_key="context.id", index=True)
    name: str = Field(nullable=False)
    image: str = Field(nullable=False)
    created_at: int = Field(nullable=False)


class ContainerState(SQLModel, table=True):
    id: str | None = Field(default=None, primary_key=True, foreign_key="container.id")
    status: str = Field(nullable=False)
    since: int = Field(nullable=False)


### Logging Models ###

@runtime_checkable
class LogProtocol(Protocol):
    def add_log_entries(self, session: SessionDep, agent_id: str | None, container_id: str | None) -> None:
        ...


class Log(SQLModel, table=True):
    """
    Represents a single log entry from a container.
    """
    id: str | None = Field(default=None, primary_key=True)
    container_id: str = Field(nullable=False, foreign_key="container.id", index=True)
    timestamp: int = Field(nullable=False)
    level: str = Field(nullable=False)
    message: str = Field(nullable=False)

    def add_log_entries(self, session: SessionDep, agent_id: str | None, container_id: str | None):
        """
        Adds this log entry to the database session for the specified agent and container.
        :param session: Database session
        :param agent_id: Not used in this context, kept for protocol compatibility
        :param container_id: Not used in this context, kept for protocol compatibility
        :return:
        """

        # Generate a unique ID for the log entry if not already set
        if self.id is None:
            self.id = str(uuid4())

        session.add(self)


class MultilineLogTransfer(BaseModel):
    """
    This class is used by the api endpoint to receive multiline log entries in a single transfer.
    """
    container_id: str
    logs: list[Log]

    def add_log_entries(self, session: SessionDep, agent_id: str | None, container_id: str | None):
        """
        Adds log entries to the database session for the specified agent and container.
        :param session: Database session
        :param agent_id: Not used in this context, kept for protocol compatibility
        :param container_id: Container ID to which the logs belong, must match self.container_id and will be validated
        """

        if self.container_id != container_id:
            raise ValueError("Container ID mismatch")

        if not self.logs:
            raise ValueError("No logs to add")

        # Check if container exists
        db_container = session.get(Container, self.container_id)
        if not db_container:
            raise ValueError("Container not found")

        for log_entry in self.logs:
            log_entry.add_log_entries(session, agent_id, self.container_id)


class MultiContainerLogTransfer(BaseModel):
    """
    This class is used by the api endpoint to receive logs from multiple containers in a single transfer.
    """
    agent_id: str
    container_logs: list[MultilineLogTransfer]

    def add_log_entries(self, session: SessionDep, agent_id: str | None, container_id: str | None):
        """
        Adds log entries to the database session for the specified agent and container.

        :param session: Database session
        :param agent_id: The ID of the agent uploading the logs
        :param container_id: Not used in this context, kept for protocol compatibility
        """
        if self.agent_id != agent_id:
            raise ValueError("Agent ID mismatch")

        if not self.container_logs:
            raise ValueError("No container logs to add")

        for container_log in self.container_logs:
            container_log.add_log_entries(session, agent_id, container_log.container_id)
