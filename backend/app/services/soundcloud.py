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
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.browser = webdriver.Chrome(options=chrome_options)
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