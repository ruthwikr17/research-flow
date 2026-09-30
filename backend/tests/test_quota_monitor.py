from datetime import datetime, timedelta, timezone

from app.services.quota_monitor import QuotaMonitor


def test_rate_limited_target_rejoins_after_cooldown():
    monitor = QuotaMonitor(["project-a", "project-b"], cooldown_seconds=10)
    monitor.record_rate_limit_error("gemini", "project-a")
    assert "project-a" not in monitor.get_available_targets("gemini")
    monitor.usage[("gemini", "project-a")].exhausted_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert "project-a" in monitor.get_available_targets("gemini")

