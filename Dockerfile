FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN useradd --create-home burnr8
USER burnr8

RUN pip install --no-cache-dir --user burnr8
ENV PATH="/home/burnr8/.local/bin:$PATH"

CMD ["python", "-m", "burnr8.server"]
