"""
Start Script for Local Development Server

This script will:
1. Install required dependencies if missing
2. Start the local development server
"""

import os
import sys
import subprocess
import importlib.util
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("local_server.log")
    ]
)
logger = logging.getLogger("local-server")

def check_package_installed(package_name):
    """Check if a package is installed."""
    spec = importlib.util.find_spec(package_name)
    is_installed = spec is not None
    
    if is_installed:
        try:
            package = importlib.import_module(package_name)
            version = getattr(package, '__version__', 'unknown')
            logger.info(f"Package {package_name} is installed (version: {version})")
            return True
        except Exception as e:
            logger.warning(f"Package {package_name} is installed but failed to import: {str(e)}")
            return False
    else:
        logger.warning(f"Package {package_name} is NOT installed")
        return False

def install_required_packages():
    """Install required packages if missing."""
    required_packages = {
        "fastapi": False,
        "uvicorn": False,
        "selenium": False,
        "webdriver-manager": False,
        "requests": False,
    }
    
    # Check which packages are installed
    for package in required_packages:
        required_packages[package] = check_package_installed(package)
    
    # Install missing packages
    missing_packages = [pkg for pkg, installed in required_packages.items() if not installed]
    
    if missing_packages:
        logger.info(f"Installing missing packages: {missing_packages}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            logger.info("Successfully installed missing packages")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install packages: {str(e)}")
            return False
    else:
        logger.info("All required packages are already installed")
        return True

def start_server():
    """Start the local development server with enhanced error handling."""
    logger.info("Starting local development server...")
    
    # Make sure we're in the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(project_root, "backend")
    
    if not os.path.exists(backend_dir):
        logger.error(f"Backend directory not found at {backend_dir}")
        print(f"ERROR: Backend directory not found at {backend_dir}")
        print("Make sure you're running this script from the project root directory.")
        return False
    
    # Change to the backend directory
    os.chdir(backend_dir)
    logger.info(f"Changed to backend directory: {backend_dir}")
    
    # Build the command
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8080"]
    
    try:
        logger.info(f"Starting server with command: {' '.join(cmd)}")
        print("Starting development server...")
        print(f"Command: {' '.join(cmd)}")
        print("Note: The server will be available at http://localhost:8080")
        print("Press Ctrl+C to stop the server")
        
        # Start the server
        process = subprocess.Popen(cmd)
        
        # Wait for a bit to check if the server starts properly
        time.sleep(2)
        
        if process.poll() is not None:
            # Server stopped immediately
            logger.error(f"Server failed to start (return code: {process.returncode})")
            print(f"ERROR: Server failed to start (return code: {process.returncode})")
            return False
        
        logger.info("Server appears to be running...")
        print("\nServer is running. Check the log file for details: local_server.log")
        
        # Wait for the server to exit
        process.wait()
        
        logger.info(f"Server exited with code {process.returncode}")
        return process.returncode == 0
    
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}", exc_info=True)
        print(f"ERROR: Failed to start server: {str(e)}")
        return False

def main():
    """Main function."""
    print("=" * 50)
    print("Playlist Converter - Local Development Server")
    print("=" * 50)
    print("This script will start the local development server.")
    print("Checking required packages...")
    
    # Install required packages
    if not install_required_packages():
        print("Failed to install required packages. See log for details.")
        print("Try installing them manually:")
        print("pip install fastapi uvicorn selenium webdriver-manager requests")
        return
    
    print("All required packages are installed.")
    print("Starting the server...")
    
    # Start the server
    start_server()

if __name__ == "__main__":
    main() 