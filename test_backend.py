import asyncio
import logging
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_backend.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

async def test_service_initialization():
    """Test that the scraper and soundcloud services can initialize properly."""
    try:
        # Add the current directory to the Python path
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, backend_dir)
        
        logger.info(f"Testing backend services initialization")
        logger.info(f"Python path: {sys.path}")
        
        # Try to import the services
        try:
            from backend.app.services.playlist_scraper import PlaylistScraper
            from backend.app.services.soundcloud import SoundCloudService
            logger.info("Successfully imported services using 'backend.app' prefix")
        except ImportError as e:
            logger.error(f"Import error with 'backend.app' prefix: {str(e)}")
            try:
                from app.services.playlist_scraper import PlaylistScraper
                from app.services.soundcloud import SoundCloudService
                logger.info("Successfully imported services using 'app' prefix")
            except ImportError as e:
                logger.error(f"Import error with 'app' prefix: {str(e)}")
                raise ImportError("Failed to import required services")
        
        # Initialize the services
        logger.info("Initializing PlaylistScraper")
        scraper = PlaylistScraper()
        await scraper.initialize_browser()
        logger.info("Successfully initialized PlaylistScraper")
        
        logger.info("Initializing SoundCloudService")
        soundcloud = SoundCloudService()
        await soundcloud.initialize_browser()
        logger.info("Successfully initialized SoundCloudService")
        
        # Test a simple playlist URL
        test_url = "https://music.apple.com/us/playlist/levitated/pl.u-vxy6696sz1VKqBX"
        logger.info(f"Testing playlist fetching with URL: {test_url}")
        
        playlist_data = await scraper.get_apple_music_playlist_data(test_url)
        if playlist_data:
            logger.info(f"Successfully fetched playlist: {playlist_data.get('name', 'Unknown')}")
            logger.info(f"Found {len(playlist_data.get('tracks', []))} tracks")
            
            # Try to search for the first track
            if playlist_data.get('tracks'):
                first_track = playlist_data['tracks'][0]
                track_name = first_track.get('name', '')
                artist_name = first_track.get('artists', [''])[0] if first_track.get('artists') else ''
                
                logger.info(f"Testing track search with: {track_name} by {artist_name}")
                result = await soundcloud.search_track(track_name, artist_name)
                
                if result:
                    logger.info(f"Successfully found match: {result.get('title', '')}")
                else:
                    logger.warning("No match found for track")
        else:
            logger.error("Failed to fetch playlist data")
        
        # Cleanup
        logger.info("Cleaning up resources")
        await scraper.cleanup()
        await soundcloud.cleanup()
        
        logger.info("Test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("Starting backend services test")
    asyncio.run(test_service_initialization()) 