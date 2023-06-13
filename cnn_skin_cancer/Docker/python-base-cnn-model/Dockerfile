FROM python:3.11.3-slim-buster

ARG docker_directory=./cnn_skin_cancer/Docker/python-base-cnn-model
ARG app_directory=./cnn_skin_cancer

COPY $docker_directory/requirements.txt /app/requirements.txt

WORKDIR /app
RUN pip3 install --upgrade pip
#RUN pip3 install --upgrade -r requirements.txt

RUN pip3 install poetry && poetry config virtualenvs.create false

COPY $app_directory/pyproject.toml $app_directory/poetry.lock $app_directory/readme.md ./
RUN poetry install --only main --no-root --no-interaction && \
    poetry cache clear pypi --all

COPY $app_directory/src /app/src
RUN poetry install --only-root


CMD ["python3"]