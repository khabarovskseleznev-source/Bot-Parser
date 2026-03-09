FROM python:3.11-slim

WORKDIR /app

# Системные зависимости для lxml, aiosqlite, chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Зависимости Python (torch CPU-only чтобы не тянуть CUDA ~3GB)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Исходный код
COPY . .

# Точка входа
CMD ["python", "main.py"]
