# Multi-stage build:
#   - builder: Installs the Apify SDK and the dependencies, pinned to the project lock file, into a virtual environment
#   - runner:  Actor image with the virtual environment and the Actor source code

# The test fixture passes the Python version of the test run as a build argument
ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# =============================================================================
# Build stage
# =============================================================================
FROM apify/actor-python:${PYTHON_VERSION} AS builder

COPY --from=uv /uv /bin/

# Copy the requirements and the Apify SDK source code with the project lock file
COPY requirements.txt ./
COPY sdk/ ./sdk/

# Install the Apify SDK and the dependencies into a virtual environment, pinned to the project lock file
RUN uv export --project sdk --frozen --no-hashes --no-emit-project --all-extras --all-groups \
    --format requirements.txt --output-file constraints.txt \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python ./sdk -r requirements.txt -c constraints.txt \
 && uv pip freeze --python /opt/venv/bin/python

# =============================================================================
# Runtime stage
# =============================================================================
FROM apify/actor-python:${PYTHON_VERSION} AS runner

# Copy the virtual environment with the installed dependencies
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Copy the Actor source code
COPY . ./

CMD ["sh", "-c", "python server.py & python -m actor"]
