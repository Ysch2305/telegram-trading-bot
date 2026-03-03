FROM python:3.11-slim

WORKDIR /app

# Install build-essential untuk kompilasi data finansial
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 1. Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# 2. Install library standar
RUN pip install --no-cache-dir -r requirements.txt

# 3. FORCE INSTALL pandas-ta (Langkah kunci)
RUN pip install --no-cache-dir pandas-ta==0.3.14b0

COPY . .

CMD ["python", "bot.py"]
