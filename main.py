import sys
import signal
import threading
import time
import os
from config import Config
from utils import setup_logging, get_logger
from scheduler import Scheduler
from redis_manager import RedisManager

def run_api():
    """Run the Flask API in a separate thread."""
    try:
        from api import app
        # Run Flask with production-ready settings
        port = int(os.environ.get('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Error starting API server: {e}")


def main():
    """Main entry point for the busker scheduler application."""
    # Set up logging
    setup_logging(Config.LOG_LEVEL)
    logger = get_logger(__name__)
    
    logger.info("Starting Busker Scheduler Application")
    
    try:
        # Validate configuration
        Config.validate()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Test Redis connection
    redis_manager = RedisManager()
    if not redis_manager.test_connection():
        logger.error("Failed to connect to Redis")
        sys.exit(1)
    logger.info("Redis connection established successfully")
    
    # Initialize and start scheduler
    scheduler = Scheduler()
    
    # Start API server in a separate thread
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("API server started on port 8080")
    
    logger.info("Busker Scheduler Application started successfully")
    logger.info(f"Scheduler will run daily at {Config.SCRAPE_TIME_HOUR}:00 Singapore time")
    
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in main application: {e}")
        sys.exit(1)
    finally:
        scheduler.shutdown()
        logger.info("Busker Scheduler Application stopped")

if __name__ == "__main__":
    main()