FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fonts-noto-cjk \
    ghostscript \
    pngquant \
    qpdf \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-kor \
    tesseract-ocr-rus \
    unpaper \
    && rm -rf /var/lib/apt/lists/*

# Use Tesseract's accuracy-focused language models for Korean, English, and Russian.
RUN curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/kor.traineddata \
      -o /usr/share/tesseract-ocr/5/tessdata/kor.traineddata \
    && curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/eng.traineddata \
      -o /usr/share/tesseract-ocr/5/tessdata/eng.traineddata \
    && curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/4.1.0/rus.traineddata \
      -o /usr/share/tesseract-ocr/5/tessdata/rus.traineddata

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app
COPY app ./app
COPY scripts ./scripts
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
