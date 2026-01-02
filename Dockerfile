FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    gstreamer1.0-plugins-base \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set environment for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# Install Playwright browsers
RUN python -m playwright install chromium
RUN python -m playwright install-deps

# Verify Playwright installation
RUN python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); browser = p.chromium.launch(); browser.close(); p.stop(); print('Playwright installation verified')"

# Additional check to ensure browser is available
RUN ls -la /root/.cache/ms-playwright/
RUN ls -la /root/.cache/ms-playwright/chromium-*/chrome-linux/ 2>/dev/null || echo 'Chrome directory not found'

# Copy application code
COPY . .

# Expose port for health check
EXPOSE 8080

# Run the application
CMD ["python", "main.py"]