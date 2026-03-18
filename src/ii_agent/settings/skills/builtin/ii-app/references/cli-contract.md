# CLI Contract

The Rust binary writes workspace-local caches by default:

```text
<workspace>/.ii-app/web.json
<workspace>/.ii-app/mobile.json
```

## Web cache shape

```json
{
  "version": 1,
  "deployment_config": {
    "preview_url": "http://127.0.0.1:3000",
    "preview_port": 3000,
    "project_name": "demo-app",
    "framework": "react-vite-shadcn",
    "directory": "/abs/path/demo-app",
    "env_file": "/abs/path/demo-app/.env",
    "servers": [
      {
        "deployment_url": "http://127.0.0.1:3000",
        "port": 3000,
        "command": "bun run dev -- --host --port {PORT}",
        "session": "ii-web-demo-app-frontend",
        "run_dir": "/abs/path/demo-app"
      }
    ]
  }
}
```

## Mobile cache shape

```json
{
  "version": 1,
  "mobile_app_config": {
    "project_name": "demo-mobile",
    "project_dir": "/abs/path/demo-mobile",
    "template": "tabs",
    "example": null,
    "with_tailwind": true,
    "web_port": 8081,
    "session": "ii-app-mobile-demo-mobile",
    "tunnel_url": "exp://127.0.0.1:8081",
    "qr_code_value": "exp://127.0.0.1:8081",
    "web_url": "http://localhost:8081",
    "startup_mode": "tunnel"
  }
}
```

Operational rules:

- `ii-app web init` fails if the project directory already exists.
- `ii-app web restart` reads the web cache, recreates or reuses tmux sessions, and updates ports if a `{PORT}` placeholder is present.
- `ii-app web screenshot` opens the cached `preview_url` with `agent-browser`, saves an image under `<workspace>/.ii-app/shots/` by default, and prints the saved path.
- `ii-app web status` captures tmux output into `<workspace>/.ii-app/status/`, saves a JSON summary path, and adds a screenshot beside it when the cached URL is previewable.
- `ii-app mobile init` fails if the mobile project directory already exists.
- `ii-app mobile restart` reads the mobile cache and refreshes tunnel or LAN URLs after restarting Expo.
- `ii-app stripe register-webhook` calls Stripe's webhook endpoint API, writes `STRIPE_WEBHOOK_SECRET` into `<project_directory>/.env`, and prints the updated env file path.
- `view-log` captures the tmux pane output for the default cached session when `--session` is omitted.
- If `web init --host-url` is omitted, preview URLs are local `http://127.0.0.1:<port>` URLs.
