# The test fixture will put the right Python version here
FROM apify/actor-python:BASE_IMAGE_VERSION_PLACEHOLDER

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/

COPY . ./

RUN apt-get update && apt-get install -y \
    git \
 && rm -rf /var/lib/apt/lists/*

RUN echo "Python version:" \
 && python --version \
 && echo "uv version:" \
 && uv --version \
 && echo "Installing dependencies pinned to the project lock file:" \
 && uv pip install --system --reinstall -r requirements.txt -c constraints.txt \
 && echo "All installed Python packages:" \
 && uv pip freeze --system

CMD ["sh", "-c", "python server.py & python -m src"]
