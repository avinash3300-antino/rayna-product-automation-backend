from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic can detect them
from app.db.models.auth import AuthUser, AuthRole, AuthUserRole  # noqa: E402, F401
from app.db.models.sessions import AuthUserSession  # noqa: E402, F401
from app.db.models.discovery import (  # noqa: E402, F401
    AIDiscoveryRun,
    AIDiscoveryDestinationCandidate,
    AIDiscoverySeedItem,
    AIDiscoveryReviewAction,
)
from app.db.models.destinations import CatalogDestination, CatalogLocation  # noqa: E402, F401
from app.db.models.sources import (  # noqa: E402, F401
    IngestionSource,
    IngestionSourceTermsPolicy,
    IngestionSourceCategoryCoverage,
    IngestionSourceLegalChecklist,
    IngestionSourceLegalChecklistItem,
)
from app.db.models.intelligence import (  # noqa: E402, F401
    IngestionDestinationIntelligenceRun,
    IngestionDestinationKeyword,
    IngestionDestinationPaaQuestion,
    IngestionSourceDiscoveryCandidate,
    IngestionApprovedSourceList,
    IngestionApprovedSourceListItem,
    IngestionApprovedSourceListAudit,
)
from app.db.models.ingestion import (  # noqa: E402, F401
    IngestionJob,
    IngestionJobSource,
    IngestionRawRecord,
    IngestionRawRecordMedia,
)
from app.db.models.workflow import (  # noqa: E402, F401
    WorkflowClassificationResult,
    WorkflowClassificationReviewQueue,
    WorkflowClassificationReviewAction,
    WorkflowAttributeMappingRun,
    WorkflowAttributeEnrichmentQueue,
)
from app.db.models.products import (  # noqa: E402, F401
    CatalogProduct,
    CatalogProductVersion,
    CatalogProductStatusHistory,
)
from app.db.models.hotels import (  # noqa: E402, F401
    CatalogHotelProduct,
    CatalogHotelRoomType,
    CatalogHotelBoardType,
    CatalogHotelAmenitiesMaster,
    CatalogHotelProductAmenity,
)
from app.db.models.attractions import (  # noqa: E402, F401
    CatalogAttractionProduct,
    CatalogAttractionOperatingHours,
    CatalogAttractionTicketType,
)
from app.db.models.transfers import CatalogTransferProduct  # noqa: E402, F401
from app.db.models.restaurants import (  # noqa: E402, F401
    CatalogRestaurantProduct,
    CatalogRestaurantCuisinesMaster,
    CatalogRestaurantProductCuisine,
    CatalogRestaurantOperatingHours,
)
from app.db.models.product_shared import (  # noqa: E402, F401
    CatalogProductMedia,
    CatalogProductFaq,
    CatalogProductSchemaMarkup,
)
from app.db.models.content import (  # noqa: E402, F401
    ContentDestinationKeywordSet,
    ContentProductContent,
    ContentContentGenerationRun,
    ContentContentReviewQueue,
    ContentContentReviewAction,
)
from app.db.models.tags import (  # noqa: E402, F401
    CatalogTagDimension,
    CatalogTag,
    CatalogProductTag,
    CatalogProductTagSuggestion,
)
from app.db.models.booking_sources import (  # noqa: E402, F401
    CatalogBookingSource,
    CatalogProductBookingSource,
    OpsBookingSourceHealthCheck,
)
from app.db.models.ops import (  # noqa: E402, F401
    OpsFreshnessRule,
    OpsProductFreshnessStatus,
    OpsProductQualityCheck,
    OpsErrorQueue,
    OpsJobMetrics,
    OpsNotification,
    OpsApiAudit,
)
from app.db.models.packages import (  # noqa: E402, F401
    PricingPackageType,
    PricingPackageRule,
    PricingPackage,
    PricingPackageComponent,
    PricingPackageTag,
    PricingPackageMedia,
    PricingPackageItineraryDay,
    PricingPackageGenerationRun,
    PricingPackagePriceCalculation,
)
from app.db.models.publishing import (  # noqa: E402, F401
    PublishingPushBatch,
    PublishingPushBatchItem,
    PublishingBatchApproval,
    PublishingRollbackBatch,
    PublishingRollbackBatchItem,
)
from app.db.models.audit import AuditAuditLog  # noqa: E402, F401
