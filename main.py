from contextlib import asynccontextmanager
import asyncio
import os

from fastapi import FastAPI
import logging
import uvicorn

from src.database import create_db_and_tables
from src.routes import router
from src.processors.manager import ProcessorManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()

    # Initialize processors
    manager = ProcessorManager()
    processors_path = os.path.join(os.path.dirname(__file__), "src", "processors")
    manager.load_all(processors_path)

    # Start interval loop
    task = asyncio.create_task(manager.start_interval_loop())

    yield

    # Clean up
    manager.shutdown()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Clogs Server", version="0.1.0", lifespan=lifespan)
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Clogs Server is running"}

if __name__ == "__main__":
    # Run the server with: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
