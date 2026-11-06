from actor.settings import *  # noqa: F403  # ty: ignore[unresolved-import]

ITEM_PIPELINES = {
    'actor.pipelines.PriceCleanerPipeline': 100,
}
