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

# Install Chrome stable (without pinning a specific version)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Get Chrome version and download matching ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F. '{print $1}') \
    && wget -q -O /tmp/chromedriver_linux64.zip https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/$(curl -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_VERSION})/linux64/chromedriver-linux64.zip \
    && unzip /tmp/chromedriver_linux64.zip -d /tmp \
    && mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm -rf /tmp/chromedriver_linux64.zip /tmp/chromedriver-linux64

# Print versions for verification
RUN echo "Chrome version:" && google-chrome --version && \
    echo "ChromeDriver version:" && chromedriver --version

# Set display port to avoid crash
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV SELENIUM_HEADLESS=true
ENV USE_SELENIUM_MANAGER=true

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