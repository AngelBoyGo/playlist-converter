FROM python:3.9-slim

# Install Chrome dependencies and Node.js
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    libgconf-2-4 \
    libxss1 \
    libnss3 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libxslt1.1 \
    fonts-liberation \
    libasound2 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js and npm
RUN curl -fsSL https://deb.nodesource.com/setup_16.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver with fixed version
RUN wget -q "https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip

# Set display port to avoid crash
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV SELENIUM_HEADLESS=true

# Set up working directory
WORKDIR /app

# Copy requirements and install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the frontend files and build
COPY frontend /app/frontend
WORKDIR /app/frontend
RUN npm install && \
    npm run build && \
    mkdir -p /app/frontend-dist && \
    cp -r dist/* /app/frontend-dist/

# Copy the rest of the application
WORKDIR /app
COPY . .

# Create a health check endpoint
RUN echo 'import fastapi; app = fastapi.FastAPI(); @app.get("/api/health"); def health(): return {"status": "ok"}' > /app/health_check.py

# Expose port
EXPOSE 8080

# Command to run the app
CMD ["python", "start_server.py"] 