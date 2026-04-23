from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic can detect them
from app.db.models.auth import AuthUser, AuthRole, AuthUserRole  # noqa: E402, F401
from app.db.models.sessions import AuthUserSession  # noqa: E402, F401
from app.db.models.destinations import CatalogDestination, CatalogLocation  # noqa: E402, F401
from app.db.models.audit import AuditAuditLog  # noqa: E402, F401
from app.db.models.activities import Activity, ActivityTimeline  # noqa: E402, F401
from app.db.models.cruises import (  # noqa: E402, F401
    CruiseProduct,
    CruiseItinerary,
    CruiseCabin,
    CruisePricingTier,
)
from app.db.models.reviews import ProductReview, ProductEmbedding  # noqa: E402, F401
from app.db.models.scraping import (  # noqa: E402, F401
    ScrapeSource,
    SourceDiscoveryRun,
    ScrapeJob,
    AhrefsCache,
    SearchCache,
)
