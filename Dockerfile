FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/HarrisonHesslink/burnr8" \
      org.opencontainers.image.description="Google Ads MCP server" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG BURNR8_VERSION=0.6.0
RUN pip install --no-cache-dir burnr8==${BURNR8_VERSION}

RUN useradd --create-home burnr8
USER burnr8

CMD ["python", "-m", "burnr8.server"]
