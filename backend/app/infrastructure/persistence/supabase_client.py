from functools import lru_cache

from supabase import Client, create_client

from app.core.config import Settings, get_settings


@lru_cache
def get_supabase_client(settings: Settings | None = None) -> Client | None:
    """Return a Supabase client when credentials are configured."""
    config = settings or get_settings()
    if not config.supabase_url or not config.supabase_service_role_key:
        return None
    return create_client(config.supabase_url, config.supabase_service_role_key)
