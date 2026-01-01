from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Dict, Any, Optional, List
import time
from config import Config
from utils import get_logger, format_datetime_for_calendar, retry_with_backoff

class CalendarManager:
    """Manages Google Calendar API operations."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.calendar_id = Config.CALENDAR_ID
        self.timezone = Config.TIMEZONE
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API using service account."""
        try:
            # Load service account credentials
            credentials = Credentials.from_service_account_file(
                Config.GOOGLE_CREDENTIALS_PATH,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Build the service object
            self.service = build('calendar', 'v3', credentials=credentials)
            self.logger.info("Successfully authenticated with Google Calendar API")
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Google Calendar API: {e}")
            raise
    
    def create_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Create a calendar event and return the event ID."""
        def create_attempt():
            try:
                # Format the event data for Google Calendar
                calendar_event = {
                    'summary': f"{event_data['busker_name']} - Busking Performance",
                    'location': event_data['location'],
                    'description': f"Busker performance by {event_data['busker_name']}",
                    'start': {
                        'dateTime': format_datetime_for_calendar(event_data['date'], event_data['start_time'], self.timezone),
                        'timeZone': self.timezone,
                    },
                    'end': {
                        'dateTime': format_datetime_for_calendar(event_data['date'], event_data['end_time'], self.timezone),
                        'timeZone': self.timezone,
                    },
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                            {'method': 'popup', 'minutes': 60},       # 1 hour before
                        ],
                    },
                }
                
                # Create the event
                created_event = self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=calendar_event,
                    sendNotifications=False  # Don't send email notifications for automated events
                ).execute()
                
                event_id = created_event.get('id')
                self.logger.info(f"Event created successfully with ID: {event_id}")
                return event_id
                
            except HttpError as e:
                self.logger.error(f"HTTP error creating event: {e}")
                if e.resp.status == 429:  # Rate limit
                    time.sleep(60)  # Wait 1 minute before retrying
                raise
            except Exception as e:
                self.logger.error(f"Error creating event: {e}")
                raise
        
        # Use retry logic for creating events
        try:
            return retry_with_backoff(create_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to create event after {Config.MAX_RETRIES} attempts: {e}")
            raise
    
    def update_event(self, event_id: str, event_data: Dict[str, Any]) -> bool:
        """Update an existing calendar event."""
        def update_attempt():
            try:
                # Get the existing event
                existing_event = self.service.events().get(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
                
                # Update the event data
                existing_event['summary'] = f"{event_data['busker_name']} - Busking Performance"
                existing_event['location'] = event_data['location']
                existing_event['description'] = f"Busker performance by {event_data['busker_name']}"
                existing_event['start'] = {
                    'dateTime': format_datetime_for_calendar(event_data['date'], event_data['start_time'], self.timezone),
                    'timeZone': self.timezone,
                }
                existing_event['end'] = {
                    'dateTime': format_datetime_for_calendar(event_data['date'], event_data['end_time'], self.timezone),
                    'timeZone': self.timezone,
                }
                
                # Update the event
                updated_event = self.service.events().update(
                    calendarId=self.calendar_id,
                    eventId=event_id,
                    body=existing_event,
                    sendNotifications=False
                ).execute()
                
                self.logger.info(f"Event updated successfully with ID: {event_id}")
                return True
                
            except HttpError as e:
                self.logger.error(f"HTTP error updating event: {e}")
                if e.resp.status == 429:  # Rate limit
                    time.sleep(60)  # Wait 1 minute before retrying
                raise
            except Exception as e:
                self.logger.error(f"Error updating event: {e}")
                raise
        
        # Use retry logic for updating events
        try:
            return retry_with_backoff(update_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to update event after {Config.MAX_RETRIES} attempts: {e}")
            return False
    
    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event."""
        def delete_attempt():
            try:
                # Delete the event
                self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
                
                self.logger.info(f"Event deleted successfully with ID: {event_id}")
                return True
                
            except HttpError as e:
                self.logger.error(f"HTTP error deleting event: {e}")
                if e.resp.status == 429:  # Rate limit
                    time.sleep(60)  # Wait 1 minute before retrying
                raise
            except Exception as e:
                self.logger.error(f"Error deleting event: {e}")
                raise
        
        # Use retry logic for deleting events
        try:
            return retry_with_backoff(delete_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to delete event after {Config.MAX_RETRIES} attempts: {e}")
            return False
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get a calendar event by ID."""
        def get_attempt():
            try:
                event = self.service.events().get(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
                
                return event
            except HttpError as e:
                self.logger.error(f"HTTP error getting event: {e}")
                if e.resp.status == 429:  # Rate limit
                    time.sleep(60)  # Wait 1 minute before retrying
                raise
            except Exception as e:
                self.logger.error(f"Error getting event: {e}")
                raise
        
        # Use retry logic for getting events
        try:
            return retry_with_backoff(get_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to get event after {Config.MAX_RETRIES} attempts: {e}")
            return None
    
    def list_events(self, time_min: str = None, time_max: str = None) -> List[Dict[str, Any]]:
        """List calendar events within a time range."""
        def list_attempt():
            try:
                # Set up the query parameters
                params = {
                    'calendarId': self.calendar_id,
                    'singleEvents': True,  # Expand recurring events
                    'orderBy': 'startTime'
                }
                
                if time_min:
                    params['timeMin'] = time_min
                if time_max:
                    params['timeMax'] = time_max
                
                # Execute the query
                events_result = self.service.events().list(**params).execute()
                events = events_result.get('items', [])
                
                return events
            except HttpError as e:
                self.logger.error(f"HTTP error listing events: {e}")
                if e.resp.status == 429:  # Rate limit
                    time.sleep(60)  # Wait 1 minute before retrying
                raise
            except Exception as e:
                self.logger.error(f"Error listing events: {e}")
                raise
        
        # Use retry logic for listing events
        try:
            return retry_with_backoff(list_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to list events after {Config.MAX_RETRIES} attempts: {e}")
            return []
    
    def event_exists(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Check if an event already exists in the calendar and return its ID if found."""
        try:
            # Format the start time to find events on the same day
            start_datetime = format_datetime_for_calendar(event_data['date'], event_data['start_time'], self.timezone)
            
            # Get events for the same day
            events = self.list_events(
                time_min=f"{event_data['date']}T00:00:00+08:00",
                time_max=f"{event_data['date']}T23:59:59+08:00"
            )
            
            # Look for a matching event based on time and location
            for event in events:
                # Extract start time from the event
                event_start = event.get('start', {}).get('dateTime', '')
                event_location = event.get('location', '').lower()
                event_summary = event.get('summary', '').lower()
                
                # Parse the start time to compare
                import re
                time_match = re.search(r'T(\d{2}:\d{2})', event_start)
                if time_match and time_match.group(1) == event_data['start_time']:
                    # Check if location matches (with some flexibility)
                    if (event_location in event_data['location'].lower() or 
                        event_data['location'].lower() in event_location or
                        event_summary and event_data['busker_name'].lower() in event_summary):
                        return event.get('id')
            
            return None
        except Exception as e:
            self.logger.error(f"Error checking if event exists in calendar: {e}")
            return None