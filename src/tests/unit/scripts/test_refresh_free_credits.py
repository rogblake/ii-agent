from ii_agent.workers.cron import refresh_free_user_credits as free_refresh


def test_monthly_free_credit_allowance_uses_plan_allowance(settings_factory, monkeypatch):
    monkeypatch.setattr(free_refresh, "get_settings", lambda: settings_factory())

    assert free_refresh._monthly_free_credit_allowance() == 10.0


def test_monthly_free_credit_allowance_falls_back_when_missing(settings_factory, monkeypatch):
    settings = settings_factory(
        credits={"default_plans_credits": {"free": None}, "default_user_credits": 7.5}
    )
    monkeypatch.setattr(free_refresh, "get_settings", lambda: settings)

    assert free_refresh._monthly_free_credit_allowance() == 7.5


def test_build_cron_job_definition_has_expected_name_and_schedule():
    job = free_refresh.build_cron_job_definition(schedule="0 12 * * *")

    assert job.name == "ii-agent-free-credit-refresh"
    assert job.schedule == "0 12 * * *"
    assert "refresh_free_user_credits" in job.command
