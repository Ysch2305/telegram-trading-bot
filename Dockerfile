FROM python:3.11-slim

# Set folder kerja di dalam server
WORKDIR /app

# Install tools tambahan agar instalasi library lancar
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy daftar library dan install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy file bot.py ke dalam server
COPY . .

# Perintah untuk menjalankan bot (pastikan nama file sesuai: bot.py)
CMD ["python", "bot.py"]
