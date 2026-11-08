FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
# Config comes from env vars (see .env.example). Results go to /app/results (mount a volume).
ENTRYPOINT ["propscout"]
CMD ["--help"]
