from contextlib import asynccontextmanager

from fastapi import FastAPI
import logging
import uvicorn

from src.database import create_db_and_tables
from src.routes import router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield
    # Clean up

app = FastAPI(title="Clogs Server", version="0.1.0", lifespan=lifespan)
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Clogs Server is running"}

if __name__ == "__main__":
    # Run the server with: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
