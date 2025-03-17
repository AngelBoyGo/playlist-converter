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
        logger.debug("Initializing PlaylistScraper")

    async def initialize_browser(self):
        """Initialize the browser with proper async handling."""
        if self._initialized:
            return

        try:
            chrome_options = webdriver.ChromeOptions()
            
            # Essential Chrome options for scraping
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Additional options for better scraping
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--lang=en-US,en')
            chrome_options.add_argument('--remote-debugging-port=9222')
            
            # Set preferences
            chrome_options.add_experimental_option('prefs', {
                'profile.default_content_settings.images': 2,  # Disable images
                'profile.default_content_setting_values.javascript': 1,  # Enable JavaScript
                'profile.default_content_setting_values.cookies': 1,  # Enable cookies
                'profile.default_content_setting_values.plugins': 1,  # Enable plugins
                'profile.default_content_setting_values.popups': 2,  # Disable popups
                'profile.default_content_setting_values.geolocation': 2,  # Disable geolocation
                'profile.default_content_setting_values.notifications': 2  # Disable notifications
            })
            
            # Set a realistic user agent
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Disable automation flags
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            logger.info("Creating Chrome browser instance...")
            self.browser = webdriver.Chrome(options=chrome_options)
            
            # Set page load timeout and wait time
            self.browser.set_page_load_timeout(30)
            self.wait = WebDriverWait(self.browser, 20)
            
            # Execute CDP commands to enable network conditions and set headers
            logger.info("Configuring CDP commands...")
            self.browser.execute_cdp_cmd('Network.enable', {})
            self.browser.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            self.browser.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                "headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
            })
            
            self._initialized = True
            logger.info("Browser initialized successfully for scraper with enhanced settings")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            if hasattr(self, 'browser') and self.browser:
                try:
                    self.browser.quit()
                except:
                    pass
            raise BrowserInitializationError(f"Failed to initialize browser: {str(e)}")

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

    async def get_apple_music_playlist_data(self, playlist_url: str) -> Dict:
        """Get playlist data from Apple Music."""
        if not self._initialized:
            await self.initialize_browser()

        try:
            logger.info(f"Fetching Apple Music playlist: {playlist_url}")
            
            # Navigate to the playlist URL with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.browser.get(playlist_url)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Navigation attempt {attempt + 1} failed: {str(e)}")
                    await asyncio.sleep(2)
            
            # Wait for the main content containers with updated selectors
            selectors_to_wait = [
                'div.songs-list-row',  # Individual song rows
                'div.songs-list-row__song-name',  # Song names
                'div.songs-list-row__by-line'  # Artist names
            ]
            
            for selector in selectors_to_wait:
                try:
                    WebDriverWait(self.browser, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                except TimeoutException:
                    logger.warning(f"Timeout waiting for selector: {selector}")
            
            # Extract playlist information using JavaScript with updated selectors
            playlist_data = self.browser.execute_script("""
                function getPlaylistData() {
                    const data = {
                        name: '',
                        tracks: [],
                        url: window.location.href,
                        platform: 'Apple Music'
                    };
                    
                    // Get playlist title
                    const titleElement = document.querySelector('h1.product-name');
                    data.name = titleElement ? titleElement.textContent.trim() : 'Unknown Playlist';
                    
                    // Get tracks
                    const trackElements = document.querySelectorAll('div.songs-list-row');
                    
                    trackElements.forEach((track, index) => {
                        try {
                            // Get song name
                            const songElement = track.querySelector('div.songs-list-row__song-name');
                            const songName = songElement ? songElement.textContent.trim() : '';
                            
                            // Get artist name
                            const artistElement = track.querySelector('div.songs-list-row__by-line');
                            let artistName = artistElement ? artistElement.textContent.trim() : '';
                            
                            // Clean up artist name
                            artistName = artistName.replace(/^By\\s+/i, '');
                            
                            // Additional artist name cleanup
                            artistName = artistName.split(/,|&|feat\.|ft\.|with/).map(a => a.trim())[0];
                            
                            if (songName) {
                                const trackData = {
                                    name: songName,
                                    artists: artistName ? [artistName] : [],
                                    position: index + 1
                                };
                                
                                // Add duration if available
                                const durationElement = track.querySelector('time.songs-list-row__duration');
                                if (durationElement) {
                                    trackData.duration = durationElement.textContent.trim();
                                }
                                
                                data.tracks.push(trackData);
                            }
                        } catch (e) {
                            console.error('Error extracting track:', e);
                        }
                    });
                    
                    data.total_tracks = data.tracks.length;
                    return data;
                }
                return getPlaylistData();
            """)
            
            if not playlist_data or not playlist_data.get('tracks'):
                logger.error("Failed to extract playlist data")
                # Take a screenshot for debugging
                screenshot_path = "playlist_scrape_error.png"
                self.browser.save_screenshot(screenshot_path)
                logger.error(f"Screenshot saved to {screenshot_path}")
                
                # Log additional debugging information
                logger.error(f"Current URL: {self.browser.current_url}")
                logger.error(f"Page title: {self.browser.title}")
                logger.error(f"Page source: {self.browser.page_source}")
                
                raise Exception("Failed to extract playlist data - no tracks found")
            
            logger.info(f"Successfully extracted playlist: {playlist_data.get('name')} with {len(playlist_data.get('tracks', []))} tracks")
            return playlist_data
            
        except Exception as e:
            logger.error(f"Error fetching playlist data: {str(e)}")
            try:
                logger.error(f"Current URL: {self.browser.current_url}")
                logger.error(f"Page title: {self.browser.title}")
                logger.error(f"Page source: {self.browser.page_source}")
            except:
                pass
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
        """Get playlist data from the appropriate platform."""
        platform = self.detect_platform(playlist_url)
        
        if platform == "apple-music":
            return await self.get_apple_music_playlist_data(playlist_url)
        elif platform == "spotify":
            return await self.get_spotify_playlist_data(playlist_url)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

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
        """Extract playlist data from Spotify."""
        search_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TRACE][{search_id}] Starting Spotify playlist data extraction for URL: {url}")
        
        # Initialize browser if not already done
        if not self.browser:
            await self.initialize_browser()
            
        # Attempt to clear browser state (without causing errors)
        try:
            # Clear cookies
            self.browser.delete_all_cookies()
            logger.info(f"[TRACE][{search_id}] Cleared browser cookies")
        except Exception as e:
            logger.warning(f"[WARN][{search_id}] Failed to clear cookies: {str(e)}")
        
        try:
            # Clear localStorage if possible
            self.browser.execute_script("try { window.localStorage.clear(); } catch(e) { console.log('localStorage not accessible'); }")
            logger.info(f"[TRACE][{search_id}] Attempted to clear localStorage")
        except Exception as e:
            logger.warning(f"[WARN][{search_id}] Failed to clear localStorage: {str(e)}")
        
        # Track extraction attempts
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"[TRACE][{search_id}] Attempt {attempt}/{max_attempts} to load playlist page")
                
                # Load the playlist page
                self.browser.get(url)
                
                # Wait for initial page load
                await asyncio.sleep(5)
                
                # Handle cookie consent if it appears
                try:
                    cookie_selectors = [
                        'button[data-testid="cookie-policy-dialog-accept-button"]',
                        'button#onetrust-accept-btn-handler',
                        'button:contains("Accept cookies")'
                    ]
                    
                    for selector in cookie_selectors:
                        try:
                            cookie_button = WebDriverWait(self.browser, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                            )
                            cookie_button.click()
                            logger.info(f"[TRACE][{search_id}] Accepted cookies using selector: {selector}")
                            await asyncio.sleep(1)
                            break
                        except:
                            continue
                            
                except Exception as e:
                    logger.info(f"[TRACE][{search_id}] No cookie consent dialog or failed to handle it: {str(e)}")
                
                # Save screenshot of loaded page for debugging
                try:
                    screenshot_path = f"spotify_page_{search_id}.png"
                    self.browser.save_screenshot(screenshot_path)
                    logger.info(f"[TRACE][{search_id}] Saved page screenshot to {screenshot_path}")
                except Exception as e:
                    logger.warning(f"[WARN][{search_id}] Failed to save screenshot: {str(e)}")
                
                # Wait for playlist content to load
                playlist_selectors = [
                    'div[data-testid="playlist-tracklist"]',
                    'section[data-testid="playlist-page"]',
                    'div.contentSpacing',
                    'div[data-testid="track-list"]'
                ]
                
                playlist_container = None
                container_selector = None
                
                for selector in playlist_selectors:
                    try:
                        playlist_container = WebDriverWait(self.browser, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        container_selector = selector
                        logger.info(f"[TRACE][{search_id}] Found playlist container with selector: {selector}")
                        break
                    except:
                        continue
                
                if not playlist_container:
                    raise Exception("Could not find playlist container element")
                
                # Scroll down to load all tracks
                for _ in range(3):
                    self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1)
                
                # Extract playlist title
                playlist_name = None
                name_selectors = [
                    'h1[data-testid="entityTitle"]',
                    'h1.Type__TypeElement',
                    'div.under-title-text h1',
                    'div[data-testid="playlist-page"] h1'
                ]
                
                for selector in name_selectors:
                    try:
                        element = self.browser.find_element(By.CSS_SELECTOR, selector)
                        playlist_name = element.text.strip()
                        if playlist_name:
                            logger.info(f"[TRACE][{search_id}] Found playlist name: {playlist_name}")
                            break
                    except:
                        continue
                
                if not playlist_name:
                    logger.warning(f"[WARN][{search_id}] Could not extract playlist name")
                    playlist_name = "Unknown Playlist"
                
                # Extract track rows
                row_selectors = [
                    'div[data-testid="tracklist-row"]',
                    'div[role="row"]',
                    'div.tracklist-container div[draggable="true"]'
                ]
                
                track_rows = []
                for selector in row_selectors:
                    try:
                        rows = playlist_container.find_elements(By.CSS_SELECTOR, selector)
                        if rows:
                            track_rows = rows
                            logger.info(f"[TRACE][{search_id}] Found {len(rows)} track rows with selector: {selector}")
                            break
                    except:
                        continue
                
                if not track_rows:
                    logger.error(f"[ERROR][{search_id}] No track rows found in playlist container")
                    raise Exception("No track rows found in playlist")
                
                # Extract track data
                tracks = []
                
                # Try multiple JavaScript extraction approaches
                track_data = self.browser.execute_script("""
                    function extractTracks() {
                        // Primary approach: use data-testid attributes
                        
                        // IMPORTANT: Only target the main playlist tracks container, not the recommendations
                        const mainPlaylistContainer = document.querySelector('div[data-testid="playlist-tracklist"]');
                        if (!mainPlaylistContainer) {
                            console.error('Main playlist container not found');
                            return [];
                        }
                        
                        // Only get track rows from within the main playlist container
                        const rows = mainPlaylistContainer.querySelectorAll('div[data-testid="tracklist-row"]');
                        console.log('Found', rows.length, 'tracks in main playlist container');
                        
                        if (rows.length > 0) {
                            const tracks = [];
                            for (const row of rows) {
                                try {
                                    // Verify this is an actual track row and not a header or recommendation
                                    if (row.closest('[data-testid="recommendations-section"]') ||
                                        row.closest('.RecommendationItem') ||
                                        row.closest('.recommended-item') ||
                                        row.closest('[data-testid="enhanced-page-section"]') ||
                                        row.hasAttribute('data-testid') && row.getAttribute('data-testid').includes('recommendation')) {
                                        console.log('Skipping recommended track');
                                        continue;
                                    }
                                    
                                    // Check for playlist end marker
                                    if (row.querySelector('.EndOfPlaylistSection') || 
                                        row.querySelector('[class*="EndOfPlaylist"]') ||
                                        row.querySelector('[data-testid="playlist-end-marker"]')) {
                                        console.log('Reached end of playlist marker');
                                        break;
                                    }
                                    
                                    // Multiple selectors for track title
                                    let nameElement = row.querySelector('div[data-testid="internal-track-link"] a');
                                    if (!nameElement) {
                                        nameElement = row.querySelector('a[data-testid="internal-track-link"]');
                                    }
                                    if (!nameElement) {
                                        nameElement = row.querySelector('a[aria-label*="play"]');
                                    }
                                    
                                    // Multiple selectors for artist
                                    let artistElement = row.querySelector('span a');
                                    if (!artistElement) {
                                        artistElement = row.querySelector('a[href*="artist"]');
                                    }
                                    
                                    // Multiple selectors for duration
                                    let durationElement = row.querySelector('div[data-testid="tracklist-duration"]');
                                    if (!durationElement) {
                                        durationElement = row.querySelector('div[aria-colindex="5"]');
                                    }
                                    
                                    const name = nameElement ? nameElement.textContent.trim() : 'Unknown Track';
                                    const artist = artistElement ? artistElement.textContent.trim() : 'Unknown Artist';
                                    const duration = durationElement ? durationElement.textContent.trim() : '';
                                    
                                    // Skip rows that seem to be headers or recommendations
                                    if (name === 'Title' || name === '#' || name === '' || 
                                        row.classList.contains('recommended') || 
                                        row.closest('[data-testid="recommendations-section"]')) {
                                        console.log('Skipping header or empty track');
                                        continue;
                                    }
                                    
                                    // Get all artist elements (there might be multiple)
                                    const artistElements = row.querySelectorAll('span a[href*="artist"]');
                                    const artists = [];
                                    
                                    if (artistElements.length > 0) {
                                        for (const elem of artistElements) {
                                            artists.push(elem.textContent.trim());
                                        }
                                    } else {
                                        artists.push(artist);
                                    }
                                    
                                    // Additional validation: skip if no track name or artists
                                    if (!name || name === 'Unknown Track' || artists.length === 0) {
                                        console.log('Skipping track with missing data');
                                        continue;
                                    }
                                    
                                    tracks.push({
                                        name: name,
                                        artists: artists,
                                        duration: duration
                                    });
                                } catch (e) {
                                    console.error('Error extracting track data:', e);
                                }
                            }
                            return tracks;
                        }
                        
                        // Fallback approach only if needed
                        return [];
                    }
                    
                    return extractTracks();
                """)
                
                if track_data and len(track_data) > 0:
                    tracks = track_data
                    logger.info(f"[TRACE][{search_id}] Successfully extracted {len(tracks)} tracks using JavaScript")
                else:
                    # Fallback to manual element extraction if JavaScript approach failed
                    logger.warning(f"[WARN][{search_id}] JavaScript extraction failed, falling back to manual extraction")
                    
                    # Find the main playlist container to exclude recommendations
                    main_container = None
                    for selector in ['div[data-testid="playlist-tracklist"]', 'section[data-testid="playlist-tracklist"]']:
                        try:
                            main_container = self.browser.find_element(By.CSS_SELECTOR, selector)
                            if main_container:
                                logger.info(f"[TRACE][{search_id}] Found main playlist container with selector: {selector}")
                                break
                        except:
                            continue
                    
                    if not main_container:
                        logger.warning(f"[WARN][{search_id}] Could not find main playlist container, using full page")
                        main_container = self.browser
                    
                    # Get track rows only from the main container
                    track_rows = []
                    for selector in row_selectors:
                        try:
                            rows = main_container.find_elements(By.CSS_SELECTOR, selector)
                            if rows:
                                track_rows = rows
                                logger.info(f"[TRACE][{search_id}] Found {len(rows)} track rows in main container with selector: {selector}")
                                break
                        except:
                            continue
                    
                    for i, row in enumerate(track_rows):
                        try:
                            # Try multiple selectors for title
                            title_selectors = [
                                'div[data-testid="internal-track-link"] a',
                                'a[data-testid="internal-track-link"]',
                                'div.tracklist-name'
                            ]
                            
                            track_name = None
                            for selector in title_selectors:
                                try:
                                    element = row.find_element(By.CSS_SELECTOR, selector)
                                    track_name = element.text.strip()
                                    if track_name:
                                        break
                                except:
                                    continue
                            
                            if not track_name:
                                logger.warning(f"[WARN][{search_id}] Could not extract name for track {i+1}")
                                continue
                            
                            # Try multiple selectors for artists
                            artist_elements = []
                            artist_selectors = [
                                'span a[href*="artist"]',
                                'div.tracklist-col.name span a',
                                'a[href*="/artist/"]'
                            ]
                            
                            for selector in artist_selectors:
                                try:
                                    elements = row.find_elements(By.CSS_SELECTOR, selector)
                                    if elements:
                                        artist_elements = elements
                                        break
                                except:
                                    continue
                            
                            artists = []
                            for element in artist_elements:
                                artists.append(element.text.strip())
                            
                            if not artists:
                                logger.warning(f"[WARN][{search_id}] Could not extract artists for track {i+1}")
                                artists = ["Unknown Artist"]
                            
                            # Try multiple selectors for duration
                            duration = "0:00"
                            duration_selectors = [
                                'div[data-testid="tracklist-duration"]',
                                'div.tracklist-duration span',
                                'div[aria-colindex="5"]'
                            ]
                            
                            for selector in duration_selectors:
                                try:
                                    element = row.find_element(By.CSS_SELECTOR, selector)
                                    duration = element.text.strip()
                                    if duration:
                                        break
                                except:
                                    continue
                            
                            tracks.append({
                                "name": track_name,
                                "artists": artists,
                                "duration": duration
                            })
                            
                        except Exception as e:
                            logger.error(f"[ERROR][{search_id}] Error extracting data for track {i+1}: {str(e)}")
                
                # Validate track data
                validated_tracks = []
                
                # Get the number of tracks displayed in the playlist header if possible
                expected_track_count = None
                try:
                    track_count_elements = self.browser.find_elements(By.CSS_SELECTOR, 
                        '.main-entityHeader-detailsText, [data-testid="playlist-track-count"]')
                    for element in track_count_elements:
                        text = element.text.strip()
                        # Look for patterns like "3 songs" or "3 tracks"
                        match = re.search(r'(\d+)\s+(song|track)', text, re.IGNORECASE)
                        if match:
                            expected_track_count = int(match.group(1))
                            logger.info(f"[TRACE][{search_id}] Found expected track count: {expected_track_count}")
                            break
                except Exception as e:
                    logger.warning(f"[WARN][{search_id}] Could not extract expected track count: {str(e)}")
                
                for idx, track in enumerate(tracks):
                    # Skip tracks without a name
                    if not track.get("name") or track.get("name") == "Unknown Track":
                        continue
                    
                    # Ensure artists is a list
                    if isinstance(track.get("artists"), str):
                        track["artists"] = [track["artists"]]
                    
                    # Ensure duration exists
                    if not track.get("duration"):
                        track["duration"] = "0:00"
                    
                    # Filter out probable recommended tracks
                    if expected_track_count and idx >= expected_track_count:
                        logger.info(f"[TRACE][{search_id}] Skipping track at position {idx+1} as it exceeds expected count of {expected_track_count}")
                        continue
                        
                    validated_tracks.append(track)
                
                # Additional validation: if we know the expected count, ensure we don't exceed it
                if expected_track_count and len(validated_tracks) > expected_track_count:
                    logger.warning(f"[WARN][{search_id}] Limiting tracks to expected count of {expected_track_count}")
                    validated_tracks = validated_tracks[:expected_track_count]
                
                # Log success
                logger.info(f"[TRACE][{search_id}] Successfully extracted {len(validated_tracks)} validated tracks")
                
                # Return playlist data
                return {
                    "platform": "spotify",
                    "url": url,
                    "name": playlist_name,
                    "tracks": validated_tracks
                }
                
            except Exception as e:
                error_msg = f"Error extracting Spotify playlist data (attempt {attempt}/{max_attempts}): {str(e)}"
                logger.error(f"[ERROR][{search_id}] {error_msg}")
                
                if attempt == max_attempts:
                    logger.error(f"[ERROR][{search_id}] All attempts failed for Spotify playlist extraction")
                    raise Exception(f"Failed to extract Spotify playlist data: {str(e)}")
                
                await asyncio.sleep(2)  # Wait before retrying
        
        raise Exception("Failed to extract Spotify playlist data: Max attempts reached") 