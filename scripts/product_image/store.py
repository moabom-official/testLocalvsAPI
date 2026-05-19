"""tech_products.image_url 저장/조회 (Phase 3 단계 3).

URL(참조)만 저장 — 이미지 파일/바이너리 DB 저장 금지. DB 접근은 기존
scripts.database 경로 재사용(지연 import — 오프라인/순수 경로 보호).
"""
from __future__ import annotations

from typing import Optional


def get_product(product_id: int) -> Optional[dict]:
    from scripts.database.queries import query_one

    return query_one(
        "SELECT product_id, name, brand, category, image_url "
        "FROM tech_products WHERE product_id = %s",
        (product_id,),
    )


def get_product_image(product_id: int) -> Optional[str]:
    row = get_product(product_id)
    if not row:
        return None
    url = row.get("image_url")
    return url if (url and str(url).strip()) else None


def set_product_image(product_id: int, image_url: str) -> None:
    from scripts.database.queries import execute_update

    execute_update(
        "UPDATE tech_products SET image_url = %s WHERE product_id = %s",
        (image_url, product_id),
    )
