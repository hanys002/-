"""소스 타입 → 수집 함수 레지스트리."""
from __future__ import annotations

from .generic_board import collect as collect_html_board
from .portal_search import collect as collect_portal
from .row_board import collect as collect_row_board
from .work24 import collect as collect_work24

REGISTRY = {
    "html_board": collect_html_board,
    "portal_search": collect_portal,
    "row_board": collect_row_board,
    "work24": collect_work24,
}

__all__ = ["REGISTRY"]
