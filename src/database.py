from typing import Annotated, Type, Any, Optional

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine
import logging

logger = logging.getLogger(__name__)

sqlite_file_name = "clogs.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


class ProcessorSession(Session):
    def add(self, instance: Any, _warn: bool = True) -> None:
        super().add(instance, _warn=_warn)
        self._run_processor_hook("on_insert", instance)

    def delete(self, instance: Any) -> None:
        super().delete(instance)
        self._run_processor_hook("on_delete", instance)

    def get(self, entity: Type[Any], ident: Any, **kwargs: Any) -> Any | None:
        instance = super().get(entity, ident, **kwargs)
        if instance:
            self._run_processor_hook("on_get", instance, model_type=entity)
        return instance

    def _run_processor_hook(self, method_name: str, instance: Any, model_type: Type = None):
        try:
            # Import locally to avoid circular dependency
            from src.processors.manager import ProcessorManager

            if model_type is None:
                model_type = type(instance)

            processors = ProcessorManager().get_processors(model_type)
            for processor in processors:
                method = getattr(processor, method_name)
                try:
                    method(instance)
                except Exception as e:
                    logger.error(f"Error in processor {method_name} for {model_type.__name__}: {e}")
        except ImportError:
            # ProcessorManager might not be ready or circular import issue during startup
            pass
        except Exception as e:
            logger.error(f"Error running processor hook: {e}")


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with ProcessorSession(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
