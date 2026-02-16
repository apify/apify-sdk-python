from src.settings import *  # noqa: F403  # ty: ignore[unresolved-import]

ITEM_PIPELINES = {
    'src.pipelines.PriceCleanerPipeline': 100,
}
