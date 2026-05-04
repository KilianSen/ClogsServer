from typing import Annotated, Type, Any, Optional

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine
import logging
import os

logger = logging.getLogger(__name__)

sqlite_file_name = ".clogs/server/clogs.db"

# Check if the directory exists, if not create it
os.makedirs(os.path.dirname(sqlite_file_name), exist_ok=True)

sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


class ProcessorSession(Session):
    def add(self, instance: Any, _warn: bool = True) -> None:
        pp = self._run_processor_hook("on_insert", instance)
        super().add(instance if not pp else pp, _warn=_warn)

    def delete(self, instance: Any) -> None:
        pp = self._run_processor_hook("on_delete", instance)
        super().delete(instance if not pp else pp)

    def get(self, entity: Type[Any], ident: Any, **kwargs: Any) -> Any | None:
        instance = super().get(entity, ident, **kwargs)
        pp: Optional[Any] = None
        if instance:
            pp = self._run_processor_hook("on_get", instance, model_type=entity)
        return instance if not pp else pp

    def _run_processor_hook(self, method_name: str, instance: Any, model_type: Type = None) -> Any:
        try:
            # Import locally to avoid circular dependency
            from src.processors.manager import ProcessorManager

            if model_type is None:
                model_type = type(instance)

            processors = ProcessorManager().get_processors(model_type)
            for processor in processors:
                # Inject the current session into the processor
                processor._session = self
                
                method = getattr(processor, method_name)
                try:
                    post_instance = method(instance)

                    output_type = ProcessorManager().get_output_type(type(processor))

                    if output_type is None and post_instance is None:
                        continue # Try next processor
                    elif post_instance is not None and output_type is None:
                        raise Exception(f"Error in processor {method_name}: Expected None but got a value.")
                    elif post_instance is None and output_type is not None:
                        return None # This processor decided to drop the instance
                    else:
                        if not isinstance(post_instance, output_type):
                            raise Exception(f"Error in processor {method_name}: Expected type {output_type.__name__} but got {type(post_instance).__name__}.")
                        instance = post_instance # Update instance for next processor
                except Exception as e:
                    logger.error(f"Error in processor {method_name} for {model_type.__name__}: {e}")
                finally:
                    # Clear the injected session to avoid leaking or side effects
                    processor._session = None
            
            return instance
        except ImportError:
            # ProcessorManager might not be ready or circular import issue during startup
            return instance
        except Exception as e:
            logger.error(f"Error running processor hook: {e}")
            return instance

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with ProcessorSession(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
