import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class SpotifyService:
    """Service for interacting with Spotify API."""
    
    def __init__(self):
        """Initialize Spotify client."""
        logger.debug("Initializing SpotifyService...")
        try:
            # Initialize without credentials for now
            self.client = None
            logger.info("SpotifyService initialized (without credentials)")
        except Exception as e:
            logger.error("Failed to initialize SpotifyService", exc_info=e)
            raise

    def playlist(self, playlist_id: str) -> Dict:
        """Get playlist data from Spotify."""
        if not self.client:
            logger.warning("Spotify client not configured")
            return {
                "name": "Untitled Playlist",
                "tracks": {"items": []},
                "total": 0
            }
        return self.client.playlist(playlist_id) 