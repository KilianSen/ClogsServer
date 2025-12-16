import time

from fastapi import Depends, Query, Response
from typing import List

from sqlmodel import select

from src.database import SessionDep
from src.model.api import MultilineLogTransfer
from src.models.agents import Agent, Container, ContainerState, Log, Heartbeat, Context, MultiContainerLogTransfer
from src.routes import router
import logging
from uuid import uuid4

logger = logging.getLogger("clogs.agent")

def add_log_entry(session: SessionDep, log: Log):
    if log.id is None:
        log.id = str(uuid4())
    session.add(log)

@router.post("/api/agent/")
def register_new_agent(agent: Agent, session: SessionDep) -> str:
    if not agent.id:
        agent.id = str(uuid4())

    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent.id

@router.delete("/api/agent/{agent_id}/", status_code=204)
def delete_agent(agent_id: str, session: SessionDep, response: Response):
    agent = session.get(Agent, agent_id)
    if agent:
        session.delete(agent)
        session.commit()
        response.status_code = 204
    else:
        logger.warning(f"Attempted to delete non-existent agent: {agent_id}")
        response.status_code = 404
    return response

@router.post("/api/agent/{agent_id}/heartbeat", status_code=204)
def receive_agent_heartbeat(agent_id: str, session: SessionDep, response: Response):
    if not session.get(Agent, agent_id):
        logger.warning(f"Heartbeat received for unknown agent: {agent_id}")
        response.status_code = 404
        return response
    session.add(Heartbeat(agent_id=agent_id, timestamp=time.time_ns()))
    session.commit()
    response.status_code = 204
    return response

@router.post("/api/agent/{agent_id}/container", status_code=201)
def register_container(container: Container, session: SessionDep, response: Response) -> str:
    if not session.get(Agent, container.agent_id):
        logger.warning(f"Attempted to register container for unknown agent: {container.agent_id}")
        response.status_code = 404
        return response

    if not container.id:
        container.id = str(uuid4())

    if session.get(Container, container.id):
        logger.warning(f"Attempted to register already existing container: {container.id}")
        response.status_code = 409
        return response


    session.add(container)
    session.commit()
    session.refresh(container)
    response.status_code = 201
    return container.id

@router.post("/api/agent/{agent_id}/logs")
def upload_agent_logs(agent_id: str, logs: MultiContainerLogTransfer | MultilineLogTransfer | Log, session: SessionDep, response: Response):
    if not session.get(Agent, agent_id):
        logger.warning(f"Attempted to upload logs for unknown agent: {agent_id}")
        response.status_code = 404
        return response

    if isinstance(logs, MultiContainerLogTransfer):
        for container_logs in logs.container_logs:
            db_container = session.get(Container, container_logs.container_id)
            if not db_container or db_container.agent_id != agent_id:
                logger.warning(f"Attempted to upload logs for non-existent or mismatched container: {container_logs.container_id} for agent {agent_id}")
                continue
            for log_entry in container_logs.logs:
                add_log_entry(session, log_entry)
            session.commit()
            return Response(status_code=200)

    db_container = session.get(Container, logs.container_id)

    if not db_container:
        logger.warning(f"DB Container not found for container_id: {logs.container_id}")
        return Response(status_code=404)

    if isinstance(logs, MultilineLogTransfer):
        for log_entry in logs.logs:
            add_log_entry(session, log_entry)

        session.commit()
        return Response(status_code=200)

    if isinstance(logs, Log):
        add_log_entry(session, logs)
        session.commit()
        return Response(status_code=200)

    return Response(status_code=404)

@router.post("/api/agent/{agent_id}/container/{container_id}/")
def update_container_state(agent_id: str, container_id: str, container: Container, session: SessionDep, response: Response):
    db_container = session.get(Container, container_id)
    if not db_container or db_container.agent_id != agent_id:
        logger.warning(f"Attempted to update non-existent or mismatched container: {container_id} for agent {agent_id}")
        response.status_code = 404
        return response

    for field, value in container.model_dump().items():
        if field.endswith("id"):
            continue  # Skip primary key and foreign key fields
        setattr(db_container, field, value)

    session.commit()
    response.status_code = 200
    return response

@router.post("/api/agent/{agent_id}/container/{container_id}/logs")
def upload_container_logs(agent_id: str, container_id: str, logs: Log | MultilineLogTransfer, session: SessionDep):
    db_container = session.get(Container, container_id)
    if not db_container or db_container.agent_id != agent_id:
        logger.warning(f"Attempted to upload logs for non-existent or mismatched container: {container_id} for agent {agent_id}")
        return Response(status_code=404)

    if isinstance(logs, MultilineLogTransfer):
        for log_entry in logs.logs:
            add_log_entry(session, log_entry)
    else:
        add_log_entry(session, logs)

    session.commit()
    return Response(status_code=200)

@router.post("/api/agent/{agent_id}/container/{container_id}/status")
def update_container_status(agent_id: str, container_id: str, status: str, session: SessionDep, response: Response):
    container = session.get(Container, container_id)
    if not container or container.agent_id != agent_id:
        logger.warning(f"Attempted to update status for non-existent or mismatched container: {container_id} for agent {agent_id}")
        response.status_code = 404
        return response

    container_state = session.get(ContainerState, container_id)
    if not container_state:
        container_state = ContainerState(
            id=container_id,
            status=status
        )
        session.merge(container_state)
    else:
        container_state.status = status

    session.commit()
    response.status_code = 200
    return response

@router.delete("/api/agent/{agent_id}/container/{container_id}/")
def delete_container(agent_id: str, container_id: str, session: SessionDep, response: Response):
    container = session.get(Container, container_id)
    if container and container.agent_id == agent_id:
        session.delete(container)
        session.commit()

        # Also delete associated container state
        container_state = session.get(ContainerState, container_id)
        if container_state:
            session.delete(container_state)
            session.commit()
        else:
            logger.debug(f"No container state found for container: {container_id} during deletion.")

        response.status_code = 204
    else:
        logger.warning(f"Attempted to delete non-existent or mismatched container: {container_id} for agent {agent_id}")
        response.status_code = 404
    return response

@router.put("/api/agent/{agent_id}/context/")
def register_context(agent_id: str, context: Context, session: SessionDep, response: Response):
    if not session.get(Agent, agent_id):
        logger.warning(f"Attempted to register context for unknown agent: {agent_id}")
        response.status_code = 404
        return response

    session.add(context)
    session.commit()
    session.refresh(context)
    response.status_code = 201
    return context.id

@router.delete("/api/agent/{agent_id}/context/{context_id}/")
def delete_context(agent_id: str, context_id: int, session: SessionDep, response: Response):
    context = session.get(Context, context_id)
    if context and context.agent_id == agent_id:
        session.delete(context)
        session.commit()
        response.status_code = 204
    else:
        logger.warning(f"Attempted to delete non-existent or mismatched context: {context_id} for agent {agent_id}")
        response.status_code = 404
    return response


# GET endpoints for agent to retrieve its configuration

@router.get("/api/agent/{agent_id}/")
def get_agent_info(agent_id: str, session: SessionDep):
    agent = session.get(Agent, agent_id)
    if not agent:
        logger.warning(f"Attempted to get info for unknown agent: {agent_id}")
        return Response(status_code=404)
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

