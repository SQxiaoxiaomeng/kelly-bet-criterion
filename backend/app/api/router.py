from fastapi import APIRouter

from app.api.routes.backtests import router as backtests_router
from app.api.routes.data import router as data_router
from app.api.routes.health import router as health_router
from app.api.routes.operations import router as operations_router
from app.api.routes.sim import router as sim_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(data_router)
api_router.include_router(backtests_router)
api_router.include_router(sim_router)
api_router.include_router(operations_router)
