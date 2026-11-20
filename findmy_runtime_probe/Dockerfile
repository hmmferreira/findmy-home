FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libseccomp2 libapparmor1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --no-create-home --home-dir /nonexistent probe
COPY native_sandbox.py child.py probe.py /probe/
WORKDIR /probe
USER 1000:1000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "-I", "-S", "-B", "/probe/probe.py"]
