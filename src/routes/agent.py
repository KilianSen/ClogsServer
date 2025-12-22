import time

from fastapi import  Query, Response, HTTPException
from typing import List

from sqlmodel import select

from src.database import SessionDep
from src.models.agents import Agent, Container, ContainerState, Log, Heartbeat, Context, MultiContainerLogTransfer, \
    LogProtocol, MultilineLogTransfer
from src.routes import router
import logging
from uuid import uuid4

logger = logging.getLogger("clogs.agent")

@router.post("/api/agent/")
def register_new_agent(agent: Agent, session: SessionDep) -> str:
    if not agent.id:
        agent.id = str(uuid4())

    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent.id

@router.delete("/api/agent/{agent_id}/", status_code=204)
def delete_agent(agent_id: str, session: SessionDep):
    agent = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    session.delete(agent)
    session.commit()
    return Response(status_code=204)

@router.post("/api/agent/{agent_id}/heartbeat", status_code=204)
def receive_agent_heartbeat(agent_id: str, session: SessionDep):
    if not session.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    session.add(Heartbeat(agent_id=agent_id, timestamp=time.time_ns()))
    session.commit()
    return

@router.post("/api/agent/{agent_id}/container", status_code=201)
def register_container(container: Container, session: SessionDep) -> str:
    if not session.get(Agent, container.agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")

    if not container.id:
        container.id = str(uuid4())

    if session.get(Container, container.id):
        raise HTTPException(status_code=409, detail="Container with this ID already exists")

    session.add(container)
    session.commit()
    session.refresh(container)
    return container.id

@router.post("/api/agent/{agent_id}/logs")
def upload_agent_logs(agent_id: str, logs: MultiContainerLogTransfer | MultilineLogTransfer | Log, session: SessionDep):
    if not session.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")

    if not isinstance(logs, LogProtocol) and not all(isinstance(logs, cls) for cls in (MultiContainerLogTransfer, MultilineLogTransfer, Log)):
        raise HTTPException(status_code=400, detail="Invalid log format")

    try:
        logs.add_log_entries(session, agent_id, None)
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    session.commit()
    return Response(status_code=200)


@router.post("/api/agent/{agent_id}/container/{container_id}/")
def update_container_state(agent_id: str, container_id: str, container: Container, session: SessionDep):
    db_container = session.get(Container, container_id)
    if not db_container or db_container.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Container not found or mismatched agent ID")

    for field, value in container.model_dump().items():
        if field.endswith("id"):
            continue  # Skip primary key and foreign key fields
        setattr(db_container, field, value)

    session.commit()
    return Response(status_code=200)


@router.post("/api/agent/{agent_id}/container/{container_id}/logs")
def upload_container_logs(agent_id: str, container_id: str, logs: Log | MultilineLogTransfer, session: SessionDep):
    if not isinstance(logs, LogProtocol) and not all(isinstance(logs, cls) for cls in (MultilineLogTransfer, Log)):
        raise HTTPException(status_code=400, detail="Invalid log format")

    db_container = session.get(Container, container_id)
    if not db_container or db_container.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Container not found or mismatched agent ID")

    try:
        logs.add_log_entries(session, agent_id, container_id)
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    session.commit()
    return Response(status_code=200)


@router.post("/api/agent/{agent_id}/container/{container_id}/status")
def update_container_status(agent_id: str, container_id: str, status: str, since: int, session: SessionDep):
    container = session.get(Container, container_id)
    if not container or container.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Container not found or mismatched agent ID")

    container_state = session.get(ContainerState, container_id)
    if not container_state:
        container_state = ContainerState(
            id=container_id,
            status=status,
            since=since
        )
        session.merge(container_state)
    else:
        container_state.status = status

    session.commit()
    return Response(status_code=200)

@router.delete("/api/agent/{agent_id}/container/{container_id}/")
def delete_container(agent_id: str, container_id: str, session: SessionDep):
    container = session.get(Container, container_id)
    if not container or container.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Container not found or mismatched agent ID")

    session.delete(container)
    session.commit()

    # Also delete associated container state
    container_state = session.get(ContainerState, container_id)
    if not container_state:
        raise HTTPException(status_code=404, detail="Inconsistent: Container state, for deletion, not found")

    session.delete(container_state)
    session.commit()

    return Response(status_code=200)

@router.put("/api/agent/{agent_id}/context/", status_code=201)
def register_context(agent_id: str, context: Context, session: SessionDep):
    if not session.get(Agent, agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")

    session.add(context)
    session.commit()
    session.refresh(context)
    return context.id

@router.delete("/api/agent/{agent_id}/context/{context_id}/", status_code=204)
def delete_context(agent_id: str, context_id: int, session: SessionDep):
    context = session.get(Context, context_id)
    if not context or context.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Context not found or mismatched agent ID")

    session.delete(context)
    session.commit()
    return Response(status_code=204)


# GET endpoints for agent to retrieve its configuration

@router.get("/api/agent/{agent_id}/")
def get_agent_info(agent_id: str, session: SessionDep) -> Agent:
    agent: Agent | None = session.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/api/agent/{agent_id}/context/")
def get_agent_contexts(agent_id: str, session: SessionDep) -> List[Context]:

    contexts = session.exec(
        select(Context).where(Context.agent_id == agent_id)
    ).all()

    return list(contexts)

@router.get("/api/agent/{agent_id}/container/")
def get_agent_containers(agent_id: str, session: SessionDep, context_id: int | None = Query(default=None)) -> List[Container]:
    query = select(Container).where(Container.agent_id == agent_id)
    if context_id is not None:
        query = query.where(Container.context == context_id)

    containers = session.exec(query).all()

    return list(containers)

