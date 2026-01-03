from flask import Flask, jsonify, render_template_string
from datetime import datetime
import logging
import os
import sys
from config import Config
from redis_manager import RedisManager
from scraper import BuskerScraper
from calendar_manager import CalendarManager
from utils import get_logger

app = Flask(__name__)

# Setup logger
logger = get_logger('api')

# Initialize managers
redis_manager = RedisManager()
calendar_manager = CalendarManager()
scraper = BuskerScraper()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify all services are working."""
    try:
        # Check Redis connection
        redis_status = redis_manager.test_connection()
        
        # Check Google Calendar connection
        calendar_status = calendar_manager.test_connection()
        
        # Check if required config is available
        config_status = all([
            Config.BUSKER_URL,
            Config.CALENDAR_ID,
            Config.GOOGLE_CREDENTIALS_PATH
        ])
        
        status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': {
                'redis': 'connected' if redis_status else 'disconnected',
                'calendar': 'connected' if calendar_status else 'disconnected',
                'config': 'valid' if config_status else 'invalid'
            },
            'overall_status': 'healthy' if all([redis_status, calendar_status, config_status]) else 'unhealthy'
        }
        
        return jsonify(status), 200 if status['overall_status'] == 'healthy' else 503
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

@app.route('/scrape', methods=['POST'])
def manual_scrape():
    """Manually trigger the scraper to run immediately."""
    try:
        logger.info("Manual scrape request received")
        
        # Test Redis connection first
        redis_status = redis_manager.test_connection()
        if not redis_status:
            return jsonify({
                'status': 'error',
                'message': 'Redis connection failed'
            }), 503
        
        # Test Calendar connection
        calendar_status = calendar_manager.test_connection()
        if not calendar_status:
            return jsonify({
                'status': 'error',
                'message': 'Calendar connection failed'
            }), 503
        
        # Run the scraper
        events = scraper.scrape_busker_schedule()
        
        if not events:
            return jsonify({
                'status': 'success',
                'message': 'Scraping completed successfully',
                'events_found': 0
            }), 200
        
        # Process events - store in Redis and add to calendar
        processed_count = 0
        errors = []
        
        for event_data in events:
            try:
                # Store in Redis to prevent duplicates
                event_hash = redis_manager.generate_event_hash(event_data)
                
                # Check if event already exists
                if not redis_manager.event_exists(event_hash):
                    # Create event in Google Calendar
                    calendar_event = calendar_manager.create_event(
                        event_data['date'], 
                        event_data['start_time'], 
                        event_data['end_time'], 
                        event_data['location'],
                        event_data['busker_name']
                    )
                    
                    if calendar_event:
                        # Store in Redis
                        redis_manager.store_event(event_data, calendar_event['id'])
                        processed_count += 1
                        logger.info(f"Event processed: {event_data['date']} {event_data['location']}")
                    else:
                        errors.append(f"Failed to create calendar event for {event_data['date']} {event_data['location']}")
                else:
                    logger.info(f"Event already exists in Redis, skipping: {event_data['date']} {event_data['location']}")
            except Exception as e:
                errors.append(f"Error processing event {event_data.get('date', 'unknown')}: {str(e)}")
                logger.error(f"Error processing event: {e}")
        
        result = {
            'status': 'success',
            'message': f'Scraping completed. Processed {processed_count} new events out of {len(events)} found.',
            'events_found': len(events),
            'events_processed': processed_count,
            'timestamp': datetime.now().isoformat()
        }
        
        if errors:
            result['errors'] = errors
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Manual scrape failed: {e}")
        # Return a proper error response even if the scraping fails
        error_message = str(e)
        if 'Executable doesn\'t exist' in error_message:
            error_message = "Browser executable not found. Playwright browsers may not be properly installed in the deployment environment."
        return jsonify({
            'status': 'error',
            'message': f'Manual scrape failed: {error_message}',
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/', methods=['GET'])
def index():
    """Serve the status dashboard page."""
    try:
        # Read the status.html file content
        with open('status.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return render_template_string(html_content)
    except FileNotFoundError:
        return jsonify({'error': 'Status page not found'}), 404
    except Exception as e:
        logger.error(f"Error serving status page: {e}")
        return jsonify({'error': 'Error loading status page'}), 500

@app.route('/status', methods=['GET'])
def status_check():
    """Get detailed status of the application."""
    try:
        # Get Redis connection status
        redis_status = redis_manager.test_connection()
        
        # Get calendar connection status
        calendar_status = calendar_manager.test_connection()
        
        # Get recent metrics from Redis if available
        metrics = {}
        if redis_status:
            try:
                metrics = redis_manager.get_recent_metrics()
            except Exception as e:
                logger.warning(f"Could not retrieve metrics: {e}")
        
        # Get last scrape info if available
        last_scrape = {}
        if redis_status:
            try:
                last_scrape = redis_manager.get_last_scrape_info()
            except Exception as e:
                logger.warning(f"Could not retrieve last scrape info: {e}")
        
        status = {
            'status': 'running',
            'timestamp': datetime.now().isoformat(),
            'services': {
                'redis': 'connected' if redis_status else 'disconnected',
                'calendar': 'connected' if calendar_status else 'disconnected'
            },
            'config': {
                'busker_url_set': bool(Config.BUSKER_URL),
                'calendar_id_set': bool(Config.CALENDAR_ID),
                'timezone': Config.TIMEZONE
            },
            'metrics': metrics,
            'last_scrape': last_scrape
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)