# Security

## Authentication Flow

II-Agent supports three authentication methods, resolved in `auth/dependencies.py` via `get_current_user()`:

### 1. JWT (Primary)

- **Algorithm:** HS256 via `auth/jwt_handler.py`
- **Token types:** Access token (short-lived) + Refresh token (long-lived)
- **Payload:** `{user_id, email, role, type: "access"|"refresh", exp, iat}`
- **Expiry:** Configurable via `Settings.access_token_expire_minutes` and `Settings.refresh_token_expire_days`
- **Security scheme:** `HTTPBearer()` — tokens sent as `Authorization: Bearer <token>`

### 2. OIDC (OAuth Login)

Two OAuth providers are supported:

**II OAuth** (`/auth/oauth/ii/login` → `/auth/oauth/ii/callback`):
- PKCE flow (code_verifier + code_challenge)
- Session state stored in-memory during redirect
- ID token verified via PyJWT with JWKS from discovery endpoint
- Supports RS256/RS384/RS512 and ES256/ES384/ES512 algorithms
- `at_hash` claim verified when present

**Google OAuth** (`/auth/oauth/google/login` → `/auth/oauth/google/callback`):
- Via `fastapi_sso.GoogleSSO`
- Also used for Google Drive connector authorization
- Auto-creates user on first login via `find_or_create_oauth_user()`

### 3. API Keys

- **Format:** `ii_<32_random_chars>` (generated via `auth/api_key_utils.py`)
- **Storage:** `api_keys` table with `user_id` FK, `is_active` flag
- **One active key per user** — created during user registration
- **Lookup:** Indexed on `api_key` column (unique)

## User Lifecycle

1. OAuth login or API key authentication
2. `check_waitlist()` — blocks registration unless email is in `waitlist` table or `@ii.inc` domain (can be disabled via config)
3. `create_user()` creates: User row + API key + `credit_balance` row (via `CreditService.ensure_balance_exists`)
4. Soft delete via `delete_user()` sets `is_active=False`

## Secrets Management

### Application Secrets (GCP Secret Manager)

- **Integration:** `core/secrets/` with `GCPSecretManagerSource`
- **Activation:** `USE_GCP_SECRETS=true` environment variable
- **Priority:** Settings loaded from: init kwargs > env vars > GCP secrets > .env file
- GCP secrets fetched at app startup during `lifespan` and merged into Settings

### Project Secrets (Per-Project)

- **Service:** `projects/secrets/service.py` — `SecretService`
- **Encryption:** Secrets encrypted before storage in `Project.secrets_json` (JSONB)
- **Operations:** `replace_session_project_secrets()`, `add_secrets()`, `delete_secrets()`
- **Sync:** Secrets synced to E2B sandbox environment via `SandboxEnvSyncService`

## Data Isolation

- **User scoping:** All queries filter by `user_id`. Sessions, projects, files, billing — all scoped to the authenticated user.
- **Session ownership:** `get_session_by_id_and_user()` checks both `session_id` AND `user_id` AND `deleted_at IS NULL`.
- **Public sessions:** Opt-in via `is_public=True`. Public endpoints use `get_public_session_details()` which checks `is_public AND deleted_at IS NULL`.
- **File access:** Files tied to `user_id` and optionally `session_id`. Public file access requires session to be public.

## Connector Security

- **Connector model** stores `access_token`, `refresh_token`, `token_expiry` per user per connector type
- **Types:** GOOGLE_DRIVE, GITHUB, REVENUECAT, CHATGPT_MCP, COMPOSIO
- **Unique constraint:** `(user_id, connector_type)` — one connection per service per user
- **Composio profiles** store encrypted MCP URLs with toolkit metadata

## Billing Security

- **Row-level locking:** `SELECT ... FOR UPDATE` on `credit_balances` prevents concurrent balance mutations
- **Idempotency keys:** `ON CONFLICT DO NOTHING` on `credit_ledger` prevents double-charging on retries
- **SAVEPOINT atomicity:** Ledger + balance mutations wrapped in `db.begin_nested()`
- **Decimal precision:** All credit amounts use `Decimal(18,6)` — never floats
- **Output token cap:** Reserved amount enforced at provider level via `max_tokens` parameter

## CI Security

- **gitleaks.yml** — Secret scanning in CI pipeline
- **Pre-commit hooks** — Automated checks before commits
