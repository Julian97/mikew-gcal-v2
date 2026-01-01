"""
Manual testing script for the Busker Scheduler application.
This script allows you to test each component individually to verify functionality.
"""
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils import setup_logging, get_logger
from scraper import BuskerScraper
from calendar_manager import CalendarManager
from redis_manager import RedisManager
from scheduler import Scheduler

def test_config():
    """Test configuration loading."""
    print("Testing Configuration...")
    try:
        # Check if required config values are set
        issues = []
        if not Config.BUSKER_URL:
            issues.append("BUSKER_URL is not set")
        if not Config.CALENDAR_ID:
            issues.append("CALENDAR_ID is not set")
        if not os.path.exists(Config.GOOGLE_CREDENTIALS_PATH):
            issues.append(f"Google credentials file not found at {Config.GOOGLE_CREDENTIALS_PATH}")
        
        if issues:
            print(f"✗ Configuration issues found: {'; '.join(issues)}")
            return False
        else:
            print("✓ Configuration validation passed")
            print(f"  - Busker URL: {'SET' if Config.BUSKER_URL else 'NOT SET'}")
            print(f"  - Calendar ID: {'SET' if Config.CALENDAR_ID else 'NOT SET'}")
            print(f"  - Redis Host: {Config.REDIS_HOST}")
            print(f"  - Timezone: {Config.TIMEZONE}")
            return True
    except Exception as e:
        print(f"✗ Configuration validation failed: {e}")
        return False

def test_redis_connection():
    """Test Redis connection."""
    print("\nTesting Redis Connection...")
    try:
        redis_manager = RedisManager()
        if redis_manager.test_connection():
            print("✓ Redis connection successful")
            # Test basic Redis operations
            test_key = f"test:{int(datetime.now().timestamp())}"
            redis_manager.redis_client.setex(test_key, 60, "test_value")
            value = redis_manager.redis_client.get(test_key)
            if value == "test_value":
                print("✓ Redis basic operations working")
            else:
                print("✗ Redis basic operations failed")
            return True
        else:
            print("✗ Redis connection failed")
            return False
    except Exception as e:
        print(f"✗ Redis connection test failed: {e}")
        return False

def test_scraper():
    """Test the scraper functionality."""
    print("\nTesting Web Scraper...")
    try:
        scraper = BuskerScraper()
        print(f"  - Scraping URL: {scraper.url}")
        print("  - This may take a moment...")
        
        # Scrape events (this is a test, so we won't store them)
        events = scraper.scrape_busker_schedule()
        print(f"✓ Scraping successful - found {len(events)} events")
        
        if events:
            print("  Sample event:")
            event = events[0]
            for key, value in event.items():
                print(f"    {key}: {value}")
        
        # Validate the scraped data
        validated_events = scraper.validate_scraped_data(events)
        print(f"  - Validated events: {len(validated_events)}")
        
        return True
    except Exception as e:
        print(f"✗ Scraping test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_calendar_connection():
    """Test Google Calendar connection."""
    print("\nTesting Google Calendar Connection...")
    try:
        calendar_manager = CalendarManager()
        print("✓ Google Calendar authentication successful")
        
        # Test listing events (get recent events to verify API is working)
        # Limit to recent events to avoid too much data
        from utils import get_current_singapore_time
        from datetime import timedelta
        
        now = get_current_singapore_time()
        time_min = (now - timedelta(days=7)).isoformat()
        time_max = (now + timedelta(days=30)).isoformat()
        
        events = calendar_manager.list_events(time_min=time_min, time_max=time_max)
        print(f"✓ Calendar API working - found {len(events)} events in date range")
        
        return True
    except Exception as e:
        print(f"✗ Calendar connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_redis_store_event():
    """Test storing an event in Redis."""
    print("\nTesting Redis Event Storage...")
    try:
        redis_manager = RedisManager()
        
        # Create a sample event
        sample_event = {
            'date': '2024-12-25',
            'start_time': '19:00',
            'end_time': '21:00',
            'location': 'Test Location',
            'busker_name': 'Test Busker',
            'busker_id': 'test-busker-id',
            'scraped_at': datetime.now().isoformat()
        }
        
        # Store the event
        success = redis_manager.store_event(sample_event)
        if success:
            print("✓ Event stored in Redis successfully")
            
            # Check if event exists
            exists = redis_manager.event_exists(sample_event)
            if exists:
                print("✓ Event duplicate check working")
            else:
                print("✗ Event duplicate check failed")
            
            return True
        else:
            print("✗ Event storage failed")
            return False
    except Exception as e:
        print(f"✗ Redis event storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_scheduler_components():
    """Test scheduler components."""
    print("\nTesting Scheduler Components...")
    try:
        scheduler = Scheduler()
        print("✓ Scheduler initialization successful")
        print(f"  - Jobs scheduled: {len(scheduler.scheduler.get_jobs())}")
        for job in scheduler.scheduler.get_jobs():
            print(f"    - {job.name} (ID: {job.id})")
        return True
    except Exception as e:
        print(f"✗ Scheduler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_full_manual_test():
    """Run all manual tests."""
    print("Starting Manual Testing of Busker Scheduler Components\n")
    print("="*60)
    
    setup_logging('INFO')
    
    results = []
    
    # Run each test
    results.append(("Configuration", test_config()))
    results.append(("Redis Connection", test_redis_connection()))
    results.append(("Web Scraper", test_scraper()))
    results.append(("Calendar Connection", test_calendar_connection()))
    results.append(("Redis Event Storage", test_redis_store_event()))
    results.append(("Scheduler Components", test_scheduler_components()))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY:")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"{symbol} {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The application is ready for deployment.")
    else:
        print("⚠️  Some tests failed. Please check the output above for details.")
    
    return passed == total

def run_single_test(test_name):
    """Run a single specific test."""
    setup_logging('INFO')
    
    test_functions = {
        'config': test_config,
        'redis': test_redis_connection,
        'scraper': test_scraper,
        'calendar': test_calendar_connection,
        'redis_store': test_redis_store_event,
        'scheduler': test_scheduler_components
    }
    
    if test_name.lower() in test_functions:
        print(f"Running {test_name} test...")
        result = test_functions[test_name.lower()]()
        status = "PASS" if result else "FAIL"
        print(f"\n{test_name} test: {status}")
        return result
    else:
        print(f"Unknown test: {test_name}")
        print(f"Available tests: {', '.join(test_functions.keys())}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        run_single_test(test_name)
    else:
        # Run all tests
        run_full_manual_test()