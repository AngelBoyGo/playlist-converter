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
        """Initialize browser with Chrome options."""
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            # Use environment variable for Chrome binary location if available (for Heroku)
            chrome_binary = os.environ.get('CHROME_EXECUTABLE_PATH')
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
            
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-infobars')
            
            # Add user agent to avoid detection
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.browser = webdriver.Chrome(options=chrome_options)
            self.browser.set_page_load_timeout(60)
            self.browser.implicitly_wait(10)
            
            logger.info("Browser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            raise BrowserInitializationError(f"Failed to initialize browser: {str(e)}")

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

    async def get_spotify_playlist_data(self, playlist_url: str) -> Dict:
        """Get playlist data from Spotify."""
        request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"[TRACE][{request_id}] Starting Spotify playlist data extraction for URL: {playlist_url}")
        
        if not self._initialized:
            await self.initialize_browser()
            
        # Ensure we're starting with a fresh page
        try:
            self.browser.delete_all_cookies()
            self.browser.execute_script("window.localStorage.clear();")
            self.browser.execute_script("window.sessionStorage.clear();")
        except Exception as e:
            logger.warning(f"[WARN][{request_id}] Failed to clear browser state: {str(e)}")
        
        start_time = datetime.now()
        scraping_stats = self._create_scraping_stats(request_id, playlist_url)
        
        try:
            # Navigate to the playlist URL with retry logic
            max_retries = 3
            retry_count = 0
            page_load_start = datetime.now()
            
            while retry_count < max_retries:
                try:
                    logger.info(f"[TRACE][{request_id}] Attempt {retry_count + 1}/{max_retries} to load playlist page")
                    self.browser.get(playlist_url)
                    
                    # Wait for initial page load
                    await asyncio.sleep(5)
                    
                    # Check if page loaded successfully
                    if "spotify.com" not in self.browser.current_url:
                        raise Exception("Page did not load correctly")
                    
                    # Try to accept cookies if the button exists
                    try:
                        cookie_button = WebDriverWait(self.browser, 5).until(
                            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                        )
                        cookie_button.click()
                        logger.info(f"[TRACE][{request_id}] Accepted cookies")
                        await asyncio.sleep(2)
                    except TimeoutException:
                        logger.info(f"[TRACE][{request_id}] No cookie banner found or already accepted")
                    
                    scraping_stats['page_load_success'] = True
                    scraping_stats['performance_metrics']['page_load_duration'] = self._serialize_datetime(datetime.now() - page_load_start)
                    break
                    
                except Exception as e:
                    retry_count += 1
                    error_msg = f"Failed to load page (attempt {retry_count}): {str(e)}"
                    scraping_stats['errors'].append({
                        'phase': 'page_load',
                        'attempt': retry_count,
                        'error': str(e),
                        'timestamp': self._serialize_datetime(datetime.now())
                    })
                    logger.error(f"[ERROR][{request_id}] {error_msg}")
                    
                    if retry_count == max_retries:
                        raise Exception(f"Failed to load page after {max_retries} attempts")
                    await asyncio.sleep(2 ** retry_count)
            
            # Wait for main content containers with detailed logging
            content_load_start = datetime.now()
            
            # First wait for any of these selectors to be present
            playlist_container_selectors = [
                'div[data-testid="playlist-tracklist"]',
                'div[data-testid="playlist-page"]',
                'div.contentSpacing',
                'div[class*="PlaylistPage"]'
            ]
            
            container_found = False
            for selector in playlist_container_selectors:
                try:
                    WebDriverWait(self.browser, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"[TRACE][{request_id}] Found playlist container with selector: {selector}")
                    container_found = True
                    break
                except TimeoutException:
                    continue
            
            if not container_found:
                error_msg = "Failed to find playlist container with any selector"
                logger.error(f"[ERROR][{request_id}] {error_msg}")
                raise TimeoutException(error_msg)
            
            # Wait for track rows with multiple selectors
            track_row_selectors = [
                'div[data-testid="track-row"]',
                'div[role="row"]',
                'div[class*="TrackListRow"]',
                'div.tracklist-row'
            ]
            
            track_rows = None
            used_selector = None
            
            for selector in track_row_selectors:
                try:
                    logger.info(f"[TRACE][{request_id}] Trying track row selector: {selector}")
                    # Use a shorter timeout for each selector attempt
                    track_rows = WebDriverWait(self.browser, 5).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                    )
                    if track_rows and len(track_rows) > 0:
                        used_selector = selector
                        logger.info(f"[TRACE][{request_id}] Successfully found {len(track_rows)} track rows with selector: {selector}")
                        break
                except TimeoutException:
                    logger.warning(f"[WARN][{request_id}] Selector {selector} failed")
                    continue
            
            if not track_rows:
                error_msg = "Failed to find track rows with any selector"
                logger.error(f"[ERROR][{request_id}] {error_msg}")
                # Take screenshot for debugging
                screenshot_path = f"error_screenshot_{request_id}_no_tracks.png"
                self.browser.save_screenshot(screenshot_path)
                logger.info(f"[TRACE][{request_id}] Saved error screenshot to {screenshot_path}")
                raise TimeoutException(error_msg)
            
            scraping_stats['content_load_success'] = True
            scraping_stats['performance_metrics']['content_load_duration'] = self._serialize_datetime(datetime.now() - content_load_start)
            
            # Extract playlist data with improved selector for actual playlist tracks
            extraction_start = datetime.now()
            try:
                playlist_data = self.browser.execute_script("""
                    function getPlaylistData() {
                        // Get playlist name
                        const playlistName = document.querySelector('h1')?.textContent?.trim() || 'Unknown Playlist';
                        
                        // Get only the main playlist tracks container, excluding recommendations
                        const playlistContainer = document.querySelector('div[data-testid="playlist-tracklist"]');
                        if (!playlistContainer) {
                            console.error('Playlist container not found');
                            return null;
                        }
                        
                        // Get only the track rows within the main playlist section
                        const trackRows = Array.from(playlistContainer.querySelectorAll('div[data-testid="tracklist-row"]'));
                        console.log('Processing', trackRows.length, 'track rows');
                        
                        const tracks = [];
                        trackRows.forEach((row, index) => {
                            try {
                                // Try multiple selectors for title
                                const titleElement = 
                                    row.querySelector('[data-testid="internal-track-link"]') ||
                                    row.querySelector('a[href*="/track/"]') ||
                                    row.querySelector('div[class*="tracklist-name"]') ||
                                    row.querySelector('div[class*="track-name"]');
                                
                                // Try multiple selectors for artists
                                const artistElements = 
                                    Array.from(row.querySelectorAll('a[href*="/artist/"]')) ||
                                    Array.from(row.querySelectorAll('span[class*="artist-name"]')) ||
                                    Array.from(row.querySelectorAll('span[class*="track-artist"]'));
                                
                                // Try multiple selectors for duration
                                const durationElement = 
                                    row.querySelector('[data-testid="tracklist-duration"]') ||
                                    row.querySelector('div[class*="duration"]') ||
                                    row.querySelector('span[class*="duration"]');
                                
                                // Check if this is a valid track row (has required elements)
                                if (titleElement && artistElements.length > 0) {
                                    const track = {
                                        name: titleElement.textContent.trim(),
                                        artists: artistElements.map(el => el.textContent.trim()).filter(Boolean),
                                        duration: durationElement ? durationElement.textContent.trim() : '',
                                        position: index + 1
                                    };
                                    
                                    tracks.push(track);
                                    console.log('Added track:', track.name, 'by', track.artists.join(', '));
                                }
                            } catch (e) {
                                console.error('Error processing track row:', e);
                            }
                        });
                        
                        return {
                            name: playlistName,
                            tracks: tracks,
                            total_tracks: tracks.length,
                            platform: 'spotify',
                            url: window.location.href
                        };
                    }
                    return getPlaylistData();
                """)
                
                if not playlist_data:
                    raise Exception("Failed to extract playlist data - no data returned from script")
                
                if not playlist_data.get('tracks'):
                    raise Exception("Failed to extract playlist data - no tracks found")
                
                scraping_stats['track_extraction_success'] = True
                scraping_stats['total_tracks_found'] = len(playlist_data.get('tracks', []))
                scraping_stats['performance_metrics']['extraction_duration'] = self._serialize_datetime(datetime.now() - extraction_start)
                
                # Log success information
                logger.info(f"[TRACE][{request_id}] Successfully extracted playlist data:")
                logger.info(f"[TRACE][{request_id}] - Name: {playlist_data.get('name')}")
                logger.info(f"[TRACE][{request_id}] - Total tracks: {len(playlist_data.get('tracks', []))}")
                
                # Log first few tracks for verification
                for idx, track in enumerate(playlist_data.get('tracks', [])[:3], 1):
                    logger.info(f"[TRACE][{request_id}] - Track {idx}: {track.get('name')} by {', '.join(track.get('artists', []))}")
                
                return playlist_data
                
            except Exception as e:
                error_msg = f"Failed to extract playlist data: {str(e)}"
                scraping_stats['errors'].append({
                    'phase': 'data_extraction',
                    'error': str(e),
                    'timestamp': self._serialize_datetime(datetime.now())
                })
                logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
                raise
                
        except Exception as e:
            error_msg = f"Failed to fetch Spotify playlist data: {str(e)}"
            logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
            raise
            
        finally:
            # Log final statistics
            try:
                end_time = datetime.now()
                scraping_stats['end_time'] = self._serialize_datetime(end_time)
                scraping_stats['duration'] = str((end_time - start_time).total_seconds())
                
                # Convert any remaining datetime objects
                stats_json = json.dumps(scraping_stats, default=self._serialize_datetime, indent=2)
                logger.info(f"[TRACE][{request_id}] Scraping statistics: {stats_json}")
            except Exception as stats_error:
                logger.error(f"[ERROR][{request_id}] Failed to log scraping statistics: {str(stats_error)}") 