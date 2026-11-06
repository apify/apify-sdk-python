ARG UV_VERSION=0.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# The test fixture will put the right Python version here
FROM apify/actor-python:BASE_IMAGE_VERSION_PLACEHOLDER

COPY --from=uv /uv /bin/

COPY . ./

RUN apt-get update && apt-get install -y \
    git \
 && rm -rf /var/lib/apt/lists/*

RUN uv export --project sdk_lock --frozen --no-hashes --no-emit-project --all-extras --all-groups \
    --format requirements.txt --output-file constraints.txt \
 && uv pip install --system --reinstall -r requirements.txt -c constraints.txt \
 && uv pip freeze --system

CMD ["sh", "-c", "python server.py & python -m src"]
