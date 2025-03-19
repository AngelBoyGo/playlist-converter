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
import time
import uuid
from fastapi import BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.exceptions import HTTPException
from contextlib import asynccontextmanager

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
    # Add detailed progress tracking
    processing_phase: str = "initializing"
    detailed_status: str = "Starting conversion process"
    last_action_time: Optional[str] = None
    performance_stats: Optional[Dict[str, Any]] = None

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

# Helper functions
def get_request_id():
    """Generate a unique ID for each request."""
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]

@asynccontextmanager
async def timeout_context(seconds: int):
    """Context manager for handling timeouts in async functions."""
    try:
        yield
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(f"Operation timed out after {seconds} seconds")

def is_valid_url(url: str) -> bool:
    """Validate if the URL has a proper format."""
    if not url:
        return False
    url_pattern = re.compile(
        r'^(?:http|https)://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    return bool(url_pattern.match(url))

# Create API router with /api prefix
api_router = APIRouter(prefix="/api")

# Health check endpoint
@api_router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

def create_error_response(message: str, request_id: str = None, progress: Dict = None) -> ConversionResponse:
    """Helper function to create standardized error responses"""
    if request_id:
        logger.error(f"[ERROR][{request_id}] {message}")
    
    # Default progress values if not provided
    if not progress:
        progress = {
            'processing_phase': 'error',
            'detailed_status': message,
            'last_action_time': datetime.now().isoformat()
        }
    
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
            tracks=[],
            processing_phase=progress.get('processing_phase', 'error'),
            detailed_status=progress.get('detailed_status', message),
            last_action_time=progress.get('last_action_time', datetime.now().isoformat())
        )
    )

def create_success_response(
    success_count: int,
    failure_count: int,
    results: List[TrackResult],
    converted_tracks: List[Dict[str, Any]],
    request_id: str,
    current_batch: Dict[str, Any],
    processing_phase: str = "complete",
    detailed_status: str = "Conversion complete",
    last_action_time: str = None,
    performance_stats: Dict[str, Any] = None
) -> ConversionResponse:
    """Helper function to create standardized success responses"""
    
    # Calculate success rate
    total_tracks = success_count + failure_count
    success_rate = success_count / total_tracks if total_tracks > 0 else 0
    
    if not last_action_time:
        last_action_time = datetime.now().isoformat()
    
    return ConversionResponse(
        success=True,
        message=f"Successfully converted {success_count} of {total_tracks} tracks",
        success_count=success_count,
        failure_count=failure_count,
        results=results,
        details=ConversionDetails(
            converted_tracks=success_count,
            total_tracks=total_tracks,
            success_rate=success_rate,
            tracks=converted_tracks,
            current_batch=current_batch,
            processing_phase=processing_phase,
            detailed_status=detailed_status,
            last_action_time=last_action_time,
            performance_stats=performance_stats
        )
    )

