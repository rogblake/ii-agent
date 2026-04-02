from typing import Optional


def extract_db_url(database_json: Optional[dict]) -> Optional[str]:
    """Extract database connection URL from a database JSON dict."""
    if not isinstance(database_json, dict):
        return None

    for key in (
        "connection_url",
        "connection_uri",
        "uri",
        "url",
        "connection_string",
        "dsn",
    ):
        value = database_json.get(key)
        if isinstance(value, str) and value:
            return value

    return None
