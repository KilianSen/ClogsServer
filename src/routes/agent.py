import time

from fastapi import Depends, Query, Response
from typing import List, Optional, Type
import json
from sqlalchemy.orm import Session

from src.external import (
    AgentRegistration,
    Heartbeat,
    AgentState,
    LogMessage
)
from src.database import SessionDep
from src.models.agents import Agent, Container, ContainerState, Log
from src.routes import router
import logging

logger = logging.getLogger("clogs.agent")

@router.post("/api/agent/")
def register_new_agent(agent: Agent, session: SessionDep) -> str:
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

    if session.get(Container, container.id):
        logger.warning(f"Attempted to register already existing container: {container.id}")
        response.status_code = 409
        return response

    session.add(container)
    session.commit()
    session.refresh(container)
    response.status_code = 201
    return container.id

@router.post("/api/agent/{agent_id}/container/{container_id}/")
def update_container_state(agent_id: str, container_id: str, container: Container, session: SessionDep, response: Response):
    db_container = session.get(Container, container_id)
    if not db_container or db_container.agent_id != agent_id:
        logger.warning(f"Attempted to update non-existent or mismatched container: {container_id} for agent {agent_id}")
        response.status_code = 404
        return response

    for field, value in container.model_dump().items():
        setattr(db_container, field, value)

    session.commit()
    response.status_code = 200
    return response

@router.post("/api/agent/{agent_id}/container/{container_id}/logs")
def upload_container_logs(agent_id: str, container_id: str, logs: List[Log], session: SessionDep):
    db_container = session.get(Container, container_id)

    if not db_container or db_container.agent_id != agent_id:
        logger.warning(f"Attempted to upload logs for non-existent or mismatched container: {container_id} for agent {agent_id}")
        return {"status": "error", "message": "Container not found"}, 404

    for log in logs:
        log.container_id = container_id
        session.add(log)

    session.commit()
    return {"status": "logs_uploaded", "count": len(logs)}

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
        session.add(container_state)
    else:
        container_state.status = status

    session.commit()
    response.status_code = 200
    return response

@router.delete("/api/agent/{agent_id}/container/{container_id}/")
def delete_container(agent_id: str, container_id: str, session: SessionDep, response: Response):
    container = session.get(sql_models.Container, container_id)
    if container and container.agent_id == agent_id:
        session.delete(container)
        session.commit()
        response.status_code = 204
    else:
        logger.warning(f"Attempted to delete non-existent or mismatched container: {container_id} for agent {agent_id}")
        response.status_code = 404
    return response