FROM python:3.9-slim

# Update and install dependencies
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
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up Chrome and install ChromeDriver properly
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1) \
    && echo "Detected Chrome version: ${CHROME_VERSION}" \
    && LATEST_DRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json" | grep -o '"chrome": "[^"]*"' | head -1 | sed 's/"chrome": "\(.*\)"/\1/') \
    && echo "Using Chrome for Testing version: ${LATEST_DRIVER_URL}" \
    && wget -q --no-check-certificate "https://storage.googleapis.com/chrome-for-testing-public/$(curl -s https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json | grep -o '"url": "[^"]*chromedriver-linux64.zip"' | sed 's/"url": "//;s/"$//')" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /tmp/ \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64

# Verify installation
RUN echo "Chrome version:" && google-chrome --version && \
    echo "ChromeDriver version:" && chromedriver --version

# Create directories for Chrome
RUN mkdir -p /tmp/chrome-data /var/chrome_cache

# Configure environment
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV SELENIUM_HEADLESS=true
ENV USE_SELENIUM_MANAGER=false
ENV PYTHONIOENCODING=utf-8

# Additional environment variables for optimization
ENV CHROMEDRIVER_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu --single-process"
ENV NODE_OPTIONS="--max-old-space-size=256"
ENV PYTHONHASHSEED=0
ENV WDM_SSL_VERIFY=0
ENV WDM_LOG_LEVEL=0

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
    cp -r dist/* /app/frontend-dist/ && \
    # Clean up npm cache to reduce image size
    npm cache clean --force && \
    rm -rf node_modules

# Copy the rest of the application
WORKDIR /app
COPY . .

# Create directory for frontend-dist if build in previous step failed
RUN mkdir -p /app/frontend-dist

# Create a health check endpoint
RUN echo 'import fastapi; app = fastapi.FastAPI(); @app.get("/api/health"); def health(): return {"status": "ok"}' > /app/health_check.py

# Expose port
EXPOSE 8080

# Set up runtime limits for the container
ENV CHROME_MEMORY_LIMIT="512m"
ENV MAX_CONCURRENT_BROWSERS=1

# Command to run the app
CMD ["python", "start_server.py"] 