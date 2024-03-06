# The test fixture will put the right Python version here
FROM apify/actor-python:BASE_IMAGE_VERSION_PLACEHOLDER

COPY . ./

RUN echo "Python version:" \
 && python --version \
 && echo "Pip version:" \
 && pip --version \
 && echo "Installing dependencies:" \
 && pip install --force-reinstall -r requirements.txt \
 && echo "All installed Python packages:" \
 && pip freeze

CMD ["python3", "-m", "src"]
