# TODO: make the Python version a parameter
# so we can run integration tests in GitHub with a matrix of Python versions
FROM apify/actor-python:3.9

COPY . ./

RUN echo "Python version:" \
 && python --version \
 && echo "Pip version:" \
 && pip --version \
 && echo "Installing dependencies:" \
 && pip install -r requirements.txt \
 && echo "All installed Python packages:" \
 && pip freeze

CMD ["python3", "-m", "src"]
