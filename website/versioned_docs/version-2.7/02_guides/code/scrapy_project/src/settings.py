BOT_NAME = 'titlebot'
DEPTH_LIMIT = 1
LOG_LEVEL = 'INFO'
NEWSPIDER_MODULE = 'src.spiders'
ROBOTSTXT_OBEY = True
SPIDER_MODULES = ['src.spiders']
TELNETCONSOLE_ENABLED = False
# Do not change the Twisted reactor unless you really know what you are doing.
TWISTED_REACTOR = 'twisted.internet.asyncioreactor.AsyncioSelectorReactor'
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 7200
