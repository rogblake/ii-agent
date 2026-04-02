"""HTML templates for auth domain responses."""

import json
from typing import Optional


_AUTH_CALLBACK_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>II Login</title>
</head>
<body>
<script>
  (function() {
    const payload = %s;
    const targetOrigin = %s;
    const redirectUrl = %s;
    const message = { type: 'ii-auth-success', payload };
    const fallbackOrigin = (() => {
      if (targetOrigin) return targetOrigin;
      try {
        if (redirectUrl) return new URL(redirectUrl).origin;
      } catch (e) {}
      return window.location.origin;
    })();

    function redirectWithHash() {
      if (!redirectUrl) return;
      try {
        const url = new URL(redirectUrl);
        url.hash = 'ii-auth=' + encodeURIComponent(JSON.stringify(payload));
        window.location.replace(url.toString());
      } catch (e) {
        window.location.replace(redirectUrl);
      }
    }

    try {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(message, fallbackOrigin || '*');
        window.close();
        return;
      }
    } catch (err) {
      console.error('postMessage to opener failed', err);
    }

    if (redirectUrl) {
      redirectWithHash();
      return;
    }

    document.body.innerHTML = '<p>Login successful. You can close this window.</p>';
  })();
</script>
</body>
</html>
"""


def render_auth_callback_html(
    token_payload: dict,
    return_origin: Optional[str],
    return_url: Optional[str],
) -> str:
    """Render the OAuth callback HTML that posts tokens back to the opener."""
    return _AUTH_CALLBACK_HTML % (
        json.dumps(token_payload),
        json.dumps(return_origin or ""),
        json.dumps(return_url or ""),
    )
