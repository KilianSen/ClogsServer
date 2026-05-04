import asyncio
import logging
import time
from typing import Type, List, get_args

from fastapi import APIRouter
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

    def load_all(self, path: str, router: APIRouter):
        logger.info(f"Loading processors from {path}")
        processor_classes = load_processors(path)
        for cls in processor_classes:
            try:
                instance = cls()
                instance._router = router
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
        args = self._get_generic_args(cls)
        return args[0] if args else None

    def get_output_type(self, cls: Type[Processor]) -> Type | None:
        args = self._get_generic_args(cls)
        return args[1] if len(args) > 1 else None

    @staticmethod
    def _get_generic_args(cls):
        # Look for __orig_bases__ to find generic arguments in a more standard way
        for base in getattr(cls, "__orig_bases__", []):
            if get_args(base):
                return get_args(base)
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
        max_retries = 3
        retry_delay = 0.5
        
        try:
            # Run on_interval which may handle its own session
            for attempt in range(max_retries):
                try:
                    processor.on_interval()
                    break
                except Exception as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    logger.error(f"Error in on_interval for {type(processor).__name__}: {e}")
                    break

            # Also run on_interval_each
            model_type = self.get_model_type(type(processor))
            if model_type:
                # Use a fresh session and ensure it's closed
                with Session(engine) as session:
                    for attempt in range(max_retries):
                        try:
                            # Paginated processing to avoid memory exhaustion
                            offset = 0
                            batch_size = 100
                            
                            while True:
                                statement = select(model_type).offset(offset).limit(batch_size)
                                results = session.exec(statement).all()
                                
                                if not results:
                                    break
                                    
                                for item in results:
                                    try:
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
                                    except Exception as e:
                                        logger.error(f"Error processing item in on_interval_each for {type(processor).__name__}: {e}")
                                
                                offset += batch_size
                                # Commit after each batch to keep transaction sizes manageable
                                session.commit()
                            
                            break
                        except Exception as e:
                            session.rollback()
                            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            logger.error(f"Failed to commit interval_each for {type(processor).__name__}: {e}")
                            break
                    finally:
                        session.close()

            setattr(processor, "_last_run", time.time())
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error running interval for {type(processor).__name__}: {e}\n{traceback.format_exc()}")

    def shutdown(self):
        self.running = False
        for processor in self.processors:
            try:
                processor.on_shutdown()
                processor.close()
            except Exception as e:
                logger.error(f"Error shutting down processor {type(processor).__name__}: {e}")

