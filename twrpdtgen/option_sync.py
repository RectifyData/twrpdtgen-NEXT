# SPDX-License-Identifier: Apache-2.0
"""Single CLI-derived option schema for desktop and browser interfaces.

The generator's argparse parser is the source of truth: GUI controls are
rendered from its choices and every future supported option is auto-exposed.
Unrepresentable argparse actions fail loudly instead of silently diverging.
"""
from __future__ import annotations

from argparse import _StoreFalseAction, _StoreTrueAction
from pathlib import Path
from typing import Mapping

# These already have dedicated source/image/output controls or GUI actions.
_FIXED = frozenset((
    "help", "image", "output", "boot_image", "vendor_boot", "init_boot",
    "skeleton", "recovery_layout", "recovery_root_mode", "recovery_fragment",
    "boot_size", "recovery_size", "super_size", "dynamic_group_size",
    "overwrite", "extract_only", "gui", "web", "cli",
))
_CHOICE_FIELDS = ("skeleton", "recovery_layout", "recovery_root_mode")


def _actions():
    from twrpdtgen.main import build_parser
    return tuple(
        a for a in build_parser()._actions
        if a.option_strings and a.dest not in ("help", "gui", "web", "cli")
    )


def _kind(action):
    if isinstance(action, (_StoreTrueAction, _StoreFalseAction)):
        return "boolean"
    if action.nargs is not None:
        raise ValueError(
            "Unsupported CLI option {}; update option schema mapping"
            .format(action.dest))
    if action.choices is not None:
        return "choice"
    if action.type is Path:
        return "path"
    return "text"


def _extra_actions():
    return tuple(a for a in _actions() if a.dest not in _FIXED)


def interface_schema():
    """Return a JSON-safe schema for both GUIs; no hardcoded choice lists."""
    core = {}
    extras = []
    for action in _actions():
        kind = _kind(action)
        if action.dest in _CHOICE_FIELDS:
            core[action.dest] = {
                "choices": [str(c) for c in action.choices],
                "default": str(action.default),
            }
        if action.dest not in _FIXED:
            names = [s for s in action.option_strings if s.startswith("--")]
            if not names:
                raise ValueError(
                    "CLI flag {} lacks a long option for the GUI".format(
                        action.dest))
            extras.append({
                "name": action.dest,
                "flag": names[-1],
                "label": action.help or action.dest.replace("_", " ").title(),
                "kind": kind,
                "choices": (
                    [str(c) for c in action.choices]
                    if action.choices is not None else []),
                "default": (
                    bool(action.default) if kind == "boolean"
                    else str(action.default) if action.default is not None
                    else ""),
            })
    missing = _CHOICE_FIELDS and set(_CHOICE_FIELDS) - set(core)
    if missing:
        raise ValueError("Missing shared CLI option(s): {}".format(
            ", ".join(sorted(missing))))
    return {"choices": core, "extras": extras}


def validate_extra_values(values):
    """Reject unsupported/unknown frontend keys, even on localhost."""
    if values is None:
        values = {}
    if not isinstance(values, Mapping):
        raise ValueError("CLI options must be a mapping")
    actions = {a.dest: a for a in _extra_actions()}
    if set(values) - set(actions):
        raise ValueError(
            "Unknown GUI CLI options: {}".format(
                ", ".join(sorted(set(values) - set(actions)))))
    cleaned = {}
    for name, raw in values.items():
        action = actions[name]
        kind = _kind(action)
        if kind == "boolean":
            if type(raw) is not bool:
                raise ValueError("{} must be a checkbox value".format(name))
            cleaned[name] = raw
            continue
        if not isinstance(raw, str):
            raise ValueError("{} must be text".format(name))
        if len(raw) > 4096:
            raise ValueError("{} is too long".format(name))
        if raw and action.choices and raw not in [
                str(c) for c in action.choices]:
            raise ValueError("{} is not a valid choice".format(name))
        cleaned[name] = raw
    return cleaned


def extra_cli_argv(values):
    """Serialize GUI extras back into flags consumed by the real CLI parser."""
    cleaned = validate_extra_values(values)
    result = []
    for action in _extra_actions():
        if action.dest not in cleaned:
            continue
        raw = cleaned[action.dest]
        kind = _kind(action)
        flag = next(
            (s for s in action.option_strings if s.startswith("--")),
            action.option_strings[0])
        if kind == "boolean":
            if isinstance(action, _StoreTrueAction) and raw:
                result.append(flag)
            elif isinstance(action, _StoreFalseAction) and not raw:
                result.append(flag)
        elif raw:
            result.extend([flag, raw])
    return result
