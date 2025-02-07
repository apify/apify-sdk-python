FROM apify/actor-python:3.13

COPY requirements.txt ./

RUN pip install --no-cache-dir --requirement requirements.txt \
    && pip freeze

COPY . ./

RUN python3 -m compileall -q .

CMD ["python3", "-m", "src"]
