FROM apify/actor-python-playwright:PYTHON_VERSION_PLACEHOLDER

COPY . ./

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --force-reinstall -r requirements.txt

CMD ["sh", "-c", "python server.py & python -m src"]
