FROM python:3.13-slim

# Set a working directory
WORKDIR /app

# Avoid buffering so logs appear immediately
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app

# Use a non-root user for safety
RUN groupadd -r app && useradd -r -g app app || true
USER app

# Default command
CMD ["python", "bot.py"]
