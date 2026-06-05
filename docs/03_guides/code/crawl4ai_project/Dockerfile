# Use the Apify Playwright base image, which already ships a browser together
# with all of its system-level dependencies. Crawl4AI drives this browser
# through Playwright and reuses the binaries the image provides, so no separate
# browser-install step is needed.
#
# The Python 3.13 image is used because some of Crawl4AI's dependencies do not
# yet publish wheels for newer Python versions.
FROM apify/actor-python-playwright:3.13-1.60.0

# Copy just requirements.txt first to leverage the Docker build cache.
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install -r requirements.txt

# Copy the rest of the source code and verify that it compiles.
COPY --chown=myuser:myuser . ./
RUN python -m compileall -q my_actor/

# Specify how to launch the Actor.
CMD ["python", "-m", "my_actor"]
