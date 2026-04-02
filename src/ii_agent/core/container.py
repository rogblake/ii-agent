"""Centralized service container for non-router consumers.

Created once in app.py lifespan after secrets are loaded.
Passed to socket handlers, MCP SSE, subscribers, cron, etc.

Router endpoints use FastAPI Depends() via per-domain dependencies.py files instead.

The create() factory delegates to the same factory functions used by FastAPI
Depends(), keeping wiring logic in a single place per service.
"""

from __future__ import annotations

from ii_agent.core.config.settings import get_settings

# -- Factory imports (from domain dependencies.py files) ----------------
from ii_agent.auth.users.dependencies import (
    get_api_key_repository,
    get_user_repository,
    get_user_service,
    get_waitlist_repository,
)
from ii_agent.billing.credits.dependencies import (
    get_credit_service,
    get_metrics_repository,
)
from ii_agent.billing.dependencies import (
    get_billing_service,
    get_stripe_config,
)
from ii_agent.content.media.dependencies import (
    get_media_template_repository,
    get_media_template_service,
)
from ii_agent.content.skills.dependencies import (
    get_skill_repository,
    get_skill_service,
)
from ii_agent.content.storybook.dependencies import (
    get_storybook_repository,
    get_storybook_service,
)
from ii_agent.core.llm.dependencies import (
    get_llm_billing_service,
    get_llm_config_resolver,
)
from ii_agent.engine.agents.dependencies import (
    get_agent_run_service,
    get_agent_run_task_repository,
    get_agent_service,
    get_execution_service,
    get_plan_service,
)
from ii_agent.engine.sandboxes.dependencies import (
    get_sandbox_repository,
    get_sandbox_service,
)
from ii_agent.files.dependencies import (
    get_file_repository,
    get_file_service,
)
from ii_agent.integrations.connectors.composio.dependencies import (
    get_composio_profile_repository,
    get_composio_service,
)
from ii_agent.integrations.connectors.dependencies import (
    get_connector_repository,
    get_connector_service,
)
from ii_agent.projects.dependencies import (
    get_deployment_orchestration_service,
    get_project_repository,
    get_project_service,
)
from ii_agent.projects.deployments.dependencies import (
    get_deployments_repository,
    get_deployments_service,
)
from ii_agent.realtime.events.dependencies import (
    get_event_repository,
    get_event_service,
)
from ii_agent.sessions.dependencies import (
    get_session_fork_service,
    get_session_repository,
    get_session_service,
    get_session_validation_service,
)
from ii_agent.settings.llm.dependencies import (
    get_llm_setting_repository,
    get_llm_setting_service,
)
from ii_agent.settings.mcp.dependencies import (
    get_mcp_setting_repository,
    get_mcp_setting_service,
)

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ii_agent.engine.agents.agent_run_service import AgentRunService
    from ii_agent.engine.agents.agent_service import AgentService
    from ii_agent.engine.agents.execution_service import ExecutionService
    from ii_agent.engine.agents.plan_service import PlanService
    from ii_agent.billing.service import BillingService
    from ii_agent.billing.credits.service import CreditService
    from ii_agent.integrations.connectors.composio.service import ComposioService
    from ii_agent.integrations.connectors.service import ConnectorService
    from ii_agent.core.config.settings import Settings
    from ii_agent.core.llm.billing_service import LLMBillingService
    from ii_agent.core.llm.config_resolver import LLMConfigResolver
    from ii_agent.realtime.events.service import EventService
    from ii_agent.files.service import FileService
    from ii_agent.settings.llm.service import LLMSettingService
    from ii_agent.settings.mcp.service import MCPSettingService
    from ii_agent.content.media.service import MediaTemplateService
    from ii_agent.projects.deployment_orchestration_service import (
        DeploymentOrchestrationService,
    )
    from ii_agent.projects.deployments.service import DeploymentsService
    from ii_agent.projects.service import ProjectService
    from ii_agent.engine.sandboxes.service import SandboxService
    from ii_agent.sessions.service import SessionService
    from ii_agent.sessions.fork_service import SessionForkService
    from ii_agent.sessions.validation_service import SessionValidationService
    from ii_agent.content.skills.service import SkillService
    from ii_agent.content.storybook.service import StorybookService
    from ii_agent.auth.users.service import UserService


