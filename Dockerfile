FROM python:3.11-slim-bookworm

# 1. Install required system tools
RUN apt-get update && apt-get install -y ffmpeg curl ca-certificates && rm -rf /var/lib/apt/lists/*

# 2. Install standalone yt-dlp based on architecture
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
        curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64 -o /usr/local/bin/yt-dlp; \
    else \
        curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux -o /usr/local/bin/yt-dlp; \
    fi && \
    chmod +x /usr/local/bin/yt-dlp

# 3. Set up a non-root user for security
RUN useradd -m appuser
USER appuser

# 4. Set up the working directory and install Python packages
WORKDIR /app
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
# 5. Copy the application code
COPY --chown=appuser:appuser ./app /app

# Ensure local bin is on PATH
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Expose the web dashboard port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]