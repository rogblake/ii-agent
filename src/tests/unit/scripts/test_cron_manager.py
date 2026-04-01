from types import SimpleNamespace

from ii_agent.workers.cron.cron_manager import CronJobDefinition, CronManager


class FakeCron:
    def __init__(self):
        self.entries = []
        self.writes = 0

    def __iter__(self):
        return iter(self.entries)

    def new(self, command, comment):
        entry = SimpleNamespace(command=command, comment=comment, schedule=None)

        def _setall(schedule):
            entry.schedule = schedule

        entry.setall = _setall
        self.entries.append(entry)
        return entry

    def remove(self, entry):
        self.entries.remove(entry)

    def write(self):
        self.writes += 1


def test_install_replaces_existing_jobs_and_writes():
    cron = FakeCron()
    cron.entries.append(SimpleNamespace(comment="job-a", command="old", setall=lambda *_: None))

    manager = CronManager(tab=cron)
    manager.install(job=CronJobDefinition(name="job-a", schedule="* * * * *", command="echo hi"))

    assert len(cron.entries) == 1
    assert cron.entries[0].command == "echo hi"
    assert cron.writes == 1


def test_remove_returns_signal_and_skips_write_on_dry_run():
    cron = FakeCron()
    cron.entries.append(SimpleNamespace(comment="job-a", command="x", setall=lambda *_: None))

    manager = CronManager(tab=cron)
    removed = manager.remove(name="job-a", dry_run=True)

    assert removed is True
    assert cron.writes == 0


def test_sync_replaces_only_managed_jobs():
    cron = FakeCron()
    cron.entries.extend(
        [
            SimpleNamespace(comment="managed", command="old", setall=lambda *_: None),
            SimpleNamespace(comment="unmanaged", command="keep", setall=lambda *_: None),
        ]
    )

    manager = CronManager(tab=cron)
    manager.sync(jobs=[CronJobDefinition(name="managed", schedule="0 * * * *", command="new")])

    assert any(e.comment == "managed" and e.command == "new" for e in cron.entries)
    assert any(e.comment == "unmanaged" and e.command == "keep" for e in cron.entries)
