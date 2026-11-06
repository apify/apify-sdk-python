# The test fixture passes the Python version of the test run as a build argument
ARG PYTHON_VERSION=3.14

FROM apify/actor-python-playwright:${PYTHON_VERSION}

COPY . ./

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --force-reinstall -r requirements.txt

# Reinstall the Chromium binary so it matches the just-installed Playwright version
# (the base image's pre-installed browser can lag behind a newer Playwright pulled via crawlee[playwright]).
RUN playwright install chromium

CMD ["sh", "-c", "python server.py & python -m actor"]
