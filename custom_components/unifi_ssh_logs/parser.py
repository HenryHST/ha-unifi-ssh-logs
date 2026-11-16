"""Regex rule engine for UniFi syslog lines."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .const import (
    MAX_CUSTOM_RULES,
    MAX_PATTERN_LEN,
    MAX_TOTAL_RULES,
    PUBLIC_SAMPLE_LEN,
    SOURCE_ANY,
)
from .sanitize import redact_text

_LOGGER = logging.getLogger(__name__)

MAX_SAMPLE_LEN = PUBLIC_SAMPLE_LEN

# Nested quantifiers that commonly enable catastrophic backtracking.
_NESTED_QUANT = re.compile(
    r"(\([^)]*[+*][^)]*\)[+*{])|([+*]\s*[+*])|(\{\d+,?\d*\}\s*[+*{])"
)


@dataclass
class AlertRule:
    """Compiled alert rule."""

    id: str
    name: str
    severity: str
    source: str
    pattern: str
    enabled: bool = True
    clear_after_minutes: int = 30
    regex: re.Pattern[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.regex = re.compile(self.pattern)


@dataclass
class RuleMatch:
    """A single rule match against a log line."""

    rule_id: str
    name: str
    severity: str
    source: str
    line: str
    matched_at: datetime


@dataclass
class AlertState:
    """Runtime state for a rule binary sensor."""

    active: bool = False
    match_count: int = 0
    last_match: datetime | None = None
    sample_line: str = ""
    severity: str = "info"
    name: str = ""
    clear_after: timedelta = field(default_factory=lambda: timedelta(minutes=30))


def _load_yaml_rules(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as err:
        _LOGGER.error("Failed to load rules from %s: %s", path, err)
        return []
    if not isinstance(data, list):
        _LOGGER.error("Rules file %s must be a YAML list", path)
        return []
    return [item for item in data if isinstance(item, dict)]


def _pattern_allowed(pattern: str) -> bool:
    """Reject oversized or nested-quantifier patterns (ReDoS guard)."""
    if len(pattern) > MAX_PATTERN_LEN:
        return False
    if _NESTED_QUANT.search(pattern):
        return False
    return True


def load_rules(
    bundled_path: Path,
    custom_dir: Path | None = None,
) -> list[AlertRule]:
    """Load bundled rules, then merge custom rules.d/*.yaml (override by id)."""
    by_id: dict[str, dict[str, Any]] = {}
    for item in _load_yaml_rules(bundled_path):
        rid = str(item.get("id") or "").strip()
        if rid:
            by_id[rid] = item

    custom_count = 0
    if custom_dir and custom_dir.is_dir():
        for path in sorted(custom_dir.glob("*.yaml")) + sorted(custom_dir.glob("*.yml")):
            for item in _load_yaml_rules(path):
                if custom_count >= MAX_CUSTOM_RULES:
                    _LOGGER.warning(
                        "Ignoring custom rules beyond MAX_CUSTOM_RULES=%s",
                        MAX_CUSTOM_RULES,
                    )
                    break
                rid = str(item.get("id") or "").strip()
                if rid:
                    by_id[rid] = item
                    custom_count += 1
            if custom_count >= MAX_CUSTOM_RULES:
                break

    rules: list[AlertRule] = []
    for item in by_id.values():
        if len(rules) >= MAX_TOTAL_RULES:
            _LOGGER.warning("Ignoring rules beyond MAX_TOTAL_RULES=%s", MAX_TOTAL_RULES)
            break
        try:
            pattern = str(item["pattern"])
            if not _pattern_allowed(pattern):
                _LOGGER.error(
                    "Rejected rule %s: pattern too long or nested quantifiers",
                    item.get("id"),
                )
                continue
            rules.append(
                AlertRule(
                    id=str(item["id"]),
                    name=str(item.get("name") or item["id"]),
                    severity=str(item.get("severity") or "warning"),
                    source=str(item.get("source") or SOURCE_ANY),
                    pattern=pattern,
                    enabled=bool(item.get("enabled", True)),
                    clear_after_minutes=int(item.get("clear_after_minutes") or 30),
                )
            )
        except (KeyError, TypeError, re.error) as err:
            _LOGGER.error("Invalid rule %s: %s", item.get("id"), err)
    return rules


def match_lines(
    rules: list[AlertRule],
    lines_by_source: dict[str, list[str]],
) -> list[RuleMatch]:
    """Match log lines against enabled rules filtered by source."""
    now = datetime.now(timezone.utc)
    matches: list[RuleMatch] = []
    for source, lines in lines_by_source.items():
        for line in lines:
            text = line.rstrip("\n")
            if not text.strip():
                continue
            for rule in rules:
                if not rule.enabled:
                    continue
                if rule.source not in (SOURCE_ANY, source):
                    continue
                if rule.regex.search(text):
                    matches.append(
                        RuleMatch(
                            rule_id=rule.id,
                            name=rule.name,
                            severity=rule.severity,
                            source=source,
                            line=redact_text(text, max_len=MAX_SAMPLE_LEN),
                            matched_at=now,
                        )
                    )
    return matches


def apply_matches(
    states: dict[str, AlertState],
    rules: list[AlertRule],
    matches: list[RuleMatch],
) -> list[RuleMatch]:
    """Update alert states from matches; return newly activated matches for events."""
    rule_meta = {r.id: r for r in rules}
    for rule in rules:
        if rule.id not in states:
            states[rule.id] = AlertState(
                name=rule.name,
                severity=rule.severity,
                clear_after=timedelta(minutes=rule.clear_after_minutes),
            )

    newly_active: list[RuleMatch] = []
    for match in matches:
        meta = rule_meta.get(match.rule_id)
        state = states.setdefault(
            match.rule_id,
            AlertState(
                name=match.name,
                severity=match.severity,
                clear_after=timedelta(
                    minutes=meta.clear_after_minutes if meta else 30
                ),
            ),
        )
        was_active = state.active
        state.active = True
        state.match_count += 1
        state.last_match = match.matched_at
        state.sample_line = match.line
        state.severity = match.severity
        state.name = match.name
        if not was_active:
            newly_active.append(match)
    return newly_active


def clear_expired(states: dict[str, AlertState], now: datetime | None = None) -> list[str]:
    """Clear alerts past clear_after; return cleared rule ids."""
    now = now or datetime.now(timezone.utc)
    cleared: list[str] = []
    for rule_id, state in states.items():
        if not state.active or state.last_match is None:
            continue
        if now - state.last_match >= state.clear_after:
            state.active = False
            cleared.append(rule_id)
    return cleared


def clear_all(states: dict[str, AlertState]) -> None:
    """Manually clear all alert states."""
    for state in states.values():
        state.active = False
