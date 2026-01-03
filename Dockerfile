FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright and general functionality
RUN apt-get update && apt-get install -y \
    chromium-browser \
    chromium \
    chromium-driver \
    gstreamer1.0-plugins-base \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    wget \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN mkdir -p /ms-playwright

# Install Playwright browsers
RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright python -m playwright install chromium --with-deps
RUN python -m playwright install-deps

# Verify Playwright installation
RUN PLAYWRIGHT_BROWSERS_PATH=/ms-playwright python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser = p.chromium.launch(); browser.close(); p.stop(); print('Playwright installation verified')"

# Clean up to save disk space
RUN rm -rf /root/.cache/ms-playwright/*/debugger/ /root/.cache/ms-playwright/*/swiftshader/ 2>/dev/null || true

# Copy Playwright browsers to expected location if needed
RUN if [ -d /ms-playwright ]; then cp -r /ms-playwright/* /root/.cache/ms-playwright/ 2>/dev/null || true; fi

# Copy application code
COPY . .

# Expose port for health check
EXPOSE 8080

# Run the application
CMD ["python", "main.py"]