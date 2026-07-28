"""
Enhanced rate limiter with role-based rate limiting and violation tracking.

Supports different rate limits for different user roles (admin vs regular users)
and logs violations for monitoring and analytics.
"""
import time
import logging
from fastapi import HTTPException, status
import redis
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

try:
    redis_client = redis.Redis(host="localhost",
                                port=6379,
                                  decode_responses=True,
                                    socket_connect_timeout=2)
    redis_client.ping()
except (redis.ConnectionError, redis.TimeoutError):
    redis_client = None

# Rate limit configuration (requests per window)
RATE_LIMITS = {
    'admin': 300,      # 300 requests per minute for admins
    'user': 100,       # 100 requests per minute for regular users
    'guest': 20        # 20 requests per minute for guests/unauthenticated
}

WINDOW = 60  # Time window in seconds (1 minute)


def rate_limit(
    user_id: str,
    role: str = "user",
    endpoint: str = "unknown"
) -> None:
    """
    Check and enforce rate limiting based on user role.
    
    Different roles have different rate limits:
    - admin: 300 requests/minute
    - user: 100 requests/minute
    - guest: 20 requests/minute
    
    Args:
        user_id: Unique identifier for the user
        role: User role ('admin', 'user', 'guest')
        endpoint: API endpoint being accessed (for logging)
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    # Skip rate limiting if Redis is not available
    if redis_client is None:
        logger.warning("Redis not available - rate limiting disabled")
        return
    
    try:
        # Get rate limit for this role
        limit = RATE_LIMITS.get(role, RATE_LIMITS['user'])
        
        now = int(time.time())
        # Create a unique key for this user+role+window
        key = f"rate:{user_id}:{role}:{now // WINDOW}"
        
        # Increment the counter for this user in this window
        current = redis_client.incr(key)
        
        # Set expiration time for the key if it's newly created
        if current == 1:
            redis_client.expire(key, WINDOW)
        
        # Check if the current count exceeds the rate limit
        if current > limit:
            # Log violation
            _log_rate_limit_violation(
                user_id=user_id,
                role=role,
                endpoint=endpoint,
                current_count=current,
                limit=limit
            )
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Limit: {limit} requests per {WINDOW} seconds."
            )
        
        # Return the remaining requests
        return current
        
    except redis.ConnectionError as e:
        logger.error(f"Redis connection error in rate limiter: {e}")
        # Gracefully skip rate limiting if Redis connection fails
    except redis.TimeoutError as e:
        logger.error(f"Redis timeout in rate limiter: {e}")
        # Gracefully skip rate limiting if Redis times out


def _log_rate_limit_violation(
    user_id: str,
    role: str,
    endpoint: str,
    current_count: int,
    limit: int
) -> None:
    """
    Log a rate limit violation for monitoring and analytics.
    
    Args:
        user_id: User identifier
        role: User role
        endpoint: API endpoint
        current_count: Current request count in this window
        limit: Rate limit for this role
    """
    now = int(time.time())
    violation_key = f"violation:{user_id}:{now // WINDOW}"
    
    try:
        # Increment violation counter
        redis_client.incr(violation_key)
        redis_client.expire(violation_key, WINDOW * 5)  # Keep for 5 windows
        
        # Log to application logger
        logger.warning(
            f"Rate limit exceeded - User: {user_id}, Role: {role}, "
            f"Endpoint: {endpoint}, Count: {current_count}, Limit: {limit}"
        )
        
        # Store violation details in Redis for analytics
        violation_details = {
            'user_id': user_id,
            'role': role,
            'endpoint': endpoint,
            'current_count': current_count,
            'limit': limit,
            'timestamp': now
        }
        #   redis_client.hset(name, key, value) 
        #   Redis عنده نوع بيانات اسمه Hash (زي Dictionary في Python)
        #   hset بتستخدم عشان تخزن مجموعة key-value جوه key واحد رئيسي  
        redis_client.hset(
            f"violation_details:{user_id}:{now // WINDOW}",
            mapping={str(k): str(v) for k, v in violation_details.items()}
        )
        
    except Exception as e:
        logger.error(f"Error logging rate limit violation: {e}")


def get_rate_limit_remaining(
    user_id: str,
    role: str = "user"
) -> int:
    """
    Get the number of remaining requests for a user in the current window.
    
    Args:
        user_id: User identifier
        role: User role
        
    Returns:
        Number of remaining requests (0 if limit exceeded)
    """
    if redis_client is None:
        return -1  # Unlimited if Redis not available
    
    try:
        limit = RATE_LIMITS.get(role, RATE_LIMITS['user'])
        now = int(time.time())
        key = f"rate:{user_id}:{role}:{now // WINDOW}"
        
        current = redis_client.get(key)
        if current is None:
            return limit
        
        remaining = limit - int(current)
        return max(remaining, 0)
        
    except Exception as e:
        logger.error(f"Error getting rate limit remaining: {e}")
        return -1


def reset_rate_limit(user_id: str, role: str = "user") -> bool:
    """
    Reset rate limit for a user (useful for admin operations).
    
    Args:
        user_id: User identifier
        role: User role
        
    Returns:
        True if reset successful, False otherwise
    """
    if redis_client is None:
        return False
    
    try:
        now = int(time.time())
        key = f"rate:{user_id}:{role}:{now // WINDOW}"
        redis_client.delete(key)
        logger.info(f"Rate limit reset for user: {user_id}, role: {role}")
        return True
    except Exception as e:
        logger.error(f"Error resetting rate limit: {e}")
        return False
