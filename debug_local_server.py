"""
Debug script to diagnose local development server issues.
This will check Python environment, required packages, and server configuration.
"""

import os
import sys
import subprocess
import importlib.util
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("debug_local.log")
    ]
)
logger = logging.getLogger("local-debug")

def check_python_version():
    """Check Python version and location."""
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Python executable: {sys.executable}")
    logger.info(f"Python path: {sys.path}")
    
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    logger.info(f"Running in virtual environment: {in_venv}")
    
    return {
        "version": sys.version,
        "executable": sys.executable,
        "in_venv": in_venv
    }

def check_package_installed(package_name):
    """Check if a package is installed."""
    spec = importlib.util.find_spec(package_name)
    is_installed = spec is not None
    
    if is_installed:
        try:
            package = importlib.import_module(package_name)
            version = getattr(package, '__version__', 'unknown')
            logger.info(f"Package {package_name} is installed (version: {version})")
            return {"installed": True, "version": version}
        except Exception as e:
            logger.warning(f"Package {package_name} is installed but failed to import: {str(e)}")
            return {"installed": True, "importable": False, "error": str(e)}
    else:
        logger.warning(f"Package {package_name} is NOT installed")
        return {"installed": False}

def check_directory_structure():
    """Check the directory structure of the application."""
    current_dir = os.getcwd()
    logger.info(f"Current working directory: {current_dir}")
    
    # Check if backend directory exists
    backend_dir = os.path.join(current_dir, 'backend')
    backend_exists = os.path.isdir(backend_dir)
    logger.info(f"Backend directory exists: {backend_exists}")
    
    # Check main.py file existence
    main_file = os.path.join(backend_dir, 'app', 'main.py')
    main_exists = os.path.isfile(main_file)
    logger.info(f"main.py file exists: {main_exists}")
    
    # List backend directory contents
    if backend_exists:
        logger.info("Backend directory contents:")
        for item in os.listdir(backend_dir):
            item_path = os.path.join(backend_dir, item)
            if os.path.isdir(item_path):
                logger.info(f" - {item}/ (directory)")
            else:
                logger.info(f" - {item} (file)")
    
    return {
        "cwd": current_dir,
        "backend_exists": backend_exists,
        "main_exists": main_exists if backend_exists else False
    }

def try_install_packages():
    """Try to install required packages."""
    logger.info("Attempting to install required packages...")
    
    packages = [
        "fastapi",
        "uvicorn",
        "selenium",
        "webdriver-manager"
    ]
    
    results = {}
    for package in packages:
        logger.info(f"Installing {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            results[package] = {"success": True}
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install {package}: {str(e)}")
            results[package] = {"success": False, "error": str(e)}
    
    return results

def try_start_server():
    """Try to start the server with detailed error reporting."""
    logger.info("Attempting to start the server...")
    
    # Change to backend directory
    try:
        os.chdir("backend")
        logger.info("Changed to backend directory")
    except Exception as e:
        logger.error(f"Failed to change to backend directory: {str(e)}")
        return {"success": False, "error": str(e)}
    
    # Try to run the server
    try:
        cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8080"]
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Run with subprocess to capture output
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for a short time to check for immediate errors
        try:
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode is not None and process.returncode != 0:
                logger.error(f"Server failed to start. Return code: {process.returncode}")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                return {
                    "success": False, 
                    "returncode": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr
                }
            else:
                logger.info("Server appears to have started successfully")
                return {"success": True}
        except subprocess.TimeoutExpired:
            # This is actually good - it means the server is running
            logger.info("Server is running (process did not exit)")
            return {"success": True, "running": True}
        
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        return {"success": False, "error": str(e)}

def main():
    """Run all diagnostics."""
    logger.info("=============== Starting Local Server Diagnostics ===============")
    
    # Check Python setup
    python_info = check_python_version()
    
    # Check required packages
    packages_info = {
        "fastapi": check_package_installed("fastapi"),
        "uvicorn": check_package_installed("uvicorn"),
        "selenium": check_package_installed("selenium"),
        "webdriver_manager": check_package_installed("webdriver_manager")
    }
    
    # Check directory structure
    dir_info = check_directory_structure()
    
    # Install missing packages if needed
    missing_packages = [pkg for pkg, info in packages_info.items() if not info.get("installed")]
    if missing_packages:
        logger.info(f"Missing packages: {missing_packages}")
        install_results = try_install_packages()
        
        # Recheck installed packages
        logger.info("Rechecking packages after installation...")
        for package in missing_packages:
            packages_info[package] = check_package_installed(package)
    
    # Try to start the server
    server_result = try_start_server()
    
    # Print summary
    logger.info("\n=============== Diagnostics Summary ===============")
    logger.info(f"Python: {python_info['version'].split()[0]} ({python_info['executable']})")
    logger.info(f"Virtual environment: {python_info['in_venv']}")
    
    logger.info("\nPackages:")
    for pkg, info in packages_info.items():
        status = "✓ Installed" if info.get("installed") else "✗ Not installed"
        version = f" (v{info.get('version')})" if info.get("installed") and info.get("version") != "unknown" else ""
        logger.info(f"  {pkg}: {status}{version}")
    
    logger.info("\nDirectory structure:")
    logger.info(f"  Backend directory: {'✓ Found' if dir_info['backend_exists'] else '✗ Not found'}")
    logger.info(f"  main.py file: {'✓ Found' if dir_info['main_exists'] else '✗ Not found'}")
    
    logger.info("\nServer start:")
    if server_result.get("success"):
        logger.info("  ✓ Server started successfully")
    else:
        logger.info(f"  ✗ Server failed to start: {server_result.get('error', 'Unknown error')}")
    
    logger.info("\n=============== Next Steps ===============")
    if not python_info['in_venv']:
        logger.info("- Consider creating and using a virtual environment")
    
    for pkg, info in packages_info.items():
        if not info.get("installed"):
            logger.info(f"- Install {pkg} with: pip install {pkg}")
    
    if not dir_info['backend_exists']:
        logger.info("- Make sure you're in the correct project directory")
    
    if not server_result.get("success"):
        logger.info("- Check the error messages above for server startup issues")
        logger.info("- Try running the uvicorn command manually with the corrected Python path")
    
    logger.info("=============== End of Diagnostics ===============")

if __name__ == "__main__":
    main() 