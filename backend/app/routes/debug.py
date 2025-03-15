"""Debug routes to help diagnose issues with Chrome/ChromeDriver."""

import os
import sys
import platform
from fastapi import APIRouter, HTTPException
import logging
import json
import subprocess
from typing import Dict, List, Any, Optional
import shutil

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/debug-chrome", response_model=Dict[str, Any])
async def debug_chrome_environment():
    """Provides detailed information about the Chrome/ChromeDriver environment."""
    try:
        debug_info = {
            "environment": {
                "os": platform.system(),
                "python_version": sys.version,
                "platform": platform.platform(),
                "is_heroku": 'DYNO' in os.environ
            },
            "chrome": {
                "binary_paths": []
            },
            "chromedriver": {
                "paths": []
            },
            "environment_variables": {},
            "paths": {},
            "files_found": {}
        }
        
        # Check environment variables
        chrome_vars = [
            "GOOGLE_CHROME_BIN", 
            "CHROME_EXECUTABLE_PATH", 
            "CHROMEDRIVER_PATH",
            "CHROME_PATH",
            "CHROME_BINARY"
        ]
        
        for var in chrome_vars:
            debug_info["environment_variables"][var] = os.environ.get(var, "Not set")
            
        # Check PATH
        debug_info["paths"]["PATH"] = os.environ.get("PATH", "Not available")
        
        # Check common Chrome locations
        chrome_locations = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/app/.apt/usr/bin/google-chrome",
            "/app/.apt/opt/google/chrome/chrome",
            "/app/.chrome/bin/chrome"
        ]
        
        for location in chrome_locations:
            if os.path.exists(location):
                debug_info["chrome"]["binary_paths"].append({
                    "path": location,
                    "exists": True,
                    "is_executable": os.access(location, os.X_OK),
                    "size": os.path.getsize(location) if os.path.isfile(location) else "N/A"
                })
            else:
                debug_info["chrome"]["binary_paths"].append({
                    "path": location,
                    "exists": False
                })
        
        # Check for chromedriver in standard paths
        chromedriver_locations = [
            "/usr/bin/chromedriver",
            "/usr/local/bin/chromedriver",
            "/app/.chromedriver/bin/chromedriver",
            "/app/.chrome-for-testing/chromedriver-linux64/chromedriver",
            "/app/bin/chromedriver"
        ]
        
        for location in chromedriver_locations:
            if os.path.exists(location):
                debug_info["chromedriver"]["paths"].append({
                    "path": location,
                    "exists": True,
                    "is_executable": os.access(location, os.X_OK),
                    "size": os.path.getsize(location) if os.path.isfile(location) else "N/A"
                })
            else:
                debug_info["chromedriver"]["paths"].append({
                    "path": location,
                    "exists": False
                })
        
        # If on Heroku, explore some directories
        if 'DYNO' in os.environ:
            for directory in ['/app', '/app/.apt', '/app/.chrome-for-testing']:
                if os.path.exists(directory):
                    try:
                        # Get top-level files/directories
                        contents = os.listdir(directory)
                        debug_info["files_found"][directory] = contents[:50]  # Limit to first 50 items
                    except Exception as e:
                        debug_info["files_found"][directory] = f"Error listing directory: {str(e)}"
        
        # Try to execute chrome --version
        try:
            chrome_bin = os.environ.get('GOOGLE_CHROME_BIN', 'google-chrome')
            if shutil.which(chrome_bin):
                result = subprocess.run([chrome_bin, '--version'], 
                                      capture_output=True, text=True, timeout=5)
                debug_info["chrome"]["version_cmd_result"] = {
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "returncode": result.returncode
                }
            else:
                debug_info["chrome"]["version_cmd_result"] = "Chrome binary not found in PATH"
        except Exception as e:
            debug_info["chrome"]["version_cmd_result"] = f"Error executing Chrome: {str(e)}"
        
        # Try to execute chromedriver --version
        try:
            chromedriver_bin = os.environ.get('CHROMEDRIVER_PATH', 'chromedriver')
            if shutil.which(chromedriver_bin):
                result = subprocess.run([chromedriver_bin, '--version'], 
                                      capture_output=True, text=True, timeout=5)
                debug_info["chromedriver"]["version_cmd_result"] = {
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "returncode": result.returncode
                }
            else:
                debug_info["chromedriver"]["version_cmd_result"] = "ChromeDriver not found in PATH"
        except Exception as e:
            debug_info["chromedriver"]["version_cmd_result"] = f"Error executing ChromeDriver: {str(e)}"
        
        logger.info(f"Chrome debug info: {json.dumps(debug_info, indent=2)}")
        return debug_info
    except Exception as e:
        logger.error(f"Error in debug_chrome_environment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting debug info: {str(e)}")

@router.get("/find-chromedriver")
async def find_chromedriver():
    """Attempt to locate chromedriver in the filesystem."""
    results = {
        "search_performed": False,
        "chromedriver_found": False,
        "locations": []
    }
    
    try:
        # First try which
        chromedriver_path = shutil.which("chromedriver")
        if chromedriver_path:
            results["locations"].append({
                "path": chromedriver_path,
                "method": "which",
                "exists": os.path.exists(chromedriver_path),
                "is_executable": os.access(chromedriver_path, os.X_OK) if os.path.exists(chromedriver_path) else False
            })
            results["chromedriver_found"] = True
        
        # Check in PATH locations
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for path_dir in path_dirs:
            candidate = os.path.join(path_dir, "chromedriver")
            if os.path.exists(candidate) and candidate not in [loc["path"] for loc in results["locations"]]:
                results["locations"].append({
                    "path": candidate,
                    "method": "PATH",
                    "exists": True,
                    "is_executable": os.access(candidate, os.X_OK)
                })
                results["chromedriver_found"] = True
        
        # Check common locations
        common_locations = [
            "/usr/bin/chromedriver",
            "/usr/local/bin/chromedriver",
            "/app/.chromedriver/bin/chromedriver",
            "/app/.chrome-for-testing/chromedriver-linux64/chromedriver",
            "/app/bin/chromedriver"
        ]
        
        for location in common_locations:
            if os.path.exists(location) and location not in [loc["path"] for loc in results["locations"]]:
                results["locations"].append({
                    "path": location,
                    "method": "common_location",
                    "exists": True,
                    "is_executable": os.access(location, os.X_OK)
                })
                results["chromedriver_found"] = True
        
        # If we haven't found it yet and we're on Heroku, search recursively in /app
        if not results["chromedriver_found"] and 'DYNO' in os.environ:
            results["search_performed"] = True
            search_dirs = ['/app']
            
            for root_dir in search_dirs:
                if not os.path.exists(root_dir):
                    continue
                    
                for root, dirs, files in os.walk(root_dir, topdown=True):
                    # Skip some large directories
                    dirs[:] = [d for d in dirs if d not in ['.heroku', '.cache', 'node_modules']]
                    
                    if 'chromedriver' in files:
                        driver_path = os.path.join(root, 'chromedriver')
                        results["locations"].append({
                            "path": driver_path,
                            "method": "recursive_search",
                            "exists": True,
                            "is_executable": os.access(driver_path, os.X_OK)
                        })
                        results["chromedriver_found"] = True
        
        return results
    except Exception as e:
        logger.error(f"Error in find_chromedriver: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error searching for chromedriver: {str(e)}") 