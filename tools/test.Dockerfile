FROM node:24-bookworm-slim AS ui
WORKDIR /ui
COPY tools/ui-tests/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
FROM dragon/findmy-home:0.1.0
USER root
WORKDIR /src
COPY . /src
COPY --from=ui /usr/local/bin/node /usr/local/bin/node
COPY --from=ui /ui/node_modules /src/tools/ui-tests/node_modules
COPY --from=ui /ui/package-lock.json /src/tools/ui-tests/package-lock.json
ENV PYTHONPATH=/src/findmy_home/rootfs/app
ENTRYPOINT []
CMD ["python","-m","unittest","discover","-s","tests","-v"]
