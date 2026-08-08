"""
Enhanced rate limiter with role-based rate limiting and violation tracking.

Supports different rate limits for different user roles (admin vs regular users)
and logs violations for monitoring and analytics.
"""

import time
import logging
from fastapi import HTTPException, status
import redis

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

try:
    redis_client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.redis_db,
        decode_responses=True,
        socket_connect_timeout=2,
    )
    redis_client.ping()
except (redis.ConnectionError, redis.TimeoutError, redis.ResponseError) as e:
    logger.warning(f"Redis connection error in rate limiter: {e}")
    redis_client = None

# Rate limit configuration (requests per window)
RATE_LIMITS = {
    "admin": 300,  # 300 requests per minute for admins
    "user": 100,  # 100 requests per minute for regular users
    "guest": 20,  # 20 requests per minute for guests/unauthenticated
}

# Stricter limits for sensitive unauthenticated endpoints (login, register).
# Keyed by client IP to block brute-force / credential-stuffing attacks.
AUTH_RATE_LIMITS = {
    "login": 10,  # 10 attempts per minute per IP before lockout
    "register": 5,  # 5 registrations per minute per IP
}

WINDOW = 60  # Time window in seconds (1 minute)


def rate_limit(user_id: str, role: str = "user", endpoint: str = "unknown") -> None:
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
        limit = RATE_LIMITS.get(role, RATE_LIMITS["user"])

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
                limit=limit,
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Limit: {limit} requests per {WINDOW} seconds.",
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
    user_id: str, role: str, endpoint: str, current_count: int, limit: int
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
            "user_id": user_id,
            "role": role,
            "endpoint": endpoint,
            "current_count": current_count,
            "limit": limit,
            "timestamp": now,
        }
        #   redis_client.hset(name, key, value)
        #   Redis عنده نوع بيانات اسمه Hash (زي Dictionary في Python)
        #   hset بتستخدم عشان تخزن مجموعة key-value جوه key واحد رئيسي
        redis_client.hset(
            f"violation_details:{user_id}:{now // WINDOW}",
            mapping={str(k): str(v) for k, v in violation_details.items()},
        )

    except Exception as e:
        logger.error(f"Error logging rate limit violation: {e}")


def get_rate_limit_remaining(user_id: str, role: str = "user") -> int:
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
        limit = RATE_LIMITS.get(role, RATE_LIMITS["user"])
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


def ip_rate_limit(client_ip: str, endpoint: str = "unknown") -> None:
    """
    Enforce a per-IP rate limit for unauthenticated endpoints (login, register).

    This function uses the client's IP address as the key so that a single
    IP cannot brute-force credentials across multiple accounts.  Limits are
    defined in AUTH_RATE_LIMITS and are deliberately stricter than the
    per-user limits used for authenticated endpoints.

    Args:
        client_ip: Client IP address from the HTTP request.
        endpoint:  Logical endpoint name used to look up the correct limit
                   (e.g. ``'login'``, ``'register'``).

    Raises:
        HTTPException 429: If the IP has exceeded its allowed request count
                           for the current time window.
    """
    if redis_client is None:
        logger.warning(
            "Redis not available — IP rate limiting disabled for %s", endpoint
        )
        return

    limit = AUTH_RATE_LIMITS.get(endpoint, AUTH_RATE_LIMITS.get("login", 10))

    try:
        now = int(time.time())
        key = f"ip_rate:{client_ip}:{endpoint}:{now // WINDOW}"

        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, WINDOW)

        if current > limit:
            logger.warning(
                "IP rate limit exceeded — IP: %s, endpoint: %s, count: %s/%s",
                client_ip,
                endpoint,
                current,
                limit,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many requests from your IP. "
                    f"Limit: {limit} requests per {WINDOW} seconds."
                ),
            )

    except HTTPException:
        raise
    except redis.ConnectionError as e:
        logger.error("Redis connection error in IP rate limiter: %s", e)
    except redis.TimeoutError as e:
        logger.error("Redis timeout in IP rate limiter: %s", e)
    except Exception as e:
        logger.error("Unexpected error in IP rate limiter: %s", e)
