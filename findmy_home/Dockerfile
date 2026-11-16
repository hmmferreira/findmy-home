FROM rust:1.90-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
ARG EXPORTER_REV=29f44e20da97e98ebac8083b5a542a571551f26a
WORKDIR /src
RUN git init . && git remote add origin https://github.com/malmeloo/findmy-export.git \
    && git fetch --depth 1 origin "${EXPORTER_REV}" && git checkout --detach FETCH_HEAD
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true
RUN git config --global url."https://github.com/".insteadOf "git@github.com:" \
    && cargo build --release --locked -j 2
# Upstream only converts https to wss. Local helpers require http to ws too.
RUN find /usr/local/cargo/git/checkouts -path '*/omnisette/src/remote_anisette_v3.rs' \
    -exec sed -i 's@.replace("https://", "wss://");@.replace("https://", "wss://").replace("http://", "ws://");@' {} + \
    && cargo clean --release -p omnisette \
    && cargo build --release --locked -j 2
COPY build/escrow-diagnostics.pl /tmp/escrow-diagnostics.pl
RUN find /usr/local/cargo/git/checkouts -path '*/src/icloud/keychain.rs' -exec perl /tmp/escrow-diagnostics.pl {} + \
    && cargo clean --release -p rustpush \
    && cargo build --release --locked -j 2
COPY build/escrow-endpoint-fix.pl /tmp/escrow-endpoint-fix.pl
RUN find /usr/local/cargo/git/checkouts -path '*/src/icloud/keychain.rs' -printf '%h/../..\n' \
    | xargs -I{} perl /tmp/escrow-endpoint-fix.pl {} /src
RUN cargo clean --release -p rustpush \
    && cargo test --release -p rustpush dragon_escrow_endpoint_tests --lib -j 2 \
    && cargo build --release --locked -j 2
COPY build/session-cache.pl /tmp/session-cache.pl
RUN find /usr/local/cargo/git/checkouts -path '*/src/icloud/keychain.rs' -printf '%h/../..\n' \
    | xargs -I{} perl /tmp/session-cache.pl {} /src
RUN cargo clean --release -p icloud_auth \
    && cargo test --release --bin findmy-export dragon_session_tests -j 2 \
    && cargo build --release --locked -j 2
COPY build/account-services.pl /tmp/account-services.pl
RUN perl /tmp/account-services.pl /src/src/main.rs \
    && cargo test --release --bin findmy-export dragon_session_tests -j 2 \
    && cargo build --release --locked -j 2
COPY build/service-token-cache.pl /tmp/service-token-cache.pl
RUN find /usr/local/cargo/git/checkouts -path '*/src/icloud/keychain.rs' -printf '%h/../..\n' \
    | xargs -I{} perl /tmp/service-token-cache.pl {} /src
RUN cargo clean --release -p rustpush \
    && cargo test --release --bin findmy-export dragon_session_tests -j 2 \
    && cargo build --release --locked -j 2
COPY build/private-recovery-password.pl /tmp/private-recovery-password.pl
RUN perl /tmp/private-recovery-password.pl /src/src/main.rs \
    && cargo test --release --bin findmy-export dragon_ -j 2 \
    && cargo build --release --locked -j 2
FROM dadoum/anisette-v3-server@sha256:d551c75454bcbee68dc262d4247d5f87fa309dfc8f2125644d333c648596e3c7 AS anisette
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3 libstdc++6 curl libplist-dev \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1000 --home-dir /data/findmy_home/home --no-create-home findmy
COPY --from=build /src/target/release/findmy-export /usr/local/bin/findmy-export
COPY --from=anisette /opt/ /opt/
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY rootfs/app /app
WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/bootstrap.py"]
