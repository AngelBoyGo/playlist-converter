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
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
            
            # Add any additional Chrome flags from environment variables
            chrome_flags = os.environ.get("CHROMEDRIVER_FLAGS", "")
            if chrome_flags:
                for flag in chrome_flags.split():
                    if flag.strip():
                        chrome_options.add_argument(flag.strip())
                logger.info(f"Added additional Chrome flags: {chrome_flags}")
            
            # First try using the pre-installed ChromeDriver
            try:
                logger.info("Trying with pre-installed ChromeDriver at /usr/bin/chromedriver")
                chrome_service = webdriver.ChromeService(executable_path="/usr/bin/chromedriver")
                self.browser = webdriver.Chrome(service=chrome_service, options=chrome_options)
            except Exception as e:
                logger.warning(f"Failed with pre-installed ChromeDriver: {str(e)}")
                
                # Fallback to Selenium's built-in WebDriver manager
                logger.info("Falling back to Selenium's WebDriver Manager")
                from selenium.webdriver.chrome.service import Service as ChromeService
                from webdriver_manager.chrome import ChromeDriverManager
                
                # Set environment variables for WebDriver Manager
                os.environ['WDM_LOG_LEVEL'] = '0'  # Suppress WebDriver Manager logs
                os.environ['WDM_SSL_VERIFY'] = '0'  # Bypass SSL verification
                
                chrome_service = ChromeService(ChromeDriverManager().install())
                self.browser = webdriver.Chrome(service=chrome_service, options=chrome_options)
            
            self.browser.implicitly_wait(10)
            self._initialized = True
            logger.info("SoundCloud browser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SoundCloud browser: {str(e)}")
            if self.browser:
                await self.cleanup()
            raise

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
        source_words = [w for w in source.split() if w not in stop_words]
        
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
            
            # Generate optimized search queries in order of specificity
            search_queries = []
            
            # 1. Most specific exact match search (in quotes)
            if artist_names:
                for artist in artist_names:
                    # Try with quotes around both
                    search_queries.append(f'"{track_name}" "{artist}"')
                    
            # 2. Exact track name with artist
            if artist_names:
                for artist in artist_names:
                    search_queries.append(f'"{track_name}" {artist}')
            
            # 3. Track name with each artist
            if artist_names:
                for artist in artist_names:
                    search_queries.append(f'{track_name} {artist}')
            
            # 4. Just the track name in quotes
            search_queries.append(f'"{track_name}"')
            
            # 5. Just the track name
            search_queries.append(track_name)
            
            # 6. Track name without special characters
            clean_track_name = re.sub(r'[^\w\s]', ' ', track_name).strip()
            if clean_track_name and clean_track_name != track_name:
                search_queries.append(clean_track_name)
            
            # 7. For tracks with brackets or parentheses, try searching without them
            simplified_track_name = re.sub(r'[\(\[\{].*?[\)\]\}]', '', track_name).strip()
            if simplified_track_name and simplified_track_name != track_name and len(simplified_track_name) > 3:
                search_queries.append(simplified_track_name)
            
            # Remove duplicates while preserving order
            search_queries = list(dict.fromkeys(search_queries))
            
            best_match = None
            highest_similarity = 0
            all_results = []  # Keep track of all results for final evaluation
            
            for search_query in search_queries:
                try:
                    encoded_query = quote(search_query)
                    search_url = f"https://soundcloud.com/search/sounds?q={encoded_query}"
                    
                    logger.info(f"[TRACE][{search_id}] Trying search query: '{search_query}'")
                    
                    self.browser.get(search_url)
                    # Wait for initial page load
                    await asyncio.sleep(2)
                    
                    # Wait for search results with multiple selectors
                    selectors = [
                        'ul.sc-list-nostyle',
                        'div[role="main"] ul',
                        'div.searchList__results',
                        'div.sound__body',
                        'div.searchList'
                    ]
                    
                    results_found = False
                    for selector in selectors:
                        try:
                            WebDriverWait(self.browser, 10).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            results_found = True
                            logger.info(f"[TRACE][{search_id}] Results found with selector: {selector}")
                            break
                        except TimeoutException:
                            continue
                    
                    if not results_found:
                        logger.warning(f"[WARN][{search_id}] No results found for query: {search_query}")
                        continue
                    
                    # Scroll down to load more results
                    for _ in range(2):  # Scroll multiple times to load more results
                        self.browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        await asyncio.sleep(1)
                    
                    # Take screenshot for debugging if needed
                    screenshot_path = f"search_results_{search_id}_{search_queries.index(search_query)}.png"
                    try:
                        self.browser.save_screenshot(screenshot_path)
                        logger.info(f"[TRACE][{search_id}] Saved screenshot to {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"[WARN][{search_id}] Failed to save screenshot: {str(e)}")
                    
                    # Extract track information with improved selectors
                    track_data = self.browser.execute_script("""
                        function getTrackData() {
                            const tracks = [];
                            const selectors = [
                                'ul.sc-list-nostyle li',
                                'div[role="main"] ul li',
                                'div.searchList__results div.sound__content',
                                'div.searchList li',
                                'div.sound'
                            ];
                            
                            for (const selector of selectors) {
                                const items = document.querySelectorAll(selector);
                                console.log(`Found ${items.length} items with selector ${selector}`);
                                
                                if (items.length > 0) {
                                    for (const item of items) {
                                        try {
                                            // Multiple selectors for title
                                            const titleSelectors = [
                                                'a[href*="/track/"]',
                                                'a.sc-link-primary',
                                                'a.soundTitle__title',
                                                'a[href*="soundcloud.com"][title]',
                                                'a.soundTitle__titleLink',
                                                'h2 a'
                                            ];
                                            
                                            // Multiple selectors for user
                                            const userSelectors = [
                                                'a.sc-link-secondary[href*="/"]',
                                                'a.soundTitle__username',
                                                'a[href*="soundcloud.com/"][class*="user"]',
                                                'div.soundTitle__usernameText a',
                                                'span.soundTitle__username a'
                                            ];
                                            
                                            let titleElement = null;
                                            for (const ts of titleSelectors) {
                                                const el = item.querySelector(ts);
                                                if (el) {
                                                    titleElement = el;
                                                    break;
                                                }
                                            }
                                            
                                            let userElement = null;
                                            for (const us of userSelectors) {
                                                const el = item.querySelector(us);
                                                if (el) {
                                                    userElement = el;
                                                    break;
                                                }
                                            }
                                            
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
                                                const durationSelectors = [
                                                    'span[aria-label*="Duration"]',
                                                    'span.duration',
                                                    'span[class*="duration"]',
                                                    'span[class*="time"]'
                                                ];
                                                
                                                for (const ds of durationSelectors) {
                                                    const durationElement = item.querySelector(ds);
                                                    if (durationElement) {
                                                        track.duration = durationElement.textContent.trim();
                                                        break;
                                                    }
                                                }
                                                
                                                // Only add if we don't already have this URL
                                                const exists = tracks.some(t => t.url === track.url);
                                                if (!exists) {
                                                    tracks.push(track);
                                                }
                                            }
                                        } catch (e) {
                                            console.error('Error processing track:', e);
                                        }
                                    }
                                }
                            }
                            
                            return tracks;
                        }
                        return getTrackData();
                    """)
                    
                    if not track_data:
                        logger.warning(f"[WARN][{search_id}] No track data extracted for query: {search_query}")
                        continue
                    
                    logger.info(f"[TRACE][{search_id}] Found {len(track_data)} tracks for query: {search_query}")
                    
                    # Store all results for later analysis
                    for track in track_data:
                        if not (blacklisted_urls and track['url'] in blacklisted_urls):
                            if not any(r['url'] == track['url'] for r in all_results):
                                all_results.append(track)
                    
                    # Find best match in this batch
                    for track in track_data:
                        # Skip blacklisted URLs
                        if blacklisted_urls and track['url'] in blacklisted_urls:
                            logger.info(f"[TRACE][{search_id}] Skipping blacklisted track: {track['url']}")
                            continue
                        
                        # Quick exact match check first (case insensitive)
                        track_title_lower = track['title'].lower()
                        if track_title_lower == track_name.lower() or track_title_lower == original_track_name.lower():
                            if artist_name:
                                track_artist_lower = track['user']['username'].lower()
                                # Check if any artist name variation matches
                                if any(artist.lower() == track_artist_lower for artist in artist_names):
                                    logger.info(f"[TRACE][{search_id}] Found exact match: {track['title']} by {track['user']['username']}")
                                    return track
                            else:
                                logger.info(f"[TRACE][{search_id}] Found exact match: {track['title']}")
                                return track
                        
                        # Calculate similarity scores
                        title_similarity = max(
                            self._calculate_similarity(track_name, track['title']),
                            self._calculate_similarity(original_track_name, track['title'])
                        )
                        
                        # Calculate artist similarity if artist name is provided
                        artist_similarity = 0
                        if artist_name:
                            track_artist = track['user']['username']
                            # Check similarity against all artist name variations
                            artist_similarities = [
                                self._calculate_similarity(artist, track_artist)
                                for artist in artist_names
                            ]
                            artist_similarity = max(artist_similarities)
                        else:
                            artist_similarity = 1.0  # Don't penalize if no artist name provided
                        
                        # Weighted similarity calculation with more weight on title
                        combined_similarity = (title_similarity * 0.75) + (artist_similarity * 0.25)
                        
                        # Additional boost for partial matches
                        if track_name.lower() in track_title_lower or original_track_name.lower() in track_title_lower:
                            combined_similarity = min(1.0, combined_similarity + 0.15)
                        
                        if artist_name and any(artist.lower() in track['user']['username'].lower() for artist in artist_names):
                            combined_similarity = min(1.0, combined_similarity + 0.1)
                        
                        if combined_similarity > highest_similarity:
                            highest_similarity = combined_similarity
                            best_match = track
                            search_stats['best_match_similarity'] = highest_similarity
                            logger.info(f"[TRACE][{search_id}] New best match: {track['title']} ({combined_similarity:.2f})")
                        
                        # Return immediately if we found a very good match
                        if highest_similarity > 0.9:
                            logger.info(f"[TRACE][{search_id}] Found excellent match: '{best_match['title']}' by {best_match['user']['username']}")
                            return best_match
                    
                    # Break search if we found a good enough match
                    if highest_similarity > 0.8:
                        logger.info(f"[TRACE][{search_id}] Breaking search early - found good match: {best_match['title']} ({highest_similarity:.2f})")
                        break
                        
                except Exception as e:
                    logger.error(f"[ERROR][{search_id}] Error with search query '{search_query}': {str(e)}")
                    search_stats['errors'].append({'phase': 'search_query', 'error': str(e)})
                    continue
            
            # If we didn't find a good match from individual searches, analyze all results together
            if (not best_match or highest_similarity <= 0.7) and all_results:
                logger.info(f"[TRACE][{search_id}] Analyzing all {len(all_results)} results together")
                
                # Re-analyze all collected results with more sophisticated matching
                for track in all_results:
                    # Skip if already checked or blacklisted
                    if blacklisted_urls and track['url'] in blacklisted_urls:
                        continue
                    
                    # Calculate fuzzy token similarity for titles
                    title_tokens_similarity = self._token_similarity(track_name, track['title'])
                    original_title_tokens_similarity = self._token_similarity(original_track_name, track['title'])
                    title_similarity = max(title_tokens_similarity, original_title_tokens_similarity)
                    
                    # Calculate artist similarity
                    artist_similarity = 0
                    if artist_name:
                        track_artist = track['user']['username']
                        # Calculate token similarity for artists
                        artist_similarities = [
                            self._token_similarity(artist, track_artist)
                            for artist in artist_names
                        ]
                        artist_similarity = max(artist_similarities)
                    else:
                        artist_similarity = 1.0
                    
                    # Weighted similarity with more sophisticated calculation
                    combined_similarity = (title_similarity * 0.75) + (artist_similarity * 0.25)
                    
                    # Special boost for exact word matches
                    track_title_words = set(re.findall(r'\w+', track['title'].lower()))
                    search_words = set(re.findall(r'\w+', track_name.lower()))
                    
                    # Calculate word overlap
                    if search_words:
                        word_overlap = len(track_title_words.intersection(search_words)) / len(search_words)
                        combined_similarity = min(1.0, combined_similarity + (word_overlap * 0.2))
                    
                    if combined_similarity > highest_similarity:
                        highest_similarity = combined_similarity
                        best_match = track
                        search_stats['best_match_similarity'] = highest_similarity
                        logger.info(f"[TRACE][{search_id}] New best match from all results: {track['title']} ({combined_similarity:.2f})")
            
            # Return best match if it's good enough
            if best_match and highest_similarity > 0.5:
                logger.info(f"[TRACE][{search_id}] Final best match with similarity {highest_similarity:.2f}: '{best_match['title']}' by {best_match['user']['username']}")
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

    def _clean_input(self, text: str) -> str:
        """Clean input text for better matching."""
        if not text:
            return ""
        # Remove emojis
        text = text.encode('ascii', 'ignore').decode('ascii')
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove special characters at beginning/end
        text = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', text).strip()
        return text
        
    def _token_similarity(self, str1: str, str2: str) -> float:
        """Calculate token-based similarity between strings."""
        if not str1 or not str2:
            return 0.0
            
        # Convert to lowercase and tokenize
        tokens1 = set(re.findall(r'\w+', str1.lower()))
        tokens2 = set(re.findall(r'\w+', str2.lower()))
        
        # Calculate Jaccard similarity
        if not tokens1 or not tokens2:
            return 0.0
            
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        
        return intersection / union if union > 0 else 0.0

    def search_tracks(self, query: str) -> List[Dict]:
        """Search for tracks on SoundCloud."""
        if not self.browser:
            logger.warning("SoundCloud browser not initialized")
            return []
        return []  # Will be implemented with actual API integration later 
        return []  # Will be implemented with actual API integration later 