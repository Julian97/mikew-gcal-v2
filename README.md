# Busker Schedule to Google Calendar

A Python application that scrapes busker schedules daily at 11 PM GMT+8 and automatically adds them to Google Calendar, using Redis for persistence across redeployments, deployable on Zeabur.

## Overview

This application:
- Scrapes busker performance schedules from: https://eservices.nac.gov.sg/Busking/busker/profile/dbc5b6bc-e22a-4e60-9fe4-f4d6a1aa17a4
- Creates events in Google Calendar (ID: fec731e846c5f2bf53f17ade0152aa8fe1197c79fcbcc470460b6fc2f8106701@group.calendar.google.com)
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
   - Place the service account JSON file in `./credentials/service-account.json`

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
6. Upload JSON to deployment securely

## Configuration

The application uses environment variables for configuration. Copy `.env.example` to `.env` and customize the values:

```bash
BUSKER_URL=https://eservices.nac.gov.sg/Busking/busker/profile/dbc5b6bc-e22a-4e60-9fe4-f4d6a1aa17a4
CALENDAR_ID=fec731e846c5f2bf53f17ade0152aa8fe1197c79fcbcc470460b6fc2f8106701@group.calendar.google.com
GOOGLE_CREDENTIALS_PATH=./credentials/service-account.json
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
TIMEZONE=Asia/Singapore
LOG_LEVEL=INFO
EVENT_TTL_DAYS=90
```

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

## Development

### Running Tests

Since this is a scraping application, testing involves:
1. Manual verification of scraped data
2. Checking Google Calendar for created events
3. Verifying Redis state persistence

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

### Logging

The application logs to console with configurable log level. Check logs for error details and execution status.

## Security Considerations

- Never commit service account JSON to Git (excluded by .gitignore)
- Use environment variables for sensitive configuration
- Implement proper access controls for the deployed application

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Specify your license here]