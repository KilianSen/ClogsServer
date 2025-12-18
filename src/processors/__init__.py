from importlib import util
import os
from abc import ABCMeta, abstractmethod
from inspect import isabstract
from typing import Optional, Type, get_args

from fastapi import APIRouter
from pydantic import BaseModel, PrivateAttr
from sqlmodel import Session

from src.database import engine


class Processor[X: BaseModel, Y: BaseModel | None](BaseModel, metaclass=ABCMeta):
    interval: int = 60
    _router: Optional[APIRouter] = PrivateAttr(default=None)
    _session: Optional[Session] = PrivateAttr(default=None)

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session(engine)
        return self._session

    # "Incremental" processor methods (called for each data item)

    @abstractmethod
    def on_insert(self, data: X) -> Optional[Y]:
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

    def close(self):
        if self._session:
            self._session.close()
            self._session = None

    def get_generic_types(self):
        cls = type(self)

        base = cls.__orig_bases__[0]

        return get_args(base)


def load_processors(path) -> list[type[Processor]]:
    processors: list[Type[Processor]] = []

    for root, dirs, files in os.walk(path):
        for file in files:
            if not file.endswith(".py"):
                continue
            if file == "__init__.py":
                continue

            full_path = os.path.join(root, file)
            module_name = file[:-3]

            spec = util.spec_from_file_location(module_name, full_path)
            if spec and spec.loader:
                module = util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr in dir(module):
                    val = getattr(module, attr)
                    if not isinstance(val, type):
                        continue
                    if not issubclass(val, Processor):
                        continue
                    if val is Processor:
                        continue
                    if isabstract(val):
                        continue

                    processors.append(val)
    return processors
