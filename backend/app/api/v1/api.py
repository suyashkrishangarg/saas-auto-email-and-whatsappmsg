from fastapi import APIRouter

from app.api.v1.endpoints import admin, auth, clients, gmail, ingestion, notices

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(clients.router, prefix="/clients", tags=["clients"])
api_router.include_router(notices.router, prefix="/notices", tags=["notices"])
api_router.include_router(ingestion.router, prefix="/ingest", tags=["ingestion"])
api_router.include_router(gmail.router, prefix="/gmail", tags=["gmail"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
