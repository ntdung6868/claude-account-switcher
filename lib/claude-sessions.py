#!/usr/bin/env python3
"""Repair Claude Code local session metadata after account switches.

Claude Code stores raw transcripts as JSONL files under
~/.claude/projects/<project>/<session-id>.jsonl. The recent session pointers
that power continue/resume live in ~/.claude.json under the "projects" key.
If that config loses project entries while csw swaps accounts, the transcripts
still exist but the UI can look empty. This helper rebuilds those project
entries from the raw transcripts without modifying transcript contents.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class Transcript:
    session_id: str
    path: pathlib.Path
    cwd: str
    created_at_ms: int
    updated_at_ms: int
    first_prompt: str
    title: str
    message_count: int


def parse_iso_ms(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.astimezone(dt.timezone.utc).timestamp() * 1000)


def clean_text(value: str, limit: int = 4000) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = value.strip()
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def one_line(value: str, limit: int = 200) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "input_text", "message", "content"):
            text = extract_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = extract_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return ""


def transcript_id_from_path(path: pathlib.Path) -> str | None:
    if path.suffix != ".jsonl":
        return None
    stem = path.stem
    return stem if UUID_RE.match(stem) else None


def is_top_level_transcript(path: pathlib.Path, projects_dir: pathlib.Path) -> bool:
    try:
        rel = path.relative_to(projects_dir)
    except ValueError:
        return False
    # Expected shape: <project-dir>/<session-id>.jsonl. Ignore subagent JSONLs.
    return len(rel.parts) == 2 and transcript_id_from_path(path) is not None


def parse_transcript(path: pathlib.Path) -> Transcript | None:
    session_id = transcript_id_from_path(path)
    if not session_id:
        return None

    stat = path.stat()
    first_seen_ms: int | None = None
    last_seen_ms: int | None = None
    cwd = ""
    first_prompt = ""
    ai_title = ""
    custom_title = ""
    last_prompt = ""
    message_count = 0

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                line_session_id = obj.get("sessionId")
                if isinstance(line_session_id, str) and UUID_RE.match(line_session_id):
                    session_id = line_session_id

                ts_ms = parse_iso_ms(obj.get("timestamp"))
                if ts_ms is not None:
                    first_seen_ms = ts_ms if first_seen_ms is None else min(first_seen_ms, ts_ms)
                    last_seen_ms = ts_ms if last_seen_ms is None else max(last_seen_ms, ts_ms)

                value = obj.get("cwd")
                if isinstance(value, str) and value and not cwd:
                    cwd = value

                obj_type = obj.get("type")
                if obj_type in ("user", "assistant"):
                    message_count += 1

                if obj_type == "user" and not first_prompt:
                    message = obj.get("message")
                    if isinstance(message, dict):
                        first_prompt = extract_text(message.get("content"))
                    else:
                        first_prompt = extract_text(message)
                elif obj_type == "ai-title" and not ai_title:
                    ai_title = extract_text(obj.get("aiTitle"))
                elif obj_type == "custom-title" and not custom_title:
                    custom_title = extract_text(obj.get("customTitle"))
                elif obj_type == "last-prompt" and not last_prompt:
                    last_prompt = extract_text(obj.get("lastPrompt"))
    except OSError as exc:
        print(f"Warning: cannot read transcript {path}: {exc}", file=sys.stderr)
        return None

    if not cwd:
        # Fall back to a best-effort decoded project name only when the JSONL
        # itself does not contain cwd. Normal Claude transcripts do contain cwd.
        cwd = project_name_to_cwd(path.parent.name)

    created_ms = first_seen_ms or int(stat.st_ctime * 1000)
    updated_ms = last_seen_ms or int(stat.st_mtime * 1000) or created_ms
    first_prompt = clean_text(first_prompt or last_prompt)
    title = one_line(custom_title or ai_title or first_prompt or session_id)

    return Transcript(
        session_id=session_id,
        path=path,
        cwd=cwd,
        created_at_ms=created_ms,
        updated_at_ms=updated_ms,
        first_prompt=first_prompt,
        title=title,
        message_count=message_count,
    )


def project_name_to_cwd(name: str) -> str:
    if name.startswith("-"):
        name = name[1:]
    return "/" + name.replace("-", "/")


def collect_transcripts(claude_home: pathlib.Path) -> list[Transcript]:
    projects_dir = claude_home / "projects"
    if not projects_dir.is_dir():
        return []
    transcripts: list[Transcript] = []
    for path in sorted(projects_dir.rglob("*.jsonl")):
        if not is_top_level_transcript(path, projects_dir):
            continue
        transcript = parse_transcript(path)
        if transcript:
            transcripts.append(transcript)
    return transcripts


def latest_by_project(transcripts: list[Transcript]) -> dict[str, Transcript]:
    latest: dict[str, Transcript] = {}
    for transcript in transcripts:
        current = latest.get(transcript.cwd)
        if current is None or transcript.updated_at_ms >= current.updated_at_ms:
            latest[transcript.cwd] = transcript
    return latest


def transcripts_by_project(transcripts: list[Transcript]) -> dict[str, dict[str, Transcript]]:
    grouped: dict[str, dict[str, Transcript]] = {}
    for transcript in transcripts:
        grouped.setdefault(transcript.cwd, {})[transcript.session_id] = transcript
    return grouped


def load_config(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def backup_file(src: pathlib.Path, backup_dir: pathlib.Path | None) -> pathlib.Path | None:
    if not src.exists():
        return None
    if backup_dir is None:
        backup_dir = src.parent / "backups" / "csw-sessions"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{src.name}.{stamp}.bak"
    shutil.copy2(src, dest)
    dest.chmod(0o600)
    return dest


def atomic_write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def project_updates(config: dict[str, Any], transcripts: list[Transcript]) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    projects = config.get("projects")
    if not isinstance(projects, dict):
        projects = {}

    latest = latest_by_project(transcripts)
    grouped = transcripts_by_project(transcripts)
    updates: dict[str, dict[str, Any]] = {}
    stats = {
        "config_projects": len(projects),
        "transcripts": len(transcripts),
        "projects_with_transcripts": len(latest),
        "projects_added": 0,
        "projects_updated": 0,
        "stale_last_session": 0,
    }

    for cwd, transcript in sorted(latest.items()):
        current = projects.get(cwd)
        if not isinstance(current, dict):
            current = {}
            stats["projects_added"] += 1

        next_meta = dict(current)
        before = json.dumps(next_meta, sort_keys=True, ensure_ascii=False)

        old_last_session = next_meta.get("lastSessionId")
        project_transcripts = grouped.get(cwd, {})
        old_transcript = project_transcripts.get(old_last_session) if isinstance(old_last_session, str) else None
        old_modified = next_meta.get("lastSessionModified")
        old_modified_ms = old_modified if isinstance(old_modified, int) else 0
        if old_last_session and old_transcript is None:
            stats["stale_last_session"] += 1

        # Keep permissions/MCP/trust settings intact. Only repair recent-session
        # pointers and small display metadata derived from local transcripts.
        chosen = transcript
        should_promote_latest = (
            old_transcript is None
            or not old_last_session
            or old_modified_ms < transcript.updated_at_ms
        )
        if not should_promote_latest and old_transcript is not None:
            chosen = old_transcript

        if next_meta.get("lastSessionId") != chosen.session_id:
            next_meta["lastSessionId"] = chosen.session_id
        if next_meta.get("lastHintSessionId") not in project_transcripts:
            next_meta["lastHintSessionId"] = chosen.session_id
        if old_modified_ms < chosen.updated_at_ms:
            next_meta["lastSessionModified"] = chosen.updated_at_ms
        if not next_meta.get("lastSessionFirstPrompt") and chosen.first_prompt:
            next_meta["lastSessionFirstPrompt"] = one_line(chosen.first_prompt, limit=200)
        if "lastSessionMetrics" not in next_meta:
            next_meta["lastSessionMetrics"] = {}

        after = json.dumps(next_meta, sort_keys=True, ensure_ascii=False)
        if before != after and cwd in projects:
            stats["projects_updated"] += 1
        updates[cwd] = next_meta

    return updates, stats


def cmd_repair(args: argparse.Namespace) -> int:
    claude_home = pathlib.Path(args.claude_home).expanduser()
    claude_json = pathlib.Path(args.claude_json).expanduser()
    transcripts = collect_transcripts(claude_home)
    config = load_config(claude_json)
    updates, stats = project_updates(config, transcripts)

    changed = stats["projects_added"] + stats["projects_updated"]
    backup = None
    if not args.dry_run and changed:
        backup_dir = (
            pathlib.Path(args.backup_dir).expanduser()
            if args.backup_dir
            else claude_home / "backups" / "csw-sessions"
        )
        if not args.no_backup:
            backup = backup_file(claude_json, backup_dir)
        projects = config.get("projects")
        if not isinstance(projects, dict):
            projects = {}
        projects.update(updates)
        config["projects"] = projects
        atomic_write_json(claude_json, config)

    mode = "dry-run " if args.dry_run else ""
    print(
        f"Claude session repair {mode}OK: "
        f"transcripts={stats['transcripts']} "
        f"projects_with_transcripts={stats['projects_with_transcripts']} "
        f"config_projects={stats['config_projects']} "
        f"projects_added={stats['projects_added']} "
        f"projects_updated={stats['projects_updated']} "
        f"stale_last_session={stats['stale_last_session']}"
    )
    if backup:
        print(f"Backup: {backup}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    claude_home = pathlib.Path(args.claude_home).expanduser()
    claude_json = pathlib.Path(args.claude_json).expanduser()
    transcripts = collect_transcripts(claude_home)
    config = load_config(claude_json)
    _, stats = project_updates(config, transcripts)
    print(
        f"Claude sessions: transcripts={stats['transcripts']} "
        f"projects_with_transcripts={stats['projects_with_transcripts']} "
        f"config_projects={stats['config_projects']} "
        f"projects_added={stats['projects_added']} "
        f"projects_updated={stats['projects_updated']} "
        f"stale_last_session={stats['stale_last_session']}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    repair = sub.add_parser("repair", help="Rebuild ~/.claude.json project session pointers")
    repair.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    repair.add_argument("--claude-json", default=os.path.expanduser("~/.claude.json"))
    repair.add_argument("--dry-run", action="store_true")
    repair.add_argument("--no-backup", action="store_true")
    repair.add_argument("--backup-dir")
    repair.set_defaults(func=cmd_repair)

    status = sub.add_parser("status", help="Print local Claude session metadata counts")
    status.add_argument("--claude-home", default=os.path.expanduser("~/.claude"))
    status.add_argument("--claude-json", default=os.path.expanduser("~/.claude.json"))
    status.set_defaults(func=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
