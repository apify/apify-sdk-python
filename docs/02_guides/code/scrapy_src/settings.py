"""Scrapy settings module.

This module contains Scrapy settings for the project, defining various configurations
and options.

For more comprehensive details on Scrapy settings, refer to the official documentation:
http://doc.scrapy.org/en/latest/topics/settings.html
"""

BOT_NAME = 'titlebot'
DEPTH_LIMIT = 1
LOG_LEVEL = 'INFO'
NEWSPIDER_MODULE = 'spiders'
REQUEST_FINGERPRINTER_IMPLEMENTATION = '2.7'
ROBOTSTXT_OBEY = True
SPIDER_MODULES = ['spiders']
