import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Any, Optional, TypeVar, Generic, AsyncContextManager
from contextlib import asynccontextmanager
import traceback

logger = logging.getLogger(__name__)

T = TypeVar('T')

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

@asynccontextmanager
async def timeout_context(timeout_seconds: float) -> AsyncContextManager[None]:
    """
    Async context manager that raises TimeoutError if the code inside takes longer than timeout_seconds.
    
    Args:
        timeout_seconds: Maximum time in seconds before raising TimeoutError
        
    Yields:
        None
        
    Raises:
        TimeoutError: If the operation takes longer than timeout_seconds
    """
    try:
        # Start a task with a timeout
        yield await asyncio.wait_for(asyncio.shield(asyncio.sleep(0)), timeout=0)
    except asyncio.TimeoutError:
        # This shouldn't happen as we're just yielding a completed sleep(0)
        pass
        
    # The actual timeout happens here
    task = asyncio.create_task(asyncio.sleep(timeout_seconds))
    
    # Wait for either the task to complete (indicating timeout)
    # or the context to exit normally
    done, pending = await asyncio.wait(
        [task], 
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # If the sleep task completed, we hit the timeout
    if task in done:
        raise TimeoutError(f"Operation timed out after {timeout_seconds} seconds")
    
    # Otherwise cancel the sleep task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

class CircuitBreaker:
    """
    Circuit breaker pattern implementation to prevent repeated calls to failing services.
    
    When the failure count reaches a threshold, the circuit "opens" and calls are 
    rejected for a cooling period before allowing a single test call to see if the 
    service has recovered.
    """
    
    def __init__(
        self, 
        failure_threshold: int = 5, 
        cooling_period: float = 60.0, 
        half_open_timeout: float = 5.0
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening the circuit
            cooling_period: Time in seconds to wait before trying again
            half_open_timeout: Timeout in seconds for the test call when half-open
        """
        self.failure_threshold = failure_threshold
        self.cooling_period = cooling_period
        self.half_open_timeout = half_open_timeout
        
        self.failures = 0
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF-OPEN
        self.last_failure_time = 0
        self.stats = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'rejected_calls': 0,
            'circuit_opened_count': 0,
        }
    
    def record_success(self):
        """Record a successful call and reset the circuit if it was half-open."""
        self.failures = 0
        if self.state == 'HALF-OPEN':
            self.state = 'CLOSED'
            logger.info("Circuit breaker reset to CLOSED state after successful test call")
        self.stats['successful_calls'] += 1
    
    def record_failure(self):
        """Record a failed call and potentially open the circuit."""
        self.failures += 1
        self.last_failure_time = time.time()
        self.stats['failed_calls'] += 1
        
        if self.state == 'CLOSED' and self.failures >= self.failure_threshold:
            self.state = 'OPEN'
            self.stats['circuit_opened_count'] += 1
            logger.warning(f"Circuit OPENED after {self.failures} consecutive failures")
        elif self.state == 'HALF-OPEN':
            self.state = 'OPEN'
            self.last_failure_time = time.time()  # Reset the timer
            logger.warning("Circuit re-OPENED after test call failure")
    
    def can_execute(self) -> bool:
        """Check if a call can be executed based on the circuit state."""
        self.stats['total_calls'] += 1
        
        if self.state == 'CLOSED':
            return True
        
        if self.state == 'OPEN':
            # Check if cooling period has elapsed
            cooling_time_elapsed = time.time() - self.last_failure_time >= self.cooling_period
            if cooling_time_elapsed:
                self.state = 'HALF-OPEN'
                logger.info(f"Circuit switched to HALF-OPEN state after {self.cooling_period}s cooling period")
                return True
            else:
                self.stats['rejected_calls'] += 1
                return False
                
        # HALF-OPEN state allows one test call
        return True
    
    def get_stats(self) -> dict:
        """Get the current statistics of the circuit breaker."""
        return {
            **self.stats,
            'current_state': self.state,
            'current_failures': self.failures,
            'time_since_last_failure': time.time() - self.last_failure_time if self.last_failure_time > 0 else None,
        }

class RateLimiter:
    """
    Rate limiter to prevent too many requests in a short period of time.
    Uses a token bucket algorithm to allow for bursts while maintaining
    a long-term rate limit.
    """
    
    def __init__(self, rate: float = 1.0, burst: int = 5):
        """
        Initialize the rate limiter.
        
        Args:
            rate: Number of tokens per second to add to the bucket
            burst: Maximum number of tokens that can be in the bucket
        """
        self.rate = rate  # tokens per second
        self.burst = burst  # maximum tokens
        self.tokens = burst  # start with a full bucket
        self.last_refill = time.time()
        self.stats = {
            'allowed_requests': 0,
            'limited_requests': 0,
            'total_requests': 0,
        }
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens were acquired, False otherwise
        """
        self.stats['total_requests'] += 1
        
        # Refill the bucket based on time elapsed
        now = time.time()
        time_elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + time_elapsed * self.rate)
        self.last_refill = now
        
        # Try to acquire tokens
        if self.tokens >= tokens:
            self.tokens -= tokens
            self.stats['allowed_requests'] += 1
            return True
        else:
            self.stats['limited_requests'] += 1
            return False
    
    async def wait_for_token(self, tokens: int = 1) -> None:
        """
        Wait until tokens are available in the bucket.
        
        Args:
            tokens: Number of tokens to acquire
        """
        while not await self.acquire(tokens):
            # Calculate time to wait for at least one token
            wait_time = (tokens - self.tokens) / self.rate
            wait_time = max(0.1, min(wait_time, 5.0))  # Between 0.1 and 5 seconds
            await asyncio.sleep(wait_time)
    
    def get_stats(self) -> dict:
        """Get the current statistics of the rate limiter."""
        return {
            **self.stats,
            'current_tokens': self.tokens,
            'refill_rate': self.rate,
            'burst_size': self.burst,
        }

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