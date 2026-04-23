"""Enrichment service — backward-compatible wrapper.

Enrichment logic is now inside each pipeline class (activity_pipeline, cruise_pipeline).
This module provides the legacy `enrich_activity()` function for existing callers.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activities import Activity
from app.services.pipelines.activity_pipeline import ActivityPipeline

logger = logging.getLogger(__name__)

_activity_pipeline = ActivityPipeline()


async def enrich_activity(
    db: AsyncSession,
    activity: Activity,
) -> Activity:
    """Enrich an activity using Claude AI rewrite.

    Delegates to ActivityPipeline.enrich_product().
    """
    await _activity_pipeline.enrich_product(db, activity)
    return activity
