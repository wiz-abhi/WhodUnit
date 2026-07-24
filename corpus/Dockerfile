# Whodunit demo corpus generator — slim image.
#
# Emits synthetic OTLP traces + logs for the 8-service "shop" with one seeded
# structural fault per run. In the compose network the SigNoz OTLP ingester is
# reachable as the service name `ingester`, so that is the default endpoint.
#
# Build (from Track2/whodunit/):
#   docker build -f corpus/Dockerfile -t whodunit-corpus .
# Run against a compose network that has an `ingester` service:
#   docker run --rm --network <signoz-net> whodunit-corpus \
#       --traces 5000 --seed 42 --fault conditional_dep --fault-rate 0.12
#
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install only the two direct deps (+ pinned transitives) — no build toolchain.
COPY corpus/REQUIREMENTS.txt /app/corpus/REQUIREMENTS.txt
RUN pip install --no-cache-dir -r /app/corpus/REQUIREMENTS.txt

# Copy the package.
COPY corpus/ /app/corpus/

# The manifest is written under /app/corpus/out; mount a volume there to keep it.
VOLUME ["/app/corpus/out"]

# Default target = the compose ingester service. Override --endpoint to change.
ENTRYPOINT ["python", "-m", "corpus.generate", "--endpoint", "http://ingester:4318"]
CMD ["--traces", "5000", "--seed", "42", "--fault", "conditional_dep", "--fault-rate", "0.12"]
