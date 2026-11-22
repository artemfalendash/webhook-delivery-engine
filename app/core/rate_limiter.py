import time
from urllib.parse import urlparse


def extract_domain(target_url: str) -> str:
    """Extracts the hostname (e.g. 'webhook.site') from a full URL."""

    parsed = urlparse(target_url)
    
    return parsed.netloc or parsed.path.split("/")[0]


async def is_rate_limited(
    redis_client,
    domain: str,
    max_requests: int = 10,
    window_seconds: int = 1,
) -> bool:
    """Checks if a domain has exceeded its request quota for the current time window."""
    current_time = int(time.time())
    key = f"rate_limit:{domain}:{current_time}"

    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds + 1)
    results = await pipe.execute()

    request_count = results[0]
    return request_count > max_requests
