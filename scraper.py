from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pytz
from config import Config
from utils import get_logger, retry_with_backoff

class BuskerScraper:
    """Web scraper for busker schedules using Playwright."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.url = Config.BUSKER_URL
        self.timeout = Config.PLAYWRIGHT_TIMEOUT
        self.headless = Config.PLAYWRIGHT_HEADLESS
    
    def scrape_busker_schedule(self) -> List[Dict[str, Any]]:
        """Scrape the busker schedule from the website."""
        self.logger.info(f"Starting to scrape busker schedule from {self.url}")
        
        def scrape_attempt():
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                
                try:
                    # Navigate to the page
                    page.goto(self.url, timeout=self.timeout)
                    self.logger.info("Page loaded successfully")
                    
                    # Wait for the schedule elements to load
                    page.wait_for_selector('[data-testid="schedule-item"]', timeout=self.timeout)
                    
                    # Get the page content after JavaScript execution
                    content = page.content()
                    
                    # Close browser
                    browser.close()
                    
                    # Parse the content with BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    events = self._parse_schedule(soup)
                    
                    self.logger.info(f"Successfully scraped {len(events)} events")
                    return events
                    
                except PlaywrightTimeoutError:
                    browser.close()
                    self.logger.error(f"Timeout while scraping {self.url}")
                    raise
                except Exception as e:
                    browser.close()
                    self.logger.error(f"Error during scraping: {e}")
                    raise
        
        # Use retry logic for scraping
        try:
            return retry_with_backoff(scrape_attempt, max_retries=Config.MAX_RETRIES, delay=Config.RETRY_DELAY)
        except Exception as e:
            self.logger.error(f"Failed to scrape after {Config.MAX_RETRIES} attempts: {e}")
            raise
    
    def _parse_schedule(self, soup) -> List[Dict[str, Any]]:
        """Parse the schedule from the BeautifulSoup object."""
        events = []
        
        # Look for schedule items - these selectors are based on common patterns
        # The actual selectors might need to be adjusted based on the real page structure
        schedule_items = soup.find_all('div', {'data-testid': 'schedule-item'}) or \
                        soup.find_all('div', class_=re.compile(r'.*schedule.*', re.IGNORECASE)) or \
                        soup.find_all('div', class_=re.compile(r'.*event.*', re.IGNORECASE))
        
        if not schedule_items:
            # Try more general selectors
            schedule_items = soup.find_all('div', class_=re.compile(r'.*row.*|.*item.*|.*card.*', re.IGNORECASE))
        
        for item in schedule_items:
            event = self._extract_event_from_item(item)
            if event:
                events.append(event)
        
        # If we couldn't find events with data-testid, try parsing by text content
        if not events:
            events = self._parse_by_text_content(soup)
        
        return events
    
    def _extract_event_from_item(self, item) -> Optional[Dict[str, Any]]:
        """Extract event details from a single schedule item."""
        try:
            # Look for date - common patterns
            date_elements = item.find_all(text=re.compile(r'\d{4}-\d{2}-\d{2}')) or \
                           item.find_all(text=re.compile(r'\d{1,2}/\d{1,2}/\d{4}')) or \
                           item.find_all(text=re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec).*\d{1,2}.*\d{4}'))
            
            if date_elements:
                date_text = str(date_elements[0]).strip()
                date = self._parse_date(date_text)
            else:
                # Try to find date in child elements
                date_elem = item.find(['span', 'div', 'p'], text=re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec).*\d{1,2}.*\d{4}'))
                if date_elem:
                    date = self._parse_date(str(date_elem.text).strip())
                else:
                    # Could not find date, skip this item
                    return None
            
            # Look for time - common patterns
            time_elements = item.find_all(text=re.compile(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)?')) or \
                           item.find_all(text=re.compile(r'\d{1,2}\.\d{2}'))  # For formats like 7.30pm
            
            if time_elements:
                time_text = str(time_elements[0]).strip()
                start_time, end_time = self._parse_time_range(time_text)
            else:
                # Try to find time in child elements
                time_elem = item.find(['span', 'div', 'p'], text=re.compile(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)?|\d{1,2}\.\d{2}'))
                if time_elem:
                    start_time, end_time = self._parse_time_range(str(time_elem.text).strip())
                else:
                    # Could not find time, skip this item
                    return None
            
            # Look for location
            location_elements = item.find_all(['span', 'div', 'p'], text=re.compile(r'location|venue|@|at', re.IGNORECASE))
            if not location_elements:
                # Look for common location patterns
                location_elem = item.find(['span', 'div', 'p'], text=re.compile(r'[A-Z][a-z]+.*[A-Z][a-z]+|.*Singapore|.*St\.?|.*Ave\.?|.*Rd\.?', re.IGNORECASE))
                if location_elem:
                    location = str(location_elem.text).strip()
                else:
                    location = "Unknown Location"
            else:
                location = str(location_elements[0]).strip()
            
            # Clean up location text
            location = re.sub(r'location[:\s]*|venue[:\s]*', '', location, flags=re.IGNORECASE).strip()
            
            # Look for busker name
            name_elem = item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'p'], 
                                 text=re.compile(r'busker|performer|artist', re.IGNORECASE))
            if not name_elem:
                # Try to find any text that might be a name
                name_elem = item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'p'])
            
            busker_name = str(name_elem.text).strip() if name_elem else "Unknown Busker"
            busker_name = re.sub(r'busker|performer|artist', '', busker_name, flags=re.IGNORECASE).strip()
            
            # Create event object
            event = {
                'date': date,
                'start_time': start_time,
                'end_time': end_time,
                'location': location,
                'busker_name': busker_name,
                'busker_id': self._extract_busker_id(self.url),  # Extract from URL
                'scraped_at': datetime.now().isoformat()
            }
            
            return event
            
        except Exception as e:
            self.logger.warning(f"Error extracting event from item: {e}")
            return None
    
    def _parse_by_text_content(self, soup) -> List[Dict[str, Any]]:
        """Parse schedule by looking for date/time patterns in the text."""
        events = []
        
        # Get all text content
        text_content = soup.get_text()
        
        # Find date patterns
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})',
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})'
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                
                # Look for time near this date
                start_pos = max(0, match.start() - 200)
                end_pos = min(len(text_content), match.end() + 200)
                context = text_content[start_pos:end_pos]
                
                # Find time patterns in context
                time_matches = re.findall(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', context)
                if time_matches:
                    start_time, end_time = self._parse_time_range(time_matches[0])
                    
                    # Look for location in context
                    location_match = re.search(r'at\s+([A-Z][^,.\n]{10,50})|@([A-Z][^,.\n]{10,50})', context, re.IGNORECASE)
                    location = location_match.group(1) or location_match.group(2) if location_match else "Unknown Location"
                    
                    event = {
                        'date': parsed_date,
                        'start_time': start_time,
                        'end_time': end_time,
                        'location': location.strip(),
                        'busker_name': "Unknown Busker",
                        'busker_id': self._extract_busker_id(self.url),
                        'scraped_at': datetime.now().isoformat()
                    }
                    
                    events.append(event)
        
        return events
    
    def _parse_date(self, date_str: str) -> str:
        """Parse date string into YYYY-MM-DD format."""
        date_str = date_str.strip()
        
        # Handle different date formats
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d-%m-%Y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d %B %Y',
            '%d %b %Y'
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # If no format matches, return the original string
        self.logger.warning(f"Could not parse date: {date_str}")
        return date_str
    
    def _parse_time_range(self, time_str: str) -> tuple:
        """Parse time string and return start and end times."""
        time_str = time_str.strip()
        
        # Handle time ranges like "7:30pm - 9:30pm" or "7.30pm to 9.30pm"
        range_pattern = r'(\d{1,2}[:\.]\d{2}\s*(?:AM|PM|am|pm)?)\s*[-–to]+\s*(\d{1,2}[:\.]\d{2}\s*(?:AM|PM|am|pm)?)'
        range_match = re.match(range_pattern, time_str, re.IGNORECASE)
        
        if range_match:
            start_time = self._normalize_time_format(range_match.group(1))
            end_time = self._normalize_time_format(range_match.group(2))
            return start_time, end_time
        
        # Handle single time (assume 2 hours duration)
        single_time = self._normalize_time_format(time_str)
        start_time = single_time
        
        # Calculate end time (add 2 hours as default duration)
        try:
            time_obj = datetime.strptime(single_time, '%H:%M')
            end_time_obj = time_obj + timedelta(hours=2)
            end_time = end_time_obj.strftime('%H:%M')
        except ValueError:
            end_time = single_time  # If parsing fails, use same time
            
        return start_time, end_time
    
    def _normalize_time_format(self, time_str: str) -> str:
        """Normalize time string to 24-hour HH:MM format."""
        time_str = time_str.strip()
        
        # Handle formats like "7.30pm"
        time_str = time_str.replace('.', ':')
        
        # Handle 12-hour format
        if 'am' in time_str.lower() or 'pm' in time_str.lower():
            try:
                # Handle formats like "7:30pm" or "7:30 PM"
                if ':' in time_str:
                    time_obj = datetime.strptime(time_str.upper(), '%I:%M %p')
                else:
                    # Handle formats like "7pm" - add minutes
                    time_str = re.sub(r'(\d+)([ap]m)', r'\1:00\2', time_str, flags=re.IGNORECASE)
                    time_obj = datetime.strptime(time_str.upper(), '%I:%M %p')
                
                return time_obj.strftime('%H:%M')
            except ValueError:
                # If parsing fails, return original
                self.logger.warning(f"Could not parse time: {time_str}")
                return time_str
        else:
            # Handle 24-hour format
            if ':' not in time_str:
                # If no colon, assume it's like "1900" for 19:00
                if len(time_str) == 4 and time_str.isdigit():
                    time_str = time_str[:2] + ':' + time_str[2:]
                elif len(time_str) == 3 and time_str.isdigit():
                    time_str = time_str[0] + ':' + time_str[1:]
            
            # Validate 24-hour format
            try:
                time_obj = datetime.strptime(time_str, '%H:%M')
                return time_str
            except ValueError:
                self.logger.warning(f"Could not parse time: {time_str}")
                return time_str
    
    def _extract_busker_id(self, url: str) -> str:
        """Extract busker ID from URL."""
        # Extract the UUID from the URL
        match = re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', url, re.IGNORECASE)
        return match.group(0) if match else "unknown"
    
    def validate_scraped_data(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and clean scraped data."""
        validated_events = []
        
        for event in events:
            # Validate required fields
            if not all(key in event for key in ['date', 'start_time', 'location']):
                self.logger.warning(f"Event missing required fields: {event}")
                continue
            
            # Validate date format
            try:
                datetime.strptime(event['date'], '%Y-%m-%d')
            except ValueError:
                self.logger.warning(f"Invalid date format: {event['date']}")
                continue
            
            # Validate time format
            try:
                datetime.strptime(event['start_time'], '%H:%M')
                if 'end_time' in event:
                    datetime.strptime(event['end_time'], '%H:%M')
            except ValueError:
                self.logger.warning(f"Invalid time format in event: {event}")
                continue
            
            validated_events.append(event)
        
        return validated_events