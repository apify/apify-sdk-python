# Multi-stage build:
#   - builder: Installs the Apify SDK and the dependencies, pinned to the project lock file, into a virtual environment
#   - runner:  Actor image with Playwright browsers, the virtual environment and the Actor source code

# Required: the test fixture passes the Python version of the test run as a build argument
ARG PYTHON_VERSION
ARG UV_VERSION=0.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# =============================================================================
# Build stage
# =============================================================================
FROM apify/actor-python-playwright:${PYTHON_VERSION} AS builder

COPY --from=uv /uv /bin/

# Create the virtual environment from the base image's Python, which the runner stage has too
ENV UV_PYTHON_DOWNLOADS=never

# Copy the requirements and the Apify SDK source code with the project lock file
COPY requirements.txt ./
COPY sdk/ ./sdk/

# Install the Apify SDK and the dependencies into a virtual environment, pinned to the project lock file
RUN uv export --project sdk --frozen --no-hashes --no-emit-project --all-extras --all-groups \
        --format requirements.txt --output-file constraints.txt && \
    uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python ./sdk -r requirements.txt -c constraints.txt && \
    uv pip freeze --python /opt/venv/bin/python

# =============================================================================
# Runtime stage
# =============================================================================
FROM apify/actor-python-playwright:${PYTHON_VERSION} AS runner

# Copy the virtual environment with the installed dependencies
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Install the Chromium build that matches the installed Playwright version, which can be newer than the base image's
RUN playwright install chromium

# Copy the Actor source code
COPY . ./

CMD ["sh", "-c", "python server.py & python -m actor"]
