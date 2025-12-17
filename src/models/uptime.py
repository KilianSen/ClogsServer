from sqlmodel import SQLModel, Field

class ContainerUptime(SQLModel, table=True):
    container_id: str = Field(primary_key=True, foreign_key="container.id")
    uptime_seconds: int = Field(default=0)
    uptime_percentage: float = Field(default=0.0)
    first_recorded: int = Field(default_factory=lambda: 0)
