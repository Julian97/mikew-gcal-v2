from typing import Dict, Any, List
from calendar_manager import CalendarManager
from redis_manager import RedisManager
from config import Config
from utils import get_logger, get_current_singapore_time
from datetime import datetime, timedelta

class SyncManager:
    """Manages synchronization and reconciliation between Redis cache and Google Calendar."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.calendar_manager = CalendarManager()
        self.redis_manager = RedisManager()
    
    def reconcile_calendar_with_redis(self) -> Dict[str, Any]:
        """Reconcile Google Calendar with Redis cache to identify and fix discrepancies."""
        self.logger.info("Starting calendar reconciliation...")
        
        result = {
            "timestamp": get_current_singapore_time().isoformat(),
            "synced_events": 0,
            "deleted_events": 0,
            "created_events": 0,
            "updated_events": 0,
            "errors": []
        }
        
        try:
            # Get all events from Redis for the next 90 days
            current_date = get_current_singapore_time().strftime("%Y-%m-%d")
            end_date = (get_current_singapore_time() + timedelta(days=90)).strftime("%Y-%m-%d")
            
            redis_events = self.redis_manager.get_events_by_date_range(current_date, end_date)
            self.logger.info(f"Found {len(redis_events)} events in Redis cache")
            
            # Get all events from Google Calendar for the same period
            start_datetime = f"{current_date}T00:00:00+08:00"
            end_datetime = f"{end_date}T23:59:59+08:00"
            
            calendar_events = self.calendar_manager.list_events(start_datetime, end_datetime)
            self.logger.info(f"Found {len(calendar_events)} events in Google Calendar")
            
            # Create mappings for comparison
            redis_event_map = {}
            for event in redis_events:
                event_hash = f"{event['date']}_{event['start_time']}_{event['location']}"
                redis_event_map[event_hash] = event
            
            calendar_event_map = {}
            for event in calendar_events:
                # Extract date and time from calendar event
                start_time_str = event.get('start', {}).get('dateTime', '')
                if start_time_str:
                    # Parse date and time from ISO format
                    try:
                        import re
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', start_time_str)
                        time_match = re.search(r'T(\d{2}:\d{2})', start_time_str)
                        location = event.get('location', '')
                        
                        if date_match and time_match:
                            date_str = date_match.group(1)
                            time_str = time_match.group(1)
                            event_hash = f"{date_str}_{time_str}_{location}"
                            calendar_event_map[event_hash] = {
                                'id': event['id'],
                                'summary': event['summary'],
                                'location': location,
                                'date': date_str,
                                'start_time': time_str
                            }
                    except Exception as e:
                        self.logger.warning(f"Could not parse calendar event time: {event.get('summary', 'Unknown')}, error: {e}")
            
            # Find events that exist in Redis but not in Calendar (need to be created)
            redis_only = set(redis_event_map.keys()) - set(calendar_event_map.keys())
            for event_hash in redis_only:
                try:
                    redis_event = redis_event_map[event_hash]
                    event_id = self.calendar_manager.create_event(redis_event)
                    if event_id:
                        redis_event['calendar_event_id'] = event_id
                        self.redis_manager.store_event(redis_event)
                        result["created_events"] += 1
                        self.logger.info(f"Created missing event in calendar: {redis_event['date']} {redis_event['start_time']} at {redis_event['location']}")
                    else:
                        result["errors"].append(f"Failed to create event: {redis_event}")
                except Exception as e:
                    result["errors"].append(f"Error creating event {redis_event_hash}: {e}")
                    self.logger.error(f"Error creating event {event_hash}: {e}")
            
            # Find events that exist in Calendar but not in Redis (might need deletion)
            calendar_only = set(calendar_only) - set(redis_event_map.keys())
            for event_hash in calendar_only:
                try:
                    calendar_event = calendar_event_map[event_hash]
                    # Check if this is a busker event by looking at the summary
                    if 'busker' in calendar_event['summary'].lower() or 'performance' in calendar_event['summary'].lower():
                        # This might be an old event that was not properly removed from calendar
                        # For safety, we won't delete automatically - just log for review
                        self.logger.info(f"Found calendar event not in Redis (might need manual review): {calendar_event['summary']} on {calendar_event['date']}")
                except Exception as e:
                    result["errors"].append(f"Error checking calendar-only event {event_hash}: {e}")
            
            # Find events that exist in both but may need updating
            common_events = set(redis_event_map.keys()) & set(calendar_event_map.keys())
            for event_hash in common_events:
                try:
                    redis_event = redis_event_map[event_hash]
                    calendar_event = calendar_event_map[event_hash]
                    
                    # Compare key fields to see if update is needed
                    calendar_summary = calendar_event['summary']
                    expected_summary = f"{redis_event['busker_name']} - Busking Performance"
                    
                    # Check if details match
                    needs_update = (
                        expected_summary != calendar_summary or
                        redis_event['location'] != calendar_event['location']
                    )
                    
                    if needs_update:
                        # Update the calendar event with Redis data
                        success = self.calendar_manager.update_event(
                            calendar_event['id'], 
                            redis_event
                        )
                        if success:
                            result["updated_events"] += 1
                            self.logger.info(f"Updated event in calendar: {redis_event['date']} {redis_event['start_time']}")
                        else:
                            result["errors"].append(f"Failed to update event: {redis_event}")
                except Exception as e:
                    result["errors"].append(f"Error updating event {event_hash}: {e}")
                    self.logger.error(f"Error updating event {event_hash}: {e}")
            
            result["synced_events"] = len(common_events)
            self.logger.info(f"Reconciliation completed: {result}")
            
        except Exception as e:
            error_msg = f"Error during reconciliation: {e}"
            result["errors"].append(error_msg)
            self.logger.error(error_msg)
        
        return result
    
    def cleanup_expired_events(self) -> int:
        """Clean up events that have expired."""
        try:
            removed_count = self.redis_manager.cleanup_old_events()
            self.logger.info(f"Cleaned up {removed_count} expired events from timeline")
            return removed_count
        except Exception as e:
            self.logger.error(f"Error cleaning up expired events: {e}")
            return 0
    
    def validate_redis_integrity(self) -> Dict[str, Any]:
        """Validate the integrity of Redis data."""
        result = {
            "total_events": 0,
            "events_with_calendar_id": 0,
            "events_without_calendar_id": 0,
            "validation_errors": []
        }
        
        try:
            # Get all events from Redis for the next 90 days
            current_date = get_current_singapore_time().strftime("%Y-%m-%d")
            end_date = (get_current_singapore_time() + timedelta(days=90)).strftime("%Y-%m-%d")
            
            redis_events = self.redis_manager.get_events_by_date_range(current_date, end_date)
            
            result["total_events"] = len(redis_events)
            
            for event in redis_events:
                if 'calendar_event_id' in event and event['calendar_event_id']:
                    result["events_with_calendar_id"] += 1
                else:
                    result["events_without_calendar_id"] += 1
                    
                    # Try to find the event in Google Calendar
                    existing_event_id = self.calendar_manager.event_exists(event)
                    if existing_event_id:
                        # Update the Redis entry with the calendar event ID
                        event['calendar_event_id'] = existing_event_id
                        self.redis_manager.store_event(event)
                        self.logger.info(f"Found and updated missing calendar ID for event: {event['date']} {event['start_time']}")
                    else:
                        result["validation_errors"].append(f"Event not found in calendar: {event}")
        
        except Exception as e:
            result["validation_errors"].append(f"Error validating Redis integrity: {e}")
            self.logger.error(f"Error validating Redis integrity: {e}")
        
        return result
    
    def run_full_sync(self) -> Dict[str, Any]:
        """Run a full synchronization and validation process."""
        self.logger.info("Starting full sync process...")
        
        result = {
            "timestamp": get_current_singapore_time().isoformat(),
            "reconciliation": {},
            "validation": {},
            "cleanup": 0
        }
        
        try:
            # Run reconciliation
            result["reconciliation"] = self.reconcile_calendar_with_redis()
            
            # Run validation
            result["validation"] = self.validate_redis_integrity()
            
            # Clean up expired events
            result["cleanup"] = self.cleanup_expired_events()
            
            self.logger.info("Full sync process completed successfully")
            
        except Exception as e:
            error_msg = f"Error in full sync process: {e}"
            self.logger.error(error_msg)
            result["error"] = error_msg
        
        return result