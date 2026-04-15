ARG REGISTRY="docker.io/library"
ARG BUILD_IMAGE='python'
ARG BUILD_TAG='3.12-trixie'
ARG BASE_IMAGE='python'
ARG BASE_TAG='3.12-slim-trixie'

FROM $REGISTRY/$BUILD_IMAGE:$BUILD_TAG AS builder
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_DISABLE_PIP_VERSION_CHECK=yes
ARG PIP_CERT
ARG PIP_CLIENT_CERT
ARG PIP_TRUSTED_HOST
ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL
ARG GIT_BRANCH_NAME
# expected to be public registry (e.g pypi.org)
ARG UV_DEFAULT_INDEX
# expected to be private registry
ARG UV_INDEX_URL
ARG UV_INSECURE_HOST
# Ensure uv installs to the correct directory
ENV UV_PROJECT_ENVIRONMENT=/usr/local

COPY debian.txt /tmp/src/
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    $(grep -vE "^\s*(#|$)" /tmp/src/debian.txt | tr "\n" " ") && \
    rm -rf /tmp/src/debian.txt /var/lib/apt/lists/*

# copy all files not in .dockerignore
COPY ./ /tmp/src
RUN pip install uv

# build and install package
WORKDIR /tmp/src
# Install all dependencies
RUN uv sync --frozen --no-editable
# Install package with version attached. (hatchling and hatch-vcs installed after sync to avoid being uninstalled)
RUN uv pip install --system hatchling hatch-vcs
RUN uv build . --out-dir /tmp/
RUN uv pip uninstall --system azul-plugin-jadx
RUN uv pip install --system --no-deps --find-links /tmp/ azul-plugin-jadx==$(hatchling version)

# Upgrade to dev azul dependencies or upgrade non-dev azul dependencies depending on branch.
RUN if [ "$GIT_BRANCH_NAME" = "refs/heads/dev" ] ; then \
    uv pip freeze | grep 'azul-.*==' | grep -v '^azul-plugin-jadx' | cut -d "=" -f 1 | xargs -I {} uv pip install --extra-index-url=$UV_INDEX_URL --system --upgrade --no-deps --prerelease allow '{}>=0.0.0-dev'; \
    else \
    uv pip freeze | grep 'azul-.*==' | grep -v '^azul-plugin-jadx' | cut -d "=" -f 1 | xargs -I {} uv pip install --extra-index-url=$UV_INDEX_URL --system --upgrade --no-deps '{}>=0.0.0'; \
    fi

FROM $REGISTRY/$BASE_IMAGE:$BASE_TAG AS base
ENV DEBIAN_FRONTEND=noninteractive
COPY debian.txt /tmp/src/

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    $(grep -vE "^\s*(#|$)" /tmp/src/debian.txt | tr "\n" " ") && \
    rm -rf /tmp/src/debian.txt /var/lib/apt/lists/*


ARG UID=21000
ARG GID=21000
RUN groupadd -g $GID azul && useradd --create-home --shell /bin/bash -u $UID -g $GID azul
USER azul
COPY --from=builder /usr/local /usr/local
USER root
RUN ln -sf /usr/local/lib/jadx/bin/jadx /usr/local/bin/jadx
USER azul

# run tests during build to verify dockerfile has all requirements
FROM base AS tester
ENV PIP_DISABLE_PIP_VERSION_CHECK=yes
ARG PIP_CERT
ARG PIP_CLIENT_CERT
ARG PIP_TRUSTED_HOST
ARG PIP_INDEX_URL
ARG UV_DEFAULT_INDEX
ARG UV_INDEX_URL
ARG UV_INSECURE_HOST
ARG PIP_EXTRA_INDEX_URL
ARG UID=21000
ARG GID=21000
# Easiest way to install with uv managing packages.
USER root
COPY ./pyproject.toml ./pyproject.toml
RUN uv pip install --system --group dev
USER azul
# test scripts will be installed to the local user bin dir. Add local bin path for the azul user.
ENV PATH="/home/azul/.local/bin:$PATH"
COPY --chown=azul ./tests /tmp/tests
RUN --mount=type=secret,uid=$UID,gid=$GID,id=testSecret export $(cat /run/secrets/testSecret) && \
    pytest -o cache_dir=/tmp/cache --tb=short /tmp/tests
# generate empty file to copy to `release` stage so this stage is not skipped due to optimisations.
RUN touch /tmp/testingpassed

FROM base AS release
# copy from `tester` stage to ensure testing is not skipped due to build optimisations.
COPY --from=tester /tmp/testingpassed /tmp/
ENTRYPOINT ["azul-plugin-jadx"]
