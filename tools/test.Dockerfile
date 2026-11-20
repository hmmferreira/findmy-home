FROM node:24-bookworm-slim AS ui
WORKDIR /ui
COPY tools/ui-tests/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
FROM python:3.12-slim-bookworm
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /src/retrace/requirements.lock && pip check
COPY --from=ui /usr/local/bin/node /usr/local/bin/node
COPY --from=ui /ui/node_modules /src/tools/ui-tests/node_modules
COPY --from=ui /ui/package-lock.json /src/tools/ui-tests/package-lock.json
ENV PYTHONPATH=/src/retrace/rootfs/app
ENTRYPOINT []
CMD ["python","-m","unittest","discover","-s","tests","-v"]
