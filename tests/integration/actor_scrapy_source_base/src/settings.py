"""
Scrapy settings module

This module contains Scrapy settings for the project, defining various configurations and options.

For more comprehensive details on Scrapy settings, refer to the official documentation:
http://doc.scrapy.org/en/latest/topics/settings.html
"""

# You can update these options and add new ones
BOT_NAME = 'titlebot'
DEPTH_LIMIT = 1
LOG_LEVEL = 'INFO'
NEWSPIDER_MODULE = 'src.spiders'
REQUEST_FINGERPRINTER_IMPLEMENTATION = '2.7'
ROBOTSTXT_OBEY = True
SPIDER_MODULES = ['src.spiders']
ITEM_PIPELINES = {
    'src.pipelines.TitleItemPipeline': 123,
}
SPIDER_MIDDLEWARES = {
    'src.middlewares.TitleSpiderMiddleware': 543,
}
DOWNLOADER_MIDDLEWARES = {
    'src.middlewares.TitleDownloaderMiddleware': 543,
}
