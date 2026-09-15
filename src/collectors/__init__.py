"""소스 타입 → 수집 함수 레지스트리."""
from __future__ import annotations

from .generic_board import collect as collect_html_board
from .jobkorea import collect as collect_jobkorea
from .saramin import collect as collect_saramin
from .work24 import collect as collect_work24

REGISTRY = {
    "html_board": collect_html_board,
    "saramin": collect_saramin,
    "jobkorea": collect_jobkorea,
    "work24": collect_work24,
}

__all__ = ["REGISTRY"]
