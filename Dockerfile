# Use an official Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl gnupg2 build-essential chromium-driver chromium-browser \
    && apt-get clean

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Copy and install backend
COPY backend/ backend/
RUN pip install --upgrade pip
RUN pip install -r backend/requirements.txt

# Copy and build frontend
COPY frontend/ frontend/
WORKDIR /app/frontend
RUN npm install
RUN npm run build

# Move frontend build into backend static files (adjust if needed)
WORKDIR /app
RUN mkdir -p backend/static && cp -r frontend/dist/* backend/static/

# Expose the port Flask will run on
EXPOSE 5000

# Run backend
CMD ["python", "backend/app.py"]
