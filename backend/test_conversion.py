import asyncio
import logging
import sys
import traceback
from typing import Dict, Any, Optional
from datetime import datetime

from backend.app.services.playlist_scraper import PlaylistScraper, BrowserInitializationError, ScrapingError
from backend.app.services.playlist_converter import PlaylistConverter
from backend.app.services.soundcloud import SoundCloudService

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_conversion.log', mode='w')  # 'w' mode to start fresh
    ]
)

logger = logging.getLogger(__name__)

class TestError(Exception):
    """Base exception for test-specific errors"""
    pass

class ScraperInitError(TestError):
    """Failed to initialize scraper"""
    pass

class ConverterInitError(TestError):
    """Failed to initialize converter"""
    pass

class PlaylistFetchError(TestError):
    """Failed to fetch playlist data"""
    pass

class ConversionError(TestError):
    """Failed to convert playlist"""
    pass

def log_test_phase(phase: str, details: Dict[str, Any] = None) -> None:
    """Log detailed information about the current test phase."""
    separator = "=" * 50
    logger.info(f"\n{separator}")
    logger.info(f"Test Phase: {phase}")
    if details:
        for key, value in details.items():
            logger.info(f"{key}: {value}")
    logger.info(separator)

def log_track_details(track: Dict[str, Any], prefix: str = "") -> None:
    """Log detailed information about a track."""
    logger.info(f"{prefix}Track: {track.get('name', 'Unknown')}")
    logger.info(f"{prefix}Artists: {', '.join(track.get('artists', ['Unknown']))}")
    logger.info(f"{prefix}Status: {track.get('status', 'Unknown')}")
    if 'error' in track:
        logger.warning(f"{prefix}Error: {track['error']}")
    if 'success' in track:
        logger.info(f"{prefix}Success: {track['success']}")
    if 'conversion_progress' in track:
        logger.info(f"{prefix}Progress: {track['conversion_progress']}%")

async def initialize_services():
    """Initialize scraper and converter services with detailed error handling."""
    scraper = None
    converter = None
    
    try:
        logger.info("Starting service initialization...")
        
        logger.info("Initializing scraper...")
        scraper = PlaylistScraper(max_retries=3, retry_delay=2)
        logger.info("Scraper initialized successfully")
        
        logger.info("Initializing converter...")
        converter = PlaylistConverter(max_retries=3, retry_delay=2)
        logger.info("Converter initialized successfully")
        
        return scraper, converter
        
    except Exception as e:
        logger.error("Service initialization failed", exc_info=True)
        if scraper:
            await scraper.cleanup()
        if converter:
            await converter.cleanup()
        raise ScraperInitError(f"Failed to initialize services: {str(e)}")

async def fetch_playlist_data(scraper: PlaylistScraper, url: str) -> Dict[str, Any]:
    """Fetch playlist data with detailed error handling."""
    try:
        logger.info("Starting playlist fetch process...")
        
        logger.info("Initializing browser for scraper...")
        await scraper.initialize_browser()
        logger.info("Browser initialized successfully")
        
        logger.info(f"Fetching playlist from URL: {url}")
        playlist_data = await scraper.get_apple_music_playlist_data(url)
        
        if not playlist_data:
            raise PlaylistFetchError("Playlist data is empty")
            
        logger.info("Successfully fetched playlist data:")
        logger.info(f"Playlist Name: {playlist_data.get('name', 'Unknown')}")
        logger.info(f"Total Tracks: {len(playlist_data.get('tracks', []))}")
        
        # Log first 5 tracks for verification
        logger.info("\nFirst 5 tracks in playlist:")
        for idx, track in enumerate(playlist_data.get('tracks', [])[:5], 1):
            logger.info(f"\nTrack {idx}:")
            log_track_details(track, prefix="  ")
        
        return playlist_data
        
    except BrowserInitializationError as e:
        logger.error("Browser initialization failed", exc_info=True)
        raise PlaylistFetchError(f"Browser initialization failed: {str(e)}")
    except ScrapingError as e:
        logger.error("Scraping failed", exc_info=True)
        raise PlaylistFetchError(f"Scraping error: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during playlist fetch", exc_info=True)
        raise PlaylistFetchError(f"Unexpected error: {str(e)}")

