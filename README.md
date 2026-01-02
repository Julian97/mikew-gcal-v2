# Busker Schedule to Google Calendar

A Python application that scrapes busker schedules daily at 11 PM GMT+8 and automatically adds them to Google Calendar, using Redis for persistence across redeployments, deployable on Zeabur.

## Overview

This application:
- Scrapes busker performance schedules from the configured URL
- Creates events in the configured Google Calendar
- Runs daily at 11 PM Singapore time (GMT+8)
- Uses Redis to prevent duplicate events and maintain state across container restarts
- Deploys on Zeabur via GitHub

## Features

- **Web Scraping**: Uses Playwright to handle JavaScript-rendered content on the busking website
- **Duplicate Prevention**: Hash-based deduplication persists across redeployments
- **Distributed Locking**: Prevents multiple container instances from running simultaneously
- **Error Handling**: Comprehensive try-catch with Redis error logging
- **Retry Logic**: Exponential backoff for scraping and API failures
- **Metrics Tracking**: Counts scrapes, events created, errors in Redis
- **Graceful Shutdown**: Handles container stops cleanly
- **Sync/Reconciliation**: Optional daily job to reconcile Redis cache with Google Calendar

## Technology Stack

- Python 3.11+
- Playwright (handles JavaScript-rendered content on the busking website)
- Redis (persistent storage)
- Google Calendar API v3 (service account authentication)
- APScheduler (cron scheduling)
- Docker (Zeabur deployment)

## Installation and Setup

### Prerequisites

1. Python 3.11+
2. Redis server
3. Google Cloud Service Account with Calendar API access

### Local Development Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd busker-scheduler
   ```

2. Obtain your busker profile URL:
   - Navigate to the busker profile page you want to scrape
   - Copy the URL from your browser
   - This will be your BUSKER_URL value

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install Playwright browsers:
   ```bash
   playwright install chromium
   ```

5. Set up Google Calendar API:
   - Follow the steps in the "Google Calendar Setup" section below
   - Either place the service account JSON file in `./credentials/service-account.json` (for local development)
   - Or set the `GOOGLE_CREDENTIALS_JSON` environment variable with the JSON content (for deployment on Zeabur)

6. Create and configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your specific values
   ```

7. Run the application:
   ```bash
   python main.py
   ```

### Google Calendar Setup

1. Create a Google Cloud Project
2. Enable Google Calendar API
3. Create Service Account with Calendar scope
4. Download JSON key file
5. Share target calendar with service account email (Make changes to events permission)
6. Get your Google Calendar ID (found in calendar settings)
7. Upload JSON to deployment securely

## Configuration

The application uses environment variables for configuration. Copy `.env.example` to `.env` and customize the values:

```bash
BUSKER_URL=<YOUR_BUSKER_PROFILE_URL>
CALENDAR_ID=<YOUR_GOOGLE_CALENDAR_ID>
# For local development only - for Zeabur deployment use GOOGLE_CREDENTIALS_JSON instead
GOOGLE_CREDENTIALS_PATH=./credentials/service-account.json
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
TIMEZONE=Asia/Singapore
LOG_LEVEL=INFO
EVENT_TTL_DAYS=90
```

**Note**: For deployment on Zeabur, instead of using `GOOGLE_CREDENTIALS_PATH`, you can set the `GOOGLE_CREDENTIALS_JSON` environment variable with the full content of your service account JSON file. This allows you to keep your credentials secure without needing to mount a file.

**Important**: The BUSKER_URL and CALENDAR_ID should be treated as sensitive information and kept private. Do not share these values publicly or commit them to version control.

## Deployment on Zeabur

1. Push your code to a GitHub repository
2. Link the repository to Zeabur
3. Add Redis service through Zeabur dashboard
4. Configure environment variables in Zeabur dashboard
5. Upload Google service account JSON securely through Zeabur's secret management
6. Deploy the application

### Docker Configuration for Zeabur

The Dockerfile is already configured for Zeabur deployment:
- Uses Python 3.11-slim base
- Installs Playwright and Chromium browser
- Installs all Python dependencies
- Runs main.py on container start

## Architecture

### Key Components

1. **Web Scraper Module** (`scraper.py`)
   - Uses Playwright headless browser to scrape busker profile page
   - Extracts: date, start time, end time, location, busker name
   - Handles dynamic content loading and errors with retry logic
   - Properly extracts busker name from profile image alt attribute
   - Robust parsing for date/time/location from complex HTML structures

