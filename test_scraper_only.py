"""
Quick test script to verify the scraper functionality.
This script tests just the web scraping component.
"""
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils import setup_logging, get_logger
from scraper import BuskerScraper

def main():
    setup_logging('INFO')
    logger = get_logger(__name__)
    
    print("Busker Scraper Test")
    print("="*50)
    
    # Validate configuration
    try:
        Config.validate()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        print(f"❌ Configuration error: {e}")
        return False
    
    # Check if BUSKER_URL is set
    if not Config.BUSKER_URL:
        print("❌ BUSKER_URL is not set in environment variables")
        print("Please set BUSKER_URL in your .env file")
        return False
    
    print(f"🎯 Scraping URL: {Config.BUSKER_URL}")
    
    try:
        # Initialize scraper
        scraper = BuskerScraper()
        logger.info("Scraper initialized successfully")
        
        # Run the scrape
        print("🔄 Starting scrape...")
        events = scraper.scrape_busker_schedule()
        
        print(f"✅ Scraping completed successfully!")
        print(f"📊 Found {len(events)} events")
        
        if events:
            print("\n📋 Sample Event Data:")
            print("-" * 30)
            for i, event in enumerate(events[:3]):  # Show first 3 events
                print(f"Event {i+1}:")
                for key, value in event.items():
                    print(f"  {key}: {value}")
                print()
        
        # Validate the scraped data
        validated_events = scraper.validate_scraped_data(events)
        print(f"✅ Validation completed: {len(validated_events)} valid events")
        
        if len(validated_events) != len(events):
            print(f"⚠️  Some events were filtered during validation: {len(events) - len(validated_events)} invalid events removed")
        
        return True
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        import traceback
        traceback.print_exc()
        print(f"❌ Scraping failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n🎉 Scraper test completed successfully!")
        print("The scraper is working and can extract busker schedule data.")
    else:
        print("\n❌ Scraper test failed!")
        print("Check the error messages above for troubleshooting.")
        sys.exit(1)