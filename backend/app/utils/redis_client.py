import redis

from app.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def cache_job_status(job_id: str, status: str, ttl: int = 3600) -> None:
    try:
        redis_client.setex(f"job_status:{job_id}", ttl, status)
    except redis.RedisError:
        # PostgreSQL remains the source of truth when the cache is unavailable.
        return


def get_cached_status(job_id: str) -> str | None:
    try:
        return redis_client.get(f"job_status:{job_id}")
    except redis.RedisError:
        return None
