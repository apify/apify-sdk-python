## Python Scrapy template

A template example built with Scrapy to scrape page titles from URLs defined in the input parameter. It shows how to use Apify SDK for Python and Scrapy pipelines to save results.

## Included features

- **[Apify SDK](https://docs.apify.com/sdk/python/)** for Python - a toolkit for building Apify [Actors](https://apify.com/actors) and scrapers in Python
- **[Input schema](https://docs.apify.com/platform/actors/development/input-schema)** - define and easily validate a schema for your Actor's input
- **[Request queue](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-request-queues)** - queues into which you can put the URLs you want to scrape
- **[Dataset](https://docs.apify.com/sdk/python/docs/concepts/storages#working-with-datasets)** - store structured data where each object stored has the same attributes
- **[Scrapy](https://scrapy.org/)** - a fast high-level web scraping framework

## How it works

This code is a Python script that uses Scrapy to scrape web pages and extract data from them. Here's a brief overview of how it works:

- The script reads the input data from the Actor instance, which is expected to contain a `start_urls` key with a list of URLs to scrape.
- The script then creates a Scrapy spider that will scrape the URLs. This Spider (class `TitleSpider`) is storing URLs and titles.
- Scrapy pipeline is used to save the results to the default dataset associated with the Actor run using the `push_data` method of the Actor instance.
- The script catches any exceptions that occur during the [web scraping](https://apify.com/web-scraping) process and logs an error message using the `Actor.log.exception` method.

## Resources

- [Web scraping with Scrapy](https://blog.apify.com/web-scraping-with-scrapy/)
- [Python tutorials in Academy](https://docs.apify.com/academy/python)
- [Alternatives to Scrapy for web scraping in 2023](https://blog.apify.com/alternatives-scrapy-web-scraping/)
- [Beautiful Soup vs. Scrapy for web scraping](https://blog.apify.com/beautiful-soup-vs-scrapy-web-scraping/)
- [Integration with Zapier](https://apify.com/integrations), Make, Google Drive, and others
- [Video guide on getting scraped data using Apify API](https://www.youtube.com/watch?v=ViYYDHSBAKM)
- A short guide on how to build web scrapers using code templates:

[web scraper template](https://www.youtube.com/watch?v=u-i-Korzf8w)
