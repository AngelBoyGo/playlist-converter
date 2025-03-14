import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    """
    Normalize text by removing special characters and converting to lowercase.
    """
    if not text:
        return ""
    # Remove special characters and convert to lowercase
    normalized = ''.join(c.lower() for c in text if c.isalnum() or c.isspace())
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    return normalized

async def retry_with_exponential_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: The function to retry
        max_retries: Maximum number of retries
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each retry
        exceptions: Tuple of exceptions to catch and retry on
    
    Returns:
        The result of the function if successful
    
    Raises:
        The last exception encountered if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retries failed", exc_info=True)
                raise
            
            logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s", exc_info=True)
            await asyncio.sleep(delay)
            delay = min(delay * backoff_factor, max_delay)
    
    raise last_exception 