from __future__ import annotations

from autospace.models import MatchRule, Window


def window_matches(window: Window, rule: MatchRule) -> bool:
    if rule.app_id and _norm(window.app_id) != _norm(rule.app_id):
        return False
    if rule.wm_class and _norm(window.wm_class) != _norm(rule.wm_class):
        return False
    if rule.title and _norm(rule.title) not in _norm(window.title):
        return False
    if rule.pid is not None and window.pid != rule.pid:
        return False
    return True


def _norm(value: str | None) -> str:
    return (value or "").casefold()
