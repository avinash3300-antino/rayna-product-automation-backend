from fastapi import APIRouter

from app.api.v1.routes.activities import router as activities_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.destinations import router as destinations_router
from app.api.v1.routes.discovery import router as discovery_router
from app.api.v1.routes.reviews import router as reviews_router
from app.api.v1.routes.scraping import router as scraping_router
from app.api.v1.routes.sessions import router as sessions_router
from app.api.v1.routes.users import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(sessions_router)
router.include_router(users_router)
router.include_router(destinations_router)
router.include_router(discovery_router)
router.include_router(scraping_router)
router.include_router(activities_router)
router.include_router(reviews_router)
