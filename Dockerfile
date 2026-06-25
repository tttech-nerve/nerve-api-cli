ARG BASE_IMAGE=python:3.14-alpine3.24
ARG BUILDER_IMAGE=${BASE_IMAGE}
ARG RELEASE_IMAGE=${BASE_IMAGE}

# build stage
FROM ${BUILDER_IMAGE} AS build

# perform os update and install necessary packages
RUN apk update && apk upgrade && \
    apk add --no-cache curl git

# create virtual environment, set repository, upgrade pip and install poetry
RUN python3 -m venv /opt/env \
    && /opt/env/bin/python -m pip install --upgrade pip \
    && curl -sSL https://install.python-poetry.org | /opt/env/bin/python3 -

# create project folder
RUN /root/.local/bin/poetry new /opt/nerve-cli/release/

# copy poetry files
COPY pyproject.toml /opt/nerve-cli/pyproject.toml
COPY poetry.lock /opt/nerve-cli/poetry.lock
COPY README.md /opt/nerve-cli/README.md
RUN mkdir -p /opt/nerve-cli/nerve_cli
COPY nerve_cli/__init__.py /opt/nerve-cli/nerve_cli/__init__.py

# install dependencies (use BuildKit secret mounts with RUN --mount)
RUN /root/.local/bin/poetry config virtualenvs.in-project true && \
    cd /opt/nerve-cli && /root/.local/bin/poetry install --without dev

# application stage
FROM ${RELEASE_IMAGE} AS release

# perform os update
RUN apk update && apk upgrade

# create non-root privilleged worker user and group
RUN addgroup --gid 1000 workergroup && \
    adduser -u 1000 -G workergroup --no-create-home -D worker

# create the necessary directories
RUN mkdir -p /opt/nerve-cli/app && \
    mkdir -p /workdir

# copy the virtual environment
COPY --from=build /opt/nerve-cli/.venv /opt/nerve-cli/.venv

# remove pip to reduce image size and attack surface
RUN python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.14/site-packages/pip* \
    && rm -rf /usr/local/bin/pip* \
    && rm -rf /usr/lib/python3.14/ensurepip \
    && rm -rf /usr/local/lib/python3.14/ensurepip \
    && /opt/nerve-cli/.venv/bin/python -m pip uninstall -y pip setuptools wheel \
    && rm -rf /opt/nerve-cli/.venv/lib/python3.14/site-packages/pip* \
    && rm -rf /opt/nerve-cli/.venv/bin/pip*

# set the owner of the directories
RUN chown -R worker:workergroup /opt/nerve-cli && \
    chgrp workergroup /opt/nerve-cli && \
    chmod g+s /opt/nerve-cli && \
    chown -R worker:workergroup /workdir && \
    chgrp workergroup /workdir

# switch to worker user
USER worker

# set the working directory
WORKDIR /workdir

# mark volumes
VOLUME ["/workdir"]

# copy the application code
COPY ./nerve_cli /opt/nerve-cli/nerve_cli
# remove the __pycache__ directories if they exist
USER root
RUN rm -rf /opt/nerve-cli/app/__pycache__
USER worker

# set the entrypoint
ENTRYPOINT ["/opt/nerve-cli/.venv/bin/nerve-cli"]