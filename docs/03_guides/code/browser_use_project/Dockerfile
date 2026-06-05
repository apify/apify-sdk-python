# Use the Apify Playwright base image, which already ships a Chromium browser together
# with all of its system-level dependencies. Browser Use launches that browser via CDP,
# so no extra browser install step is needed.
FROM apify/actor-python-playwright:3.14-1.60.0

USER myuser

# Copy just requirements.txt first to leverage the Docker build cache.
COPY --chown=myuser:myuser requirements.txt ./
RUN pip install -r requirements.txt

# Copy the rest of the source code and verify that it compiles.
COPY --chown=myuser:myuser . ./
RUN python -m compileall -q my_actor/

# Disable Browser Use telemetry and cloud sync inside the Actor.
ENV ANONYMIZED_TELEMETRY=false
ENV BROWSER_USE_CLOUD_SYNC=false

# Specify how to launch the Actor.
CMD ["python", "-m", "my_actor"]
