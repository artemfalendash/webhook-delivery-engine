import random


def get_retry_delay(
    attempt_number: int,
    base_delay: float = 5.0,
    max_delay: float = 3600.0
) -> float:
    """Calculates exponential backoff delay with Full Jitter in seconds.
    
    Formula: min(max_delay, base_delay * (5 ** (attempt_number - 1)))
    """
    # 1. Calculate max upper bound exponential backoff
    calculated_backoff = min(max_delay, base_delay * (5 ** (attempt_number - 1)))

    # 2. Apply Full Jitter (pick a random float between 0 and calculated_backoff)
    jittered_delay = random.uniform(0, calculated_backoff)

    return round(jittered_delay, 2)
