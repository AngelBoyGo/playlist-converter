import sys
import os
import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.app.services.playlist_scraper import PlaylistScraper
from backend.app.services.soundcloud import SoundCloudService
import re
from backend.app.routes.debug import router as debug_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Log system information at startup
logger.info(f"Python version: {sys.version}")
logger.info(f"Python executable: {sys.executable}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Module search paths: {sys.path}")
logger.info(f"Environment variables: PATH={os.environ.get('PATH', 'Not set')}")
logger.info(f"Chrome env vars: GOOGLE_CHROME_BIN={os.environ.get('GOOGLE_CHROME_BIN', 'Not set')}, CHROMEDRIVER_PATH={os.environ.get('CHROMEDRIVER_PATH', 'Not set')}")

# Define request and response models
class ConversionRequest(BaseModel):
    url: str
    target_platform: str
    start_index: int = 0
    batch_size: int = 5

class Track(BaseModel):
    name: str
    artists: List[str]
    position: int
    url: Optional[str] = None

class ConversionResponse(BaseModel):
    tracks: List[Track]
    total_tracks: int
    playlist_name: str
    source_platform: str
    target_platform: str
    message: Optional[str] = None

class SearchRequest(BaseModel):
    track_name: str
    artist_name: Optional[str] = None
    exclude_current: Optional[bool] = False
    blacklisted_urls: Optional[List[str]] = None

# Initialize the FastAPI app
app = FastAPI(
    title="Playlist Converter API",
    description="Convert playlists between different music streaming platforms",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, you should specify the exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include debug routes
app.include_router(debug_router, prefix="/debug", tags=["debug"])

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
    logger.info("Mounted static files successfully")
except Exception as e:
    logger.error(f"Failed to mount static files: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def get_root():
    """Serve the root HTML file."""
    try:
        with open("../frontend/index.html") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"Failed to read index.html: {str(e)}")
        return HTMLResponse(content="Internal Server Error", status_code=500)

@app.post("/api/convert", response_model=ConversionResponse)
async def convert_playlist(request: ConversionRequest):
    """Convert a playlist from one platform to another."""
    logger.info(f"Received conversion request: {request.dict()}")
    
    try:
        # Initialize the playlist scraper
        playlist_scraper = PlaylistScraper()
        try:
            await playlist_scraper.initialize_browser()
            logger.info("Successfully initialized playlist scraper browser")
        except Exception as browser_err:
            logger.error(f"Failed to initialize browser: {str(browser_err)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to initialize browser: {str(browser_err)}")
        
        # Get the playlist data
        try:
            playlist_data = await playlist_scraper.get_playlist_data(request.url)
            logger.info(f"Successfully scraped playlist: {playlist_data.get('name', 'Unknown')}")
        except Exception as scrape_err:
            logger.error(f"Error scraping playlist: {str(scrape_err)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error during playlist scraping: {str(scrape_err)}")
        finally:
            # Always clean up the browser
            await playlist_scraper.cleanup()
        
        # Initialize SoundCloud service if needed
        soundcloud = None
        if request.target_platform.lower() == "soundcloud":
            try:
                soundcloud = SoundCloudService()
                await soundcloud.initialize_browser()
                logger.info("Successfully initialized SoundCloud service browser")
            except Exception as sc_err:
                logger.error(f"Failed to initialize SoundCloud browser: {str(sc_err)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Failed to initialize SoundCloud browser: {str(sc_err)}")
        
        # Get a batch of tracks
        tracks = playlist_data.get("tracks", [])
        start = request.start_index
        end = min(start + request.batch_size, len(tracks))
        batch = tracks[start:end]
        
        # Convert tracks
        converted_tracks = []
        for track in batch:
            try:
                track_name = track.get("name", "").strip()
                artists = track.get("artists", [])
                artist_name = artists[0] if artists else None
                
                # Search for track on target platform
                target_url = None
                if request.target_platform.lower() == "soundcloud" and soundcloud:
                    result = await soundcloud.search_track(track_name, artist_name)
                    if result:
                        target_url = result.get("url")
                
                # Create track object
                converted_track = Track(
                    name=track_name,
                    artists=artists,
                    position=track.get("position", 0),
                    url=target_url
                )
                converted_tracks.append(converted_track)
                logger.info(f"Converted track: {track_name}")
            except Exception as track_err:
                logger.error(f"Error converting track {track.get('name', 'Unknown')}: {str(track_err)}")
                # Continue with next track rather than failing the whole request
        
        # Clean up SoundCloud browser
        if soundcloud:
            await soundcloud.cleanup()
        
        # Create response
        response = ConversionResponse(
            tracks=converted_tracks,
            total_tracks=len(tracks),
            playlist_name=playlist_data.get("name", "Unknown Playlist"),
            source_platform=playlist_data.get("platform", "Unknown"),
            target_platform=request.target_platform,
            message=f"Converted {len(converted_tracks)} of {len(tracks)} tracks"
        )
        
        return response
    except Exception as e:
        error_msg = f"Error during conversion process: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/health")
async def health_check():
    """Health check endpoint to verify the service is running."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# Search endpoint
@app.post("/api/search")
async def search_track(request: SearchRequest):
    """Search for a track on SoundCloud with support for blacklisting."""
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"[TRACE][{request_id}] Starting track search: {request.dict()}")
    
    sc_service = None
    try:
        sc_service = SoundCloudService()
        await sc_service.initialize_browser()
        
        result = await sc_service.search_track(
            request.track_name,
            request.artist_name,
            request.blacklisted_urls
        )
        
        if result:
            return {
                "success": True,
                "matches": [result]
            }
        else:
            return {
                "success": False,
                "message": "No matches found"
            }
            
    except Exception as e:
        logger.error(f"[ERROR][{request_id}] Search failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Search failed: {str(e)}"
        }
    finally:
        if sc_service:
            await sc_service.cleanup()

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="debug") 