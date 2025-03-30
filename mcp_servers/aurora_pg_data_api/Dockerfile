# Use an official Python runtime as a parent image
# Using slim-buster for a smaller image size
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /usr/src/app

# Install system dependencies if needed (e.g., for certain Python packages)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*
# System dependencies like freetds-dev are not needed for RDS Data API

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create a non-root user and group
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership of the application directory
RUN chown -R appuser:appgroup /usr/src/app

# Switch to the non-root user
USER appuser

# Command to run the application
CMD ["python", "aurora_pg_data_api_server.py"]