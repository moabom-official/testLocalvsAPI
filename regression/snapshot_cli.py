"""골든 픽스처 적재/검증 CLI (오프라인 전용 — DB·LLM 호출 없음).

사용:
  python -m regression.snapshot_cli ingest --report 4 --file out.md --label v1
  python -m regression.snapshot_cli validate --report 2 --file new.json
  python -m regression.snapshot_cli list

실제 파이프라인을 돌려 골든을 캡처하는 live 모드는 Phase 0 범위 밖이다. 팀이
이미 가진 실제 출력물을 ingest 로 적재한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from regression._fixtures import (
    GOLDEN_ROOT,
    discover_fixtures,
    ext_for,
    load_report,
    report_kind_for,
    validate,
)
from regression.fingerprint import fingerprint


def _normalized_text(report_kind: str, src_path: str) -> str:
    """저장용 정규화 — JSON 은 정렬·들여쓰기, 마크다운은 개행 정규화."""
    with open(src_path, "r", encoding="utf-8") as f:
        raw = f.read()
    if ext_for(report_kind) == "json":
        return json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n"
    return raw.replace("\r\n", "\n").rstrip() + "\n"


def cmd_ingest(args) -> int:
    report_kind = report_kind_for(args.report)
    if not os.path.isfile(args.file):
        print(f"[ERROR] 입력 파일이 없습니다: {args.file}")
        return 2

    dest_dir = os.path.join(GOLDEN_ROOT, report_kind)
    os.makedirs(dest_dir, exist_ok=True)
    ext = ext_for(report_kind)
    dest = os.path.join(dest_dir, f"{args.label}.{ext}")

    try:
        normalized = _normalized_text(report_kind, args.file)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 파싱 실패: {e}")
        return 2

    with open(dest, "w", encoding="utf-8") as f:
        f.write(normalized)

    report = load_report(report_kind, dest)
    result = validate(report_kind, report)
    fp = fingerprint(report_kind, report)

    meta = {
        "report_kind": report_kind,
        "label": args.label,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_path": os.path.abspath(args.file),
        "fingerprint": fp,
        "contract_status": result.status,
    }
    meta_path = os.path.join(dest_dir, f"{args.label}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[OK] 적재 완료: {dest}")
    print(f"     meta      : {meta_path}")
    print(f"     status    : {result.status}")
    if result.violations:
        print(result.detail())
    return 0


def cmd_validate(args) -> int:
    report_kind = report_kind_for(args.report)
    if not os.path.isfile(args.file):
        print(f"[ERROR] 입력 파일이 없습니다: {args.file}")
        return 2
    try:
        report = load_report(report_kind, args.file)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 파싱 실패: {e}")
        return 2

    result = validate(report_kind, report)
    print(result.detail())
    # validate 는 점검용 — 위반이 있어도 종료 코드 1 로 알리되 게이트는 아님
    return 0 if result.is_ok else 1


def cmd_list(args) -> int:
    fixtures = discover_fixtures()
    if not fixtures:
        print("(골든 픽스처 없음)")
        return 0
    print(f"{'report':<9} {'label':<14} {'status':<18} path")
    print("-" * 72)
    for fx in fixtures:
        try:
            status = fx.check().status
        except Exception as e:  # noqa: BLE001 — CLI 표시용
            status = f"load_error:{type(e).__name__}"
        rel = os.path.relpath(fx.path, os.path.dirname(GOLDEN_ROOT))
        print(f"{fx.report_kind:<9} {fx.label:<14} {status:<18} {rel}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m regression.snapshot_cli")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("ingest", help="파일을 골든 픽스처로 적재")
    pi.add_argument("--report", type=int, required=True, choices=(1, 2, 3, 4))
    pi.add_argument("--file", required=True)
    pi.add_argument("--label", required=True)
    pi.set_defaults(func=cmd_ingest)

    pv = sub.add_parser("validate", help="임의 파일에 계약 검증기 실행")
    pv.add_argument("--report", type=int, required=True, choices=(1, 2, 3, 4))
    pv.add_argument("--file", required=True)
    pv.set_defaults(func=cmd_validate)

    pl = sub.add_parser("list", help="golden/ 픽스처 목록")
    pl.set_defaults(func=cmd_list)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
