import os
# Set environment variable before importing Playwright
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', '/root/.cache/ms-playwright')

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
                # Launch browser with specific executable path if available
                try:
                    # Try system chromium first
                    browser = p.chromium.launch(headless=self.headless, executable_path="/usr/bin/chromium-browser")
                except Exception:
                    try:
                        # Try another common location
                        browser = p.chromium.launch(headless=self.headless, executable_path="/usr/bin/chromium")
                    except Exception:
                        # Fallback to Playwright's installed browser
                        browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                
                try:
                    # Navigate to the page
                    page.goto(self.url, timeout=self.timeout)
                    self.logger.info("Page loaded successfully")
                    
                    # Wait for the booking content to load (it's loaded dynamically)
                    try:
                        # Wait for the main booking container to load
                        page.wait_for_selector('#div-booking-result-view', timeout=30000)
                        self.logger.info("Booking result view loaded")
                        
                        # Wait additional time for all booking items to populate
                        page.wait_for_timeout(20000)
                        
                        # Verify booking items are loaded by checking for booking divs
                        booking_items = page.query_selector_all('[id^="div-booking-"]')
                        if booking_items:
                            self.logger.info(f"Found {len(booking_items)} booking items")
                        else:
                            self.logger.warning("No booking items found after waiting")
                        
                        # Scroll to load all content
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(5000)
                        
                    except PlaywrightTimeoutError:
                        self.logger.warning("Booking content didn't load within timeout, continuing with available content")
                    
                    # Get the page content after JavaScript execution
                    content = page.content()
                    
                    # Close browser
                    browser.close()
                    
                    # Parse the content with BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract the busker name from the page
                    busker_name = self._extract_busker_name(soup)
                    
                    events = self._parse_schedule(soup)
                    
                    # Update all events with the busker name
                    for event in events:
                        event['busker_name'] = busker_name
                    
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
        
        # Look for booking items specifically
        # The booking items are in divs with IDs like 'div-booking-[uuid]'
        booking_items = soup.find_all('div', id=re.compile(r'^div-booking-'))
        
        if booking_items:
            self.logger.info(f"Found {len(booking_items)} booking items")
            
            for item in booking_items:
                event = self._extract_event_from_booking_item(item)
                if event:
                    events.append(event)
        
        # If no events found from booking items, try the original approach
        if not events:
            # Look for elements that might contain event information
            # Try various selectors that might match the actual page structure
            possible_selectors = [
                '[class*="event"]',
                '[class*="schedule"]',
                '[class*="booking"]',
                '[class*="calendar"]',
                '[class*="performance"]',
                '.event',
                '.schedule',
                '.booking',
                '.calendar',
                '.performance'
            ]
            
            schedule_items = []
            
            # Try to find elements using different selectors
            for selector in possible_selectors:
                if selector.startswith('.'):
                    # Handle class selectors
                    class_name = selector[1:]
                    items = soup.find_all(class_=re.compile(f'.*{class_name}.*', re.IGNORECASE))
                    schedule_items.extend(items)
                elif selector.startswith('['):
                    # Handle attribute selectors
                    if 'class*=' in selector:
                        search_term = selector.split('class*=')[1].strip('\"\'\'')
                        items = soup.find_all(class_=re.compile(f'.*{search_term}.*', re.IGNORECASE))
                        schedule_items.extend(items)
                    elif 'data-testid' in selector:
                        attr_parts = selector[1:-1].split('=')
                        if len(attr_parts) == 2:
                            attr_name = attr_parts[0]
                            attr_value = attr_parts[1].strip('\"\'\'')
                            items = soup.find_all(attrs={attr_name: attr_value})
                            schedule_items.extend(items)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_items = []
            for item in schedule_items:
                if item not in seen:
                    seen.add(item)
                    unique_items.append(item)
            
            schedule_items = unique_items
            
            if schedule_items:
                self.logger.info(f"Found {len(schedule_items)} potential schedule items")
                
                for item in schedule_items:
                    event = self._extract_event_from_item(item)
                    if event:
                        events.append(event)
        
        # If no events found from structured elements, try text-based parsing as a fallback
        if not events:
            self.logger.info("No events extracted from structured elements, using text-based extraction")
            events = self._parse_by_text_content(soup)
        
        return events
    
    def _extract_event_from_booking_item(self, item) -> Optional[Dict[str, Any]]:
        """Extract event details from a booking item div."""
        try:
            # The booking item has a specific structure with ul.dash-bx-times
            # containing date, time, and location in separate li elements
            times_list = item.find('ul', class_='dash-bx-times')
            if not times_list:
                self.logger.debug("No dash-bx-times list found in booking item")
                return None
            
            # Extract date from the li that contains the date pattern
            date_str = None
            all_lis = times_list.find_all('li')
            for li in all_lis:
                li_text = li.get_text().strip()
                if re.search(r'[A-Za-z]{3},\s*\d{2}\s+\w+', li_text):
                    # Extract the date part: "Fri, 02 January" -> "02 January"
                    date_match = re.search(r'(\d{2}\s+\w+)', li_text)
                    if date_match:
                        # Since year is not in the date string, use current year
                        current_year = datetime.now().year
                        date_str = f"{date_match.group(1)} {current_year}"
                    break
            
            # Extract time from the span inside the li element
            start_time = None
            end_time = None
            
            # Find the li element containing the time span
            time_spans = times_list.find_all('span')
            if time_spans:
                time_text = time_spans[0].get_text().strip()
                # Clean the text to remove any special characters including non-breaking spaces
                time_text = time_text.replace('\xa0', ' ')  # Replace non-breaking space with regular space
                # Remove only specific unwanted control characters, preserve useful ones
                # Keep: space(32), tab(9), newline(10), carriage return(13)
                # Remove: other control characters
                time_text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]+', '', time_text)  # Remove unwanted control chars
                
                # Look for time range pattern
                time_range_match = re.search(r'(\d{1,2}:\d{2}:[AaPp][Mm])\s*[-–]\s*(\d{1,2}:\d{2}:[AaPp][Mm])', time_text)
                if time_range_match:
                    start_time_raw = time_range_match.group(1)
                    end_time_raw = time_range_match.group(2)
                    
                    # Normalize time format (convert 10:00:AM to 10:00 AM)
                    start_time = re.sub(r':([AaPp][Mm])', r' \1', start_time_raw)
                    end_time = re.sub(r':([AaPp][Mm])', r' \1', end_time_raw)
                    
                    start_time = self._normalize_time_format(start_time)
                    end_time = self._normalize_time_format(end_time)
            
            # Extract location from the li with class 'address'
            location = "Unknown Location"
            address_li = times_list.find('li', class_='address')
            if address_li:
                location_link = address_li.find('a')
                if location_link:
                    # Get text after the image tag
                    location_text = location_link.get_text().strip()
                    # Clean the text to remove special characters
                    location_text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]+', '', location_text)  # Remove unwanted control chars
                    # Extract just the location part (after the image alt text)
                    # Handle both &nbsp; and non-breaking space (\xa0)
                    location_text = location_text.replace('&nbsp;', ' ')
                    location_text = location_text.replace('\xa0', ' ')  # Replace non-breaking space with regular space
                                
                    # Find the location text (usually the last significant part)
                    loc_match = re.search(r'[\w\s,\.\(\)-]+$', location_text.strip())
                    if loc_match:
                        location = loc_match.group(0).strip()
                else:
                    location = address_li.get_text().strip()
                    # Clean the text to remove special characters
                    location = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]+', '', location).strip()
                    location = location.replace('&nbsp;', ' ').replace('\xa0', ' ').strip()  # Handle non-breaking spaces
            
            # Validate we have the required information
            if date_str and start_time and end_time and location:
                date = self._parse_date(date_str)
                
                # Extract busker name from the profile image alt attribute
                profile_img = item.find('img', id='profileImage')
                busker_name = "Unknown Busker"
                if profile_img and profile_img.get('alt'):
                    busker_name = profile_img.get('alt').strip()
                
                event = {
                    'date': date,
                    'start_time': start_time,
                    'end_time': end_time,
                    'location': location,
                    'busker_name': busker_name,
                    'busker_id': self._extract_busker_id(self.url),
                    'scraped_at': datetime.now().isoformat()
                }
                
                # Validate that we have essential fields
                if event['date'] and event['start_time'] and event['location']:
                    return event
            
            self.logger.debug(f"Incomplete event data - date: {date_str}, start_time: {start_time}, end_time: {end_time}, location: {location}")
            return None
            
        except Exception as e:
            self.logger.warning(f"Error extracting event from booking item: {e}")
            return None
    
    def _extract_busker_name(self, soup) -> str:
        """Extract the busker name from the page."""
        try:
            # Look for the busker name in multiple possible locations
            # 1. From the profile image alt attribute
            profile_img = soup.find('img', id='profileImage')
            if profile_img and profile_img.get('alt'):
                return profile_img.get('alt').strip()
            
            # 2. From an h2 tag
            h2_tag = soup.find('h2')
            if h2_tag:
                h2_text = h2_tag.get_text().strip()
                if h2_text and len(h2_text) > 1:  # Make sure it's not empty
                    return h2_text
            
            # 3. From a span that might contain the name
            spans = soup.find_all('span')
            for span in spans:
                span_text = span.get_text().strip()
                if 'busker' in span_text.lower() or len(span_text) > 1:
                    # Look for spans that might contain the actual name
                    if len(span_text) > 5 and not span_text.lower().startswith('location'):
                        return span_text
            
            # If none found, return default
            return "Unknown Busker"
            
        except Exception as e:
            self.logger.warning(f"Error extracting busker name: {e}")
            return "Unknown Busker"
    
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
                    # Try to find date by looking for elements with date-like content
                    # Look for elements with date pattern
                    for tag in item.find_all(['span', 'div', 'p', 'li', 'td']):
                        text_content = tag.get_text().strip()
                        if re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec).*\d{1,2}.*\d{4}', text_content, re.IGNORECASE):
                            date = self._parse_date(text_content)
                            break
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
                time_elem = item.find(['span', 'div', 'p', 'li', 'td'], text=re.compile(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)?|\d{1,2}\.\d{2}'))
                if time_elem:
                    start_time, end_time = self._parse_time_range(str(time_elem.text).strip())
                else:
                    # Try to find time by looking for elements with time-like content
                    for tag in item.find_all(['span', 'div', 'p', 'li', 'td']):
                        text_content = tag.get_text().strip()
                        if re.search(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)?|\d{1,2}\.\d{2}', text_content, re.IGNORECASE):
                            start_time, end_time = self._parse_time_range(text_content)
                            break
                    else:
                        # Could not find time, skip this item
                        return None
            
            # Look for location - try multiple approaches
            location = "Unknown Location"
            
            # First, look for location-related text
            location_elements = item.find_all(['span', 'div', 'p', 'li', 'td'], text=re.compile(r'location|venue|@|at|\bat\b|\bpark\b|\btheatre\b|\bstreet\b|\bplaza\b', re.IGNORECASE))
            if location_elements:
                location = str(location_elements[0]).strip()
            else:
                # Look for elements that might contain location information
                for tag in item.find_all(['span', 'div', 'p', 'li', 'td']):
                    text_content = tag.get_text().strip()
                    # Look for text that might be a location (contains capital words, Singapore, or address-like patterns)
                    if re.search(r'[A-Z][a-z]+.*[A-Z][a-z]+|.*Singapore|.*St\.?|.*Ave\.?|.*Rd\.?|.*Lane|.*Circle|.*Plaza|.*Park|.*Theatre|.*Center|.*Centre', text_content, re.IGNORECASE):
                        location = text_content
                        break
            
            # Clean up location text
            location = re.sub(r'location[:\s]*|venue[:\s]*|@|at[:\s]*', '', location, flags=re.IGNORECASE).strip()
            
            # Look for busker name
            busker_name = "Unknown Busker"
            
            # Look for text that might be a name
            name_elem = item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'p', 'strong', 'b'], 
                                 text=re.compile(r'busker|performer|artist|musician|band|singer|guitarist|violinist', re.IGNORECASE))
            if name_elem:
                busker_name = str(name_elem.text).strip()
                # Remove performer-related terms
                busker_name = re.sub(r'busker|performer|artist|musician|band|singer|guitarist|violinist', '', busker_name, flags=re.IGNORECASE).strip()
            else:
                # Try to find the first significant text content as the name
                all_text = item.get_text().strip()
                lines = all_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 2 and not re.match(r'\d.*\d|.*\d{4}.*|.*\d{1,2}:\d{2}.*', line):  # Skip if it looks like a date or time
                        busker_name = line
                        break
            
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
            
            # Validate that we have essential fields
            if event['date'] and event['start_time'] and event['location']:
                return event
            else:
                self.logger.debug(f"Incomplete event data: {event}")
                return None
            
        except Exception as e:
            self.logger.warning(f"Error extracting event from item: {e}")
            return None
    
    def _parse_by_text_content(self, soup) -> List[Dict[str, Any]]:
        """Parse schedule by looking for date/time patterns in the text."""
        events = []
        
        # Get all text content
        text_content = soup.get_text()
        
        # Enhanced pattern to match the format you mentioned: "Fri, 02 January 06:00:PM - 07:00:PM HOUGANG CENTRAL HUB"
        # Pattern: Day, date Month Year time - time Location
        event_pattern = r'([A-Za-z]{3}, \d{2} \w+ \d{4})\s+(\d{1,2}:\d{2})\s*([AaPp][Mm])\s*-\s*(\d{1,2}:\d{2})\s*([AaPp][Mm])\s+([A-Z\s]+)'
        
        matches = re.finditer(event_pattern, text_content)
        for match in matches:
            date_part = match.group(1)  # "Fri, 02 January 2024"
            start_time = f"{match.group(2)} {match.group(3)}"  # "06:00 PM"
            end_time = f"{match.group(4)} {match.group(5)}"  # "07:00 PM"
            location = match.group(6).strip()  # "HOUGANG CENTRAL HUB"
            
            # Extract just the date part to parse
            date_str = re.search(r'(\d{2} \w+ \d{4})', date_part)
            if date_str:
                parsed_date = self._parse_date(date_str.group(1))
                parsed_start_time = self._normalize_time_format(start_time)
                parsed_end_time = self._normalize_time_format(end_time)
                
                event = {
                    'date': parsed_date,
                    'start_time': parsed_start_time,
                    'end_time': parsed_end_time,
                    'location': location,
                    'busker_name': "Unknown Busker",
                    'busker_id': self._extract_busker_id(self.url),
                    'scraped_at': datetime.now().isoformat()
                }
                
                events.append(event)
        
        # If the specific format wasn't found, fall back to the original method
        if not events:
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