FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Environment-based config (override at runtime)
ENV ENSEMBL_BASE_URL="https://rest.ensembl.org"
ENV ENSEMBL_TIMEOUT_SECONDS=30
ENV ENSEMBL_CACHE_TTL_SECONDS=30
ENV ENSEMBL_RETRIES=3

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

