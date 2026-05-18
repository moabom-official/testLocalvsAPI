from regression.run_gate import GateReport, GateRow, collect_gate_report


def test_gate_passes_on_current_golden():
    report = collect_gate_report()
    assert report.passed
    assert report.exit_code == 0
    assert report.failing == []


def test_gate_scoped_to_single_report():
    report = collect_gate_report(only_report="report4")
    assert {r.report_kind for r in report.rows} == {"report4"}
    assert report.exit_code == 0


def test_valid_fixtures_are_ok():
    report = collect_gate_report()
    valids = [r for r in report.rows if r.is_valid_label]
    assert len(valids) == 4  # report1~4 각 valid 1개
    assert all(r.status == "ok" for r in valids)


def test_broken_fixtures_do_not_fail_gate():
    report = collect_gate_report()
    broken = [r for r in report.rows if r.label == "broken"]
    assert broken and all(r.status == "violated" for r in broken)
    # broken 은 valid 라벨이 아니므로 게이트를 실패시키지 않는다
    assert report.passed


def test_violated_valid_label_fails_gate():
    rows = [
        GateRow("report1", "valid", "violated", True, 1, 0, ["R1.MISSING_SECTION"]),
        GateRow("report2", "broken", "violated", False, 1, 0, ["R2.X"]),
    ]
    report = GateReport(rows=rows)
    assert not report.passed
    assert report.exit_code == 1
    assert len(report.failing) == 1
    assert report.failing[0].report_kind == "report1"


def test_fallback_valid_label_does_not_fail_gate():
    rows = [GateRow("report4", "valid", "fallback", True, 0, 1, [])]
    report = GateReport(rows=rows)
    assert report.passed
    assert report.exit_code == 0
