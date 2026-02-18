# Use a slim Python image to keep size down
FROM python:3.12-slim

# 1. Install System Dependencies
# We need poppler (PDFs), tesseract (OCR), and libgl1 (OpenCV)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Set Work Directory
WORKDIR /app

# 3. Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy Application Code
COPY . .

# 5. Environment Setup
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default command (will be overridden by compose for worker vs backend)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]