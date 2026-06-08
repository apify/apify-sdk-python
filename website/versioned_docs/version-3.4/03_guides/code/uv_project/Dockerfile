# syntax=docker/dockerfile:1
# First, specify the base Docker image.
# You can see the Docker images from Apify at https://hub.docker.com/r/apify/.
# You can also use any other image from Docker Hub.
FROM apify/actor-python:3.14

# Add the uv binary from its official distroless image (pinned to the 0.11.x line).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Configure uv for container builds:
#  - compile installed packages to bytecode, so the Actor starts faster,
#  - copy packages instead of hardlinking, which avoids warnings with the cache mount,
#  - never download a managed Python, always reuse the base image's interpreter,
#  - put the project virtual environment first on PATH, so `python` resolves to it.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/usr/src/app/.venv/bin:$PATH"

# Install dependencies into the project virtual environment (.venv) as a separate
# layer. The cache mount speeds up repeated builds, and the bind mounts make the
# project metadata available without copying it into the image. This layer is
# rebuilt only when uv.lock or pyproject.toml change - not on source code edits.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev

# Next, copy the remaining files and directories with the source code.
# Since we do this after installing the dependencies, quick rebuilds will be
# really fast for most source file changes.
COPY . ./

# Use compileall to ensure the runnability of the Actor Python code.
RUN python -m compileall -q my_actor/

# Specify how to launch the source code of your Actor.
CMD ["python", "-m", "my_actor"]
