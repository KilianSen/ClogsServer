from abc import ABCMeta, abstractmethod
from typing import Optional

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