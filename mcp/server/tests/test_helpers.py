"""
Helper functions for MCP server tests
"""

import asyncio
import time
import random
from typing import Any, Callable, TypeVar
import httpx

T = TypeVar('T')


async def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 5,
    base_delay: float = 10.0,
    max_delay: float = 120.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> T:
    """
    Retry a function with exponential backoff for rate limiting
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retries
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay on each retry
        jitter: Add random jitter to prevent thundering herd
    
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            
            # Check if it's a rate limiting error or connection issue
            is_rate_limit = False
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                is_rate_limit = e.response.status_code == 429
            elif isinstance(e, httpx.HTTPStatusError):
                is_rate_limit = e.response.status_code == 429
            elif "429" in str(e) or "rate" in str(e).lower():
                is_rate_limit = True
            elif "BrokenResourceError" in str(type(e)) or "BrokenResourceError" in str(e):
                is_rate_limit = True  # Treat connection issues as rate limiting
            elif "ConnectionError" in str(type(e)) or "TimeoutError" in str(type(e)):
                is_rate_limit = True  # Treat connection issues as rate limiting
            
            # If it's not a rate limit error, don't retry
            if not is_rate_limit and attempt == 0:
                raise e
            
            # If this was the last attempt, raise the exception
            if attempt == max_retries:
                raise e
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            print(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
            await asyncio.sleep(delay)
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


def sync_retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> T:
    """
    Synchronous version of retry_with_backoff
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            
            # Check if it's a rate limiting error
            is_rate_limit = False
            if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                is_rate_limit = e.response.status_code == 429
            elif isinstance(e, httpx.HTTPStatusError):
                is_rate_limit = e.response.status_code == 429
            elif "429" in str(e) or "rate" in str(e).lower():
                is_rate_limit = True
            
            # If it's not a rate limit error, don't retry
            if not is_rate_limit and attempt == 0:
                raise e
            
            # If this was the last attempt, raise the exception
            if attempt == max_retries:
                raise e
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)
            
            print(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
            time.sleep(delay)
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


async def rate_limited_sleep(min_delay: float = 0.5, max_delay: float = 2.0):
    """
    Sleep for a random amount of time to help avoid rate limits
    """
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)


def sync_rate_limited_sleep(min_delay: float = 0.5, max_delay: float = 2.0):
    """
    Synchronous version of rate_limited_sleep
    """
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)
