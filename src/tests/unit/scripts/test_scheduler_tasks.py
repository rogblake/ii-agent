from ii_agent.workers.cron import tasks


class FakeScheduler:
    def __init__(self):
        self.running = False
        self.jobs = []
        self.started = 0
        self.stopped = 0

    def add_job(self, *args, **kwargs):
        self.jobs.append((args, kwargs))

    def start(self):
        self.running = True
        self.started += 1

    def shutdown(self, wait=True):
        self.running = False
        self.stopped += 1

    def get_jobs(self):
        return self.jobs


def test_start_scheduler_registers_cleanup_jobs(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.start_scheduler()

    assert fake_scheduler.started == 1
    assert len(fake_scheduler.jobs) == 5
    job_ids = [j[1]["id"] for j in fake_scheduler.jobs]
    assert "cleanup_stale_agent_run_tasks" in job_ids
    assert "cleanup_stale_chat_runs" in job_ids
    assert "expire_stale_reservations" in job_ids
    assert "retry_billing_usage_facts" in job_ids
    assert "alert_settlement_failures" in job_ids


def test_shutdown_scheduler_is_idempotent(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 0

    fake_scheduler.running = True
    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 1
