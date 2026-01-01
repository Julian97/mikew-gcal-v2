import hashlib
import logging
from datetime import datetime
from typing import Dict, Any
import pytz

def setup_logging(level: str = 'INFO'):
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)

def generate_event_hash(event_data: Dict[str, Any]) -> str:
    """Generate a unique hash for an event based on its key properties."""
    # Create a string from the key properties that define uniqueness
    hash_string = f"{event_data['date']}|{event_data['start_time']}|{event_data['location']}|{event_data.get('busker_id', '')}"
    return hashlib.sha256(hash_string.encode()).hexdigest()

def format_datetime_for_calendar(date_str: str, time_str: str, timezone_str: str = 'Asia/Singapore') -> str:
    """Format date and time strings into ISO 8601 format for Google Calendar."""
    # Parse the date and time
    dt_str = f"{date_str} {time_str}"
    
    # Parse the datetime assuming it's in the specified timezone
    tz = pytz.timezone(timezone_str)
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    
    # Localize to the specified timezone
    localized_dt = tz.localize(dt)
    
    # Return in ISO 8601 format
    return localized_dt.isoformat()

def parse_singapore_datetime(date_str: str, time_str: str) -> datetime:
    """Parse date and time strings in Singapore timezone."""
    tz = pytz.timezone('Asia/Singapore')
    dt_str = f"{date_str} {time_str}"
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return tz.localize(dt)

def get_current_singapore_time() -> datetime:
    """Get the current time in Singapore timezone."""
    sg_tz = pytz.timezone('Asia/Singapore')
    return datetime.now(sg_tz)

def retry_with_backoff(func, max_retries: int = 3, delay: int = 5):
    """Execute a function with retry logic and exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = delay * (2 ** attempt)  # Exponential backoff
            get_logger(__name__).warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            import time
            time.sleep(wait_time)
    
    raise Exception(f"Function failed after {max_retries} attempts")