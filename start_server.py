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
    
    # Determine if we're in production or development
    is_prod = os.environ.get("ENV", "").lower() == "production" or os.environ.get("RENDER", "")
    
    # Configure host and port
    host = "0.0.0.0"  # Bind to all interfaces for production
    port = int(os.environ.get("PORT", 8080))
    
    logger.info(f"Starting server on {host}:{port} (Production: {is_prod})...")
    
    # Start the FastAPI server
    uvicorn.run(
        "backend.app.main:app",  # Use the module path relative to the python path
        host=host,
        port=port,
        reload=not is_prod,  # Only enable reload in development
        workers=1,  # Single worker for Selenium compatibility
        log_level="info" if is_prod else "debug"
    )

if __name__ == "__main__":
    main() 