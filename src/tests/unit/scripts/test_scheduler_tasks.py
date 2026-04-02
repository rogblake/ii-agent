from ii_agent.scripts import tasks


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


def test_start_scheduler_registers_cleanup_job(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.start_scheduler()

    assert fake_scheduler.started == 1
    assert len(fake_scheduler.jobs) == 1
    assert fake_scheduler.jobs[0][1]["id"] == "cleanup_stale_agent_run_tasks"


def test_shutdown_scheduler_is_idempotent(monkeypatch):
    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(tasks, "scheduler", fake_scheduler)

    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 0

    fake_scheduler.running = True
    tasks.shutdown_scheduler()
    assert fake_scheduler.stopped == 1