async def convert_playlist_data(converter: PlaylistConverter, playlist_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert playlist data with detailed error handling."""
    try:
        logger.info("Starting playlist conversion process...")
        
        logger.info("Initializing browser for converter...")
        converter._init_browser()
        logger.info("Browser initialized successfully")
        
        total_tracks = len(playlist_data.get('tracks', []))
        logger.info(f"Beginning conversion of {total_tracks} tracks...")
        
        converted_data = await converter.convert_playlist(playlist_data, "soundcloud")
        
        if not converted_data:
            raise ConversionError("Conversion produced no data")
            
        # Log conversion results
        success_count = sum(1 for track in converted_data.get('tracks', []) if track.get('success', False))
        logger.info("\nConversion Results:")
        logger.info(f"Total Tracks Processed: {total_tracks}")
        logger.info(f"Successfully Converted: {success_count}")
        logger.info(f"Success Rate: {(success_count/total_tracks)*100:.2f}%")
        
        # Log details of first 5 converted tracks
        logger.info("\nFirst 5 converted tracks:")
        for idx, track in enumerate(converted_data.get('tracks', [])[:5], 1):
            logger.info(f"\nConverted Track {idx}:")
            log_track_details(track, prefix="  ")
        
        return converted_data
        
    except Exception as e:
        logger.error("Playlist conversion failed", exc_info=True)
        raise ConversionError(f"Conversion error: {str(e)}")

async def test_playlist_conversion():
    """Test the playlist conversion process."""
    scraper = None
    soundcloud = None
    
    try:
        # Test playlist URL
        playlist_url = "https://music.apple.com/us/playlist/levitated/pl.u-vxy6696sz1VKqBX"
        
        logger.info("Initializing services...")
        
        # Initialize scraper
        scraper = PlaylistScraper()
        await scraper.initialize_browser()
        logger.info("Scraper initialized successfully")
        
        # Initialize SoundCloud service
        soundcloud = SoundCloudService()
        await soundcloud.initialize_browser()
        logger.info("SoundCloud service initialized successfully")
        
        # Fetch playlist data
        logger.info(f"Fetching playlist data from: {playlist_url}")
        playlist_data = await scraper.get_apple_music_playlist_data(playlist_url)
        
        if not playlist_data:
            raise Exception("Failed to fetch playlist data")
            
        logger.info(f"Successfully fetched playlist: {playlist_data.get('name', 'Unknown')}")
        logger.info(f"Total tracks: {len(playlist_data.get('tracks', []))}")
        
        # Process first track as a test
        if playlist_data.get('tracks'):
            track = playlist_data['tracks'][0]
            track_name = track.get('name', '').strip()
            artists = track.get('artists', [])
            artist_name = artists[0] if artists else None
            
            logger.info(f"Testing conversion with first track: {track_name} by {artist_name}")
            
            # Search for track on SoundCloud
            soundcloud_track = await soundcloud.search_track(track_name, artist_name)
            
            if soundcloud_track:
                logger.info(f"Successfully found match on SoundCloud: {soundcloud_track.get('title')}")
            else:
                logger.warning("No match found on SoundCloud")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        return False
    finally:
        # Cleanup
        if soundcloud:
            try:
                await soundcloud.cleanup()
                logger.info("SoundCloud service cleaned up")
            except Exception as e:
                logger.error(f"Failed to cleanup SoundCloud service: {str(e)}")
                
        if scraper:
            try:
                await scraper.cleanup()
                logger.info("Scraper cleaned up")
            except Exception as e:
                logger.error(f"Failed to cleanup scraper: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting test...")
    asyncio.run(test_playlist_conversion()) 