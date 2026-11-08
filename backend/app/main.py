from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_CORS_ORIGINS
from .database import init_db
from .routers import auth, cleaning, datasets, experiments, models, profiling


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="DataLab API",
    description="Automated Data Analysis, Data Cleaning & Machine Learning Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(profiling.router, prefix="/api/v1")
app.include_router(cleaning.router, prefix="/api/v1")
app.include_router(experiments.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "DataLab API is running", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
