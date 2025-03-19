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
        """Initialize browser for playlist scraping."""
        if self._initialized:
            return

        try:
            # Print the Chrome version for diagnostics
            import subprocess
            try:
                chrome_version = subprocess.check_output(['google-chrome', '--version']).decode('utf-8').strip()
                logger.info(f"Chrome version: {chrome_version}")
            except Exception as e:
                logger.warning(f"Failed to get Chrome version: {str(e)}")
            
            # Configure Chrome options
            chrome_options = webdriver.ChromeOptions()
            
            # Check if headless mode is enabled via environment variable
            headless = os.environ.get("SELENIUM_HEADLESS", "true").lower() == "true"
            if headless:
                chrome_options.add_argument('--headless=new')
                logger.info("Running Chrome in headless mode")
            
            # Essential minimal arguments only
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            
            # CRITICAL FIX: Skip webdriver-manager and use selenium-manager directly
            # This avoids the THIRD_PARTY_NOTICES file issue with webdriver-manager
            logger.info("Using Selenium Manager to find correct ChromeDriver...")
            
            # Create WebDriver directly using Selenium Manager (built into Selenium 4)
            self.browser = webdriver.Chrome(options=chrome_options)
            logger.info("Successfully initialized Chrome browser with Selenium Manager")
            
            # Set basic timeouts - increased for better reliability
            self.browser.implicitly_wait(10)
            self.browser.set_page_load_timeout(90)  # Increased from 30 to handle slow Apple Music pages
            self.browser.set_script_timeout(45)     # Increased from 30 for better script execution
            
            logger.info("Playlist scraper browser initialized successfully")
            self._initialized = True
            
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

                self.browser = None
                self.wait = None
                self._initialized = False
                logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            # Don't raise the exception as this is cleanup code

    async def get_apple_music_playlist_data(self, url: str) -> Dict:
        """
        Extract playlist data from Apple Music with optimized performance.
        
        Uses progressive loading and partial data retrieval to handle slow connections.
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
            
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Starting optimized Apple Music playlist data extraction for URL: {url}")
            
            # PERFORMANCE: Block unnecessary resources like images
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Loading playlist page with optimized settings")
            self.browser.execute_cdp_cmd('Network.setBlockedURLs', {
                'urls': [
                    '*.jpg', '*.jpeg', '*.png', '*.gif', '*.svg', 
                    '*.woff', '*.woff2', '*.ttf', '*.otf',
                    'https://www.google-analytics.com/*',
                    'https://analytics.apple.com/*',
                    'https://metrics.apple.com/*',
                    'https://*.doubleclick.net/*',
                    'https://connect.facebook.net/*'
                ]
            })
            
            # Load the page
            self.browser.get(url)
            
            # PERFORMANCE: Stop animations and resource-intensive scripts
            self.browser.execute_script("""
                // Force end page loading 
                window.stop();
                
                // Disable costly animations
                (function() {
                  var style = document.createElement('style');
                  style.type = 'text/css';
                  style.innerHTML = '* { animation-play-state: paused !important; transition: none !important; }';
                  document.head.appendChild(style);
                })();
            """)
            
            # Begin extraction immediately with aggressive timeouts
            logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Starting progressive data extraction")
            
            # Default playlist data structure with mandatory fields
            playlist_data = {
                "name": "Unknown Playlist",
                "platform": "apple-music",
                "url": url,
                "description": "",
                "tracks": [],
                "total_tracks": 0,
                "scrape_time": datetime.now().isoformat(),
                "_extraction_method": "progressive"
            }
            
            # Try to get playlist title (non-blocking, quick attempt)
            try:
                title_selectors = [
                    "h1.product-name", 
                    "div.product-title", 
                    "div.album-title"
                ]
                
                for selector in title_selectors:
                    try:
                        title_element = self.browser.find_element(By.CSS_SELECTOR, selector)
                        if title_element:
                            playlist_data["name"] = title_element.text.strip()
                            break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"Failed to get playlist title: {str(e)}")
            
            # Try to get track list with multiple selectors (partial data is better than nothing)
            all_tracks = []
            
            # Try multiple selectors that might match track elements
            track_selectors = [
                "div.songs-list div.song",
                "div.songs-list-container div.songs-list-row",
                "div.track-list div.track",
                "div.tracklist div.tracklist-item",
                "div.track-list-container table tr.track-list-row"
            ]
            
            # CRITICAL: Start with a very quick scan of page content to avoid timeout
            # We'll immediately grab any visible content, even if page isn't fully loaded
            for selector in track_selectors:
                try:
                    # Use a very short explicit wait - 2 seconds max for initial data scan
                    start_time = time.time()
                    track_elements = WebDriverWait(self.browser, 2).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                    )
                    
                    logger.info(f"[TRACE][{datetime.now().strftime('%Y%m%d_%H%M%S')}] Found {len(track_elements)} tracks with selector: {selector}")
                    
                    if track_elements:
                        logger.info(f"Found tracks with selector: {selector}")
                        # Extract track data with short timeouts per track
                        for i, track_element in enumerate(track_elements[:50]):  # Process at most 50 tracks to avoid timeout
                            try:
                                track_data = await self._extract_track_data(track_element, i)
                                if track_data and track_data.get("name"):
                                    all_tracks.append(track_data)
                            except Exception as e:
                                logger.warning(f"Error extracting track {i}: {str(e)}")
                                continue
                                
                        # If we found some tracks, we'll consider this a success
                        if all_tracks:
                            playlist_data["tracks"] = all_tracks
                            playlist_data["total_tracks"] = len(all_tracks)
                            break
                except Exception as e:
                    logger.warning(f"Selector {selector} failed: {str(e)}")
                    continue
            
            # If we still don't have tracks, try a more aggressive approach with JavaScript
            if not all_tracks:
                logger.info("Attempting JavaScript extraction fallback")
                try:
                    # Extract data using JavaScript
                    track_data_js = self.browser.execute_script("""
                        // Direct DOM traversal to find track data
                        const tracks = [];
                        
                        // Find all possible track containers
                        const trackElements = document.querySelectorAll('[class*="song"], [class*="track"], [class*="list-item"]');
                        
                        Array.from(trackElements).forEach((elem, index) => {
                            // Check if this element looks like a track
                            const hasTitle = elem.querySelector('[class*="title"], [class*="name"]');
                            const hasArtist = elem.querySelector('[class*="artist"], [class*="subtitle"]');
                            
                            if (hasTitle) {
                                const title = hasTitle.textContent.trim();
                                const artist = hasArtist ? hasArtist.textContent.trim() : "Unknown Artist";
                                
                                if (title && artist && title.length > 0) {
                                    tracks.push({
                                        name: title,
                                        artists: [artist],
                                        album: "",
                                        index: index
                                    });
                                }
                            }
                        });
                        
                        // Get the playlist title
                        let playlistTitle = "Unknown Playlist";
                        const titleElem = document.querySelector('h1, [class*="title"]:not([class*="track"]):not([class*="song"])');
                        if (titleElem) {
                            playlistTitle = titleElem.textContent.trim();
                        }
                        
                        return {
                            tracks: tracks,
                            title: playlistTitle
                        };
                    """)
                    
                    if track_data_js and "tracks" in track_data_js:
                        js_tracks = track_data_js.get("tracks", [])
                        if js_tracks:
                            all_tracks = js_tracks
                            playlist_data["tracks"] = all_tracks
                            playlist_data["total_tracks"] = len(all_tracks)
                            
                            # Update title if we got one
                            if track_data_js.get("title") and track_data_js.get("title") != "Unknown Playlist":
                                playlist_data["name"] = track_data_js.get("title")
                            
                            logger.info(f"Extracted {len(all_tracks)} tracks using JavaScript fallback")
                except Exception as e:
                    logger.error(f"JavaScript extraction failed: {str(e)}")
            
            # Final outcome
            if all_tracks:
                logger.info(f"Successfully extracted {len(all_tracks)} tracks from Apple Music playlist")
                self._log_state("apple_music_extraction_success")
                return playlist_data
            else:
                logger.error("Failed to extract any tracks from Apple Music playlist")
                self._log_state("apple_music_extraction_failure")
                raise ScrapingError("No tracks found in Apple Music playlist")
                
        except Exception as e:
            self._log_state("apple_music_extraction_error", e)
            logger.error(f"Error extracting Apple Music playlist: {str(e)}", exc_info=True)
            raise

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
        """Get playlist data from the appropriate platform with improved reliability."""
        platform = self.detect_platform(playlist_url)
        search_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TRACE][{search_id}] Starting playlist data extraction from {platform} for URL: {playlist_url}")
        
        # Initialize browser if not already done
        if not self._initialized:
            try:
                await self.initialize_browser()
            except Exception as e:
                logger.error(f"[ERROR][{search_id}] Failed to initialize browser: {str(e)}")
                raise BrowserInitializationError(f"Failed to initialize browser: {str(e)}")
        
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
                
                # Fetch based on platform with timeout handling
                if platform == "apple-music":
                    result = await self.get_apple_music_playlist_data(playlist_url)
                    return result
                elif platform == "spotify":
                    result = await self.get_spotify_playlist_data(playlist_url)
                    return result
                else:
                    raise ValueError(f"Unsupported platform: {platform}")
                
            except TimeoutException as e:
                logger.error(f"[ERROR][{search_id}] Timeout on attempt {attempt}/{max_retries}: {str(e)}")
                
                # Try to take a screenshot for debugging
                try:
                    screenshot_path = f"timeout_error_{search_id}_attempt{attempt}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[TRACE][{search_id}] Saved timeout screenshot to {screenshot_path}")
                except Exception as screenshot_e:
                    logger.warning(f"[WARN][{search_id}] Failed to save timeout screenshot: {str(screenshot_e)}")
                
                if attempt == max_retries:
                    logger.error(f"[ERROR][{search_id}] All attempts failed due to timeout")
                    raise Exception(f"Failed to fetch playlist data: {str(e)}")
                
                # Restart browser before next attempt to clear any issues
                logger.info(f"[TRACE][{search_id}] Restarting browser after timeout")
                await self.cleanup()
                await asyncio.sleep(retry_delay * attempt)  # Increasing delay between retries
                await self.initialize_browser()
                
            except Exception as e:
                logger.error(f"[ERROR][{search_id}] Error on attempt {attempt}/{max_retries}: {str(e)}")
                
                # Try to take a screenshot for debugging
                try:
                    screenshot_path = f"error_{search_id}_attempt{attempt}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[TRACE][{search_id}] Saved error screenshot to {screenshot_path}")
                except Exception as screenshot_e:
                    logger.warning(f"[WARN][{search_id}] Failed to save error screenshot: {str(screenshot_e)}")
                
                if attempt == max_retries:
                    logger.error(f"[ERROR][{search_id}] All attempts failed")
                    raise Exception(f"Failed to fetch playlist data: {str(e)}")
                
                await asyncio.sleep(retry_delay * attempt)  # Increasing delay between retries
        
        raise Exception(f"Failed to fetch playlist data from {platform}: Max retries exceeded")

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