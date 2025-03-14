import os
import sys
import logging
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api_server.log")
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Start the FastAPI server with simplified configuration."""
    try:
        logger.info("Starting Playlist Converter API server...")
        
        # Set up Python path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, current_dir)
        
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Python path: {sys.path}")
        
        # Import the app directly from backend.app.main
        from backend.app.main import app
        logger.info("Successfully imported FastAPI app")
        
        # Start the server
        logger.info("Starting uvicorn server on http://127.0.0.1:8080")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8080,
            log_level="debug"
        )
        
    except ImportError as e:
        logger.error(f"Import error: {str(e)}")
        logger.error("Make sure you have the correct directory structure and imports")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 