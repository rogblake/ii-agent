<!-- Generated: 2026-03-29 | Routes: 27 | Handlers: 21 | EventTypes: 44 | Token estimate: ~950 -->
# Backend

## API Routes

| Prefix | File | Tags |
|--------|------|------|
| `/` | `app/health.py` | Health |
| `/auth` | `auth/router.py` | Authentication (OAuth, JWT) |
| `/auth` | `users/router.py` | Users (CRUD, profile) |
| `/billing` | `billing/router.py` | Billing (Stripe) |
| `/credits` | `credits/router.py` | Credits (balance, transactions) |
| `/v1/chat` | `chat/api/router.py` | Chat API |
| `/sessions` | `sessions/router.py` | Sessions |
| `/pin` | `sessions/pin/router.py` | Session Pins |
| `/wishlist` | `sessions/wishlist/router.py` | Session Wishlists |
| `/user-settings/models` | `settings/llm/router.py` | LLM Settings |
| `/user-settings/mcp` | `settings/mcp/router.py` | MCP Settings |
| `/user-settings/skills` | `settings/skills/router.py` | Skills Settings |
| `/files` | `files/router.py` | File Upload/Download |
| `/slides` | `content/slides/router.py` | Slides |
| `/slide-templates` | `content/slides/templates/router.py` | Slide Templates |
| `/slides/design` | `content/slides/design/router.py` | Slide Design |
| `/slides/nano-banana` | `content/slides/nano_banana/router.py` | Nano Banana |
| `/storybooks` | `content/storybook/router.py` | Storybooks |
| `/media`, `/media-templates`, `/media-tools` | `content/media/router.py` | Media |
| `/project` | `projects/router.py` | Projects |
| `/projects/design` | `projects/design/router.py` | Project Design |
| `/subdomains` | `projects/subdomains/router.py` | Subdomains |
| `/connectors/composio` | `integrations/connectors/composio/router.py` | Composio |
| `/connectors` | `integrations/connectors/router.py` | Connectors (GitHub, Google) |
| `/enhance-prompt` | `integrations/enhance_prompt/router.py` | Prompt Enhancement |

Router registration: `app/routers.py::include_routers(app)`

All path parameters for entity IDs use `uuid.UUID` type (FastAPI auto-validates).

## Middleware Chain (app/middleware.py)

```
1. CORSMiddleware (all origins)
2. SessionMiddleware (OAuth session secret)
3. request_tracing_middleware (request context)
4. exception_logging_middleware (error logging)
5. GZipMiddleware (compression)
+ Global: ii_agent_error_handler for IIAgentError
```

## Socket.IO Handlers (realtime/handlers/)

| Command | Handler | Purpose |
|---------|---------|---------|
| `query` | `UserQueryHandler` | Main agent execution |
| `plan` | `PlanHandler` | Planning mode |
| `continue_run` | `ContinueRunHandler` | Resume agent |
| `cancel` | `CancelHandler` | Cancel execution |
| `ping` | `PingHandler` | Keep-alive |
| `awake_sandbox` | `AwakeSandboxHandler` | Wake sandbox |
| `sandbox_status` | `SandboxStatusHandler` | Check sandbox |
| `workspace_info` | `WorkspaceInfoHandler` | Workspace details |
| `enhance_prompt` | `EnhancePromptHandler` | Prompt enhancement |
| `publish` | `PublishProjectHandler` | Publish project |
| `cloud_run_publish` | `CloudRunPublishHandler` | Deploy to Cloud Run |
| `save_env` | `SaveEnvHandler` | Save env vars |
| `start_fork` | `StartForkHandler` | Fork session |
| `submit_testflight` | `SubmitTestflightHandler` | iOS TestFlight |
| `apple_auth` | `AppleAuthLoginHandler` | Apple OAuth login |
| `apple_auth_2fa` | `AppleAuth2FAHandler` | Apple 2FA |
| `apple_auth_select_team` | `AppleAuthSelectTeamHandler` | Apple team selection |
| `apple_app_setup` | `AppleAppSetupHandler` | Apple app config |
| `apple_list_apps` | `AppleListAppsHandler` | List Apple apps |
| `apple_check_auth` | `AppleCheckAuthHandler` | Check Apple auth |
| `save_expo_token` | `SaveExpoTokenHandler` | Save push token |

Factory: `realtime/handlers/factory.py::CommandHandlerFactory`
Manager: `realtime/manager.py::SocketIOManager`

## Service → Repository Mapping

| Domain | Service | Repository |
|--------|---------|------------|
| users | `UserService` | `UserRepository`, `APIKeyRepository` |
| sessions | `SessionService` | `SessionRepository` |
| sessions/pin | `SessionPinService` | `PinRepository` |
| sessions/wishlist | `SessionWishlistService` | `WishlistRepository` |
| tasks | `RunTaskService` | `RunTaskRepository`, `TaskLogRepository` |
| chat/messages | `MessageService` | `ChatMessageRepository` |
| chat/runs | `ChatRunService` | `ChatRunRepository` |
| billing | `BillingService` | (via Stripe API) |
| credits | `CreditService` | (credit models) |
| agents/runs | `AgentRunService` | `AgentRunTaskRepository` |
| files | `FileService` | `FileRepository` |
| projects | `ProjectService` | `ProjectRepository` |
| projects/deployments | `DeploymentsService` | `DeploymentsRepository` |
| projects/databases | `DatabaseService` | `ProjectDatabaseRepository` |
| projects/subdomains | `SubdomainService` | `SubdomainRepository` |
| projects/design | `ProjectDesignService` | `ProjectDesignRepository` |
| content/slides | `SlideService` | `SlideContentRepository` |
| content/slides/design | `SlideDesignService` | `SlideDesignRepository` |
| content/slides/templates | `SlideTemplateService` | `SlideTemplateRepository` |
| content/slides/nano_banana | `NanoBananaService` | `NanoBananaRepository` |
| content/media | `MediaTemplateService` | `MediaTemplateRepository` |
| content/storybook | `StorybookService` | `StorybookRepository` |
| integrations/connectors | `ConnectorService` | `ConnectorRepository` |
| integrations/composio | `ComposioService` | `ComposioProfileRepository` |
| integrations/apple | `AppleCredentialService` | `AppleCredentialRepository` |
| settings/llm | `LLMSettingService` | `LLMSettingRepository` |
| settings/mcp | `MCPSettingService` | `MCPSettingRepository` |
| settings/skills | `SkillService` | `SkillRepository` |
| realtime/events | — | `EventRepository` |

## Auth Dependencies (auth/dependencies.py)

```python
CurrentUser  = Annotated[User, Depends(get_current_user)]  # User.id is uuid.UUID
DBSession    = Annotated[AsyncSession, Depends(get_db)]
SettingsDep  = Annotated[Settings, Depends(get_settings)]
ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]
```

## Cron Jobs (workers/cron/)

| Job | Status |
|-----|--------|
| `refresh_free_user_credits` | Active |
| `refresh_annual_subscription_credits` | Inactive |
