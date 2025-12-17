from typing import Optional
import re
from sqlmodel import select, col, Session
from sqlalchemy.orm import object_session
from src.processors import Processor
from src.models.agents import Log

class LogCompressorProcessor(Processor[Log, Log]):
    def on_startup(self):
        pass

    interval: int = 600

    def on_insert(self, log: Log) -> Optional[Log]:
        # Get the session associated with the log object
        session: Session = object_session(log)

        if not session:
            return None

        # Query the last log for this container
        statement = select(Log).where(Log.container_id == log.container_id).order_by(col(Log.timestamp).desc()).limit(1)
        result = session.exec(statement).first()

        if result:
            last_log = result

            # Check if messages match (ignoring xNum suffix on the last log)
            match = re.search(r' x(\d+)$', last_log.message)
            last_msg_base = last_log.message
            count = 1

            if match:
                count = int(match.group(1))
                last_msg_base = last_log.message[:match.start()]

            if log.message == last_msg_base:
                # It's a repeat!
                new_count = count + 1
                last_log.message = f"{last_msg_base} x{new_count}"
                last_log.timestamp = log.timestamp # Update timestamp to latest

                session.add(last_log)

                # Remove the new log from the session so it's not inserted
                session.delete(log)

                return last_log

        return None

    def on_get(self, data: Log) -> Optional[Log]:
        return None

    def on_delete(self, data: Log) -> Optional[Log]:
        return None

    def on_interval(self):
        pass

    def on_interval_each(self, data: Log) -> Optional[Log]:
        return None

    def on_shutdown(self):
        pass

