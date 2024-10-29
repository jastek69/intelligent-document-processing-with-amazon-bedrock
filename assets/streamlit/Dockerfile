# Copyright © Amazon.com and Affiliates
# ----------------------------------------------------------------------
# File content:
#       Docker image of the streamlit container

FROM --platform=linux/amd64 public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

RUN apt-get update -y && apt-get install --no-install-recommends -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and switch to it
RUN addgroup --system appgroup && adduser --system --group appuser

COPY pyproject.toml /app
COPY .streamlit/ /app/.streamlit/

RUN pip3 --no-cache-dir install -U pip
RUN pip3 --no-cache-dir install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --only main

# Change ownership of the /app directory to the appuser
RUN chown -R appuser:appgroup /app
USER appuser

COPY src/ /app/src

EXPOSE 8501

HEALTHCHECK CMD ["curl", "--fail", "http://localhost:8501/_stcore/health"]

ENTRYPOINT ["streamlit", "run", "src/Home.py", "--server.port=8501", "--server.address=0.0.0.0"]