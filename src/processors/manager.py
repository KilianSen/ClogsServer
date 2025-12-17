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
                model_type = self.get_model_type(cls)
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

    def get_model_type(self, cls: Type[Processor]) -> Type | None:
        return self._get_pydantic_generic_args(cls)[0] if self._get_pydantic_generic_args(cls) else None

    def get_output_type(self, cls: Type[Processor]) -> Type | None:
        return self._get_pydantic_generic_args(cls)[1] if self._get_pydantic_generic_args(cls) else None

    @staticmethod
    def _get_pydantic_generic_args(cls):
        # Iterate over bases to find the one that has Pydantic metadata
        for base in cls.__bases__:
            metadata = getattr(base, "__pydantic_generic_metadata__", None)
            if metadata and "args" in metadata:
                return metadata["args"]
        return ()

    def get_processors(self, model_type: Type) -> List[Processor]:
        return self.processors_by_model.get(model_type, [])

    async def start_interval_loop(self):
        self.running = True

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
            model_type = self.get_model_type(type(processor))
            if model_type:
                with Session(engine) as session:
                    statement = select(model_type)
                    results = session.exec(statement).all()
                    for item in results:
                        # Process each item

                        processed_item = processor.on_interval_each(item)

                        if not processed_item:
                            continue

                        output_type = self.get_output_type(type(processor))

                        if not output_type:
                            raise Exception(f"Processor {type(processor).__name__} returned a value from on_interval_each but has no output type.")

                        if not isinstance(processed_item, output_type):
                            raise Exception(f"Processor {type(processor).__name__} returned wrong type from on_interval_each: expected {output_type.__name__}, got {type(processed_item).__name__}")

                        input_type = self.get_model_type(type(processor))

                        if not input_type:
                            raise Exception(f"Processor {type(processor).__name__} has no input type defined.")

                        if input_type == output_type:
                            # Same type, update the item directly
                            session.merge(processed_item)
                        else:
                            # Different types, add the new item
                            session.add(processed_item)
                    session.commit()



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

