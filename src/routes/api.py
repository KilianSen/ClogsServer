import logging
from typing import Union, List, Any
from sqlmodel import select
from sqlmodel import Session

from src.database import SessionDep
from src.models.agents import Container, ContainerState, Context, Log, Agent
from src.routes import router

logger = logging.getLogger(__name__)

@router.get("/api/health", tags=["API"])
def health_check():
    """
    Health check endpoint to verify that the API is running.
    """
    return {"status": "ok"}


class _IntersectionContainerAndState(Container, ContainerState):
    pass

@router.get("/api/web/orphans", tags=["API"])
def get_orphans(session: SessionDep) -> list[_IntersectionContainerAndState]:
    """
    Retrieves a list of containers that do not have an associated state entry.
    These are considered "orphaned" containers.
    :return:
    """

    orphans = []
    statement = select(Container).where(
        Container.context.is_(None),
    )
    results = session.exec(statement).all()

    statuses: dict[str, ContainerState] = {}
    state_statement = select(ContainerState)
    state_results = session.exec(state_statement).all()
    for state in state_results:
        statuses[state.id] = state


    orphans: list[_IntersectionContainerAndState] = []
    for container in results:
        status = statuses.get(container.id, None)


        orphan = _IntersectionContainerAndState(
            id=container.id,
            agent_id=container.agent_id,
            context=container.context,
            name=container.name,
            image=container.image,
            created_at=container.created_at,
            status=status.status if status else "unknown",
            since=status.since if status else 0,
        )
        orphans.append(orphan)

    return orphans

class _IntersectionContainerContainerAndState(_IntersectionContainerAndState, Context):
    pass

@router.get("/api/web/services", tags=["API"])
def get_services(session: SessionDep) -> dict[str, List[_IntersectionContainerContainerAndState]]:
    """
    Retrieves a mapping of context names to their associated containers and states.
    :return:
    """
    statement = select(Container, Context, ContainerState).join(
        Context, Container.context == Context.id
    ).join(
        ContainerState, Container.id == ContainerState.id
    )

    results = session.exec(statement).all()

    services: dict[str, List[_IntersectionContainerContainerAndState]] = {}
    for container, context, state in results:



        service = _IntersectionContainerContainerAndState(
            id=container.id,
            agent_id=container.agent_id,
            context=container.context,
            name=container.name,
            image=container.image,
            created_at=container.created_at,
            status=state.status,
            since=state.since,
            type=context.type,
        )
        if context.name not in services:
            services[context.name] = []
        services[context.name].append(service)

    return services

@router.get("/api/web/logs", tags=["API"])
def get_logs(container_id: Union[str, None] = None, limit: int = 100, level: str | None = None, session: SessionDep = SessionDep()) -> list[Log]:
    """
    Retrieves logs for a specific container or all containers if no container_id is provided.
    :param level: The log level to filter by (e.g., "INFO", "ERROR"). If None, retrieves logs of all levels.
    :param container_id: The ID of the container to retrieve logs for. If None, retrieves logs for all containers.
    :param limit: The maximum number of log entries to retrieve.
    :param session: The database session dependency.
    :return: A list of log entries.
    """

    statement = select(Log)
    if container_id:
        statement = statement.where(Log.container_id == container_id)
    if level:
        statement = statement.where(Log.level == level.upper())
    statement = statement.order_by(Log.timestamp.desc()).limit(limit)

    results = session.exec(statement).all()

    return results

@router.get("/api/web/agents", tags=["API"])
def get_agents(session: SessionDep) -> list[Agent]:
    """
    Retrieves a list of agents with their details.
    :return:
    """
    statement = select(Agent)
    results = session.exec(statement).all()
    agents: list[Agent] = []
    for agent in results:
        agent_model = Agent(
            id=agent.id,
            hostname=agent.hostname,
            heartbeat_interval=agent.heartbeat_interval,
            discovery_interval=agent.discovery_interval,
            on_host=agent.on_host
        )
        agents.append(agent_model)

    return agents