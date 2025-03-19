import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException
import json
import time
from urllib.parse import urlparse, parse_qs, quote
import asyncio
import aiohttp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from difflib import SequenceMatcher
import os
import traceback
from .spotify import SpotifyService
from .soundcloud import SoundCloudService
import psutil
import signal
import random

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

class BrowserInitializationError(Exception):
    """Raised when browser initialization fails after all retries."""
    pass

class ScrapingError(Exception):
    """Raised when scraping fails."""
    pass

def normalize_text(text: str) -> str:
    # ... existing code ...
    pass

class PlaylistScraper:
    """Scraper for retrieving playlist data from various music platforms."""
    
    def __init__(self):
        self.browser = None
        self.wait = None
        self._initialized = False
        self._state = {
            'last_action': 'init',
            'last_action_time': datetime.now().isoformat()
        }
        self._last_action_time = datetime.now()
        logger.debug("Initializing PlaylistScraper")

    async def initialize_browser(self):
        """Initialize browser for playlist scraping with extreme resource optimization for containerized environments."""
        if self._initialized:
            return

        try:
            # Detect if we're in a resource-constrained container environment (like Render)
            in_container = os.environ.get("RENDER", "") != "" or os.path.exists("/.dockerenv")
            logger.info(f"Environment detection: container={in_container}")
            
            # Print the Chrome version for diagnostics
            import subprocess
            try:
                chrome_version = subprocess.check_output(['google-chrome', '--version']).decode('utf-8').strip()
                logger.info(f"Chrome version: {chrome_version}")
            except Exception as e:
                logger.warning(f"Failed to get Chrome version: {str(e)}")
            
            # CRITICAL: Create a unique temporary user data directory for each Chrome instance
            import tempfile
            import uuid
            import psutil
            import signal
            import time
            
            # First, attempt to kill any existing Chrome processes - critical in container environments
            try:
                logger.info("Attempting to kill any existing Chrome processes")
                chrome_processes_killed = 0
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        # Look for any chrome-related processes
                        proc_name = proc.info['name'].lower()
                        if 'chrome' in proc_name or 'chromium' in proc_name:
                            try:
                                # Force kill the process
                                os.kill(proc.info['pid'], signal.SIGKILL)
                                chrome_processes_killed += 1
                                logger.info(f"Killed Chrome process with PID {proc.info['pid']}")
                            except Exception as kill_err:
                                logger.warning(f"Failed to kill Chrome process {proc.info['pid']}: {str(kill_err)}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                logger.info(f"Killed {chrome_processes_killed} Chrome processes")
                
                # NEW: Also forcibly kill chromedriver processes
                chromedriver_killed = 0
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        proc_name = proc.info['name'].lower()
                        if 'chromedriver' in proc_name:
                            try:
                                os.kill(proc.info['pid'], signal.SIGKILL)
                                chromedriver_killed += 1
                                logger.info(f"Killed ChromeDriver process with PID {proc.info['pid']}")
                            except Exception as kill_err:
                                logger.warning(f"Failed to kill ChromeDriver process {proc.info['pid']}: {str(kill_err)}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                logger.info(f"Killed {chromedriver_killed} ChromeDriver processes")
                
                # NEW: Clean leftover locks with system commands
                os.system("rm -f /tmp/.X*-lock")
                os.system("rm -f /tmp/.com.google.Chrome*")
                
                # NEW: Force remove all Chrome user data directories 
                import glob
                import shutil
                for chrome_dir in glob.glob("/tmp/chrome_data_*"):
                    try:
                        # First try OS-level deletion for force
                        os.system(f"rm -rf {chrome_dir}")
                        
                        # Double-check with Python's shutil
                        if os.path.exists(chrome_dir):
                            shutil.rmtree(chrome_dir, ignore_errors=True)
                            
                        logger.info(f"Forcibly removed Chrome directory: {chrome_dir}")
                    except Exception as rm_err:
                        logger.warning(f"Failed to remove directory {chrome_dir}: {str(rm_err)}")
            except Exception as proc_err:
                logger.warning(f"Error when cleaning up Chrome processes: {str(proc_err)}")
            
            # Add a random delay to allow system to clean up resources
            delay = random.uniform(0.5, 1.5)
            logger.info(f"Waiting {delay:.2f} seconds for system cleanup")
            time.sleep(delay)
            
            # NEW: Create a truly unique user data directory using process ID and timestamp
            pid = os.getpid()
            timestamp = int(time.time())
            random_id = uuid.uuid4().hex[:8]
            temp_dir = f"/tmp/chrome_tmp_{pid}_{timestamp}_{random_id}"
            
            # Ensure the directory doesn't exist
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    pass
                
            # Create fresh directory with restrictive permissions
            try:
                os.makedirs(temp_dir, mode=0o700, exist_ok=False)
                logger.info(f"Created fresh Chrome user data directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to create directory {temp_dir}: {str(e)}")
                # Fall back to RAM-based storage if we can't create the directory
                temp_dir = "/dev/shm/chrome_tmp_" + random_id
                try:
                    os.makedirs(temp_dir, mode=0o700, exist_ok=False)
                    logger.info(f"Created RAM-based Chrome user data directory: {temp_dir}")
                except Exception as e2:
                    logger.warning(f"Failed to create RAM directory: {str(e2)}")
                    # Ultimate fallback - let Chrome decide
                    temp_dir = ""
            
            # Configure Chrome options with EXTREME resource limitations for containers
            chrome_options = webdriver.ChromeOptions()
            
            # CRITICAL: Set the user data directory to our fresh directory, or bypass it completely
            if temp_dir:
                chrome_options.add_argument(f'--user-data-dir={temp_dir}')
                logger.info(f"Using custom user data directory: {temp_dir}")
            else:
                # Use a null profile directory to avoid any disk data
                chrome_options.add_argument('--incognito')
                chrome_options.add_argument('--profile-directory=Default')
                chrome_options.add_argument('--disable-infobars')
                logger.info("Using incognito mode with no user data directory")
            
            # Add flags to prevent lock file issues
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--password-store=basic')
            
            # Also disable any disk cache to prevent disk usage growth
            chrome_options.add_argument('--disk-cache-size=1')
            chrome_options.add_argument('--media-cache-size=1')
            chrome_options.add_argument('--disable-application-cache')
            
            # Always use headless mode in production environments
            chrome_options.add_argument('--headless=new')
            logger.info("Running Chrome in headless mode")
            
            # CRITICAL: Absolute minimum memory usage configuration
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # EXPERIMENTAL: Force reduced memory limits to survive in container
            chrome_options.add_argument('--disable-features=site-per-process')  # Disable site isolation
            chrome_options.add_argument('--renderer-process-limit=1')  # Only allow one renderer process
            chrome_options.add_argument('--disable-hang-monitor')  # Disable the hang monitor
            chrome_options.add_argument('--process-per-site')  # Use process-per-site instead of process-per-tab
            chrome_options.add_argument('--single-process')  # Most aggressive - force single process mode
            
            # Reduce JavaScript memory footprint drastically
            chrome_options.add_argument('--js-flags=--max-old-space-size=64')  # Limit JS heap to 64MB
            
            # Disable everything non-essential
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-component-extensions-with-background-pages')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--disable-background-networking')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--disable-translate')
            chrome_options.add_argument('--hide-scrollbars')
            chrome_options.add_argument('--mute-audio')
            chrome_options.add_argument('--blink-settings=imagesEnabled=false')
            
            # Disable storage APIs to save memory
            chrome_options.add_argument('--disable-local-storage')
            chrome_options.add_argument('--disable-session-storage')
            chrome_options.add_argument('--disable-notifications')
            
            # Prevent crash reporting and diagnostics
            chrome_options.add_argument('--disable-crash-reporter')
            chrome_options.add_argument('--disable-breakpad')  # Disable crashdump creation
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--log-level=3')  # Minimal logging
            
            # Configure prefs for minimal memory use
            chrome_options.add_experimental_option('prefs', {
                'profile.default_content_setting_values.cookies': 2,  # Block cookies
                'profile.default_content_setting_values.images': 2,  # Block images
                'profile.default_content_setting_values.popups': 2,  # Block popups
                'profile.managed_default_content_settings.javascript': 1,  # Allow JS (needed)
                'profile.default_content_setting_values.notifications': 2,  # Block notifications
                'profile.managed_default_content_settings.plugins': 2,  # Block plugins
            })
            
            # New approach: progressive browser initialization with retries
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Browser initialization attempt {attempt}/{max_retries}")
                    
                    # Create WebDriver directly using Selenium Manager (built into Selenium 4)
                    self.browser = webdriver.Chrome(options=chrome_options)
                    logger.info("Successfully initialized Chrome browser with Selenium Manager")
                    
                    # Set very aggressive timeouts for cloud environment
                    self.browser.implicitly_wait(2)  # Very short implicit wait
                    self.browser.set_page_load_timeout(20)  # Short page load timeout
                    self.browser.set_script_timeout(10)  # Short script timeout
                    
                    # Test browser with absolute minimal test
                    try:
                        # Navigate to a blank page - lowest possible resource usage
                        self.browser.get('about:blank')
                        
                        # If we get here, the browser is responsive
                        self._initialized = True
                        logger.info("Browser initialization confirmed working with minimal test")
                        return
                    except Exception as test_error:
                        logger.error(f"Browser failed initial test: {str(test_error)}")
                        # Clean up and try again with even more minimal options
                        if hasattr(self, 'browser') and self.browser:
                            try:
                                self.browser.quit()
                            except:
                                pass
                            
                            # Also try to manually clean up the Chrome user data directory
                            try:
                                import shutil
                                if os.path.exists(temp_dir):
                                    # Try force removal with system command first
                                    os.system(f"rm -rf {temp_dir}")
                                    logger.info(f"Force removed Chrome user data directory: {temp_dir}")
                                    
                                    # Then try the normal way as backup
                                    if os.path.exists(temp_dir):
                                        shutil.rmtree(temp_dir, ignore_errors=True)
                                        logger.info(f"Cleaned up Chrome user data directory: {temp_dir}")
                            except Exception as cleanup_error:
                                logger.warning(f"Failed to clean up Chrome user data directory: {str(cleanup_error)}")
                        
                        if attempt < max_retries:
                            # Wait longer between retries
                            retry_delay = random.uniform(1.0, 3.0) * attempt  # Increase delay with each retry
                            logger.info(f"Waiting {retry_delay:.2f} seconds before retry {attempt+1}/{max_retries}")
                            time.sleep(retry_delay)
                            
                            # Create a completely new temp directory for this attempt
                            pid = os.getpid()
                            timestamp = int(time.time())
                            random_id = uuid.uuid4().hex[:8]
                            new_temp_dir = f"/tmp/chrome_retry_{attempt}_{pid}_{timestamp}_{random_id}"
                            
                            try:
                                # Ensure it's empty
                                if os.path.exists(new_temp_dir):
                                    shutil.rmtree(new_temp_dir, ignore_errors=True)
                                    
                                # Create with restrictive permissions
                                os.makedirs(new_temp_dir, mode=0o700, exist_ok=False)
                                logger.info(f"Created fresh retry directory: {new_temp_dir}")
                            except Exception as e:
                                logger.warning(f"Failed to create retry directory {new_temp_dir}: {str(e)}")
                                # Use RAM-based storage as fallback
                                new_temp_dir = f"/dev/shm/chrome_retry_{attempt}_{random_id}"
                                try:
                                    os.makedirs(new_temp_dir, mode=0o700, exist_ok=False)
                                    logger.info(f"Created RAM-based retry directory: {new_temp_dir}")
                                except Exception as e2:
                                    logger.warning(f"Failed to create RAM retry directory: {str(e2)}")
                                    # Final fallback - let Chrome decide
                                    new_temp_dir = ""
                            
                            # Create a new ChromeOptions object for each retry
                            chrome_options = webdriver.ChromeOptions()
                            
                            # Make options even more minimal with each retry
                            if attempt == 1:
                                # On second attempt, use minimal options
                                chrome_options.add_argument('--headless=new')
                                chrome_options.add_argument('--no-sandbox')
                                chrome_options.add_argument('--disable-dev-shm-usage')
                                chrome_options.add_argument('--disable-gpu')
                                chrome_options.add_argument('--incognito')
                                chrome_options.add_argument('--disable-extensions')
                                chrome_options.add_argument('--disable-logging')
                                chrome_options.add_argument('--log-level=3')
                                chrome_options.add_argument('--no-first-run')
                                chrome_options.add_argument('--no-default-browser-check')
                                
                                if new_temp_dir:
                                    chrome_options.add_argument(f'--user-data-dir={new_temp_dir}')
                                    logger.info(f"Using custom retry directory: {new_temp_dir}")
                                else:
                                    logger.info("Using no user data directory for retry")
                                    
                                logger.info("Using simpler browser configuration for retry")
                            elif attempt == 2:
                                # On final attempt, try remote debugging mode - completely different approach
                                chrome_options = webdriver.ChromeOptions()
                                debug_port = random.randint(9222, 9999)
                                chrome_options.add_argument('--headless=new')
                                chrome_options.add_argument('--no-sandbox')
                                chrome_options.add_argument('--disable-dev-shm-usage')
                                chrome_options.add_argument('--disable-gpu')
                                chrome_options.add_argument('--incognito')
                                chrome_options.add_argument(f'--remote-debugging-port={debug_port}')
                                chrome_options.add_argument('--disable-extensions')
                                chrome_options.add_argument('--disable-site-isolation-trials')
                                
                                # Bypass user data directory completely
                                chrome_options.add_argument('--guest')  # Use guest mode
                                logger.info(f"Using remote debugging on port {debug_port} with guest mode for final attempt")
                            
                            # Update the temp_dir variable for cleanup
                            temp_dir = new_temp_dir
                except Exception as e:
                    logger.error(f"Browser creation error on attempt {attempt}: {str(e)}")
                    if hasattr(self, 'browser') and self.browser:
                        try:
                            self.browser.quit()
                        except:
                            pass
                    
                    if attempt == max_retries:
                        # All attempts failed
                        self._initialized = False
                        logger.error("All browser initialization attempts failed")
                        raise
        
        except Exception as e:
            logger.error(f"Browser initialization failed: {str(e)}", exc_info=True)
            self._initialized = False
            raise

    async def cleanup(self):
        """Clean up browser resources."""
        try:
            if hasattr(self, 'browser') and self.browser:
                logger.info("Cleaning up browser resources...")
                try:
                    # Close all windows
                    for handle in self.browser.window_handles:
                        self.browser.switch_to.window(handle)
                        self.browser.close()
                except Exception as e:
                    logger.warning(f"Error closing windows: {str(e)}")

                try:
                    # Quit browser
                    self.browser.quit()
                    logger.info("Browser quit successfully")
                except Exception as e:
                    logger.warning(f"Error quitting browser: {str(e)}")
                
                # Also try to find and clean up any Chrome user data directories we created
                try:
                    import shutil
                    import glob
                    
                    # Look for temp directories that match our pattern
                    temp_dirs = glob.glob("/tmp/chrome_data_*")
                    for dir_path in temp_dirs:
                        try:
                            if os.path.exists(dir_path):
                                shutil.rmtree(dir_path, ignore_errors=True)
                                logger.info(f"Cleaned up Chrome user data directory: {dir_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up Chrome user data directory {dir_path}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error during Chrome data directory cleanup: {str(e)}")

                self.browser = None
                self.wait = None
                self._initialized = False
                logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            # Don't raise the exception as this is cleanup code

    async def get_apple_music_playlist_data(self, url: str) -> Dict:
        """
        Extract playlist data from Apple Music with ultra-lightweight approach.
        
        Optimized for resource-constrained environments to prevent browser crashes.
        """
        self._log_state("start_apple_music_extraction")
        
        try:
            # Clear cookies and storage for fresh start
            self.browser.delete_all_cookies()
            self.browser.execute_script("""
                try {
                    window.localStorage.clear();
                    window.sessionStorage.clear();
                    console.log('Storage cleared');
                } catch(e) {
                    console.log('Failed to clear storage:', e);
                }
            """)
            
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Starting ultra-lightweight Apple Music data extraction for URL: {url}")
            
            # CRITICAL: Block almost all resources to minimize memory usage
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Setting up aggressive resource blocking")
            self.browser.execute_cdp_cmd('Network.setBlockedURLs', {
                'urls': [
                    '*.jpg', '*.jpeg', '*.png', '*.gif', '*.svg', 
                    '*.woff', '*.woff2', '*.ttf', '*.otf',
                    '*.css', # Block CSS to save memory (might affect page display)
                    '*.js', # Block non-essential JavaScript
                    'https://www.google-analytics.com/*',
                    'https://analytics.apple.com/*',
                    'https://metrics.apple.com/*',
                    'https://*.doubleclick.net/*',
                    'https://connect.facebook.net/*',
                    'https://*.googlesyndication.com/*',
                    'https://*.googletagmanager.com/*',
                    'https://*.googleadservices.com/*',
                    'https://*.hotjar.com/*',
                    'https://*.intercom.io/*',
                    'https://*.segment.io/*',
                    'https://cdn.optimizely.com/*'
                ]
            })
            
            # Enable cache clearing
            self.browser.execute_cdp_cmd('Network.clearBrowserCache', {})
            
            # Load the page with minimal waiting
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Loading page with minimal resources")
            self.browser.get(url)
            
            # ULTRA-LIGHTWEIGHT: Immediately abort further loading after minimal content
            self.browser.execute_script("""
                // Force end page loading to save resources
                window.stop();
                
                // Disable all animations and transitions
                document.head.insertAdjacentHTML('beforeend', 
                    '<style>* { animation: none !important; transition: none !important; }</style>'
                );
                
                // Destroy all interval and timeout based code
                for(let i = 0; i < 10000; i++) {
                    clearInterval(i);
                    clearTimeout(i);
                }
                
                // Disconnect observers if any
                if(window.MutationObserver) {
                    const observers = document.__observers || [];
                    observers.forEach(obs => {
                        try { obs.disconnect(); } catch(e) {}
                    });
                }
                
                // Kill all event listeners
                const stopPropagation = e => { 
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                };
                
                ['click', 'keydown', 'keyup', 'keypress', 'mouseover', 'mousemove', 'mousedown', 'mouseup', 'resize', 'scroll']
                .forEach(type => window.addEventListener(type, stopPropagation, true));
            """)
            
            # Wait just a tiny moment for the DOM to be accessible
            time.sleep(0.5)
            
            # Default playlist data structure with mandatory fields
            playlist_data = {
                "name": "Unknown Apple Music Playlist",
                "platform": "apple-music",
                "url": url,
                "description": "",
                "tracks": [],
                "total_tracks": 0,
                "scrape_time": datetime.now().isoformat(),
                "_extraction_method": "ultra_lightweight"
            }
            
            # IMMEDIATE EXTRACTION: Don't wait for anything to load fully
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Extracting minimal playlist data")
            
            # Get just enough information using direct JavaScript
            try:
                minimal_data = self.browser.execute_script("""
                    // Extremely simple extraction
                    function getMinimalData() {
                        // Just grab any title-looking element
                        const title = document.querySelector('h1, h2, [class*="title"]:not([class*="subtitle"])');
                        const titleText = title ? title.textContent.trim() : "Apple Music Playlist";
                        
                        // Naive track extraction
                        const tracks = [];
                        
                        // Try multiple simple track detection approaches
                        const trackElements = document.querySelectorAll('[class*="track"], [class*="song"], [role="row"], [class*="list-item"]');
                        
                        let idx = 0;
                        trackElements.forEach(el => {
                            try {
                                // Simple check if this looks like a track element
                                const text = el.textContent.trim();
                                if (!text || text.length < 3) return;
                                
                                // Skip headers
                                if (text.includes("Track") && text.includes("Time") && text.includes("Artist")) return;
                                if (text.includes("TITLE") && text.includes("ARTIST") && text.includes("ALBUM")) return;
                                
                                // Split text into segments for naive track/artist separation
                                const segments = text.split(/\\n|\\t/).map(s => s.trim()).filter(s => s.length > 1);
                                
                                if (segments.length >= 2) {
                                    const trackName = segments[0] || "Unknown Track";
                                    const artistName = segments[1] || "Unknown Artist";
                                    
                                    // Add to tracks if it seems valid
                                    if (trackName.length > 1 && artistName.length > 1) {
                                        tracks.push({
                                            name: trackName,
                                            artists: [artistName],
                                            position: idx + 1
                                        });
                                        idx++;
                                    }
                                }
                            } catch(e) {
                                // Ignore errors in track parsing
                            }
                        });
                        
                        return {
                            title: titleText,
                            tracks: tracks
                        };
                    }
                    
                    return getMinimalData();
                """)
                
                if minimal_data and minimal_data.get("tracks") and len(minimal_data["tracks"]) > 0:
                    playlist_data["name"] = minimal_data.get("title", "Apple Music Playlist")
                    playlist_data["tracks"] = minimal_data["tracks"]
                    playlist_data["total_tracks"] = len(minimal_data["tracks"])
                    logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Successfully extracted {len(minimal_data['tracks'])} tracks")
                else:
                    # One more fallback - try super simple track extraction if the above didn't work
                    logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Using emergency fallback extraction")
                    
                    fallback_tracks = self.browser.execute_script("""
                        // Emergency text-based extraction
                        const allLinks = Array.from(document.querySelectorAll('a'));
                        const tracks = [];
                        
                        // Find song title patterns
                        allLinks.forEach((link, idx) => {
                            const text = link.textContent.trim();
                            // Skip empty links
                            if (text.length < 2) return; 
                            
                            // Skip navigation links
                            if (["home", "browse", "radio", "search", "sign in", "sign out", "account"].includes(text.toLowerCase())) return;
                            
                            // If it's a link that doesn't look like navigation, it might be a track
                            const nextEl = link.nextElementSibling;
                            const prevEl = link.previousElementSibling;
                            
                            // Try to get artist from sibling element
                            let artistName = "Unknown Artist";
                            if (nextEl && nextEl.textContent.trim().length > 1) {
                                artistName = nextEl.textContent.trim();
                            } else if (prevEl && prevEl.textContent.trim().length > 1) {
                                artistName = prevEl.textContent.trim();
                            }
                            
                            tracks.push({
                                name: text,
                                artists: [artistName],
                                position: idx + 1
                            });
                        });
                        
                        return tracks.slice(0, 50); // Limit to 50 tracks
                    """)
                    
                    if fallback_tracks and len(fallback_tracks) > 0:
                        # Filter out obvious non-tracks
                        filtered_tracks = [
                            t for t in fallback_tracks 
                            if len(t["name"]) > 1 and t["name"].lower() not in [
                                "apple music", "playlist", "add", "remove", "more", "play", "next", "previous"
                            ]
                        ]
                        
                        playlist_data["tracks"] = filtered_tracks
                        playlist_data["total_tracks"] = len(filtered_tracks)
                        logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Emergency extraction found {len(filtered_tracks)} tracks")
            except Exception as e:
                logger.error(f"JavaScript extraction failed: {str(e)}")
                # We'll continue and return what we have even if extraction failed
            
            # Final outcome
            if playlist_data["tracks"] and len(playlist_data["tracks"]) > 0:
                logger.info(f"Successfully extracted {len(playlist_data['tracks'])} tracks from Apple Music playlist")
                self._log_state("apple_music_extraction_success")
                return playlist_data
            else:
                logger.error("Failed to extract any tracks from Apple Music playlist")
                self._log_state("apple_music_extraction_failure")
                
                # Fallback to minimal data rather than raising an exception
                # Add at least one dummy track so the UI doesn't completely break
                playlist_data["tracks"] = [
                    {
                        "name": "Error extracting track list",
                        "artists": ["Please try again or use a different playlist"],
                        "position": 1
                    }
                ]
                playlist_data["total_tracks"] = 1
                return playlist_data
                
        except Exception as e:
            self._log_state("apple_music_extraction_error", e)
            logger.error(f"Error extracting Apple Music playlist: {str(e)}", exc_info=True)
            
            # Create a minimal response instead of raising an exception
            return {
                "name": "Error - Apple Music Playlist",
                "platform": "apple-music",
                "url": url,
                "description": f"Error: {str(e)}",
                "tracks": [
                    {
                        "name": "Browser error occurred",
                        "artists": ["Please try again or use a different playlist URL"],
                        "position": 1
                    }
                ],
                "total_tracks": 1,
                "scrape_time": datetime.now().isoformat(),
                "_extraction_method": "error_recovery"
            }

    def _log_state(self, action: str, error: Exception = None):
        """Log current state of the scraper."""
        now = datetime.now()
        state_info = {
            'timestamp': now.isoformat(),
            'action': action,
            'browser_initialized': self._initialized,
            'browser_exists': hasattr(self, 'browser') and self.browser is not None,
            'wait_exists': hasattr(self, 'wait') and self.wait is not None,
            'error_count': 0
        }
        
        if error:
            state_info['error_type'] = type(error).__name__
            state_info['error_message'] = str(error)
            logger.error(f"Error in {action}. Current state:", extra={'state': state_info})
        else:
            logger.debug(f"State after {action}:", extra={'state': state_info})
        
        self._state['last_action'] = action
        self._last_action_time = now

    def _init_services(self):
        """Initialize service clients."""
        try:
            self.spotify = SpotifyService()
            logger.info("Spotify service initialized")
        except Exception as e:
            logger.error("Failed to initialize Spotify service", exc_info=e)
            self.spotify = None
            self._log_state('spotify_init_failed', e)

        try:
            self.soundcloud = SoundCloudService()
            logger.info("SoundCloud service initialized")
        except Exception as e:
            logger.error("Failed to initialize SoundCloud service", exc_info=e)
            self.soundcloud = None
            self._log_state('soundcloud_init_failed', e)
            
        self._log_state('services_init_complete')

    def _verify_browser_state(self):
        """Verify browser is in a valid state."""
        try:
            if not self.browser:
                raise BrowserInitializationError("Browser instance does not exist")
            
            # Try to execute a simple command to verify browser is responsive
            self.browser.current_url
            return True
        except Exception as e:
            self._log_state('browser_state_verification_failed', e)
            return False

    def _init_browser(self) -> None:
        """Initialize the Chrome browser with custom options."""
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-automation')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Disable notifications and images, enable JavaScript
            chrome_options.add_experimental_option('prefs', {
                'profile.default_content_setting_values.notifications': 2,
                'profile.managed_default_content_settings.images': 2,
                'profile.managed_default_content_settings.javascript': 1
            })
            
            # Disable automation flags
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.browser = webdriver.Chrome(options=chrome_options)
            self.browser.implicitly_wait(10)  # seconds
            
            # Verify browser is responsive
            self.browser.get('about:blank')
            self.browser.current_url  # This will raise an exception if browser is not responsive
            
            logging.info("Browser initialized successfully")
            self._initialized = True
            
        except Exception as e:
            logging.error(f"Failed to initialize browser: {str(e)}")
            if hasattr(self, 'browser') and self.browser:
                self.browser.quit()
            self.browser = None
            self._initialized = False
            raise

    def _cleanup_browser(self):
        """Clean up browser resources safely."""
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.quit()
            self._initialized = False
            logger.debug("Browser cleaned up successfully")
            self._log_state('browser_cleanup_complete')
        except Exception as e:
            logger.error(f"Error during browser cleanup: {str(e)}", exc_info=True)
            self._log_state('browser_cleanup_failed', e)

    async def _extract_track_data(self, track_element, idx):
        """Extract track data with improved selectors and JavaScript fallback."""
        try:
            # Try to extract track name using multiple methods
            name_selectors = [
                "div[class*='song-name']",
                "div[class*='track-name']",
                "div[class*='title']",
                ".//div[contains(@class, 'song-name')]",
                ".//div[contains(@class, 'track-name')]",
                ".//div[contains(@class, 'title')]"
            ]
            
            track_name = None
            for selector in name_selectors:
                try:
                    if selector.startswith(".//"):
                        element = track_element.find_element(By.XPATH, selector)
                    else:
                        element = track_element.find_element(By.CSS_SELECTOR, selector)
                    track_name = element.text.strip()
                    if track_name:
                        break
                except:
                    continue
            
            if not track_name:
                # Try JavaScript
                track_name = self.browser.execute_script("""
                    const el = arguments[0];
                    return el.querySelector('[class*="song-name"], [class*="track-name"], [class*="title"]')?.textContent?.trim();
                """, track_element)
            
            if not track_name:
                return None
            
            # Extract artists with similar approach
            artist_selectors = [
                "div[class*='artist']",
                "div[class*='by-line']",
                "div[class*='subtitle']",
                ".//div[contains(@class, 'artist')]",
                ".//div[contains(@class, 'by-line')]",
                ".//div[contains(@class, 'subtitle')]"
            ]
            
            artist_text = None
            for selector in artist_selectors:
                try:
                    if selector.startswith(".//"):
                        element = track_element.find_element(By.XPATH, selector)
                    else:
                        element = track_element.find_element(By.CSS_SELECTOR, selector)
                    artist_text = element.text.strip()
                    if artist_text:
                        break
                except:
                    continue
            
            if not artist_text:
                # Try JavaScript
                artist_text = self.browser.execute_script("""
                    const el = arguments[0];
                    return el.querySelector('[class*="artist"], [class*="by-line"], [class*="subtitle"]')?.textContent?.trim();
                """, track_element)
            
            if not artist_text:
                return None
            
            # Clean up artist text
            artist_text = re.sub(r'^by\s+', '', artist_text, flags=re.IGNORECASE)
            artists = []
            
            # Split on common separators
            for artist in re.split(r'[,&]|\bfeat\.|\bft\.|\band\b|\bx\b|\bvs\.?|\bwith\b', artist_text):
                artist = artist.strip()
                if artist and not any(word in artist.lower() for word in ['feat.', 'ft.', 'featuring']):
                    artists.append(artist)
            
            if not artists:
                return None
            
            return {
                "name": track_name,
                "artists": artists,
                "position": idx
            }
            
        except Exception as e:
            logger.warning(f"Error extracting track {idx}: {str(e)}")
            return None

    def detect_platform(self, url: str) -> str:
        """Detect the platform from the URL."""
        if "music.apple.com" in url:
            return "apple-music"
        elif "spotify.com" in url:
            return "spotify"
        else:
            raise ValueError("Unsupported platform. Only Apple Music and Spotify are supported.")

    async def get_playlist_data(self, playlist_url: str) -> Dict:
        """Get playlist data from the appropriate platform with crash protection."""
        platform = self.detect_platform(playlist_url)
        search_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TRACE][{search_id}] Starting playlist data extraction from {platform} for URL: {playlist_url}")
        
        # Initialize browser if not already done
        if not self._initialized:
            try:
                await self.initialize_browser()
            except Exception as e:
                logger.error(f"[ERROR][{search_id}] Failed to initialize browser: {str(e)}")
                # Return minimal error data instead of raising
                return {
                    "platform": platform,
                    "url": playlist_url,
                    "name": f"Error - {platform.capitalize()} Playlist",
                    "tracks": [
                        {
                            "name": "Browser initialization failed",
                            "artists": ["Please try again in a few minutes"],
                            "position": 1
                        }
                    ],
                    "total_tracks": 1
                }
        
        # Define max retries and backoff strategy
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[TRACE][{search_id}] Attempt {attempt}/{max_retries} to fetch playlist data")
                
                # Clear browser state
                try:
                    self.browser.delete_all_cookies()
                except Exception as e:
                    logger.warning(f"[WARN][{search_id}] Failed to clear cookies: {str(e)}")
                
                # Try to clear cache and storage
                try:
                    self.browser.execute_script("""
                        try {
                            window.localStorage.clear();
                            window.sessionStorage.clear();
                            console.log('Storage cleared');
                        } catch(e) {
                            console.log('Failed to clear storage:', e);
                        }
                    """)
                except Exception as e:
                    logger.warning(f"[WARN][{search_id}] Failed to clear storage: {str(e)}")
                
                # Verify browser is still responsive
                try:
                    # Quick check if browser is still alive
                    self.browser.current_url
                except Exception as e:
                    logger.error(f"[ERROR][{search_id}] Browser appears to be unresponsive: {str(e)}")
                    # Close the browser and reinitialize
                    await self.cleanup()
                    await self.initialize_browser()
                
                # Fetch based on platform with timeout handling
                if platform == "apple-music":
                    result = await self.get_apple_music_playlist_data(playlist_url)
                    return result
                elif platform == "spotify":
                    result = await self.get_spotify_playlist_data(playlist_url)
                    return result
                else:
                    # Don't raise an error, return a helpful error message
                    return {
                        "platform": "unknown",
                        "url": playlist_url,
                        "name": "Unsupported Platform",
                        "tracks": [
                            {
                                "name": f"Platform '{platform}' is not supported",
                                "artists": ["Please try a Spotify or Apple Music playlist"],
                                "position": 1
                            }
                        ],
                        "total_tracks": 1
                    }
                
            except Exception as e:
                logger.error(f"[ERROR][{search_id}] Error on attempt {attempt}/{max_retries}: {str(e)}")
                
                # Try to take a screenshot for debugging
                try:
                    screenshot_path = f"error_{search_id}_attempt{attempt}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[TRACE][{search_id}] Saved error screenshot to {screenshot_path}")
                except Exception as screenshot_e:
                    logger.warning(f"[WARN][{search_id}] Failed to save error screenshot: {str(screenshot_e)}")
                
                # Check if browser crashed
                is_crash = False
                if "tab crashed" in str(e).lower() or "session deleted" in str(e).lower() or "disconnected" in str(e).lower():
                    is_crash = True
                    logger.error(f"[ERROR][{search_id}] Browser crash detected: {str(e)}")
                
                if attempt == max_retries:
                    logger.error(f"[ERROR][{search_id}] All attempts failed")
                    
                    # Return minimal data instead of raising
                    return {
                        "platform": platform,
                        "url": playlist_url,
                        "name": f"Error - {platform.capitalize()} Playlist",
                        "tracks": [
                            {
                                "name": "Failed to fetch playlist data",
                                "artists": [f"Error: {str(e)[:100]}..."],
                                "position": 1
                            }
                        ],
                        "total_tracks": 1
                    }
                
                # For crashes, do a full browser restart
                if is_crash:
                    logger.info(f"[TRACE][{search_id}] Restarting browser after crash")
                    await self.cleanup()
                    await asyncio.sleep(retry_delay * attempt)
                    await self.initialize_browser()
                else:
                    # For other errors, just wait and retry
                    await asyncio.sleep(retry_delay * attempt)
        
        # This should never be reached due to the return in the last retry
        return {
            "platform": platform,
            "url": playlist_url,
            "name": "Error - Unknown Issue",
            "tracks": [],
            "total_tracks": 0
        }

    def _serialize_datetime(self, obj):
        """Helper method to serialize datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    def _create_scraping_stats(self, request_id: str, url: str) -> Dict:
        """Create initial scraping statistics with proper datetime handling."""
        return {
            'request_id': request_id,
            'url': url,
            'start_time': self._serialize_datetime(datetime.now()),
            'page_load_success': False,
            'content_load_success': False,
            'track_extraction_success': False,
            'total_tracks_found': 0,
            'actual_playlist_tracks': 0,
            'errors': [],
            'dom_state': {},
            'selectors_found': {},
            'performance_metrics': {
                'page_load_duration': None,
                'content_load_duration': None,
                'extraction_duration': None
            }
        }

    async def get_spotify_playlist_data(self, url: str) -> Dict:
        """Extract playlist data from Spotify with optimizations to prevent timeouts."""
        search_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TRACE][{search_id}] Starting optimized Spotify playlist data extraction for URL: {url}")
        
        # Initialize browser if not already done
        if not self.browser:
            await self.initialize_browser()
            
        # Use a simplified approach to load the playlist page
        try:
            logger.info(f"[TRACE][{search_id}] Loading playlist page with optimized settings")
            
            # Set blocked resources to reduce load time
            self.browser.execute_cdp_cmd('Network.setBlockedURLs', {
                'urls': [
                    '*.jpg', '*.jpeg', '*.png', '*.gif', '*.svg',  # Block images
                    '*.css',  # Block CSS - careful with this one, might break page structure
                    '*.woff', '*.woff2', '*.ttf', '*.otf',  # Block fonts
                    'https://www.google-analytics.com/*',  # Block analytics
                    'https://analytics.spotify.com/*',  # Block Spotify analytics
                    'https://log.spotify.com/*',  # Block Spotify logging
                    'https://ads.spotify.com/*',  # Block Spotify ads
                    'https://connect.facebook.net/*',  # Block Facebook
                    '*.hotjar.com/*',  # Block Hotjar
                ]
            })
            
            # Load the playlist page with timeout handling
            self.browser.get(url)
            
            # Wait a moment for page to start loading
            await asyncio.sleep(1)
            
            # Reduce page processing by stopping animations and heavy rendering
            self.browser.execute_script("""
                // Stop animations and timers to reduce CPU usage
                window.addEventListener('load', function() {
                    const highPriorityOnly = function() {
                        // Stop all animations
                        for (let i = 0; i < 9999; i++) {
                            window.clearInterval(i);
                        }
                        // Stop all timeouts
                        for (let i = 0; i < 9999; i++) {
                            window.clearTimeout(i);
                        }
                    };
                    setTimeout(highPriorityOnly, 2000);
                });
                console.log('Stopped animations and timers');
            """)
            
            # Wait for essential playlist content to load with a more direct approach
            logger.info(f"[TRACE][{search_id}] Waiting for essential playlist content")
            
            # Wait for any of these elements to appear, which would indicate the playlist loaded
            selectors = [
                'div[data-testid="playlist-tracklist"]',
                'div.tracklist-container',
                'div[data-testid="track-list"]',
                'section[data-testid="playlist-page"]',
                'div[data-testid="tracklist-row"]'
            ]
            
            selector_found = False
            for selector in selectors:
                try:
                    # Use a shorter timeout for each individual selector
                    WebDriverWait(self.browser, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[TRACE][{search_id}] Found playlist content with selector: {selector}")
                    selector_found = True
                    break
                except TimeoutException:
                    continue
            
            if not selector_found:
                # Try one more time with a longer timeout on the most reliable selector
                try:
                    WebDriverWait(self.browser, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="playlist-tracklist"]'))
                    )
                    selector_found = True
                    logger.info(f"[TRACE][{search_id}] Found playlist content with extended timeout")
                except TimeoutException:
                    logger.warning(f"[WARN][{search_id}] Could not find any playlist content selectors")
                    # Continue anyway, we might still extract data
            
            # Scroll just once to load more tracks without excessive scrolling
            self.browser.execute_script("window.scrollTo(0, 500);")
            await asyncio.sleep(1)
            
            # Simplified JavaScript extraction that's less resource-intensive
            logger.info(f"[TRACE][{search_id}] Extracting playlist data with optimized script")
            
            playlist_data = self.browser.execute_script("""
                function getPlaylistData() {
                    // Define result object with placeholders
                    const data = {
                        name: document.title || 'Spotify Playlist',
                        tracks: [],
                        url: window.location.href,
                        platform: 'Spotify'
                    };
                    
                    // Get playlist name with minimum selectors
                    try {
                        const titleElement = document.querySelector('h1');
                        if (titleElement) {
                            data.name = titleElement.textContent.trim();
                        }
                    } catch (e) {
                        console.error('Error getting playlist title:', e);
                    }
                    
                    // Find the main container with minimum queries
                    let trackElements = [];
                    const containers = [
                        document.querySelector('div[data-testid="playlist-tracklist"]'),
                        document.querySelector('div.tracklist-container'),
                        document.querySelector('section[data-testid="playlist-tracklist"]')
                    ];
                    
                    let container = null;
                    for (const c of containers) {
                        if (c) {
                            container = c;
                            break;
                        }
                    }
                    
                    if (container) {
                        // Try multiple selectors but with minimal DOM traversal
                        const selectors = [
                            'div[data-testid="tracklist-row"]',
                            'div[role="row"]',
                            'div[draggable="true"]'
                        ];
                        
                        for (const selector of selectors) {
                            const elements = container.querySelectorAll(selector);
                            if (elements && elements.length > 0) {
                                trackElements = Array.from(elements);
                                break;
                            }
                        }
                    } else {
                        // Fallback: look for any track-like elements
                        trackElements = Array.from(document.querySelectorAll('div[data-testid="tracklist-row"], div[role="row"]'));
                    }
                    
                    // Process track elements with minimal DOM queries
                    trackElements.forEach((track, index) => {
                        try {
                            // Extract track name and artist with minimal queries
                            const trackName = track.querySelector('a[data-testid="internal-track-link"]')?.textContent.trim() ||
                                              track.querySelector('a[aria-label*="play"]')?.textContent.trim() ||
                                              '';
                                              
                            // Skip if no track name (likely a header)
                            if (!trackName || trackName === 'Title' || trackName === '#') {
                                return;
                            }
                            
                            // Get artist with minimal DOM traversal
                            const artistElement = track.querySelector('a[href*="artist"]') ||
                                                track.querySelector('span a');
                            
                            const artistName = artistElement ? artistElement.textContent.trim() : 'Unknown Artist';
                            
                            // Add track with minimal data
                            data.tracks.push({
                                name: trackName,
                                artists: [artistName],
                                position: index + 1
                            });
                        } catch (e) {
                            console.error('Error processing track:', e);
                        }
                    });
                    
                    return data;
                }
                return getPlaylistData();
            """)
            
            # Validate and clean the data
            if not playlist_data or not playlist_data.get('tracks'):
                logger.warning(f"[WARN][{search_id}] No tracks found in playlist data")
                # Try to get a screenshot for debugging
                try:
                    screenshot_path = f"empty_playlist_{search_id}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[TRACE][{search_id}] Saved empty playlist screenshot to {screenshot_path}")
                except Exception as e:
                    logger.warning(f"[WARN][{search_id}] Failed to save screenshot: {str(e)}")
                    
                # Return minimal data
                return {
                    "platform": "spotify",
                    "url": url,
                    "name": "Spotify Playlist",
                    "tracks": []
                }
            
            # Return the playlist data
            logger.info(f"[TRACE][{search_id}] Successfully extracted {len(playlist_data.get('tracks', []))} tracks from Spotify playlist")
            return {
                "platform": "spotify",
                "url": url,
                "name": playlist_data.get('name', 'Spotify Playlist'),
                "tracks": playlist_data.get('tracks', [])
            }
            
        except Exception as e:
            logger.error(f"[ERROR][{search_id}] Error extracting Spotify playlist data: {str(e)}")
            raise Exception(f"Failed to extract Spotify playlist data: {str(e)}") 