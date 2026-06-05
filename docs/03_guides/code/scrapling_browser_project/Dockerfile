# Use the Apify Playwright base image, which already ships a browser together
# with all of its system-level dependencies.
FROM apify/actor-python-playwright:3.14-1.60.0

# Copy just requirements.txt first to leverage the Docker build cache.
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install -r requirements.txt

# Download the browser binaries that Scrapling expects. The base image already
# provides their system-level dependencies, so run this step as root and then
# switch back to the unprivileged user.
USER root
RUN scrapling install
USER myuser

# Copy the rest of the source code and verify that it compiles.
COPY --chown=myuser:myuser . ./
RUN python -m compileall -q my_actor/

# Specify how to launch the Actor.
CMD ["python", "-m", "my_actor"]
