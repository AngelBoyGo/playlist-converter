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
from backend.app.services.utils import timeout_context, CircuitBreaker, RateLimiter, retry_with_exponential_backoff

logger = logging.getLogger(__name__)

class SoundCloudService:
    """Service for interacting with SoundCloud."""
    
    def __init__(self):
        """Initialize SoundCloud service."""
        logger.debug("Initializing SoundCloudService...")
        self.browser = None
        self._initialized = False
        
        # Initialize circuit breaker for search protection
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,  # Open after 3 failures
            cooling_period=30.0,  # Wait 30s before trying again
            half_open_timeout=5.0  # 5s timeout for test call
        )
        
        # Initialize rate limiter to prevent overloading SoundCloud
        # 1 request per 2 seconds with burst capability of 3
        self.rate_limiter = RateLimiter(rate=0.5, burst=3)
        
        # Keep track of search stats
        self.search_stats = {
            'total_searches': 0,
            'successful_searches': 0,
            'failed_searches': 0,
            'timeout_searches': 0,
            'circuit_breaker_rejections': 0,
            'rate_limited_searches': 0
        }

    async def initialize_browser(self):
        """Initialize browser for SoundCloud interactions."""
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
            
            chrome_options = webdriver.ChromeOptions()
            
            # Check if headless mode is enabled via environment variable
            headless = os.environ.get("SELENIUM_HEADLESS", "true").lower() == "true"
            if headless:
                chrome_options.add_argument('--headless=new')
                logger.info("Running Chrome in headless mode")
            
            # Add default arguments for container environments
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1280,720')  # Smaller window size
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
            
            # Additional flags to improve stability in containerized environments
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-infobars')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--single-process')  # Critical for memory usage
            chrome_options.add_argument('--no-zygote')
            chrome_options.add_argument('--disable-setuid-sandbox')
            chrome_options.add_argument('--disable-site-isolation-trials')
            chrome_options.add_argument('--ignore-certificate-errors')
            
            # Add unique data directory to prevent conflicts
            chrome_options.add_argument(f'--user-data-dir=/tmp/chrome-{self._id}')
            chrome_options.add_argument('--profile-directory=Profile1')
            
            # Block unnecessary content types to speed up loading - more aggressive
            chrome_options.add_experimental_option('prefs', {
                'profile.default_content_settings.images': 2,  # Don't load images
                'profile.default_content_setting_values.notifications': 2,  # Block notifications
                'profile.default_content_setting_values.media_stream': 2,  # Block media access
                'profile.managed_default_content_settings.images': 2,  # Redundant but to be sure
                'profile.default_content_setting_values.plugins': 2,  # Block plugins
                'profile.default_content_setting_values.popups': 2,  # Block popups 
                'profile.default_content_setting_values.geolocation': 2,  # Block geolocation
                'profile.default_content_setting_values.automatic_downloads': 2,  # Block downloads
                'profile.default_content_setting_values.cookies': 1,  # Allow cookies (needed for many sites)
                'profile.default_content_setting_values.javascript': 1,  # Allow JS (needed for functionality)
                'profile.default_content_settings.media_stream_mic': 2,  # Block mic access
                'profile.default_content_settings.media_stream_camera': 2,  # Block camera access
                'profile.default_content_settings.protocol_handlers': 2,  # Block protocol handlers
                'profile.default_content_settings.midi_sysex': 2,  # Block MIDI
                'profile.default_content_settings.push_messaging': 2,  # Block push messages
                'profile.default_content_settings.ssl_cert_decisions': 2,  # Block SSL cert decisions
                'disk-cache-size': 4096,  # 4MB disk cache
                'media-cache-size': 4096  # 4MB media cache
            })
            
            # CRITICAL FIX: Try multiple ChromeDriver strategies
            browser_initialized = False
            
            # Strategy 1: Use pre-installed ChromeDriver
            try:
                logger.info("Strategy 1: Trying with pre-installed ChromeDriver at /usr/bin/chromedriver")
                if os.path.exists("/usr/bin/chromedriver"):
                    chrome_service = webdriver.ChromeService(executable_path="/usr/bin/chromedriver")
                    self.browser = webdriver.Chrome(service=chrome_service, options=chrome_options)
                    browser_initialized = True
                    logger.info("Successfully initialized browser with pre-installed ChromeDriver")
            except Exception as e:
                logger.warning(f"Strategy 1 failed with pre-installed ChromeDriver: {str(e)}")
            
            # Strategy 2: Use explicitly downloaded ChromeDriver
            if not browser_initialized:
                try:
                    logger.info("Strategy 2: Using explicit ChromeDriver download")
                    from webdriver_manager.chrome import ChromeDriverManager

                    # Disable SSL verification for WebDriver Manager
                    import ssl
                    ssl._create_default_https_context = ssl._create_unverified_context
                    
                    os.environ['WDM_SSL_VERIFY'] = '0'  # Disable SSL verification
                    os.environ['WDM_LOG_LEVEL'] = '0'   # Reduce logging noise
                    
                    # Use specific download path to avoid NOTICES file issue
                    driver_path = ChromeDriverManager().install()
                    logger.info(f"Downloaded ChromeDriver to: {driver_path}")
                    
                    # IMPORTANT: Verify the driver path points to the actual binary
                    if os.path.exists(driver_path):
                        if os.path.isdir(driver_path):
                            # If it's a directory, find the actual chromedriver binary
                            for root, dirs, files in os.walk(driver_path):
                                for file in files:
                                    if file == "chromedriver" or file.startswith("chromedriver."):
                                        driver_path = os.path.join(root, file)
                                        logger.info(f"Found chromedriver binary at: {driver_path}")
                                        break
                        
                        # Make sure it's executable
                        if not os.access(driver_path, os.X_OK):
                            logger.info(f"Making ChromeDriver executable: {driver_path}")
                            os.chmod(driver_path, 0o755)
                        
                        chrome_service = webdriver.ChromeService(executable_path=driver_path)
                        self.browser = webdriver.Chrome(service=chrome_service, options=chrome_options)
                        browser_initialized = True
                        logger.info("Successfully initialized browser with downloaded ChromeDriver")
                    else:
                        logger.error(f"Downloaded driver does not exist at path: {driver_path}")
                except Exception as e:
                    logger.warning(f"Strategy 2 failed with explicit download: {str(e)}")
            
            # Strategy 3: Use Selenium Manager (last resort)
            if not browser_initialized:
                try:
                    logger.info("Strategy 3: Using Selenium built-in WebDriver manager")
                    # Let Selenium handle everything
                    os.environ["USE_SELENIUM_MANAGER"] = "true"
                    self.browser = webdriver.Chrome(options=chrome_options)
                    browser_initialized = True
                    logger.info("Successfully initialized browser with Selenium Manager")
                except Exception as e:
                    logger.error(f"Strategy 3 failed with Selenium Manager: {str(e)}")
                    raise Exception(f"All browser initialization strategies failed: {str(e)}")
                
            # Set implicit wait and timeout (reduced from previous values)
            self.browser.implicitly_wait(5)  # Reduced from 10 seconds
            self.browser.set_page_load_timeout(30)  # Keep at 30 seconds
            
            # Set script timeout
            self.browser.set_script_timeout(15)  # Reduced from 30 seconds
            
            logger.info("SoundCloud browser initialized successfully")
            self._initialized = True
            
            # Navigate to SoundCloud homepage once to initialize cookies/storage
            try:
                self.browser.get("https://soundcloud.com/discover")
                await asyncio.sleep(1)  # Short wait
                
                # Execute basic DOM check
                self.browser.execute_script("return document.readyState")
                
                # Clear any initial dialogs or overlays
                try:
                    self.browser.execute_script("""
                        // Remove any popups or overlays
                        const overlays = document.querySelectorAll('.overlay, .modal, [class*="cookie"], [class*="gdpr"]');
                        overlays.forEach(el => el.remove());
                    """)
                except Exception:
                    pass
                    
            except Exception as e:
                logger.warning(f"Initial page load failed (non-critical): {str(e)}")
                # Continue anyway - this is just a warm-up
            
        except Exception as e:
            logger.error(f"Browser initialization failed: {str(e)}", exc_info=True)
            self._initialized = False
            raise

    async def search_track(self, track_name: str, artist_name: str = None, blacklisted_urls: List[str] = None) -> Optional[Dict]:
        """
        Search for a track on SoundCloud with improved reliability and timeout handling.
        
        Args:
            track_name: Name of the track to search for
            artist_name: Optional artist name to refine the search
            blacklisted_urls: List of URLs to exclude from results
            
        Returns:
            Dictionary with track information or None if not found
        """
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
        
        # Update global search stats
        self.search_stats['total_searches'] += 1
        
        # Check circuit breaker
        if not self.circuit_breaker.can_execute():
            logger.warning(f"[WARN][{search_id}] Circuit breaker is open, rejecting search request")
            self.search_stats['circuit_breaker_rejections'] += 1
            return None
        
        # Wait for rate limiter
        try:
            if not await self.rate_limiter.acquire():
                logger.info(f"[TRACE][{search_id}] Rate limited, waiting for token")
                self.search_stats['rate_limited_searches'] += 1
                await self.rate_limiter.wait_for_token()
                logger.info(f"[TRACE][{search_id}] Rate limiter released token, proceeding with search")
        except Exception as e:
            logger.error(f"[ERROR][{search_id}] Rate limiter error: {str(e)}")
            # Continue anyway - better to search than to fail completely
        
        if not self._initialized:
            try:
                await self.initialize_browser()
                search_stats['browser_ready'] = True
            except Exception as e:
                error_msg = f"Failed to initialize browser: {str(e)}"
                search_stats['errors'].append({'phase': 'browser_init', 'error': str(e)})
                logger.error(f"[ERROR][{search_id}] {error_msg}", exc_info=True)
                self.circuit_breaker.record_failure()
                self.search_stats['failed_searches'] += 1
                return None

        # Browser recovery mechanism
        need_browser_reset = False
        
        try:
            # Clean and normalize inputs
            original_track_name = track_name
            track_name = self._clean_input(track_name)
            
            artist_names = []
            if artist_name:
                original_artist_name = artist_name
                artist_name = self._clean_input(artist_name)
                # Split artist name by various separators
                artist_names = [a.strip() for a in re.split(r'[,&/]', artist_name) if a.strip()]
                # Add the full artist name as well
                if artist_name not in artist_names:
                    artist_names.append(artist_name)
                
                # Add versions without special characters
                normalized_artist_names = [re.sub(r'[^\w\s]', '', a).strip() for a in artist_names]
                artist_names.extend([a for a in normalized_artist_names if a and a not in artist_names])
            
            # ULTRA-SIMPLIFIED SEARCH STRATEGY:
            # 1. Use minimal search queries to avoid timeouts
            # 2. Remove quotation marks which can cause renderer issues
            # 3. Optimize for speed over precision
            
            search_queries = []
            
            # Generate minimal search queries - focus on reliability
            if artist_names:
                # Primary artist approach - use the first/main artist
                primary_artist = artist_names[0]
                # Simple search with track name and primary artist (most reliable)
                search_queries.append(f'{track_name} {primary_artist}')
            
            # Just the track name as fallback
            search_queries.append(track_name)
            
            # Remove duplicates while preserving order
            search_queries = list(dict.fromkeys(search_queries))
            
            # CRITICAL FIX: Remove all quotation marks which can cause renderer issues
            search_queries = [q.replace('"', '').replace("'", "") for q in search_queries]
            
            best_match = None
            highest_similarity = 0
            all_results = []  # Keep track of all results for final evaluation
            
            # Reduce search timeout to prevent long-running searches
            search_timeout = 15  # seconds - reduced from 30
            
            for i, search_query in enumerate(search_queries):
                try:
                    # Apply timeout to the entire search query process
                    async with timeout_context(search_timeout):
                        encoded_query = quote(search_query)
                        search_url = f"https://soundcloud.com/search/sounds?q={encoded_query}"
                        
                        logger.info(f"[TRACE][{search_id}] Trying search query: '{search_query}'")

                        # RECOVERY: If this isn't our first query and we had issues, use direct navigation
                        if i > 0 and need_browser_reset:
                            logger.info(f"[TRACE][{search_id}] Performing browser cleanup before next query")
                            # Simple recovery - clear cookies and cache
                            try:
                                self.browser.delete_all_cookies()
                                self.browser.execute_script("localStorage.clear(); sessionStorage.clear();")
                            except Exception as e:
                                logger.error(f"[ERROR][{search_id}] Cleanup failed: {str(e)}")
                            
                        # FIX: Use get with exception handling and retries
                        get_success = False
                        for retry in range(2):  # Try twice
                            try:
                                self.browser.get(search_url)
                                get_success = True
                                break
                            except Exception as e:
                                logger.warning(f"[WARN][{search_id}] Page load issue on attempt {retry+1}: {str(e)}")
                                await asyncio.sleep(1)
                        
                        if not get_success:
                            logger.error(f"[ERROR][{search_id}] Failed to load page after retries")
                            need_browser_reset = True
                            continue
                            
                        # Short initial wait
                        await asyncio.sleep(1)
                        
                        # CRITICAL FIX: Simplified JavaScript execution to stop animations
                        # Removed complex script to avoid renderer issues
                        try:
                            self.browser.execute_script("window.stop();")
                        except Exception as e:
                            logger.warning(f"[WARN][{search_id}] Couldn't stop page loading: {str(e)}")
                        
                        # Wait for search results (more reliable approach)
                        track_elements = []
                        selectors = [
                            "ul.lazyLoadingList__list li.searchList__item",  # Main search results
                            "ul.soundList__list li.soundList__item",         # Alternative layout
                            "li[role='listitem']"                            # Generic list items
                        ]
                        
                        for selector in selectors:
                            try:
                                # Shorter timeout for each selector (5 seconds)
                                wait = WebDriverWait(self.browser, 5)
                                elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                                if elements:
                                    track_elements = elements
                                    search_stats['page_loaded'] = True
                                    break
                            except Exception:
                                continue
                        
                        if not track_elements:
                            logger.warning(f"[WARN][{search_id}] No search results found for query: '{search_query}'")
                            continue
                        
                        # Process search results
                        search_stats['results_found'] = True
                        track_infos = []
                        
                        # CRITICAL FIX: Limit results processing to prevent timeouts
                        max_results = 5  # Only process first 5 results
                        
                        for element in track_elements[:max_results]:
                            try:
                                # Extract track details using simplified approach
                                html = element.get_attribute('innerHTML')
                                if not html:
                                    continue
                                    
                                # Parse with BeautifulSoup to avoid complex JS interactions
                                from bs4 import BeautifulSoup
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Extract track information using various potential formats
                                # Get track title
                                title_element = soup.select_one('a.soundTitle__title span') or \
                                              soup.select_one('a[aria-label]') or \
                                              soup.select_one('.soundTitle__title')
                                
                                if not title_element:
                                    continue
                                    
                                title = title_element.get_text().strip() if hasattr(title_element, 'get_text') else \
                                       title_element.get('aria-label', '').strip()
                                
                                # Get track URL
                                url_element = soup.select_one('a.soundTitle__title') or \
                                            soup.select_one('a[aria-label]') or \
                                            soup.select_one('a[href*="/tracks/"]')
                                            
                                if not url_element or not url_element.get('href'):
                                    continue
                                    
                                url = url_element.get('href')
                                if not url.startswith('http'):
                                    url = f"https://soundcloud.com{url}"
                                
                                # Skip if URL is blacklisted
                                if blacklisted_urls and url in blacklisted_urls:
                                    continue
                                
                                # Get username
                                user_element = soup.select_one('.soundTitle__username') or \
                                             soup.select_one('a[href*="/"]')
                                             
                                username = user_element.get_text().strip() if user_element and hasattr(user_element, 'get_text') else "Unknown Artist"
                                
                                # Create track info
                                track_info = {
                                    'title': title,
                                    'url': url,
                                    'user': {
                                        'username': username
                                    }
                                }
                                
                                track_infos.append(track_info)
                            except Exception as e:
                                logger.warning(f"[WARN][{search_id}] Error extracting track info: {str(e)}")
                                continue
                        
                        if not track_infos:
                            logger.warning(f"[WARN][{search_id}] No usable tracks found in the results for query: '{search_query}'")
                            continue
                            
                        # Simple match selection logic - find best match based on title similarity
                        search_stats['matches_found'] = len(track_infos)
                        logger.info(f"[TRACE][{search_id}] Found {len(track_infos)} potential matches")
                        
                        normalized_track_name = normalize_text(track_name)
                        normalized_artist_name = normalize_text(artist_name) if artist_name else ""
                        
                        for track_info in track_infos:
                            normalized_title = normalize_text(track_info['title'])
                            normalized_username = normalize_text(track_info['user']['username'])
                            
                            # Calculate similarity scores
                            title_similarity = self._similarity(normalized_track_name, normalized_title)
                            username_similarity = 0
                            if normalized_artist_name:
                                username_similarity = self._similarity(normalized_artist_name, normalized_username)
                            
                            # Weighted combined score - title is more important
                            combined_similarity = (title_similarity * 0.7) + (username_similarity * 0.3)
                            
                            if combined_similarity > highest_similarity:
                                highest_similarity = combined_similarity
                                best_match = track_info
                                search_stats['best_match_similarity'] = combined_similarity
                                
                                # If we have a very good match, stop looking
                                if combined_similarity > 0.8:
                                    logger.info(f"[TRACE][{search_id}] Found high quality match (score: {combined_similarity:.2f}): '{track_info['title']}' by {track_info['user']['username']}")
                                    return best_match
                        
                        # If this query gave us a decent match, stop searching
                        if highest_similarity > 0.6:
                            logger.info(f"[TRACE][{search_id}] Found acceptable match (score: {highest_similarity:.2f}): '{best_match['title']}' by {best_match['user']['username']}")
                            return best_match
                        
                        # Store results for later evaluation
                        all_results.extend(track_infos)
                    
                except TimeoutError:
                    # Handle timeout for this specific search query
                    need_browser_reset = True
                    search_stats['errors'].append({'phase': 'search_timeout', 'query': search_query})
                    self.search_stats['timeout_searches'] += 1
                    logger.error(f"[ERROR][{search_id}] Search timeout for query: '{search_query}'")
                    continue
                
                except Exception as e:
                    need_browser_reset = True
                    search_stats['errors'].append({'phase': 'search_error', 'query': search_query, 'error': str(e)})
                    logger.error(f"[ERROR][{search_id}] Error with search query '{search_query}': {str(e)}", exc_info=True)
                    continue
            
            # If we got this far and have a best match, return it
            if best_match:
                logger.info(f"[TRACE][{search_id}] Returning best match found (score: {highest_similarity:.2f}): '{best_match['title']}' by {best_match['user']['username']}")
                self.search_stats['successful_searches'] += 1
                return best_match
            
            # If we have any results at all, return the first one as a fallback
            if all_results:
                logger.info(f"[TRACE][{search_id}] No good match found, returning first result as fallback: '{all_results[0]['title']}' by {all_results[0]['user']['username']}")
                self.search_stats['successful_searches'] += 1
                return all_results[0]
                
            # No results found
            logger.warning(f"[WARN][{search_id}] No matches found for '{track_name}'" + (f" by '{artist_name}'" if artist_name else ""))
            self.search_stats['failed_searches'] += 1
            self.circuit_breaker.record_failure()
            return None
            
        except Exception as e:
            logger.error(f"[ERROR][{search_id}] Search failed: {str(e)}", exc_info=True)
            self.search_stats['failed_searches'] += 1
            self.circuit_breaker.record_failure()
            return None
            
        finally:
            # Handle potential browser reset if needed
            if need_browser_reset:
                try:
                    logger.info(f"[TRACE][{search_id}] Performing browser reset after search completion")
                    await self.cleanup()
                    await self.initialize_browser()
                except Exception as e:
                    logger.error(f"[ERROR][{search_id}] Browser reset failed: {str(e)}")

    def get_stats(self) -> Dict:
        """Get statistics about search operations."""
        return {
            'search_stats': self.search_stats,
            'circuit_breaker': self.circuit_breaker.get_stats(),
            'rate_limiter': self.rate_limiter.get_stats()
        }
        
    def _clean_input(self, text: str) -> str:
        """Clean and normalize input text."""
        if not text:
            return ""
        
        # Remove multiple spaces and trim
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove common noise words from titles
        noise_words = [
            r'official\s+(audio|video|music\s+video)',
            r'explicit', r'clean', r'premium', r'deluxe', 
            r'album\s+version', r'radio\s+edit', r'original\s+mix',
            r'ft\.', r'feat\.', r'featuring'
        ]
        
        for word in noise_words:
            text = re.sub(r'(?i)' + word, '', text)
        
        # Remove special characters except those in track names
        text = re.sub(r'[^\w\s\-\'&,.]', ' ', text)
        
        # Remove extra spaces again after all replacements
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
        
    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate the similarity between two strings using SequenceMatcher."""
        if not a or not b:
            return 0.0
            
        a = a.lower()
        b = b.lower()
        
        # Direct equality check
        if a == b:
            return 1.0
            
        # If one string contains the other completely
        if a in b or b in a:
            # Calculate containment score based on length ratio
            short, long = (a, b) if len(a) <= len(b) else (b, a)
            return 0.7 + (0.3 * (len(short) / len(long)))
        
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, a, b).ratio()

    def _token_similarity(self, a: str, b: str) -> float:
        """Calculate similarity based on word tokens, not character by character."""
        if not a or not b:
            return 0.0
            
        a_tokens = set(re.findall(r'\w+', a.lower()))
        b_tokens = set(re.findall(r'\w+', b.lower()))
        
        if not a_tokens or not b_tokens:
            return 0.0
            
        # Calculate Jaccard similarity: intersection / union
        intersection = len(a_tokens.intersection(b_tokens))
        union = len(a_tokens.union(b_tokens))
        
        return intersection / union if union > 0 else 0.0
    
    async def cleanup(self):
        """Clean up browser resources."""
        if self.browser:
            try:
                self.browser.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
            finally:
                self.browser = None
                self._initialized = False