import logging
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import asyncio
from difflib import SequenceMatcher
from urllib.parse import quote
from datetime import datetime
import re
import os

logger = logging.getLogger(__name__)

class SoundCloudService:
    """Service for interacting with SoundCloud."""
    
    def __init__(self):
        """Initialize SoundCloud service."""
        logger.debug("Initializing SoundCloudService...")
        self.browser = None
        self._initialized = False

    async def initialize_browser(self):
        """Initialize browser for SoundCloud interactions."""
        if self._initialized:
            return

        try:
            logger.info("SoundCloud: Starting browser initialization...")
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # For Heroku environment
            is_heroku = 'DYNO' in os.environ
            logger.info(f"SoundCloud: Running in Heroku environment: {is_heroku}")
            
            if is_heroku:
                chrome_binary_path = os.environ.get('GOOGLE_CHROME_BIN', '/app/.chrome-for-testing/chrome-linux64/chrome')
                logger.info(f"SoundCloud: Setting Chrome binary location to: {chrome_binary_path}")
                chrome_options.binary_location = chrome_binary_path
                
                # Verify if binary exists
                if os.path.exists(chrome_binary_path):
                    logger.info(f"SoundCloud: Chrome binary found at: {chrome_binary_path}")
                else:
                    logger.warning(f"SoundCloud: Chrome binary NOT found at: {chrome_binary_path}")
            
            logger.info("SoundCloud: Creating Chrome browser instance...")
            
            try:
                # Use WebDriverManager to handle driver installation
                from webdriver_manager.chrome import ChromeDriverManager
                from webdriver_manager.core.os_manager import ChromeType
                from selenium.webdriver.chrome.service import Service
                
                # Setup ChromeDriver differently based on environment
                if is_heroku:
                    chrome_driver_path = os.environ.get('CHROMEDRIVER_PATH', '/app/.chrome-for-testing/chromedriver-linux64/chromedriver')
                    logger.info(f"SoundCloud: Using ChromeDriver at: {chrome_driver_path}")
                    
                    # Verify if chromedriver exists
                    if os.path.exists(chrome_driver_path):
                        logger.info(f"SoundCloud: ChromeDriver found at: {chrome_driver_path}")
                        # Check if executable
                        if os.access(chrome_driver_path, os.X_OK):
                            logger.info("SoundCloud: ChromeDriver is executable")
                        else:
                            logger.warning("SoundCloud: ChromeDriver exists but is not executable")
                            try:
                                os.chmod(chrome_driver_path, 0o755)
                                logger.info("SoundCloud: Made ChromeDriver executable")
                            except Exception as chmod_error:
                                logger.error(f"SoundCloud: Failed to make ChromeDriver executable: {str(chmod_error)}")
                    else:
                        logger.warning(f"SoundCloud: ChromeDriver NOT found at: {chrome_driver_path}")
                        # Try to list directory contents
                        try:
                            heroku_bin_dir = os.path.dirname(chrome_driver_path)
                            if os.path.exists(heroku_bin_dir):
                                files = os.listdir(heroku_bin_dir)
                                logger.info(f"SoundCloud: Files in {heroku_bin_dir}: {files}")
                            else:
                                logger.warning(f"SoundCloud: Directory {heroku_bin_dir} does not exist")
                                
                                # Try to list root directories to find chromedriver
                                logger.info("SoundCloud: Searching for chromedriver in common locations...")
                                for search_dir in ['/app', '/usr/local/bin', '/usr/bin']:
                                    if os.path.exists(search_dir):
                                        logger.info(f"SoundCloud: Listing {search_dir}...")
                                        try:
                                            dir_files = os.listdir(search_dir)
                                            logger.info(f"SoundCloud: Files in {search_dir}: {dir_files[:10]}...")
                                            
                                            # Search recursively for chromedriver
                                            for root, dirs, files in os.walk(search_dir, topdown=True, followlinks=False):
                                                if 'chromedriver' in files:
                                                    found_path = os.path.join(root, 'chromedriver')
                                                    logger.info(f"SoundCloud: Found chromedriver at: {found_path}")
                                                    chrome_driver_path = found_path
                                                    break
                                                # Limit depth
                                                if root.count(os.sep) - search_dir.count(os.sep) > 2:
                                                    dirs.clear()
                                        except Exception as list_error:
                                            logger.error(f"SoundCloud: Error listing {search_dir}: {str(list_error)}")
                        except Exception as dir_error:
                            logger.error(f"SoundCloud: Error searching directories: {str(dir_error)}")
                    
                    try:
                        logger.info(f"SoundCloud: Attempting to create Chrome browser with Service({chrome_driver_path})")
                        service = Service(executable_path=chrome_driver_path)
                        self.browser = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info("SoundCloud: Successfully created Chrome browser with Service object")
                    except Exception as service_error:
                        logger.error(f"SoundCloud: Failed to create browser with Service: {str(service_error)}")
                        # Try alternate method
                        logger.info("SoundCloud: Trying alternative method for Heroku...")
                        try:
                            logger.info("SoundCloud: Setting Chrome binary path directly...")
                            chrome_options.add_argument(f"--webdriver-path={chrome_driver_path}")
                            self.browser = webdriver.Chrome(options=chrome_options)
                            logger.info("SoundCloud: Successfully created Chrome browser with direct options")
                        except Exception as alt_error:
                            logger.error(f"SoundCloud: Alternative method failed: {str(alt_error)}")
                            raise
                else:
                    # Local development
                    logger.info("SoundCloud: Using WebDriverManager for local development")
                    try:
                        # Try with ChromeDriverManager
                        driver_path = ChromeDriverManager().install()
                        logger.info(f"SoundCloud: WebDriverManager installed driver at: {driver_path}")
                        service = Service(driver_path)
                        self.browser = webdriver.Chrome(service=service, options=chrome_options)
                        logger.info("SoundCloud: Successfully created Chrome browser with WebDriverManager")
                    except Exception as wdm_error:
                        logger.error(f"SoundCloud: WebDriverManager failed: {str(wdm_error)}")
                        # Try to find chromedriver in PATH
                        logger.info("SoundCloud: Trying to find chromedriver in PATH...")
                        self.browser = webdriver.Chrome(options=chrome_options)
                        logger.info("SoundCloud: Successfully created Chrome browser from PATH")
            except ImportError as import_err:
                logger.error(f"SoundCloud: ImportError with WebDriverManager: {str(import_err)}")
                # Fallback to direct Chrome initialization
                logger.info("SoundCloud: Falling back to direct Chrome initialization...")
                self.browser = webdriver.Chrome(options=chrome_options)
                logger.info("SoundCloud: Successfully created Chrome browser with direct initialization")
            
            self.browser.implicitly_wait(10)
            self._initialized = True
            logger.info("SoundCloud browser initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize SoundCloud browser: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Log system PATH
            logger.info(f"SoundCloud: System PATH: {os.environ.get('PATH', 'Not available')}")
            if self.browser:
                await self.cleanup()
            raise Exception(error_msg)

    async def cleanup(self):
        """Clean up browser resources."""
        try:
            if self.browser:
                self.browser.quit()
                self.browser = None
            self._initialized = False
            logger.info("SoundCloud browser cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during SoundCloud browser cleanup: {str(e)}")

    def _calculate_similarity(self, source: str, target: str) -> float:
        """Calculate similarity ratio between two strings."""
        if not source or not target:
            return 0.0
            
        # Normalize strings for comparison
        source = source.lower().strip()
        target = target.lower().strip()
        
        # Remove common words and characters that might interfere with matching
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        source_words = [w for w in source.split() if w not in stop_words]
        target_words = [w for w in target.split() if w not in stop_words]
        
        # Calculate word-by-word similarity
        source_set = set(source_words)
        target_set = set(target_words)
        
        # Check for exact matches first
        if source == target:
            return 1.0
            
        # Calculate Jaccard similarity for words
        intersection = len(source_set & target_set)
        union = len(source_set | target_set)
        jaccard = intersection / union if union > 0 else 0
        
        # Calculate sequence similarity
        sequence = SequenceMatcher(None, source, target).ratio()
        
        # Combine both metrics with weights
        combined = (jaccard * 0.6) + (sequence * 0.4)
        
        # Boost score for partial matches
        if source in target or target in source:
            combined = min(1.0, combined + 0.2)
            
        return combined

    async def search_track(self, track_name: str, artist_name: str = None, blacklisted_urls: List[str] = None) -> Optional[Dict]:
        """Search for a track on SoundCloud."""
        search_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        search_stats = {
            'search_id': search_id,
            'start_time': datetime.now(),
            'track_name': track_name,
            'artist_name': artist_name,
            'browser_ready': self._initialized,
            'page_loaded': False,
            'results_found': False,
            'matches_found': 0,
            'best_match_similarity': 0,
            'blacklisted_urls': blacklisted_urls or [],
            'errors': []
        }
        
        if not self._initialized:
            try:
                await self.initialize_browser()
                search_stats['browser_ready'] = True
            except Exception as e:
                error_msg = f"Failed to initialize browser: {str(e)}"
                search_stats['errors'].append({'phase': 'browser_init', 'error': str(e)})
                logger.error(f"[ERROR][{search_id}] {error_msg}", exc_info=True)
                return None

        try:
            # Generate optimized search queries
            search_queries = []
            
            # Clean and normalize track name and artist name
            track_name = track_name.strip()
            if artist_name:
                artist_name = artist_name.strip()
                # Split artist name if it contains commas or '&'
                artist_names = [a.strip() for a in re.split(r'[,&]', artist_name)]
            
            # 1. Most specific search with quotes
            if artist_name:
                for artist in artist_names:
                    search_queries.append(f'"{track_name}" "{artist}"')
            
            # 2. Track name with each artist variation
            if artist_name:
                for artist in artist_names:
                    search_queries.append(f'{track_name} {artist}')
            
            # 3. Track name in quotes
            search_queries.append(f'"{track_name}"')
            
            # 4. Track name as is
            search_queries.append(track_name)
            
            # 5. Remove special characters from track name
            clean_track_name = re.sub(r'[^\w\s]', ' ', track_name)
            search_queries.append(clean_track_name)
            
            best_match = None
            highest_similarity = 0
            
            for search_query in search_queries:
                try:
                    encoded_query = quote(search_query)
                    search_url = f"https://soundcloud.com/search/sounds?q={encoded_query}"
                    
                    logger.info(f"[TRACE][{search_id}] Trying search query: '{search_query}'")
                    
                    self.browser.get(search_url)
                    # Wait longer for initial page load
                    await asyncio.sleep(2)
                    
                    # Wait for search results with multiple selectors
                    selectors = [
                        'ul.sc-list-nostyle',
                        'div[role="main"] ul',
                        'div.searchList__results'
                    ]
                    
                    results_found = False
                    for selector in selectors:
                        try:
                            WebDriverWait(self.browser, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            results_found = True
                            break
                        except TimeoutException:
                            continue
                    
                    if not results_found:
                        logger.warning(f"[WARN][{search_id}] No results found for query: {search_query}")
                        continue
                    
                    # Scroll down to load more results
                    self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1)
                    
                    # Extract track information with improved selectors
                    track_data = self.browser.execute_script("""
                        function getTrackData() {
                            const tracks = [];
                            const selectors = [
                                'ul.sc-list-nostyle li',
                                'div[role="main"] ul li',
                                'div.searchList__results div.sound__content'
                            ];
                            
                            for (const selector of selectors) {
                                const items = document.querySelectorAll(selector);
                                if (items.length > 0) {
                                    for (const item of items) {
                                        try {
                                            // Multiple selectors for title and user
                                            const titleElement = item.querySelector(
                                                'a[href*="/track/"], ' +
                                                'a.sc-link-primary, ' +
                                                'a.soundTitle__title, ' +
                                                'a[href*="soundcloud.com"][title]'
                                            );
                                            
                                            const userElement = item.querySelector(
                                                'a.sc-link-secondary[href*="/"], ' +
                                                'a.soundTitle__username, ' +
                                                'a[href*="soundcloud.com/"][class*="user"]'
                                            );
                                            
                                            if (titleElement && userElement) {
                                                const track = {
                                                    title: titleElement.textContent.trim(),
                                                    url: titleElement.href,
                                                    user: {
                                                        username: userElement.textContent.trim(),
                                                        url: userElement.href
                                                    }
                                                };
                                                
                                                // Add duration if available
                                                const durationElement = item.querySelector('span[aria-label*="Duration"], span.duration');
                                                if (durationElement) {
                                                    track.duration = durationElement.textContent.trim();
                                                }
                                                
                                                tracks.push(track);
                                            }
                                        } catch (e) {
                                            console.error('Error processing track:', e);
                                        }
                                    }
                                    
                                    // If we found tracks with this selector, no need to try others
                                    if (tracks.length > 0) break;
                                }
                            }
                            
                            return tracks;
                        }
                        return getTrackData();
                    """)
                    
                    if not track_data:
                        continue
                    
                    # Find best match with improved comparison
                    for track in track_data:
                        # Skip blacklisted URLs
                        if blacklisted_urls and track['url'] in blacklisted_urls:
                            logger.info(f"[TRACE][{search_id}] Skipping blacklisted track: {track['url']}")
                            continue
                        
                        # Quick exact match check first
                        if track['title'].lower() == track_name.lower():
                            if artist_name:
                                # Check if any artist name variation matches
                                for artist in artist_names:
                                    if track['user']['username'].lower() == artist.lower():
                                        return track
                            else:
                                return track
                        
                        # Calculate similarity with improved matching
                        title_similarity = self._calculate_similarity(track_name, track['title'])
                        
                        # Calculate artist similarity if artist name is provided
                        artist_similarity = 0
                        if artist_name:
                            # Check similarity against all artist name variations
                            artist_similarities = [
                                self._calculate_similarity(artist, track['user']['username'])
                                for artist in artist_names
                            ]
                            artist_similarity = max(artist_similarities)
                        else:
                            artist_similarity = 1.0  # Don't penalize if no artist name provided
                        
                        # Weighted similarity calculation
                        combined_similarity = (title_similarity * 0.7) + (artist_similarity * 0.3)
                        
                        # Additional boost for partial matches
                        if track_name.lower() in track['title'].lower():
                            combined_similarity = min(1.0, combined_similarity + 0.1)
                        
                        if artist_name and any(artist.lower() in track['user']['username'].lower() for artist in artist_names):
                            combined_similarity = min(1.0, combined_similarity + 0.1)
                        
                        if combined_similarity > highest_similarity:
                            highest_similarity = combined_similarity
                            best_match = track
                            search_stats['best_match_similarity'] = highest_similarity
                        
                        # Return immediately if we found a very good match
                        if highest_similarity > 0.9:
                            logger.info(f"[TRACE][{search_id}] Found excellent match: '{best_match['title']}' by {best_match['user']['username']}")
                            return best_match
                    
                    # Break search if we found a good enough match
                    if highest_similarity > 0.8:
                        break
                        
                except Exception as e:
                    logger.error(f"[ERROR][{search_id}] Error with search query '{search_query}': {str(e)}")
                    continue
            
            # Return best match if it's good enough
            if best_match and highest_similarity > 0.5:
                logger.info(f"[TRACE][{search_id}] Found best match with similarity {highest_similarity:.2f}: '{best_match['title']}' by {best_match['user']['username']}")
                return best_match
            else:
                logger.warning(f"[WARN][{search_id}] No suitable match found. Best similarity: {highest_similarity:.2f}")
                return None
                
        except Exception as e:
            error_msg = f"Error during track search: {str(e)}"
            search_stats['errors'].append({'phase': 'general', 'error': str(e)})
            logger.error(f"[ERROR][{search_id}] {error_msg}", exc_info=True)
            return None
        finally:
            search_stats['end_time'] = datetime.now()
            search_stats['duration'] = (search_stats['end_time'] - search_stats['start_time']).total_seconds()
            logger.info(f"[TRACE][{search_id}] Search completed. Stats: {search_stats}")

    def search_tracks(self, query: str) -> List[Dict]:
        """Search for tracks on SoundCloud."""
        if not self.browser:
            logger.warning("SoundCloud browser not initialized")
            return []
        return []  # Will be implemented with actual API integration later 
        return []  # Will be implemented with actual API integration later 