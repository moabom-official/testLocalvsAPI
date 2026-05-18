from regression.fingerprint import diff_fingerprints, fingerprint
from regression.tests._helpers import load_json, load_text


def test_markdown_fingerprint_deterministic():
    text = load_text("report4", "valid")
    assert fingerprint("report4", text) == fingerprint("report4", text)


def test_json_fingerprint_deterministic():
    data = load_json("report2", "valid")
    assert fingerprint("report2", data) == fingerprint("report2", data)


def test_removing_section_changes_fingerprint():
    text = load_text("report4", "valid")
    fp_old = fingerprint("report4", text)
    mutated = text.replace("## ⑥ 전작 대비 달라진 점 (표)", "")
    fp_new = fingerprint("report4", mutated)
    assert fp_old != fp_new
    diffs = diff_fingerprints(fp_old, fp_new)
    assert diffs
    assert any("⑥" in d for d in diffs)


def test_identical_fingerprints_no_diff():
    text = load_text("report1", "valid")
    fp = fingerprint("report1", text)
    assert diff_fingerprints(fp, fp) == []


def test_json_key_removal_reported():
    data = load_json("report3", "valid")
    fp_old = fingerprint("report3", data)
    data.pop("verdict")
    fp_new = fingerprint("report3", data)
    diffs = diff_fingerprints(fp_old, fp_new)
    assert any("verdict" in d for d in diffs)


def test_unknown_report_kind_raises():
    import pytest

    with pytest.raises(ValueError):
        fingerprint("report9", "x")
