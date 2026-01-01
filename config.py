import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Configuration class to manage environment variables and application settings."""
    
    # Busker profile URL
    BUSKER_URL = os.getenv(
        'BUSKER_URL', 
        'https://eservices.nac.gov.sg/Busking/busker/profile/dbc5b6bc-e22a-4e60-9fe4-f4d6a1aa17a4'
    )
    
    # Google Calendar settings
    CALENDAR_ID = os.getenv(
        'CALENDAR_ID', 
        'fec731e846c5f2bf53f17ade0152aa8fe1197c79fcbcc470460b6fc2f8106701@group.calendar.google.com'
    )
    GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', './credentials/service-account.json')
    
    # Redis settings
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    
    # Timezone settings
    TIMEZONE = os.getenv('TIMEZONE', 'Asia/Singapore')
    
    # Logging settings
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Event settings
    EVENT_TTL_DAYS = int(os.getenv('EVENT_TTL_DAYS', 90))
    EVENT_TTL_SECONDS = EVENT_TTL_DAYS * 24 * 60 * 60  # Convert days to seconds
    
    # Scheduler settings
    SCRAPE_TIME_HOUR = 23  # 11 PM (23:00) in GMT+8 timezone
    SYNC_TIME_HOUR = 3     # 3 AM for sync/reconciliation
    
    # Playwright settings
    PLAYWRIGHT_TIMEOUT = int(os.getenv('PLAYWRIGHT_TIMEOUT', 30000))  # 30 seconds
    PLAYWRIGHT_HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
    
    # Retry settings
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    RETRY_DELAY = int(os.getenv('RETRY_DELAY', 5))  # seconds
    
    @classmethod
    def validate(cls):
        """Validate that required configuration values are present."""
        errors = []
        
        if not cls.BUSKER_URL:
            errors.append("BUSKER_URL is required")
        
        if not cls.CALENDAR_ID:
            errors.append("CALENDAR_ID is required")
            
        if not os.path.exists(cls.GOOGLE_CREDENTIALS_PATH):
            errors.append(f"Google credentials file not found at {cls.GOOGLE_CREDENTIALS_PATH}")
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")