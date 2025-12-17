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
        logger.info("Starting processor interval loops")

        self.tasks = []
        for processor in self.processors:
            task = asyncio.create_task(self._run_processor_loop(processor))
            self.tasks.append(task)

        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Interval loop cancelled")
        finally:
            for task in self.tasks:
                task.cancel()
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _run_processor_loop(self, processor: Processor):
        logger.info(f"Started loop for {type(processor).__name__}")
        while self.running:
            start_time = time.time()
            try:
                # Run blocking operations in a separate thread
                await asyncio.to_thread(self._execute_processor_interval, processor)
            except Exception as e:
                logger.error(f"Error in processor loop for {type(processor).__name__}: {e}")

            elapsed = time.time() - start_time
            sleep_time = max(0.1, processor.interval - elapsed)

            if sleep_time > 0:
                try:
                    await asyncio.sleep(sleep_time)
                except asyncio.CancelledError:
                    break

    def _execute_processor_interval(self, processor: Processor):
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

            setattr(processor, "_last_run", time.time())
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

