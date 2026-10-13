import json

import pytest

from sitecheck.cli import run
from sitecheck.models import SiteReport


def _report(host: str, grade: str, score: int) -> SiteReport:
    return SiteReport(host=host, url=f"https://{host}", score=score, grade=grade)


def test_run_with_no_hosts_returns_usage_error(capsys):
    exit_code = run([])

    assert exit_code == 2
    assert "No hosts given" in capsys.readouterr().out


def test_run_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        "sitecheck.cli.analyze", lambda host, timeout=10.0: _report(host, "A", 95)
    )

    exit_code = run(["good.example", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["host"] == "good.example"
    assert payload[0]["grade"] == "A"


def test_run_fail_under_passes_when_grade_is_good_enough(monkeypatch):
    monkeypatch.setattr(
        "sitecheck.cli.analyze", lambda host, timeout=10.0: _report(host, "B", 85)
    )

    exit_code = run(["good.example", "--json", "--fail-under", "C"])

    assert exit_code == 0


def test_run_fail_under_fails_when_grade_is_too_low(monkeypatch):
    monkeypatch.setattr(
        "sitecheck.cli.analyze", lambda host, timeout=10.0: _report(host, "D", 65)
    )

    exit_code = run(["bad.example", "--json", "--fail-under", "C"])

    assert exit_code == 1


def test_run_reads_hosts_from_file(tmp_path, monkeypatch):
    hosts_file = tmp_path / "urls.txt"
    hosts_file.write_text("a.example\n# a comment\n\nb.example\n", encoding="utf-8")

    seen = []
    monkeypatch.setattr(
        "sitecheck.cli.analyze",
        lambda host, timeout=10.0: seen.append(host) or _report(host, "A", 95),
    )

    exit_code = run(["-f", str(hosts_file), "--json"])

    assert exit_code == 0
    assert seen == ["a.example", "b.example"]


def test_run_missing_file_returns_usage_error(tmp_path, capsys):
    missing = tmp_path / "missing.txt"

    exit_code = run(["-f", str(missing)])

    assert exit_code == 2
    assert "Could not read" in capsys.readouterr().out


@pytest.mark.parametrize("grade", ["A", "B", "C", "D", "F"])
def test_run_accepts_all_fail_under_grades(monkeypatch, grade):
    monkeypatch.setattr(
        "sitecheck.cli.analyze", lambda host, timeout=10.0: _report(host, "A", 100)
    )

    exit_code = run(["good.example", "--json", "--fail-under", grade])

    assert exit_code == 0
