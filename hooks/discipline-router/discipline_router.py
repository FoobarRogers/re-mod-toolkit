#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode SessionStart Discipline router (test1).

Routes an exact model name to a separately configured agent profile. No Handoff.
This is an optional-context injector, NOT a tool-permission mechanism.

Usage:
    python discipline_router.py [--config /path/to/route-config.json]

ZCode sends a single JSON line on stdin; stdout is reserved for protocol JSON.
The JSONL log never contains prompt text or the raw hook input.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent


def default_log_path() -> Path:
    # 日志写用户目录而非脚本同目录：插件化后脚本位于版本化安装缓存，
    # 升级会整体更换缓存目录，日志随之分叉残留。
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".zcode" / "data" / "re-mod-toolkit" / "logs" / "discipline-router.log.jsonl"


LOG_PATH = default_log_path()
try:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
INPUT_LIMIT = 1024 * 1024
DEFAULT_MAX_PROMPT_BYTES = 64 * 1024
DEFAULT_MAX_CONTEXT_CHARS = 20000
DEFAULT_MAX_OUTPUT_BYTES = 30000


def log(stage: str, **details: object) -> None:
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "stage": stage,
        **details,
    }
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def one_json_line() -> dict:
    """Read one event line without requiring EOF; bounded, strict UTF-8."""
    raw = sys.stdin.buffer.readline(INPUT_LIMIT + 1)
    if len(raw) > INPUT_LIMIT:
        raise ValueError("hook_input_exceeds_1MiB")
    if not raw.strip():
        raise ValueError("hook_input_empty")
    try:
        parsed = json.loads(raw.decode("utf-8-sig", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("hook_input_invalid_json_or_utf8") from exc
    if not isinstance(parsed, dict):
        raise ValueError("hook_input_not_object")
    return parsed


def string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def model_name(event: dict) -> str:
    value = event.get("model")
    if isinstance(value, dict):
        for key in ("id", "name", "model"):
            result = string_value(value.get(key))
            if result:
                return result
        return ""
    return string_value(value)


def model_candidates(model: str) -> tuple[str, ...]:
    """Full model first, then progressively strip provider path segments.

    Matching is done case-insensitively at the lookup site, so
    new-provider/glm-5.3-flash reaches a "GLM-5.3-Flash" route entry.
    """
    parts = [p for p in model.split("/") if p]
    return tuple("/".join(parts[i:]) for i in range(len(parts)))


def json_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig") as fp:
            raw = fp.read()
        cfg = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"config_read_failed: {path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ValueError("config_root_not_object")
    return cfg


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    found = {}
    for key, value in pairs:
        if key in found:
            raise ValueError(f"duplicate_json_key: {key}")
        found[key] = value
    return found


def resolve_relative(path_string: str, parent: Path) -> Path:
    path = Path(path_string)
    return path if path.is_absolute() else parent / path


def checked_model_routes(config: dict) -> dict[str, str]:
    if config.get("schema_version") != 1:
        raise ValueError("unsupported_schema_version")
    if set(config) != {"schema_version", "models"}:
        raise ValueError("route_config_unrecognized_or_missing_fields")
    models = config["models"]
    if not isinstance(models, dict) or not models:
        raise ValueError("route_models_must_be_nonempty_object")
    if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v.strip() for k, v in models.items()):
        raise ValueError("route_models_entries_must_be_nonempty_strings")
    return models


def profile_for(path: Path) -> dict:
    cfg = json_config(path)
    permitted = {"profile_id", "enabled", "prompt", "heading", "prepend", "max_prompt_bytes", "max_context_chars", "max_output_bytes"}
    required = {"profile_id", "enabled", "prompt", "heading"}
    if not required.issubset(cfg) or set(cfg) - permitted:
        raise ValueError("profile_missing_or_unknown_fields")
    if not isinstance(cfg["profile_id"], str) or not cfg["profile_id"].strip():
        raise ValueError("profile_id_invalid")
    if not isinstance(cfg["enabled"], bool):
        raise ValueError("enabled_must_be_boolean")
    for key in ("prompt", "heading"):
        if not isinstance(cfg[key], str) or not cfg[key].strip():
            raise ValueError(f"{key}_must_be_nonempty_string")
    if "prepend" in cfg and (not isinstance(cfg["prepend"], str) or not cfg["prepend"].strip()):
        raise ValueError("prepend_must_be_nonempty_string_when_present")
    defaults = {
        "max_prompt_bytes": DEFAULT_MAX_PROMPT_BYTES,
        "max_context_chars": DEFAULT_MAX_CONTEXT_CHARS,
        "max_output_bytes": DEFAULT_MAX_OUTPUT_BYTES,
    }
    for key, default in defaults.items():
        value = cfg.get(key, default)
        if type(value) is not int or value < 256 or value > (1024 * 1024):
            raise ValueError(f"{key}_invalid_positive_integer")
        cfg[key] = value
    return cfg


def inject_for(event: dict, config_path: Path) -> tuple[str | None, dict]:
    event_name = string_value(event.get("hook_event_name")) or string_value(event.get("hookEventName"))
    source = string_value(event.get("source"))
    agent_type = string_value(event.get("agent_type")) or string_value(event.get("agentType"))
    model = model_name(event)
    diagnostics = {"event": event_name or "(missing)", "source": source or "(missing)",
                   "agent_type": agent_type or "(missing)", "model": model or "(missing)"}

    if event_name and event_name != "SessionStart":
        return None, {**diagnostics, "reason": "wrong_event"}
    if not model:
        return None, {**diagnostics, "reason": "model_missing"}

    routes = checked_model_routes(json_config(config_path))
    routes_by_fold = {key.casefold(): value for key, value in routes.items()}
    selected_model = next((m for m in model_candidates(model) if m.casefold() in routes_by_fold), None)
    if selected_model is None:
        return None, {**diagnostics, "reason": "no_exact_model_route"}

    profile_path = resolve_relative(routes_by_fold[selected_model.casefold()], config_path.parent)
    profile = profile_for(profile_path)
    info = {**diagnostics, "matched_model": selected_model, "profile_id": profile["profile_id"],
            "profile_config": str(profile_path)}
    if not profile["enabled"]:
        return None, {**info, "reason": "profile_disabled"}

    prompt_path = resolve_relative(profile["prompt"], profile_path.parent)
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        return None, {**info, "reason": "prompt_unreadable", "error_type": type(exc).__name__}
    if len(prompt_bytes) > profile["max_prompt_bytes"]:
        return None, {**info, "reason": "prompt_over_byte_limit", "prompt_bytes": len(prompt_bytes)}
    try:
        prompt = prompt_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        return None, {**info, "reason": "prompt_invalid_utf8"}
    if not prompt.strip():
        return None, {**info, "reason": "prompt_empty"}

    # prepend 是可选前置段（如 DeepSeek Role）。读取失败只降级、不阻断主 discipline 注入：
    # role 是辅助载荷，它的缺失不应让整个 hook 放弃注入 discipline。
    prepend_text = ""
    prepend_note = "absent"
    prepend_path = None
    if profile.get("prepend"):
        prepend_path = resolve_relative(profile["prepend"], profile_path.parent)
        try:
            prepend_bytes = prepend_path.read_bytes()
        except OSError as exc:
            prepend_note = f"unreadable:{type(exc).__name__}"
        else:
            if len(prepend_bytes) > profile["max_prompt_bytes"]:
                prepend_note = "over_byte_limit"
            else:
                try:
                    prepend_text = prepend_bytes.decode("utf-8-sig", errors="strict")
                except UnicodeError:
                    prepend_note = "invalid_utf8"
                    prepend_text = ""
                else:
                    if not prepend_text.strip():
                        prepend_note = "empty"
                        prepend_text = ""
                    else:
                        prepend_note = "ok"
    info["prepend"] = prepend_note
    if prepend_text and prepend_path is not None:
        info["prepend_path"] = str(prepend_path)
        content = prepend_text.rstrip() + "\n\n" + profile["heading"].strip() + "\n\n" + prompt
    else:
        content = profile["heading"].strip() + "\n\n" + prompt
    if len(content) > profile["max_context_chars"]:
        return None, {**info, "reason": "context_over_character_limit", "context_chars": len(content)}

    output = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": content}},
                        ensure_ascii=False, separators=(",", ":"))
    output_bytes = len(output.encode("utf-8"))
    if output_bytes > profile["max_output_bytes"]:
        return None, {**info, "reason": "output_over_byte_limit", "output_bytes": output_bytes}

    return output, {**info, "reason": "inject_ready", "prompt_bytes": len(prompt_bytes),
                    "context_chars": len(content), "output_bytes": output_bytes}


def main(argv: list[str] | None = None) -> int:
    log("process_entered")
    parser = argparse.ArgumentParser(description="ZCode model -> independent Discipline profile router")
    parser.add_argument("--config", default=str(BASE / "route-config.json"))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # 宿主把退出码 2 解释为 block（PromptHook 实测），参数错误只记日志、按无注入放行
        log("argument_parse_exited", exit_code=int(exc.code))
        return 0
    try:
        event = one_json_line()
        log("stdin_parsed", event=string_value(event.get("hook_event_name")) or string_value(event.get("hookEventName")) or "(missing)")
        output, info = inject_for(event, Path(args.config).resolve())
        log("route_evaluated", **info)
        if output is not None:
            sys.stdout.buffer.write(output.encode("utf-8"))
            sys.stdout.buffer.flush()
            log("stdout_written", profile_id=info.get("profile_id"), output_bytes=info["output_bytes"])
        return 0
    except (ValueError, OSError) as exc:
        log("router_error", error_type=type(exc).__name__, error=str(exc)[:400])
        print(f"discipline-router: {type(exc).__name__}: {exc}", file=sys.stderr)
        # A bad configuration must not block the session. No malformed/partial JSON is emitted.
        return 0


if __name__ == "__main__":
    sys.exit(main())
