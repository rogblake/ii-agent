# Starter IDs

The bundled templates are copied from `src/ii_server/assets/templates` in this repo.

## Web templates

Supported `template_id` values for `ii-app web init`:

- `nextjs-shadcn`
- `react-shadcn-python`
- `react-tailwind-python`
- `react-vite-shadcn`

Runtime mapping:

- `nextjs-shadcn`
  - install: `bun install`
  - server: `PORT={PORT} bun run dev`
  - preview session: `fullstack`
- `react-shadcn-python`
  - install: `frontend -> bun install`, `backend -> pip install -r requirements.txt`
  - servers: `frontend` via Vite, `backend` via Uvicorn
  - preview session: `frontend`
- `react-tailwind-python`
  - install: `frontend -> bun install`, `backend -> pip install -r requirements.txt`
  - servers: `frontend` via Vite, `backend` via Uvicorn
  - preview session: `frontend`
- `react-vite-shadcn`
  - install: `bun install`
  - server: `bun run dev -- --host --port {PORT}`
  - preview session: `frontend`

Web sessions are namespaced with the project name, for example `ii-app-web-my-app-frontend`.

## Mobile starters

`ii-app mobile init` supports two ways to bootstrap Expo:

- `--template tabs|blank|blank-typescript`
- `--example <expo-example-name>`

Current defaults:

- template default: `tabs`
- common example: `with-reanimated`

Mobile runtime behavior:

- create project with `bunx create-expo-app@latest`
- install Expo web/tunnel support packages
- optionally install NativeWind-related packages unless `--no-tailwind` is set
- start Expo in tunnel mode first, then fall back to LAN mode
- store the web URL, tunnel URL, QR code value, and tmux session in the mobile cache
