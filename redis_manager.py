import redis
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from config import Config
from utils import get_logger, generate_event_hash

class RedisManager:
    """Manages Redis connections and operations for the busker scheduler."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.redis_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=Config.REDIS_PASSWORD,
            db=Config.REDIS_DB,
            decode_responses=True
        )
        self.ttl_seconds = Config.EVENT_TTL_SECONDS
        
    def test_connection(self) -> bool:
        """Test Redis connection."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            self.logger.error(f"Redis connection failed: {e}")
            return False
    
    def store_event(self, event_data: Dict[str, Any], calendar_event_id: str = None) -> bool:
        """Store an event in Redis with TTL, optionally including calendar event ID."""
        try:
            event_hash = generate_event_hash(event_data)
            event_key = f"event:{event_hash}"
            
            # Add calendar event ID to the event data if provided
            if calendar_event_id:
                event_data['calendar_event_id'] = calendar_event_id
            
            # Store event data as a JSON string
            event_json = json.dumps(event_data)
            
            # Store with TTL
            result = self.redis_client.setex(
                event_key,
                self.ttl_seconds,
                event_json
            )
            
            # Add to timeline sorted set for date-based queries
            timestamp = self._date_to_timestamp(event_data['date'])
            self.redis_client.zadd("events_timeline", {event_hash: timestamp})
            
            return result is not None
        except Exception as e:
            self.logger.error(f"Error storing event in Redis: {e}")
            return False
    
    def event_exists(self, event_data: Dict[str, Any]) -> bool:
        """Check if an event already exists in Redis."""
        try:
            event_hash = generate_event_hash(event_data)
            event_key = f"event:{event_hash}"
            return self.redis_client.exists(event_key) == 1
        except Exception as e:
            self.logger.error(f"Error checking if event exists in Redis: {e}")
            return False
    
    def get_event(self, event_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve an event from Redis by its hash."""
        try:
            event_key = f"event:{event_hash}"
            event_json = self.redis_client.get(event_key)
            if event_json:
                return json.loads(event_json)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving event from Redis: {e}")
            return None
    
    def acquire_lock(self, lock_name: str, timeout: int = 300) -> Optional[str]:
        """Acquire a distributed lock using Redis."""
        lock_key = f"scraper:lock:{lock_name}"
        lock_value = f"{int(time.time())}:{lock_name}"
        
        # Use SET with NX (not exists) and EX (expire) options
        result = self.redis_client.set(
            lock_key,
            lock_value,
            nx=True,  # Only set if key doesn't exist
            ex=timeout  # Set expiration
        )
        
        if result:
            return lock_value
        else:
            return None
    
    def release_lock(self, lock_name: str, lock_value: str) -> bool:
        """Release a distributed lock using Redis Lua script."""
        lock_key = f"scraper:lock:{lock_name}"
        
        # Lua script to ensure we only delete the lock if it still has the same value
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        
        script = self.redis_client.register_script(lua_script)
        result = script(keys=[lock_key], args=[lock_value])
        return result == 1
    
    def update_last_run_metadata(self, metadata: Dict[str, Any]) -> bool:
        """Update the last run metadata in Redis."""
        try:
            metadata_key = "scraper:last_run"
            metadata_json = json.dumps(metadata)
            return self.redis_client.set(metadata_key, metadata_json) is not None
        except Exception as e:
            self.logger.error(f"Error updating last run metadata: {e}")
            return False
    
    def get_last_run_metadata(self) -> Optional[Dict[str, Any]]:
        """Get the last run metadata from Redis."""
        try:
            metadata_key = "scraper:last_run"
            metadata_json = self.redis_client.get(metadata_key)
            if metadata_json:
                return json.loads(metadata_json)
            return None
        except Exception as e:
            self.logger.error(f"Error getting last run metadata: {e}")
            return None
    
    def log_error(self, error_message: str) -> bool:
        """Log an error message to Redis."""
        try:
            error_entry = {
                "timestamp": datetime.now().isoformat(),
                "message": error_message
            }
            error_json = json.dumps(error_entry)
            
            # Add to errors list, keeping only the last 100 entries
            self.redis_client.lpush("errors:log", error_json)
            self.redis_client.ltrim("errors:log", 0, 99)
            return True
        except Exception as e:
            self.logger.error(f"Error logging error to Redis: {e}")
            return False
    
    def increment_metric(self, metric_name: str, date: str = None) -> bool:
        """Increment a metric counter in Redis."""
        try:
            if date is None:
                from utils import get_current_singapore_time
                date = get_current_singapore_time().strftime("%Y-%m-%d")
            
            metric_key = f"metrics:daily:{date}"
            field_name = metric_name
            
            # Increment the counter
            result = self.redis_client.hincrby(metric_key, field_name, 1)
            
            # Set TTL on the metrics hash to match event TTL
            self.redis_client.expire(metric_key, self.ttl_seconds)
            
            return result is not None
        except Exception as e:
            self.logger.error(f"Error incrementing metric in Redis: {e}")
            return False
    
    def get_metrics(self, date: str = None) -> Dict[str, int]:
        """Get metrics for a specific date."""
        try:
            if date is None:
                from utils import get_current_singapore_time
                date = get_current_singapore_time().strftime("%Y-%m-%d")
            
            metric_key = f"metrics:daily:{date}"
            metrics = self.redis_client.hgetall(metric_key)
            
            # Convert string values to integers
            for key, value in metrics.items():
                try:
                    metrics[key] = int(value)
                except ValueError:
                    metrics[key] = 0
            
            return metrics
        except Exception as e:
            self.logger.error(f"Error getting metrics from Redis: {e}")
            return {}
    
    def get_events_by_date_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get events within a date range."""
        try:
            start_timestamp = self._date_to_timestamp(start_date)
            end_timestamp = self._date_to_timestamp(end_date)
            
            # Get event hashes within the date range
            event_hashes = self.redis_client.zrangebyscore(
                "events_timeline", start_timestamp, end_timestamp
            )
            
            events = []
            for event_hash in event_hashes:
                event_data = self.get_event(event_hash)
                if event_data:
                    events.append(event_data)
            
            return events
        except Exception as e:
            self.logger.error(f"Error getting events by date range from Redis: {e}")
            return []
    
    def _date_to_timestamp(self, date_str: str) -> int:
        """Convert date string to timestamp."""
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return int(date_obj.timestamp())
    
    def get_recent_errors(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent error logs from Redis."""
        try:
            error_logs = self.redis_client.lrange("errors:log", 0, count - 1)
            errors = []
            for error_json in error_logs:
                try:
                    errors.append(json.loads(error_json))
                except json.JSONDecodeError:
                    continue
            return errors
        except Exception as e:
            self.logger.error(f"Error getting recent errors from Redis: {e}")
            return []
    
    def cleanup_old_events(self) -> int:
        """Clean up events that have expired."""
        try:
            # Since we use TTL, events should expire automatically
            # But we can still remove expired entries from the timeline
            from utils import get_current_singapore_time
            current_timestamp = int(get_current_singapore_time().timestamp())
            
            # Remove expired entries from timeline
            removed_count = self.redis_client.zremrangebyscore(
                "events_timeline", 0, current_timestamp - self.ttl_seconds
            )
            
            return removed_count
        except Exception as e:
            self.logger.error(f"Error cleaning up old events: {e}")
            return 0
    
    def get_recent_metrics(self) -> Dict[str, Any]:
        """Get recent metrics from Redis."""
        try:
            from utils import get_current_singapore_time
            current_date = get_current_singapore_time().strftime("%Y-%m-%d")
            
            metrics = self.get_metrics(current_date)
            
            # Also get total event count
            event_count = self.redis_client.zcard("events_timeline")
            
            # Get lock status
            lock_exists = self.redis_client.exists("scraper:lock") == 1
            
            return {
                "date": current_date,
                "metrics": metrics,
                "total_events": event_count,
                "lock_exists": lock_exists
            }
        except Exception as e:
            self.logger.error(f"Error getting recent metrics: {e}")
            return {}
    
    def get_last_scrape_info(self) -> Dict[str, Any]:
        """Get the last scrape information from Redis."""
        try:
            last_run = self.get_last_run_metadata()
            return last_run if last_run else {}
        except Exception as e:
            self.logger.error(f"Error getting last scrape info: {e}")
            return {}