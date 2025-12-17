from importlib import util
import os
from abc import ABCMeta, abstractmethod
from inspect import isabstract
from typing import Optional, Type

from pydantic import BaseModel
from sqlmodel import Session

from src.database import get_session


class Processor[X: BaseModel, Y: BaseModel](BaseModel, metaclass=ABCMeta):
    interval: int
    session: Session = get_session()

    # "Incremental" processor methods (called for each data item)

    @abstractmethod
    def on_inset(self, data: X) -> Optional[Y]:
        pass

    @abstractmethod
    def on_get(self, data: X) -> Optional[Y]:
        pass

    @abstractmethod
    def on_delete(self, data: X) -> Optional[Y]:
        pass

    # Periodic processor methods (called at regular intervals)

    @abstractmethod
    def on_interval(self):
        pass

    @abstractmethod
    def on_interval_each(self, data: X) -> Optional[Y]:
        pass

    # Lifecycle methods

    @abstractmethod
    def on_shutdown(self):
        pass

    @abstractmethod
    def on_startup(self):
        pass


def load_processors(path) -> list[type[Processor]]:
    processors: list[Type[Processor]] = []

    for file in os.listdir(path):
        if not file.endswith(".py"):
            continue
        spec = util.spec_from_file_location(file[:-9], os.path.join(path, file))
        module = util.module_from_spec(spec)
        e = spec.loader.exec_module(module)


        for attr in dir(module):
            if not isinstance(getattr(module, attr), type):
                continue
            if not issubclass(getattr(module, attr), Processor):
                continue

            if isabstract(getattr(module, attr)):
                continue

            processors.append(getattr(module, attr))
    return processors
