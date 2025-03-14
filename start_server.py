import uvicorn
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start the FastAPI server."""
    logger.info("Starting Playlist Converter server...")
    
    # Set the Python path to include the backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, backend_dir)
    
    # Add the parent directory to make imports work
    sys.path.insert(0, os.path.join(backend_dir, 'backend'))
    os.environ["PYTHONPATH"] = backend_dir
    
    logger.info(f"Set PYTHONPATH to: {backend_dir}")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python path: {sys.path}")
    
    # Start the FastAPI server
    logger.info("Starting server on port 8080...")
    uvicorn.run(
        "backend.app.main:app",  # Use the module path relative to the python path
        host="127.0.0.1",
        port=8080,
        reload=True,
        log_level="debug"
    )

if __name__ == "__main__":
    main() 