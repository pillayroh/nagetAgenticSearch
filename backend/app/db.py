from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongodb_uri)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[get_settings().mongodb_db]


async def ensure_indexes() -> None:
    from app.config import get_settings

    if not get_settings().use_mongodb:
        return
    db = get_database()
    await db.runs.create_index("created_at")
    await db.url_cache.create_index("url_hash", unique=True)
    await db.url_cache.create_index("fetched_at")
