# The test fixture puts the Python version of the test run in place of BASE_IMAGE_VERSION_PLACEHOLDER.
#
# Multi-stage build:
#   - builder: Installs the dependencies, pinned to the project lock file, into a virtual environment
#   - runner:  Actor image with the virtual environment and the Actor source code

ARG UV_VERSION=0.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# =============================================================================
# Build stage
# =============================================================================
FROM apify/actor-python:BASE_IMAGE_VERSION_PLACEHOLDER AS builder

COPY --from=uv /uv /bin/

# Copy the dependency files: the requirements, the Apify SDK wheel and the project lock file
COPY requirements.txt *.whl ./
COPY sdk_lock/ ./sdk_lock/

# Install the dependencies into a virtual environment, pinned to the project lock file
RUN uv export --project sdk_lock --frozen --no-hashes --no-emit-project --all-extras --all-groups \
    --format requirements.txt --output-file constraints.txt \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python -r requirements.txt -c constraints.txt \
 && uv pip freeze --python /opt/venv/bin/python

# =============================================================================
# Runtime stage
# =============================================================================
FROM apify/actor-python:BASE_IMAGE_VERSION_PLACEHOLDER AS runner

# Copy the virtual environment with the installed dependencies
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Copy the Actor source code
COPY . ./

CMD ["sh", "-c", "python server.py & python -m src"]
