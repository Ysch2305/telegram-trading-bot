FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies sistem (Git sangat penting di sini)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Upgrade pip dan install requirements
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy sisa file
COPY . .

# Jalankan bot
CMD ["python", "bot.py"]
