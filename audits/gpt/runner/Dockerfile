# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update && \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install -y --no-install-recommends bash git time && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt /requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    PIP_CERT=/run/secrets/proxy_ca python -m pip download --only-binary=:all: \
      --require-hashes --no-deps --dest /wheelhouse -r /requirements.txt && \
    python -m pip install --no-index --find-links /wheelhouse --require-hashes -r /requirements.txt
COPY build-requirements.txt /build-requirements.txt
RUN --mount=type=secret,id=proxy_ca \
    PIP_CERT=/run/secrets/proxy_ca python -m pip download --only-binary=:all: \
      --require-hashes --no-deps --dest /build-wheelhouse -r /build-requirements.txt && \
    python -m venv /buildenv && /buildenv/bin/python -m pip install --no-index \
    --find-links /build-wheelhouse --require-hashes --no-deps -r /build-requirements.txt
