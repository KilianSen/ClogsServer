from enum import Enum

from sqlmodel import SQLModel, Field
from pydantic import BaseModel

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
    context: int = Field(nullable=False, foreign_key="context.id", index=True)
    name: str = Field(nullable=False)
    image: str = Field(nullable=False)
    created_at: int = Field(nullable=False)

class ContainerState(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True, foreign_key="container.id")
    status: str = Field(nullable=False)

### Logging Models ###

class Log(SQLModel, table=True):
    """
    Represents a single log entry from a container.
    """
    id: int | None = Field(default=None, primary_key=True)
    container_id: str = Field(nullable=False, foreign_key="container.id", index=True)
    timestamp: int = Field(nullable=False)
    level: str = Field(nullable=False)
    message: str = Field(nullable=False)

class MultilineLogTransfer(BaseModel):
    """
    This class is used by the api endpoint to receive multiline log entries in a single transfer.
    """
    container_id: str
    logs: list[Log]

class MultiContainerLogTransfer(BaseModel):
    """
    This class is used by the api endpoint to receive logs from multiple containers in a single transfer.
    """
    agent_id: str
    container_logs: list[MultilineLogTransfer]