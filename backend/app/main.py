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
from app.services.playlist_scraper import PlaylistScraper
from app.services.soundcloud import SoundCloudService
import re

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

# Define request and response models
class ConversionRequest(BaseModel):
    url: str
    target_platform: str
    start_index: int = 0
    batch_size: int = 5

class TrackResult(BaseModel):
    source_track: Dict[str, Any]
    target_track: Optional[Dict[str, Any]] = None
    success: bool
    message: Optional[str] = None

class ConversionDetails(BaseModel):
    converted_tracks: int
    total_tracks: int
    success_rate: float
    tracks: List[Dict[str, Any]]
    current_batch: Optional[Dict[str, Any]] = None

class ConversionResponse(BaseModel):
    success: bool
    message: str
    success_count: int
    failure_count: int
    results: List[TrackResult]
    details: ConversionDetails

class SearchRequest(BaseModel):
    track_name: str
    artist_name: Optional[str] = None
    exclude_current: Optional[bool] = False
    blacklisted_urls: Optional[List[str]] = None

# Initialize FastAPI app
app = FastAPI(title="Playlist Converter API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create API router with /api prefix
api_router = APIRouter(prefix="/api")

def create_error_response(message: str, request_id: str = None) -> ConversionResponse:
    """Helper function to create standardized error responses"""
    if request_id:
        logger.error(f"[ERROR][{request_id}] {message}")
    return ConversionResponse(
        success=False,
        message=message,
        success_count=0,
        failure_count=0,
        results=[],
        details=ConversionDetails(
            converted_tracks=0,
            total_tracks=0,
            success_rate=0.0,
            tracks=[]
        )
    )

def create_success_response(
    success_count: int,
    failure_count: int,
    results: List[TrackResult],
    converted_tracks: List[Dict[str, Any]],
    request_id: str,
    current_batch: Optional[Dict[str, Any]] = None
) -> ConversionResponse:
    """Helper function to create standardized success responses"""
    total_tracks = success_count + failure_count
    success_rate = (success_count / total_tracks) if total_tracks > 0 else 0.0
    
    response = ConversionResponse(
        success=True,
        message=f"Conversion completed with {success_count} successes and {failure_count} failures.",
        success_count=success_count,
        failure_count=failure_count,
        results=results,
        details=ConversionDetails(
            converted_tracks=success_count,
            total_tracks=total_tracks,
            success_rate=success_rate,
            tracks=converted_tracks,
            current_batch=current_batch
        )
    )
    
    logger.info(f"[TRACE][{request_id}] Created success response: {response.dict()}")
    return response

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Simple health check endpoint to verify API is running."""
    logger.info("[TRACE] Health check endpoint called")
    return {"status": "ok", "message": "API is running"}

# Playlist conversion endpoint
@api_router.post("/convert", response_model=ConversionResponse)
async def convert_playlist(request: ConversionRequest):
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"[TRACE][{request_id}] Starting conversion process for URL: {request.url}")
    logger.info(f"[TRACE][{request_id}] Request data: {request.dict()}")
    
    conversion_stats = {
        'request_id': request_id,
        'start_time': datetime.now(),
        'scraper_init_success': False,
        'soundcloud_init_success': False,
        'playlist_fetch_success': False,
        'tracks_processed': 0,
        'tracks_found': 0,
        'search_attempts': 0,
        'search_successes': 0,
        'errors': []
    }
    
    scraper = None
    sc_service = None
    
    try:
        # Initialize services
        scraper = PlaylistScraper()
        await scraper.initialize_browser()
        conversion_stats['scraper_init_success'] = True
        logger.info(f"[TRACE][{request_id}] Scraper initialized successfully")
        
        sc_service = SoundCloudService()
        await sc_service.initialize_browser()
        conversion_stats['soundcloud_init_success'] = True
        logger.info(f"[TRACE][{request_id}] SoundCloud service initialized successfully")
        
        # Get playlist data using the new platform-agnostic method
        try:
            playlist_data = await scraper.get_playlist_data(request.url)
            if not playlist_data:
                error_msg = "Failed to fetch playlist data: No data returned"
                logger.error(f"[ERROR][{request_id}] {error_msg}")
                return create_error_response(error_msg, request_id)
            
            conversion_stats['playlist_fetch_success'] = True
            logger.info(f"[TRACE][{request_id}] Successfully fetched playlist: {playlist_data.get('name', 'Unknown')} from {playlist_data.get('platform', 'Unknown platform')}")
            logger.debug(f"[DEBUG][{request_id}] Raw playlist data: {playlist_data}")
        except Exception as e:
            error_msg = f"Failed to fetch playlist data: {str(e)}"
            logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
            return create_error_response(error_msg, request_id)
        
        # Process tracks with pagination
        tracks = playlist_data.get('tracks', [])
        if not tracks:
            error_msg = "No tracks found in the playlist"
            logger.error(f"[ERROR][{request_id}] {error_msg}")
            return create_error_response(error_msg, request_id)
        
        conversion_stats['tracks_found'] = len(tracks)
        logger.info(f"[TRACE][{request_id}] Found {len(tracks)} tracks in playlist")
        
        results = []
        success_count = 0
        failure_count = 0
        converted_tracks = []
        
        # Get the batch of tracks based on start_index and batch_size
        start_idx = request.start_index
        end_idx = min(start_idx + request.batch_size, len(tracks))
        batch_tracks = tracks[start_idx:end_idx]
        
        # Process tracks in the current batch
        for i, track in enumerate(batch_tracks, start=start_idx):
            try:
                track_name = track.get('name', 'Unknown Track')
                artists = track.get('artists', ['Unknown Artist'])
                artist_str = ", ".join(artists)
                
                logger.info(f"[TRACE][{request_id}] Processing track {i+1}/{len(tracks)}: '{track_name}' by {artist_str}")
                
                try:
                    sc_track = await sc_service.search_track(track_name, artist_str)
                    if sc_track:
                        logger.info(f"[TRACE][{request_id}] Found match: '{sc_track.get('title')}' by {sc_track.get('user', {}).get('username')}")
                        
                        track_result = TrackResult(
                            source_track=track,
                            target_track=sc_track,
                            success=True,
                            message="Successfully found on SoundCloud"
                        )
                        
                        converted_track = {
                            "original": track,
                            "converted": sc_track,
                            "success": True,
                            "error": None
                        }
                        
                        results.append(track_result)
                        converted_tracks.append(converted_track)
                        success_count += 1
                        
                        logger.info(f"[TRACE][{request_id}] Successfully processed track {i+1}")
                    else:
                        msg = f"No matches found for '{track_name}' by {artist_str}"
                        logger.warning(f"[WARN][{request_id}] {msg}")
                        
                        track_result = TrackResult(
                            source_track=track,
                            success=False,
                            message=msg
                        )
                        
                        converted_track = {
                            "original": track,
                            "converted": None,
                            "success": False,
                            "error": msg
                        }
                        
                        results.append(track_result)
                        converted_tracks.append(converted_track)
                        failure_count += 1
                except Exception as search_error:
                    error_msg = f"Error searching track '{track_name}': {str(search_error)}"
                    logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
                    
                    track_result = TrackResult(
                        source_track=track,
                        success=False,
                        message=error_msg
                    )
                    
                    converted_track = {
                        "original": track,
                        "converted": None,
                        "success": False,
                        "error": error_msg
                    }
                    
                    results.append(track_result)
                    converted_tracks.append(converted_track)
                    failure_count += 1
            except Exception as track_error:
                error_msg = f"Error processing track: {str(track_error)}"
                logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
                
                track_result = TrackResult(
                    source_track=track,
                    success=False,
                    message=error_msg
                )
                
                converted_track = {
                    "original": track,
                    "converted": None,
                    "success": False,
                    "error": error_msg
                }
                
                results.append(track_result)
                converted_tracks.append(converted_track)
                failure_count += 1
            
            conversion_stats['tracks_processed'] += 1
        
        # Create success response with pagination info
        logger.info(f"[TRACE][{request_id}] Conversion completed. Stats: {conversion_stats}")
        response = create_success_response(
            success_count=success_count,
            failure_count=failure_count,
            results=results,
            converted_tracks=converted_tracks,
            request_id=request_id,
            current_batch={
                "start": start_idx,
                "end": end_idx,
                "has_more": end_idx < len(tracks)
            }
        )
        
        return response
        
    except Exception as e:
        error_msg = f"Error during conversion process: {str(e)}"
        logger.error(f"[ERROR][{request_id}] {error_msg}", exc_info=True)
        logger.error(f"[ERROR][{request_id}] Final conversion stats: {conversion_stats}")
        return create_error_response(error_msg, request_id)
        
    finally:
        # Cleanup
        logger.info(f"[TRACE][{request_id}] Cleaning up resources")
        if sc_service:
            try:
                await sc_service.cleanup()
                logger.info(f"[TRACE][{request_id}] SoundCloud service cleaned up")
            except Exception as e:
                logger.error(f"[ERROR][{request_id}] Error cleaning up SoundCloud service: {str(e)}", exc_info=True)
        
        if scraper:
            try:
                await scraper.cleanup()
                logger.info(f"[TRACE][{request_id}] Scraper cleaned up")
            except Exception as e:
                logger.error(f"[ERROR][{request_id}] Error cleaning up scraper: {str(e)}", exc_info=True)

# Search endpoint
@api_router.post("/search")
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

# IMPORTANT: Include the API router in the main app
app.include_router(api_router)

# Mount static files - make sure this comes AFTER the API routes
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "frontend"))
logger.info(f"Serving frontend from: {frontend_dir}")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

# Root path handler for index.html
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = os.path.join(frontend_dir, "index.html")
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="debug") 