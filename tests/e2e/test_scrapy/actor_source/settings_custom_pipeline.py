from actor.settings import *  # noqa: F403  # ty: ignore[import-not-found]

ITEM_PIPELINES = {
    'actor.pipelines.PriceCleanerPipeline': 100,
}
