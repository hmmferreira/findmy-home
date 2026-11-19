# Test-only image. No private state or Apple credentials belong in this context.
ARG TEST_BASE_IMAGE=dragon/findmy-home:0.1.12
FROM ${TEST_BASE_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /review/requirements.lock
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /review/requirements.lock
RUN pip install --no-cache-dir --only-binary=:all: pytest==9.0.3 pytest-asyncio==1.4.0 protobuf==7.36.2
COPY backend /review/backend
COPY app /review/app
COPY test_shared_discovery.py /review/test_shared_discovery.py
COPY test_controller_protocol.py /review/test_controller_protocol.py
WORKDIR /review/backend
ENV PYTHONPATH=/review/backend:/review/backend/tests:/review/app
ENTRYPOINT []
CMD ["sh","-c","python -m pytest tests -q -p no:cacheprovider && cd /review && python -m pytest test_controller_protocol.py -q -p no:cacheprovider && python -m unittest test_shared_discovery -v"]
