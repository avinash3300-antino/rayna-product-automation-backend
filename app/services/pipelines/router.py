"""Pipeline registry — maps product_type strings to pipeline instances."""

from app.services.pipelines.activity_pipeline import ActivityPipeline
from app.services.pipelines.base_pipeline import BasePipeline
from app.services.pipelines.cruise_pipeline import CruisePipeline

REGISTRY: dict[str, BasePipeline] = {
    "activities": ActivityPipeline(),
    "cruises": CruisePipeline(),
}


def get_pipeline(product_type: str) -> BasePipeline:
    """Return the pipeline instance for a product type.

    Raises ValueError if the product type is not registered.
    """
    pipeline = REGISTRY.get(product_type)
    if pipeline is None:
        raise ValueError(
            f"Unknown product type '{product_type}'. "
            f"Registered: {list(REGISTRY.keys())}"
        )
    return pipeline