# Playlist conversion endpoint
@api_router.post("/convert", response_model=ConversionResponse)
async def convert_playlist(
    request: ConversionRequest,
    background_tasks: BackgroundTasks,
    request_id: str = Depends(get_request_id),
):
    """
    Convert a playlist from one streaming service to another.
    
    Args:
        request: The conversion request containing the playlist URL and target platform.
        background_tasks: FastAPI background tasks object for cleanup.
        request_id: A unique identifier for this request.
        
    Returns:
        A response containing the conversion results.
    """
    # Helper function to update progress tracking
    def update_progress(response, phase, status, detailed_status):
        """Helper to update progress tracking"""
        response.details.processing_phase = phase
        response.details.detailed_status = status
        response.details.last_action_time = datetime.now().isoformat()
        logger.info(f"[TRACE][{request_id}] Progress: {phase} - {status}")
    
    # Initialize response
    response = ConversionResponse(
        success=False,
        message="Processing your request...",
        success_count=0,
        failure_count=0,
        results=[],
        details=ConversionDetails(
            converted_tracks=0,
            total_tracks=0,
            success_rate=0.0,
            tracks=[],
            processing_phase="starting",
            detailed_status="Initializing conversion services..."
        )
    )
    
    # Initialize results arrays
    results = []
    converted_tracks = []
    
    # Initialize conversion stats
    conversion_stats = {
        'start_time': datetime.now(),
        'tracks_processed': 0,
        'search_attempts': 0,
        'search_successes': 0,
        'perf_stats': {
            'scraper_init_time': 0.0,
            'sc_init_time': 0.0,
            'playlist_fetch_time': 0.0,
            'search_times': [],
            'total_search_time': 0.0,
            'avg_search_time': 0.0
        }
    }
    
    logger.info(f"[TRACE][{request_id}] Received conversion request for URL: {request.url}")
    
    # Record start time
    start_time = time.time()
    
    # Validate URL
    if not is_valid_url(request.url):
        logger.error(f"[ERROR][{request_id}] Invalid URL: {request.url}")
        raise HTTPException(status_code=400, detail="Invalid playlist URL")
    
    # Initialize services
    try:
        logger.info(f"[TRACE][{request_id}] Initializing playlist scraper...")
        update_progress(response, "initialization", "Initializing playlist scraper...", "starting")
        
        # Initialize the playlist scraper - this starts the browser
        playlist_scraper = PlaylistScraper()
        await playlist_scraper.initialize_browser()
        background_tasks.add_task(playlist_scraper.cleanup)
        
        logger.info(f"[TRACE][{request_id}] Initializing SoundCloud service...")
        update_progress(response, "initialization", "Initializing services...", "setting_up")
        
        # Initialize SoundCloud service
        soundcloud = SoundCloudService()
        await soundcloud.initialize_browser()
        background_tasks.add_task(soundcloud.cleanup)
        
        init_time = time.time() - start_time
        response.details.performance_stats = {
            "initialization_time": round(init_time, 2),
            "playlist_fetch_time": 0,
            "conversion_time": 0,
            "total_time": 0,
            "tracks_per_second": 0
        }
        logger.info(f"[TRACE][{request_id}] SoundCloud service initialized successfully in {init_time:.2f}s")
        
    except Exception as e:
        logger.error(f"[ERROR][{request_id}] Failed to initialize services: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initialize services: {str(e)}")
    
    # Fetch playlist data
    try:
        update_progress(response, "fetching_playlist", "Fetching playlist data", "in_progress")
        
        # Increased timeout from 60 to 180 seconds for playlist fetching
        playlist_fetch_start = time.time()
        async with timeout_context(180):  # Increased timeout for playlist fetch to 3 minutes
            logger.info(f"[TRACE][{request_id}] Fetching playlist data from {request.url}")
            playlist_data = await playlist_scraper.get_playlist_data(request.url)
            
        playlist_fetch_time = time.time() - playlist_fetch_start
        response.details.performance_stats["playlist_fetch_time"] = round(playlist_fetch_time, 2)
        
        if not playlist_data or not playlist_data.get("tracks"):
            logger.error(f"[ERROR][{request_id}] No tracks found in playlist")
            raise HTTPException(status_code=400, detail="No tracks found in playlist")
            
        tracks = playlist_data.get("tracks", [])
        logger.info(f"[TRACE][{request_id}] Found {len(tracks)} tracks in playlist")
        
        # Update response with playlist info
        response.source_platform = playlist_data.get("platform", "unknown")
        response.source_playlist_name = playlist_data.get("name", "Unknown Playlist")
        response.source_playlist_url = request.url
        
    except asyncio.TimeoutError:
        logger.error(f"[ERROR][{request_id}] Playlist fetch timed out after 180 seconds")
        update_progress(response, "error", "Error: Playlist fetch timed out after 180 seconds. Try again or use a smaller batch size.", "error")
        response.success = False
        response.message = "Playlist fetch timed out after 180 seconds. Try again or use a smaller batch size."
        return response
    except Exception as e:
        logger.error(f"[ERROR][{request_id}] Failed to fetch playlist data: {str(e)}", exc_info=True)
        update_progress(response, "error", f"Error: {str(e)}", "error")
        response.success = False
        response.message = f"Failed to fetch playlist data: {str(e)}"
        return response
    
    # Process tracks with pagination
    tracks = playlist_data.get('tracks', [])
    if not tracks:
        error_msg = "No tracks found in the playlist"
        update_progress(response, "error", f"Error: {error_msg}", "error")
        logger.error(f"[ERROR][{request_id}] {error_msg}")
        return response
    
    response.details.total_tracks = len(tracks)
    update_progress(response, "tracks_found", f"Found {len(tracks)} tracks in playlist", "in_progress")
    logger.info(f"[TRACE][{request_id}] Found {len(tracks)} tracks in playlist")
    
    # Calculate total batches
    progress = {
        'current_batch': request.start_index // request.batch_size + 1,
        'total_batches': (len(tracks) + request.batch_size - 1) // request.batch_size,
        'tracks_in_current_batch': 0,
        'current_track_index': request.start_index,
        'batch_start_time': datetime.now(),
        'estimated_completion_time': None,
        'rate_limited': False,
        'processing_phase': 'initializing',
        'detailed_status': 'Starting conversion process',
        'last_action_time': datetime.now().isoformat()
    }
    
    try:
        # Process tracks in the current batch with timeout protection
        for i, track in enumerate(tracks, start=request.start_index):
            try:
                track_name = track.get('name', 'Unknown Track')
                artists = track.get('artists', ['Unknown Artist'])
                artist_str = ", ".join(artists)
                
                # Update progress
                progress['current_track_index'] = i
                track_number = i - request.start_index + 1
                update_progress(response, "processing_batch", f"Processing batch {progress['current_batch']} of {progress['total_batches']} ({track_number}/{len(tracks)}): '{track_name}' by {artist_str}", "in_progress")
                
                logger.info(f"[TRACE][{request_id}] Processing track {i+1}/{len(tracks)}: '{track_name}' by {artist_str}")
                
                # Try to convert the track with timeout protection
                conversion_stats['search_attempts'] += 1
                
                try:
                    # Use a shorter timeout for each search
                    start_time = datetime.now()
                    sc_track = await asyncio.wait_for(
                        soundcloud.search_track(track_name, artist_str),
                        timeout=30  # REDUCED: from 60 to 30 second timeout per track
                    )
                    search_time = (datetime.now() - start_time).total_seconds()
                    conversion_stats['perf_stats']['search_times'].append(search_time)
                    conversion_stats['perf_stats']['total_search_time'] += search_time
                    
                    if sc_track:
                        update_progress(response, "track_found", f"Found match for '{track_name}' in {search_time:.2f}s", f"Found in {search_time:.2f}s")
                        logger.info(f"[TRACE][{request_id}] Found match: '{sc_track.get('title')}' by {sc_track.get('user', {}).get('username')} in {search_time:.2f}s")
                        conversion_stats['search_successes'] += 1
                        
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
                            "status": f"Found in {search_time:.2f}s",
                            "error": None
                        }
                        
                        results.append(track_result)
                        converted_tracks.append(converted_track)
                        response.success_count += 1
                        
                        logger.info(f"[TRACE][{request_id}] Successfully processed track {i+1}")
                    else:
                        msg = f"No matches found for '{track_name}' by {artist_str} (searched for {search_time:.2f}s)"
                        update_progress(response, "track_not_found", f"No match found for '{track_name}' in {search_time:.2f}s", msg)
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
                            "status": "Not found",
                            "error": msg
                        }
                        
                        results.append(track_result)
                        converted_tracks.append(converted_track)
                        response.failure_count += 1
                        
                except asyncio.TimeoutError:
                    # Handle timeout for this specific track
                    msg = f"Search timed out for '{track_name}' by {artist_str} (after 30s)"
                    update_progress(response, "track_timeout", f"Search timed out for '{track_name}' after 30s", msg)
                    logger.warning(f"[WARN][{request_id}] {msg}")
                    
                    # CRITICAL FIX: Check for browser issues and attempt recovery
                    try:
                        logger.info(f"[TRACE][{request_id}] Attempting browser recovery after timeout")
                        # Recreate SoundCloud service after timeout
                        await soundcloud.cleanup()
                        soundcloud = SoundCloudService()
                        await soundcloud.initialize_browser()
                        logger.info(f"[TRACE][{request_id}] Successfully reset browser after timeout")
                    except Exception as e:
                        logger.error(f"[ERROR][{request_id}] Failed to reset browser: {str(e)}")
                    
                    track_result = TrackResult(
                        source_track=track,
                        success=False,
                        message=msg
                    )
                    
                    converted_track = {
                        "original": track,
                        "converted": None,
                        "success": False,
                        "status": "Timed out",
                        "error": msg
                    }
                    
                    results.append(track_result)
                    converted_tracks.append(converted_track)
                    response.failure_count += 1
                
                # Estimate completion time after each track
                tracks_processed = i - request.start_index + 1
                if tracks_processed > 0:
                    elapsed_time = (datetime.now() - progress['batch_start_time']).total_seconds()
                    time_per_track = elapsed_time / tracks_processed
                    tracks_remaining = progress['tracks_in_current_batch'] - tracks_processed
                    estimated_seconds_remaining = time_per_track * tracks_remaining
                    
                    # Format as MM:SS
                    minutes = int(estimated_seconds_remaining // 60)
                    seconds = int(estimated_seconds_remaining % 60)
                    progress['estimated_completion_time'] = f"{minutes:02d}:{seconds:02d}"
                    
                    # Update average search time
                    if conversion_stats['perf_stats']['search_times']:
                        conversion_stats['perf_stats']['avg_search_time'] = conversion_stats['perf_stats']['total_search_time'] / len(conversion_stats['perf_stats']['search_times'])
                    
                    update_progress(response, "processing_batch", 
                                   f"Processed {tracks_processed}/{len(tracks)} tracks. Est. remaining: {progress['estimated_completion_time']}. Avg search: {conversion_stats['perf_stats']['avg_search_time']:.2f}s", 
                                   f"Processed {tracks_processed}/{len(tracks)} tracks. Est. remaining: {progress['estimated_completion_time']}. Avg search: {conversion_stats['perf_stats']['avg_search_time']:.2f}s")
                
                # Check if rate limited based on SoundCloud service stats
                try:
                    stats = soundcloud.get_stats()
                    if stats.get('rate_limiter', {}).get('limited_requests', 0) > 0:
                        progress['rate_limited'] = True
                        update_progress(response, "rate_limited", "Hit rate limit - searches may be slower", "Hit rate limit - searches may be slower")
                except:
                    pass
                    
                # Add small delay between tracks to avoid rate limiting
                await asyncio.sleep(1.0)  # Increased from 0.5 to 1.0 second
                
            except Exception as e:
                logger.error(f"[ERROR][{request_id}] Error processing track: {str(e)}", exc_info=True)
                update_progress(response, "track_error", f"Error processing track: {str(e)}", f"Error processing track: {str(e)}")
                
                # Still add a result for the track
                track_result = TrackResult(
                    source_track=track,
                    success=False,
                    message=f"Error processing track: {str(e)}"
                )
                
                converted_track = {
                    "original": track,
                    "converted": None,
                    "success": False,
                    "status": "Error",
                    "error": str(e)
                }
                
                results.append(track_result)
                converted_tracks.append(converted_track)
                response.failure_count += 1
            
            # Update conversion stats
            conversion_stats['tracks_processed'] += 1
        
        update_progress(response, "batch_complete", f"Completed batch {progress['current_batch']} of {progress['total_batches']}. Found {response.success_count} of {len(tracks)} tracks.", f"Completed batch {progress['current_batch']} of {progress['total_batches']}. Found {response.success_count} of {len(tracks)} tracks.")
        
        # Create conversion details with batch information
        current_batch = {
            "start": request.start_index,
            "end": request.start_index + len(tracks) - 1,
            "end_index": request.start_index + len(tracks) - 1,
            "has_more": False,
            "batch_size": request.batch_size,
            "current_batch": progress['current_batch'],
            "total_batches": progress['total_batches'],
            "estimated_completion_time": progress['estimated_completion_time'],
            "rate_limited": progress['rate_limited']
        }
        
        # Calculate performance stats for the response
        performance_stats = {
            'scraper_init_time': f"{conversion_stats['perf_stats']['scraper_init_time']:.2f}s",
            'soundcloud_init_time': f"{conversion_stats['perf_stats']['sc_init_time']:.2f}s",
            'playlist_fetch_time': f"{conversion_stats['perf_stats']['playlist_fetch_time']:.2f}s",
            'avg_search_time': f"{conversion_stats['perf_stats']['avg_search_time']:.2f}s",
            'total_search_time': f"{conversion_stats['perf_stats']['total_search_time']:.2f}s",
            'total_time': f"{(datetime.now() - conversion_stats['start_time']).total_seconds():.2f}s",
            'rate_limited': progress['rate_limited'],
            'browser_stats': soundcloud.get_stats() if soundcloud else None
        }
        
        # Return successful response with all the data
        response.success = True
        response.message = f"Successfully converted {response.success_count} of {response.details.total_tracks} tracks"
        response.details.converted_tracks = response.success_count
        response.details.total_tracks = response.details.total_tracks
        response.details.success_rate = response.success_count / response.details.total_tracks if response.details.total_tracks > 0 else 0
        response.details.tracks = converted_tracks
        response.details.current_batch = current_batch
        response.details.performance_stats = performance_stats
        return response
        
    except Exception as e:
        logger.error(f"[ERROR][{request_id}] Conversion process failed: {str(e)}", exc_info=True)
        update_progress(response, "error", f"Conversion process failed: {str(e)}", f"Conversion process failed: {str(e)}")
        response.success = False
        response.message = f"Conversion process failed: {str(e)}"
        return response

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
base_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))

# Try multiple locations for the frontend
possible_frontend_paths = [
    os.path.join(base_dir, "frontend-dist"),  # /app/frontend-dist
    os.path.join(base_dir, "frontend", "dist"),  # /app/frontend/dist
    "/app/frontend-dist"  # Absolute path in Docker container
]

frontend_dir = None
for path in possible_frontend_paths:
    if os.path.exists(path):
        frontend_dir = path
        logger.info(f"Found frontend at: {frontend_dir}")
        break

if frontend_dir:
    # Add a catch-all route for static files
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    logger.info(f"Mounted frontend at {frontend_dir}")
    
    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not found")
else:
    logger.warning("Frontend build not found - serving API only")
    
    @app.get("/")
    async def api_root():
        return {"message": "API is running. Frontend not available."}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="debug") 