2. **Redis Manager Module** (`redis_manager.py`)
   - Stores event hashes to detect duplicates
   - Implements distributed locking
   - Tracks metrics and stores last scrape metadata
   - Sets 90-day TTL on events

3. **Google Calendar Manager Module** (`calendar_manager.py`)
   - Service account authentication
   - Creates calendar events with proper timezone
   - Handles API rate limits and errors

4. **Scheduler Module** (`scheduler.py`)
   - APScheduler with cron trigger for 11 PM daily
   - Main job workflow with lock acquisition and release

5. **Sync/Reconciliation Module** (`sync_manager.py`)
   - Optional daily job to reconcile Redis cache with Google Calendar

### Redis Data Structures

- `event:{hash}` - Hash containing event details + Google Calendar event ID (TTL: 90 days)
- `events_timeline` - Sorted set for querying events by date
- `scraper:lock` - Distributed lock (TTL: 5 minutes)
- `scraper:last_run` - Hash with execution metadata
- `errors:log` - List of recent errors (keep last 100)
- `metrics:daily:{date}` - Hash with daily counters

## Usage

The application runs automatically according to the schedule defined in the configuration. By default:
- Scraping job runs daily at 11 PM Singapore time
- Sync job runs daily at 3 AM Singapore time

### API Endpoints

The application also exposes the following API endpoints for monitoring and manual operations:

- `GET /` - Status dashboard web page with UI controls
- `GET /health` - Health check to verify all services are working
- `GET /status` - Get detailed status of the application
- `POST /scrape` - Manually trigger the scraper to run immediately

Example usage:
```bash
# Check health
curl -X GET http://localhost:8080/health

# Get status
curl -X GET http://localhost:8080/status

# Manually trigger scraping
curl -X POST http://localhost:8080/scrape
```

## Development

### Manual Testing

The application includes manual test scripts to verify functionality before deployment:

1. **Scraper Test** (recommended first test):
   ```bash
   python test_scraper_only.py
   ```
   This tests just the web scraping functionality to ensure it can extract data from the busker profile page, including date, time, location, and busker name from dynamically loaded content.

2. **Full Manual Test**:
   ```bash
   python test_manual.py
   ```
   This runs comprehensive tests on all components including:
   - Configuration validation
   - Redis connection
   - Web scraping
   - Google Calendar connection
   - Redis event storage
   - Scheduler components

3. **Individual Component Tests**:
   ```bash
   python test_manual.py config      # Test configuration
   python test_manual.py redis       # Test Redis connection
   python test_manual.py scraper     # Test web scraping
   python test_manual.py calendar    # Test Google Calendar
   python test_manual.py redis_store # Test Redis storage
   python test_manual.py scheduler   # Test scheduler
   ```

### Prerequisites for Testing

Before running the tests, ensure you have:
1. Set up your `.env` file with the required values
2. Installed the dependencies: `pip install -r requirements.txt`
3. Installed Playwright browsers: `playwright install chromium`
4. Set up Google Calendar API with service account
5. Started a Redis server

### Interpreting Test Results

- Green checkmarks (✓) indicate successful tests
- Red X marks (✗) indicate failed tests
- Pay attention to error messages for troubleshooting

The scraper test is the best place to start as it validates the core functionality without requiring all services to be configured.

### Local Testing

For local testing without waiting for the scheduled time:
1. Modify the scheduler in `scheduler.py` to run immediately for testing
2. Run the application: `python main.py`

## Troubleshooting

### Common Issues

1. **Playwright Browser Issues**: Make sure Chromium is installed properly
2. **Google Calendar API Errors**: Verify service account permissions and JSON file
3. **Redis Connection Issues**: Check Redis server status and connection parameters
4. **Scraping Failures**: The target website structure may have changed
5. **Dynamic Content Issues**: The website uses JavaScript to load content after the page loads, which requires proper wait strategies in the scraper

### Logging

The application logs to console with configurable log level. Check logs for error details and execution status.

## Security Considerations

- Never commit service account JSON to Git (excluded by .gitignore)
- Never commit BUSKER_URL or CALENDAR_ID to Git (excluded by .gitignore)
- Use environment variables for all sensitive configuration
- Treat BUSKER_URL and CALENDAR_ID as private API keys
- Implement proper access controls for the deployed application

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License

Copyright (c) 2026 Julian97

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.