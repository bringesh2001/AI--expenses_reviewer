from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import engine
from .seed import seed_employees
from .routers import health, employees, submissions, qa


@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_employees()
    yield
    await engine.dispose()


app = FastAPI(
    title="Switchyard — Expense Pre-Review API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(employees.router)
app.include_router(submissions.router)
app.include_router(qa.router)


@app.get("/")
def root():
    return {"service": "switchyard-api", "docs": "/docs"}
