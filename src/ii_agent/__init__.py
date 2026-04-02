"""ii_agent package initialization."""

try:
    import pyparsing as pp
except Exception:
    pp = None

if pp is not None and hasattr(pp, "DelimitedList"):
    # Avoid DeprecationWarning from httplib2 using pp.delimitedList.
    pp.delimitedList = pp.DelimitedList