@dataclass
class ServiceContainer:
    """Centralized service container for non-router consumers.

    A single ServiceContainer is created once in app.py lifespan (after
    GCP secrets are loaded) and threaded through to all non-router consumers:
    socket handlers, MCP SSE, subscribers, and cron tasks.

    This avoids module-level singleton imports and ensures every consumer
    receives services wired with the post-secrets-loaded config.
    """

    config: Settings
    credit_service: CreditService
    llm_billing_service: LLMBillingService
    llm_config_resolver: LLMConfigResolver
    session_service: SessionService
    session_fork_service: SessionForkService
    session_validation_service: SessionValidationService
    event_service: EventService
    llm_setting_service: LLMSettingService
    file_service: FileService
    agent_run_service: AgentRunService
    agent_service: AgentService
    execution_service: ExecutionService
    plan_service: PlanService
    sandbox_service: SandboxService
    project_service: ProjectService
    deployments_service: DeploymentsService
    deployment_orchestration_service: DeploymentOrchestrationService
    billing_service: BillingService
    mcp_setting_service: MCPSettingService
    user_service: UserService
    connector_service: ConnectorService
    composio_service: ComposioService
    media_template_service: MediaTemplateService
    skill_service: SkillService
    storybook_service: StorybookService

    @classmethod
    def create(cls) -> ServiceContainer:
        """Factory that wires all services with shared config.

        Call this after GCP secrets have been applied to settings.

        Delegates to factory functions from domain dependencies.py files
        to keep wiring logic in a single place per service.
        """

        cfg = get_settings()

        # ── Repositories (leaf nodes) ────────────────────────────────────────
        user_repo = get_user_repository()
        api_key_repo = get_api_key_repository()
        waitlist_repo = get_waitlist_repository()
        session_repo = get_session_repository()
        event_repo = get_event_repository()
        project_repo = get_project_repository()
        file_repo = get_file_repository()
        sandbox_repo = get_sandbox_repository()
        agent_run_repo = get_agent_run_task_repository()
        llm_setting_repo = get_llm_setting_repository()
        mcp_setting_repo = get_mcp_setting_repository()
        media_template_repo = get_media_template_repository()
        deployments_repo = get_deployments_repository()
        composio_repo = get_composio_profile_repository()
        skill_repo = get_skill_repository()
        storybook_repo = get_storybook_repository()
        metrics_repo = get_metrics_repository()
        connector_repo = get_connector_repository()

        # ── Leaf services (depend only on repos / config) ────────────────────
        credit_svc = get_credit_service(user_repo, metrics_repo)
        agent_run_svc = get_agent_run_service(agent_run_repo)
        event_svc = get_event_service(event_repo)
        mcp_setting_svc = get_mcp_setting_service(mcp_setting_repo)
        sandbox_svc = get_sandbox_service(sandbox_repo)
        skill_svc = get_skill_service(skill_repo)
        storybook_svc = get_storybook_service(storybook_repo)
        connector_svc = get_connector_service(connector_repo)
        agent_svc = get_agent_service()
        execution_svc = get_execution_service()
        plan_svc = get_plan_service()
        deployment_orch_svc = get_deployment_orchestration_service()
        stripe_config = get_stripe_config()

        # ── Services with cross-service deps ─────────────────────────────────
        user_svc = get_user_service(user_repo, api_key_repo, waitlist_repo)
        session_svc = get_session_service(
            session_repo, event_repo, sandbox_repo, agent_run_svc
        )
        session_fork_svc = get_session_fork_service(session_repo, sandbox_repo)
        file_svc = get_file_service(file_repo, session_repo)
        llm_setting_svc = get_llm_setting_service(llm_setting_repo, session_repo)
        composio_svc = get_composio_service(mcp_setting_svc, composio_repo)
        billing_svc = get_billing_service(stripe_config, user_repo)
        project_svc = get_project_service(project_repo, session_repo)
        deployments_svc = get_deployments_service(project_repo, deployments_repo)
        media_template_svc = get_media_template_service(media_template_repo)

        # ── LLM infrastructure & validation ──────────────────────────────────
        llm_billing_svc = get_llm_billing_service(credit_svc, cfg)
        llm_config_resolver = get_llm_config_resolver(llm_setting_svc, cfg)
        session_validation_svc = get_session_validation_service(
            session_svc, credit_svc
        )

        return cls(
            config=cfg,
            credit_service=credit_svc,
            llm_billing_service=llm_billing_svc,
            llm_config_resolver=llm_config_resolver,
            session_service=session_svc,
            session_fork_service=session_fork_svc,
            session_validation_service=session_validation_svc,
            event_service=event_svc,
            llm_setting_service=llm_setting_svc,
            file_service=file_svc,
            agent_run_service=agent_run_svc,
            agent_service=agent_svc,
            execution_service=execution_svc,
            plan_service=plan_svc,
            sandbox_service=sandbox_svc,
            project_service=project_svc,
            deployments_service=deployments_svc,
            deployment_orchestration_service=deployment_orch_svc,
            billing_service=billing_svc,
            mcp_setting_service=mcp_setting_svc,
            user_service=user_svc,
            connector_service=connector_svc,
            composio_service=composio_svc,
            media_template_service=media_template_svc,
            skill_service=skill_svc,
            storybook_service=storybook_svc,
        )
