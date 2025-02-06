"""Scrapy middlewares module.

This module defines Scrapy middlewares. Middlewares are processing components that handle requests and
responses, typically used for adding custom headers, retrying requests, and handling exceptions.

There are 2 types of middlewares: spider middlewares and downloader middlewares. For detailed information
on creating and utilizing them, refer to the official documentation:
https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
https://docs.scrapy.org/en/latest/topics/spider-middleware.html
"""
# ruff: noqa: ARG002, UP028

from __future__ import annotations

from typing import TYPE_CHECKING

# Useful for handling different item types with a single interface
from scrapy import Request, Spider, signals

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from scrapy.crawler import Crawler
    from scrapy.http import Response


class TitleSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> TitleSpiderMiddleware:
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response: Response, spider: Spider) -> None:
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(
        self,
        response: Response,
        result: Iterable,
        spider: Spider,
    ) -> Generator[Iterable[Request] | None, None, None]:
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(
        self,
        response: Response,
        exception: BaseException,
        spider: Spider,
    ) -> Iterable[Request] | None:
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    def process_start_requests(
        self, start_requests: Iterable[Request], spider: Spider
    ) -> Iterable[Request]:  # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn't have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider: Spider) -> None:
        pass


class TitleDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> TitleDownloaderMiddleware:
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request: Request, spider: Spider) -> Request | Response | None:
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request: Request, response: Response, spider: Spider) -> Request | Response:
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request: Request, exception: BaseException, spider: Spider) -> Response | None:
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider: Spider) -> None:
        pass
