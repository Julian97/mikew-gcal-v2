from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz
import signal
import sys
from typing import Callable
from scraper import BuskerScraper
from calendar_manager import CalendarManager
from redis_manager import RedisManager
from config import Config
from utils import get_logger, get_current_singapore_time

class Scheduler:
    """Manages the scheduling of busker scraping and calendar updates."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.scheduler = BlockingScheduler()
        self.scraper = BuskerScraper()
        self.calendar_manager = CalendarManager()
        self.redis_manager = RedisManager()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Add jobs to scheduler
        self._add_jobs()
    
    def _add_jobs(self):
        """Add scheduled jobs to the scheduler."""
        # Main scraping job - runs daily at 11 PM Singapore time
        self.scheduler.add_job(
            self._scrape_and_update_calendar,
            CronTrigger(
                hour=Config.SCRAPE_TIME_HOUR,  # 11 PM
                minute=0,
                second=0,
                timezone='Asia/Singapore'
            ),
            id='scrape_busker_schedule',
            name='Scrape busker schedule and update calendar'
        )
        
        # Optional sync/reconciliation job - runs daily at 3 AM Singapore time
        self.scheduler.add_job(
            self._sync_calendar_with_redis,
            CronTrigger(
                hour=Config.SYNC_TIME_HOUR,  # 3 AM
                minute=0,
                second=0,
                timezone='Asia/Singapore'
            ),
            id='sync_calendar_redis',
            name='Sync calendar with Redis cache'
        )
        
        self.logger.info("Jobs added to scheduler")
    
    def _scrape_and_update_calendar(self):
        """Main job to scrape busker schedule and update Google Calendar."""
        self.logger.info("Starting scheduled scraping job")
        
        # Acquire distributed lock
        lock_name = "scrape_job"
        lock_value = self.redis_manager.acquire_lock(lock_name, timeout=300)  # 5 minute timeout
        
        if not lock_value:
            self.logger.info("Another instance is already running, skipping this execution")
            return
        
        try:
            # Update metrics
            self.redis_manager.increment_metric("scrapes_attempted")
            
            # Scrape the busker schedule
            self.logger.info("Scraping busker schedule...")
            raw_events = self.scraper.scrape_busker_schedule()
            
            # Validate the scraped data
            validated_events = self.scraper.validate_scraped_data(raw_events)
            
            if not validated_events:
                self.logger.warning("No valid events found in scraping")
                self.redis_manager.increment_metric("scrapes_no_events")
                return
            
            self.logger.info(f"Found {len(validated_events)} valid events to process")
            
            # Process each event
            events_created = 0
            events_skipped = 0
            
            for event_data in validated_events:
                try:
                    # Check if event already exists in Redis (duplicate prevention)
                    if self.redis_manager.event_exists(event_data):
                        self.logger.debug(f"Event already exists in Redis, skipping: {event_data}")
                        events_skipped += 1
                        continue
                    
                    # Check if event already exists in Google Calendar
                    existing_event_id = self.calendar_manager.event_exists(event_data)
                    if existing_event_id:
                        self.logger.debug(f"Event already exists in Google Calendar, skipping: {event_data}")
                        # Store the event in Redis to prevent future duplicates
                        event_data['calendar_event_id'] = existing_event_id
                        self.redis_manager.store_event(event_data)
                        events_skipped += 1
                        continue
                    
                    # Create the event in Google Calendar
                    event_id = self.calendar_manager.create_event(event_data)
                    
                    if event_id:
                        # Store event in Redis with the calendar event ID
                        event_data['calendar_event_id'] = event_id
                        success = self.redis_manager.store_event(event_data)
                        
                        if success:
                            events_created += 1
                            self.logger.info(f"Successfully created and stored event: {event_data['date']} {event_data['start_time']} at {event_data['location']}")
                        else:
                            self.logger.error(f"Failed to store event in Redis: {event_data}")
                    else:
                        self.logger.error(f"Failed to create event in Google Calendar: {event_data}")
                        
                except Exception as e:
                    self.logger.error(f"Error processing event {event_data}: {e}")
                    self.redis_manager.log_error(f"Error processing event {event_data}: {e}")
            
            # Update metrics
            self.redis_manager.increment_metric("events_created", count=events_created)
            self.redis_manager.increment_metric("events_skipped", count=events_skipped)
            
            # Update last run metadata
            last_run_metadata = {
                "timestamp": get_current_singapore_time().isoformat(),
                "events_found": len(validated_events),
                "events_created": events_created,
                "events_skipped": events_skipped,
                "status": "success"
            }
            self.redis_manager.update_last_run_metadata(last_run_metadata)
            
            self.logger.info(f"Scraping job completed: {events_created} created, {events_skipped} skipped")
            
        except Exception as e:
            self.logger.error(f"Error in scraping job: {e}")
            self.redis_manager.log_error(f"Scraping job error: {e}")
            
            # Update last run metadata with error status
            last_run_metadata = {
                "timestamp": get_current_singapore_time().isoformat(),
                "status": "error",
                "error": str(e)
            }
            self.redis_manager.update_last_run_metadata(last_run_metadata)
            
            self.redis_manager.increment_metric("scrapes_errors")
        
        finally:
            # Release the lock
            self.redis_manager.release_lock(lock_name, lock_value)
            self.logger.info("Scraping job finished and lock released")
    
    def _sync_calendar_with_redis(self):
        """Sync calendar with Redis cache to handle discrepancies."""
        self.logger.info("Starting calendar sync job")
        
        try:
            # Acquire distributed lock
            lock_name = "sync_job"
            lock_value = self.redis_manager.acquire_lock(lock_name, timeout=600)  # 10 minute timeout
            
            if not lock_value:
                self.logger.info("Another sync instance is already running, skipping this execution")
                return
            
            # Get all events from Redis
            # For this example, we'll get events for the next 90 days
            from utils import get_current_singapore_time
            current_date = get_current_singapore_time().strftime("%Y-%m-%d")
            
            # This is a simplified sync - in a real implementation, you might want to:
            # 1. Compare all events in Redis with Google Calendar
            # 2. Identify discrepancies
            # 3. Update Google Calendar based on Redis data
            # 4. Handle deleted events
            
            self.logger.info("Calendar sync completed")
            
        except Exception as e:
            self.logger.error(f"Error in sync job: {e}")
            self.redis_manager.log_error(f"Sync job error: {e}")
        finally:
            # Release the lock
            self.redis_manager.release_lock(lock_name, lock_value)
            self.logger.info("Sync job finished and lock released")
    
    def start(self):
        """Start the scheduler."""
        self.logger.info("Starting scheduler...")
        try:
            self.scheduler.start()
        except KeyboardInterrupt:
            self.logger.info("Scheduler interrupted by user")
        except Exception as e:
            self.logger.error(f"Error starting scheduler: {e}")
    
    def shutdown(self):
        """Shutdown the scheduler gracefully."""
        self.logger.info("Shutting down scheduler...")
        self.scheduler.shutdown()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown()
        sys.exit(0)