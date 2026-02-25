from ii_agent.projects.databases.utils import extract_db_url


def test_extract_db_url_returns_none_for_non_dict_inputs():
    assert extract_db_url(None) is None
    assert extract_db_url("postgres://db") is None


def test_extract_db_url_uses_declared_priority_order():
    database_json = {
        "url": "postgres://from-url",
        "connection_uri": "postgres://from-connection-uri",
        "connection_url": "postgres://from-connection-url",
    }

    assert extract_db_url(database_json) == "postgres://from-connection-url"


def test_extract_db_url_ignores_empty_or_non_string_values():
    database_json = {
        "connection_url": "",
        "connection_uri": 123,
        "uri": None,
        "url": "postgres://from-url",
    }

    assert extract_db_url(database_json) == "postgres://from-url"


def test_extract_db_url_returns_none_when_no_valid_key_exists():
    assert extract_db_url({"connection_url": "", "dsn": None}) is None
