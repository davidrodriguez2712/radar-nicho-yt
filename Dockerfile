# Multi-architecture digests verified against official registries on 2026-09-13.
FROM ghcr.io/astral-sh/uv:0.10.0@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f AS uv
FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS runtime
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH" \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false OMP_NUM_THREADS=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY .streamlit ./.streamlit
RUN uv sync --locked --no-dev && useradd --create-home --uid 10001 radar
USER radar

FROM runtime AS backend
EXPOSE 8000
CMD ["nicheradar-api"]

FROM runtime AS worker
USER root
RUN uv sync --locked --no-dev --extra embeddings
COPY scripts/install_embedding_model.py /tmp/install_embedding_model.py
ARG TARGETARCH
RUN python /tmp/install_embedding_model.py /models/paraphrase-MiniLM-L3-v2 "$TARGETARCH" \
    && rm /tmp/install_embedding_model.py \
    && chown -R radar:radar /models
ENV NR_EMBEDDING_MODEL_DIRECTORY=/models/paraphrase-MiniLM-L3-v2 \
    NR_EMBEDDING_MODEL_VERSION=paraphrase-MiniLM-L3-v2@4ca70771034acceecb2e72475f72050fcdde4ddc-qint8-$TARGETARCH
USER radar
CMD ["nicheradar-worker"]

FROM runtime AS dashboard
EXPOSE 8501
CMD ["nicheradar-dashboard"]
