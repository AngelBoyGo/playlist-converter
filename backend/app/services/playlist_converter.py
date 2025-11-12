import logging
from typing import Dict, List, Optional, Any
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import asyncio
import re
import unicodedata
from urllib.parse import quote
from datetime import datetime
import time
import json
from .utils import normalize_text, retry_with_exponential_backoff

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for better matching."""
    if not text:
        return ""
    # Convert to lowercase
    text = text.lower()
    # Remove accents
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    # Remove special characters but keep spaces and hyphens
    text = re.sub(r"[^\w\s-]", " ", text)
    # Remove extra whitespace
    text = " ".join(text.split())
    # Remove common stop words
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
    }
    words = text.split()
    words = [w for w in words if w.lower() not in stop_words]
    return " ".join(words)


def calculate_similarity(a: str, b: str) -> float:
    """Calculate similarity between two strings."""
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    # Calculate word overlap
    a_words = set(a.split())
    b_words = set(b.split())
    common_words = a_words & b_words

    if not common_words:
        return 0.0

    # Calculate Jaccard similarity
    similarity = len(common_words) / len(a_words | b_words)

    # Boost score if one string contains the other
    if a in b or b in a:
        similarity += 0.3

    # Boost score if they start with the same word
    if a.split()[0] == b.split()[0]:
        similarity += 0.2

    return min(similarity, 1.0)


class PlaylistConverter:
    def __init__(self, max_retries=3, retry_delay=2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.browser = None
        self.wait = None
        self._initialized = False
        logger.debug(
            f"Initializing PlaylistConverter (max_retries={max_retries}, retry_delay={retry_delay})"
        )

    async def initialize_browser(self):
        """Initialize the browser with proper async handling."""
        if self._initialized:
            return

        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")

            self.browser = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.browser, 10)
            self._initialized = True
            logger.info("Browser initialized successfully for converter")

        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            if self.browser:
                await self.cleanup()
            raise

    async def cleanup(self):
        """Clean up browser resources with proper async handling."""
        try:
            if self.browser:
                self.browser.quit()
                self.browser = None
                self.wait = None
                self._initialized = False
                logger.info("Browser resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during browser cleanup: {str(e)}")

    async def convert_to_soundcloud(self, playlist_data: Dict) -> Dict:
        """Convert playlist to SoundCloud format."""
        if not self._initialized:
            await self.initialize_browser()

        try:
            playlist_name = playlist_data.get("name", "Unknown Playlist")
            logger.info(f"Starting conversion of playlist: {playlist_name}")

            tracks = playlist_data.get("tracks", [])
            total_tracks = len(tracks)

            if total_tracks == 0:
                raise Exception("No tracks to convert")

            converted_tracks = []
            success_count = 0

            for idx, track in enumerate(tracks, 1):
                try:
                    track_name = track.get("name", "").strip()
                    artists = track.get("artists", [])
                    artist_name = artists[0].strip() if artists else ""

                    if not track_name:
                        logger.warning(f"Track {idx}: Missing track name")
                        continue

                    search_query = f"{track_name} {artist_name}".strip()
                    logger.info(
                        f"Processing track {idx}/{total_tracks}: {search_query}"
                    )

                    # Simulate SoundCloud search with a delay
                    await asyncio.sleep(0.5)  # Simulate API call

                    # Create a simulated match
                    normalized_name = track_name.lower().replace(" ", "-")
                    soundcloud_track = {
                        "id": hash(search_query),
                        "title": track_name,
                        "user": {"username": artist_name},
                        "duration": 180000,  # 3 minutes in milliseconds
                        "url": f"https://soundcloud.com/{normalized_name}",
                        "permalink_url": f"https://soundcloud.com/track/{normalized_name}",
                        "artwork_url": "https://example.com/artwork.jpg",
                        "stream_url": f"https://api.soundcloud.com/tracks/{hash(search_query)}",
                    }

                    converted_track = {
                        "original": track,
                        "converted": soundcloud_track,
                        "success": True,
                        "status": "converted",
                        "conversion_progress": (idx / total_tracks) * 100,
                    }

                    converted_tracks.append(converted_track)
                    success_count += 1
                    logger.info(f"Successfully converted track: {track_name}")

                except Exception as e:
                    logger.error(f"Error converting track {idx}: {str(e)}")
                    converted_tracks.append(
                        {
                            "original": track,
                            "success": False,
                            "status": "error",
                            "error": str(e),
                            "conversion_progress": (idx / total_tracks) * 100,
                        }
                    )

            success_rate = success_count / total_tracks if total_tracks > 0 else 0

            result = {
                "name": playlist_name,
                "tracks": converted_tracks,
                "total_tracks": total_tracks,
                "converted_tracks": success_count,
                "success_rate": success_rate,
                "status": "completed",
                "platform": "SoundCloud",
            }

            logger.info(
                f"Conversion completed. Success rate: {success_rate * 100:.1f}%"
            )
            return result

        except Exception as e:
            logger.error(f"Error during conversion: {str(e)}")
            raise
        finally:
            # Only cleanup after the entire conversion is done
            await self.cleanup()

    def find_best_match(
        self, track: Dict, search_results: List[Dict]
    ) -> Optional[Dict]:
        """Find the best matching track from search results."""
        try:
            if not search_results:
                return None

            track_name = track.get("name", "").lower()
            artists = [a.lower() for a in track.get("artists", [])]

            best_match = None
            highest_score = 0

            for result in search_results:
                result_name = result.get("title", "").lower()
                result_artist = result.get("user", {}).get("username", "").lower()

                # Calculate name similarity
                name_similarity = calculate_similarity(track_name, result_name)

                # Calculate artist similarity
                artist_similarity = (
                    max(
                        calculate_similarity(artist, result_artist)
                        for artist in artists
                    )
                    if artists
                    else 0
                )

                # Combined score (weighted)
                score = (name_similarity * 0.7) + (artist_similarity * 0.3)

                if score > highest_score and score > 0.5:  # Minimum threshold
                    highest_score = score
                    best_match = result

            return best_match

        except Exception as e:
            logger.error(f"Error finding best match: {str(e)}")
            return None

    async def _search_soundcloud(self, query: str) -> List[Dict[str, Any]]:
        """Search for tracks on SoundCloud."""
        try:
            # For now, return simulated results
            # In a real implementation, this would make an API call to SoundCloud
            await asyncio.sleep(0.5)  # Simulate API call delay

            # Create a more realistic mock result
            normalized_query = query.lower().replace(" ", "-")
            return [
                {
                    "title": query,
                    "user": {"username": "artist"},
                    "duration": 180000,
                    "url": f"https://soundcloud.com/example/{normalized_query}",
                    "permalink_url": f"https://soundcloud.com/example/{normalized_query}",
                    "stream_url": f"https://api.soundcloud.com/tracks/{hash(query)}",
                    "artwork_url": "https://example.com/artwork.jpg",
                }
            ]

        except Exception as e:
            logger.error(f"Error searching SoundCloud: {str(e)}")
            return []
