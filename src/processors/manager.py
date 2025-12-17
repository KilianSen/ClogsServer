import asyncio
import logging
import time
from typing import Type, List, get_args

from sqlmodel import Session, select

from src.database import engine
from src.processors import Processor, load_processors

logger = logging.getLogger(__name__)

class ProcessorManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.processors = []
            cls._instance.processors_by_model = {}
            cls._instance.running = False
        return cls._instance

    def load_all(self, path: str):
        logger.info(f"Loading processors from {path}")
        processor_classes = load_processors(path)
        for cls in processor_classes:
            try:
                instance = cls()
                self.processors.append(instance)

                # Inspect generic type X
                model_type = self._get_model_type(cls)
                if model_type:
                    if model_type not in self.processors_by_model:
                        self.processors_by_model[model_type] = []
                    self.processors_by_model[model_type].append(instance)
                    logger.info(f"Registered processor {cls.__name__} for model {model_type.__name__}")
                else:
                    logger.warning(f"Could not determine model type for processor {cls.__name__}")

                instance.on_startup()
            except Exception as e:
                logger.error(f"Failed to load processor {cls}: {e}")

    def _get_model_type(self, cls: Type[Processor]) -> Type | None:
        for base in cls.__bases__:
            args = get_args(base)
            if args and len(args) >= 1:
                return args[0]
        return None

    def get_processors(self, model_type: Type) -> List[Processor]:
        return self.processors_by_model.get(model_type, [])

    async def start_interval_loop(self):
        self.running = True
        logger.info("Starting processor interval loop")
        while self.running:
            try:
                await self._run_intervals()
            except Exception as e:
                logger.error(f"Error in interval loop: {e}")
            await asyncio.sleep(1)

    async def _run_intervals(self):
        now = time.time()

        for processor in self.processors:
            last_run = getattr(processor, "_last_run", 0)
            if now - last_run >= processor.interval:
                try:
                    processor.on_interval()

                    # Also run on_interval_each
                    model_type = self._get_model_type(type(processor))
                    if model_type:
                        with Session(engine) as session:
                            statement = select(model_type)
                            results = session.exec(statement).all()
                            for item in results:
                                processor.on_interval_each(item)

                    setattr(processor, "_last_run", now)
                except Exception as e:
                    logger.error(f"Error running interval for {type(processor).__name__}: {e}")

    def shutdown(self):
        self.running = False
        for processor in self.processors:
            try:
                processor.on_shutdown()
                processor.close()
            except Exception as e:
                logger.error(f"Error shutting down processor {type(processor).__name__}: {e}")

