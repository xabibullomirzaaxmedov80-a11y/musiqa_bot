FROM python:3.10-slim

# FFmpeg ni o'rnatish (yt-dlp ishlashi uchun zarur)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render'da PORT orqali ulanish imkonini berish
EXPOSE 8080

CMD ["python", "main.py"]
