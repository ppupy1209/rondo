"""Fast, private work history and approved scheduled prompts for one repository."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path

from .knowledge import KnowledgeError, _checked_text, _redacted
from .paths import CACHE, atomic_json, repo_key

MAX_EVENTS = 5_000
MAX_JOBS = 100
MAX_QUERY = 200
AGENT_NAME = re.compile(r"[A-Za-z0-9_.-]{1,32}")
JOB_STATES = {"pending", "active", "paused", "completed"}


class JournalError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def journal_home(root: Path) -> Path:
    return CACHE / "journal" / repo_key(root)


def database_path(root: Path) -> Path:
    return journal_home(root) / "state.db"


def _private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _prepare(root: Path) -> Path:
    root = root.resolve()
    directory = journal_home(root)
    section = directory.parent
    for path in (section, directory):
        if path.is_symlink():
            raise JournalError("state_unsafe")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    meta = directory / "meta.json"
    expected = str(root)
    deadline = time.monotonic() + 5
    while True:
        if meta.is_symlink():
            raise JournalError("state_unsafe")
        if meta.exists():
            break
        try:
            atomic_json(meta, {"schema": 1, "root": expected})
            break
        except PermissionError:
            # Windows may reject replace() when another fresh process wins the
            # same metadata publication race. Accept only its fully written,
            # subsequently validated result; every other failure stays closed.
            if time.monotonic() >= deadline:
                raise JournalError("state_unsafe") from None
            time.sleep(0.025)
    while True:
        try:
            value = json.loads(meta.read_text(encoding="utf-8"))
        except (PermissionError, FileNotFoundError):
            # A concurrent Windows replace can also deny the first read for a
            # moment. Retry only access/disappearance races, never malformed
            # or mismatched content.
            if time.monotonic() >= deadline:
                raise JournalError("state_unsafe") from None
            time.sleep(0.025)
            continue
        except (OSError, ValueError):
            raise JournalError("state_unsafe") from None
        if value.get("schema") != 1 or value.get("root") != expected:
            raise JournalError("state_unsafe")
        break
    _private(meta)

    target = database_path(root)
    if target.is_symlink():
        raise JournalError("state_unsafe")
    return target


def _connect(root: Path) -> sqlite3.Connection:
    target = _prepare(root)
    connection = None
    try:
        connection = sqlite3.connect(target, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        # WAL negotiation takes an exclusive lock even though normal SQLite
        # writes honor busy_timeout. Fresh concurrent Rondo processes can all
        # arrive here before the first one finishes initialization, so retry
        # this pragma explicitly instead of misclassifying a transient lock as
        # corrupt state.
        deadline = time.monotonic() + 5
        while True:
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                break
            except sqlite3.OperationalError as error:
                locked = any(word in str(error).casefold() for word in ("locked", "busy"))
                if not locked or time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                reference TEXT NOT NULL DEFAULT '',
                agent TEXT NOT NULL DEFAULT '',
                session TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_created_at ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS events_session ON events(session, created_at DESC);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                agent TEXT NOT NULL,
                schedule_kind TEXT NOT NULL,
                schedule_value TEXT NOT NULL,
                state TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                next_run INTEGER,
                last_run INTEGER,
                last_error TEXT NOT NULL DEFAULT '',
                failures INTEGER NOT NULL DEFAULT 0,
                lease_until INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state, next_run, lease_until);
            """
        )
        try:
            connection.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                    summary, reference, content='events', content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 2'
                );
                CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                    INSERT INTO events_fts(rowid, summary, reference)
                    VALUES (new.rowid, new.summary, new.reference);
                END;
                CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, summary, reference)
                    VALUES ('delete', old.rowid, old.summary, old.reference);
                END;
                CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
                    INSERT INTO events_fts(events_fts, rowid, summary, reference)
                    VALUES ('delete', old.rowid, old.summary, old.reference);
                    INSERT INTO events_fts(rowid, summary, reference)
                    VALUES (new.rowid, new.summary, new.reference);
                END;
                """
            )
        except sqlite3.OperationalError:
            # Some minimal Python/SQLite builds omit FTS5. LIKE search remains available.
            pass
        _private(target)
        for sidecar in target.parent.glob(target.name + "-*"):
            _private(sidecar)
        return connection
    except sqlite3.Error as error:
        if connection is not None:
            connection.close()
        code = (
            "busy" if any(word in str(error).casefold() for word in ("locked", "busy"))
            else "state_unsafe"
        )
        raise JournalError(code) from error


def _clean_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "-", value)[:80]


def _event_dict(row: sqlite3.Row | dict) -> dict:
    item = dict(row)
    try:
        if (
            not re.fullmatch(r"[0-9a-f]{12}", item["id"])
            or not re.fullmatch(r"[a-z0-9_-]{1,32}", item["kind"])
            or not isinstance(item["summary"], str)
            or not item["summary"]
            or len(item["summary"]) > 500
            or _redacted(item["summary"]) != item["summary"]
            or not isinstance(item["reference"], str)
            or len(item["reference"]) > 500
            or _redacted(item["reference"]) != item["reference"]
            or not isinstance(item["agent"], str)
            or _clean_label(item["agent"]) != item["agent"]
            or not isinstance(item["session"], str)
            or _clean_label(item["session"]) != item["session"]
            or not isinstance(item["created_at"], int)
            or isinstance(item["created_at"], bool)
            or item["created_at"] < 0
        ):
            raise JournalError("state_unsafe")
    except (KeyError, TypeError, ValueError):
        raise JournalError("state_unsafe") from None
    return {
        "id": item["id"], "kind": item["kind"], "name": item["agent"],
        "content": item["summary"], "reference": item["reference"],
        "session": item["session"], "at": item["created_at"],
    }


def _new_id(connection: sqlite3.Connection, table: str) -> str:
    while True:
        value = secrets.token_hex(6)
        if not connection.execute(
            f"SELECT 1 FROM {table} WHERE id = ?", (value,)
        ).fetchone():
            return value


def record(
    root: Path,
    kind: str,
    summary: str,
    reference: str = "",
    agent: str = "",
    session: str = "",
) -> dict:
    summary = _redacted(summary)
    if not summary:
        raise JournalError("empty")
    reference = _redacted(reference)
    kind = re.sub(r"[^a-z0-9_-]", "-", kind.casefold())[:32] or "event"
    agent = _clean_label(agent)
    session = _clean_label(session)
    now = int(time.time())
    connection = _connect(root)
    try:
        with connection:
            event_id = _new_id(connection, "events")
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, kind, summary, reference, agent, session, now),
            )
            connection.execute(
                """
                DELETE FROM events WHERE rowid IN (
                    SELECT rowid FROM events ORDER BY created_at DESC, rowid DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (MAX_EVENTS,),
            )
        return {
            "id": event_id, "kind": kind, "content": summary,
            "reference": reference, "agent": agent, "session": session, "at": now,
        }
    except sqlite3.Error as error:
        raise JournalError("busy") from error
    finally:
        connection.close()


def _tokens(query: str) -> list[str]:
    if len(query) > MAX_QUERY or any(char in query for char in "\r\n\0"):
        raise JournalError("invalid_query")
    return re.findall(r"[\w.-]+", query.casefold(), re.UNICODE)


def _fts_available(connection: sqlite3.Connection) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events_fts'"
    ).fetchone() is not None


def search(root: Path, query: str = "", limit: int = 20) -> list[dict]:
    tokens = _tokens(query.strip())
    limit = max(1, min(limit, 100))
    connection = _connect(root)
    try:
        if tokens and _fts_available(connection):
            expression = " AND ".join(
                '"' + token.replace('"', '""') + '"' for token in tokens
            )
            rows = connection.execute(
                """
                SELECT e.* FROM events_fts
                JOIN events e ON e.rowid = events_fts.rowid
                WHERE events_fts MATCH ?
                ORDER BY bm25(events_fts), e.created_at DESC LIMIT ?
                """,
                (expression, limit),
            ).fetchall()
        elif tokens:
            where = " AND ".join("(lower(summary) LIKE ? OR lower(reference) LIKE ?)" for _ in tokens)
            values = [part for token in tokens for part in (f"%{token}%", f"%{token}%")]
            rows = connection.execute(
                f"SELECT * FROM events WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
    except sqlite3.Error as error:
        raise JournalError("state_unsafe") from error
    finally:
        connection.close()
    return [_event_dict(row) for row in rows]


def get_event(root: Path, value: str) -> dict:
    connection = _connect(root)
    try:
        rows = connection.execute(
            "SELECT * FROM events WHERE id LIKE ? ORDER BY created_at DESC LIMIT 2",
            (value + "%",),
        ).fetchall()
    finally:
        connection.close()
    if len(rows) != 1:
        raise JournalError("not_found")
    return _event_dict(rows[0])


def sessions(root: Path, limit: int = 20) -> list[dict]:
    connection = _connect(root)
    try:
        rows = connection.execute(
            """
            SELECT session, MAX(agent) AS agent, MIN(created_at) AS started_at,
                   MAX(created_at) AS updated_at, COUNT(*) AS events
            FROM events WHERE session != '' GROUP BY session
            ORDER BY updated_at DESC LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
    finally:
        connection.close()
    result = []
    for row in rows:
        item = dict(row)
        if (
            not isinstance(item.get("session"), str)
            or not item["session"]
            or _clean_label(item["session"]) != item["session"]
            or not isinstance(item.get("agent"), str)
            or _clean_label(item["agent"]) != item["agent"]
            or any(
                not isinstance(item.get(key), int) or isinstance(item[key], bool)
                or item[key] < 0
                for key in ("started_at", "updated_at", "events")
            )
        ):
            raise JournalError("state_unsafe")
        result.append(item)
    return result


def parse_interval(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]{0,5})([smhdw])", value.strip().casefold())
    if not match:
        raise JournalError("invalid_schedule")
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match.group(2)]
    if seconds < 10 or seconds > 31_536_000:
        raise JournalError("invalid_schedule")
    return seconds


def parse_at(value: str) -> int:
    epoch = _at_epoch(value)
    if epoch <= int(time.time()):
        raise JournalError("invalid_schedule")
    return epoch


def _at_epoch(value: str) -> int:
    try:
        moment = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise JournalError("invalid_schedule") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return int(moment.timestamp())


def _cron_values(field: str, minimum: int, maximum: int, weekday: bool = False) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        base, slash, step_text = part.partition("/")
        if slash and (not step_text.isdigit() or int(step_text) < 1):
            raise JournalError("invalid_schedule")
        step = int(step_text) if slash else 1
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            first, last = base.split("-", 1)
            if not (first.isdigit() and last.isdigit()):
                raise JournalError("invalid_schedule")
            start, end = int(first), int(last)
        elif base.isdigit():
            start = int(base)
            end = maximum if slash else start
        else:
            raise JournalError("invalid_schedule")
        if start < minimum or end > maximum or start > end:
            raise JournalError("invalid_schedule")
        values.update(range(start, end + 1, step))
    if weekday and 7 in values:
        values.remove(7)
        values.add(0)
    return values


def _cron_parts(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int], bool, bool]:
    fields = expression.strip().split()
    if len(fields) != 5:
        raise JournalError("invalid_schedule")
    minute, hour, day, month, weekday = fields
    return (
        _cron_values(minute, 0, 59),
        _cron_values(hour, 0, 23),
        _cron_values(day, 1, 31),
        _cron_values(month, 1, 12),
        _cron_values(weekday, 0, 7, weekday=True),
        day == "*",
        weekday == "*",
    )


def next_cron(expression: str, after: int) -> int:
    minutes, hours, days, months, weekdays, any_day, any_weekday = _cron_parts(expression)
    timezone = dt.datetime.now().astimezone().tzinfo
    candidate = ((after // 60) + 1) * 60
    for _ in range(60 * 24 * 366 * 2):
        moment = dt.datetime.fromtimestamp(candidate, timezone)
        cron_weekday = (moment.weekday() + 1) % 7
        day_match = moment.day in days
        weekday_match = cron_weekday in weekdays
        calendar_match = (
            day_match and weekday_match if any_day or any_weekday else day_match or weekday_match
        )
        if (
            moment.minute in minutes and moment.hour in hours and moment.month in months
            and calendar_match
        ):
            return candidate
        candidate += 60
    raise JournalError("invalid_schedule")


def next_run(kind: str, value: str, after: int | None = None) -> int:
    after = int(time.time()) if after is None else int(after)
    if kind == "every":
        return after + parse_interval(value)
    if kind == "at":
        epoch = _at_epoch(value)
        if epoch <= after:
            raise JournalError("invalid_schedule")
        return epoch
    if kind == "cron":
        return next_cron(value, after)
    raise JournalError("invalid_schedule")


def propose_job(
    root: Path, prompt: str, agent: str, schedule_kind: str,
    schedule_value: str, source: str,
) -> dict:
    try:
        prompt = _checked_text(prompt)
    except KnowledgeError as error:
        raise JournalError(error.code) from None
    if not isinstance(agent, str) or not AGENT_NAME.fullmatch(agent):
        raise JournalError("invalid_agent")
    planned = next_run(schedule_kind, schedule_value)
    source = re.sub(r"[^A-Za-z0-9_.-]", "-", str(source))[:32] or "unknown"
    now = int(time.time())
    connection = _connect(root)
    try:
        with connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE state != 'completed'"
            ).fetchone()[0]
            if count >= MAX_JOBS:
                raise JournalError("jobs_full")
            job_id = _new_id(connection, "jobs")
            connection.execute(
                """
                INSERT INTO jobs(
                    id, prompt, agent, schedule_kind, schedule_value, state, source,
                    created_at, updated_at, next_run
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (job_id, prompt, agent, schedule_kind, schedule_value, source, now, now, planned),
            )
        return get_job(root, job_id)
    except sqlite3.Error as error:
        raise JournalError("busy") from error
    finally:
        connection.close()


def _find_job(connection: sqlite3.Connection, value: str) -> sqlite3.Row:
    rows = connection.execute(
        "SELECT * FROM jobs WHERE id LIKE ? ORDER BY created_at DESC LIMIT 2", (value + "%",)
    ).fetchall()
    if len(rows) != 1:
        raise JournalError("not_found")
    return rows[0]


def _job_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    try:
        if (
            not re.fullmatch(r"[0-9a-f]{12}", item["id"])
            or not all(
                isinstance(item[key], str)
                for key in (
                    "prompt", "agent", "schedule_kind", "schedule_value",
                    "state", "source", "last_error",
                )
            )
            or _checked_text(item["prompt"]) != item["prompt"]
            or not AGENT_NAME.fullmatch(item["agent"])
            or item["state"] not in JOB_STATES
            or not AGENT_NAME.fullmatch(item["source"])
            or not all(
                isinstance(item[key], int) and not isinstance(item[key], bool)
                and item[key] >= 0
                for key in ("created_at", "updated_at")
            )
            or not all(
                value is None or (
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                )
                for value in (item["next_run"], item["last_run"])
            )
            or not isinstance(item["failures"], int)
            or isinstance(item["failures"], bool)
            or item["failures"] < 0
            or not isinstance(item["lease_until"], int)
            or isinstance(item["lease_until"], bool)
            or item["lease_until"] < 0
            or len(item["last_error"]) > 500
            or _redacted(item["last_error"]) != item["last_error"]
        ):
            raise JournalError("state_unsafe")
        if item["schedule_kind"] == "every":
            parse_interval(item["schedule_value"])
        elif item["schedule_kind"] == "cron":
            _cron_parts(item["schedule_value"])
        elif item["schedule_kind"] == "at":
            _at_epoch(item["schedule_value"])
        else:
            raise JournalError("state_unsafe")
    except (KeyError, TypeError, ValueError):
        raise JournalError("state_unsafe") from None
    return item


def get_job(root: Path, value: str) -> dict:
    connection = _connect(root)
    try:
        return _job_dict(_find_job(connection, value))
    finally:
        connection.close()


def jobs(root: Path, include_completed: bool = False) -> list[dict]:
    connection = _connect(root)
    try:
        where = "" if include_completed else "WHERE state != 'completed'"
        rows = connection.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?", (MAX_JOBS,)
        ).fetchall()
        return [_job_dict(row) for row in rows]
    finally:
        connection.close()


def job_action(root: Path, value: str, action: str, actor: str) -> dict:
    if actor != "human":
        raise JournalError("human_only")
    now = int(time.time())
    connection = _connect(root)
    try:
        with connection:
            item = _find_job(connection, value)
            state = item["state"]
            if action == "approve" and state == "pending":
                planned = next_run(item["schedule_kind"], item["schedule_value"], now)
                connection.execute(
                    "UPDATE jobs SET state='active', next_run=?, updated_at=? WHERE id=?",
                    (planned, now, item["id"]),
                )
            elif action == "reject" and state == "pending":
                connection.execute("DELETE FROM jobs WHERE id=?", (item["id"],))
                return _job_dict(item) | {"state": "rejected"}
            elif action == "pause" and state == "active":
                connection.execute(
                    "UPDATE jobs SET state='paused', updated_at=?, lease_until=0 WHERE id=?",
                    (now, item["id"]),
                )
            elif action == "resume" and state == "paused":
                planned = next_run(item["schedule_kind"], item["schedule_value"], now)
                connection.execute(
                    "UPDATE jobs SET state='active', next_run=?, updated_at=? WHERE id=?",
                    (planned, now, item["id"]),
                )
            elif action == "run" and state in {"active", "paused"}:
                connection.execute(
                    "UPDATE jobs SET state='active', next_run=?, updated_at=?, lease_until=0 WHERE id=?",
                    (now, now, item["id"]),
                )
            elif action == "remove" and state in JOB_STATES:
                connection.execute("DELETE FROM jobs WHERE id=?", (item["id"],))
                return _job_dict(item) | {"state": "removed"}
            else:
                raise JournalError("invalid_action")
        return get_job(root, item["id"])
    except sqlite3.Error as error:
        raise JournalError("busy") from error
    finally:
        connection.close()


def claim_due(root: Path, now: int | None = None, limit: int = 4) -> list[dict]:
    now = int(time.time()) if now is None else int(now)
    connection = _connect(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT * FROM jobs
            WHERE state='active' AND next_run <= ? AND lease_until <= ?
            ORDER BY next_run, created_at LIMIT ?
            """,
            (now, now, max(1, min(limit, 4))),
        ).fetchall()
        lease = now + 90
        claimed = []
        for row in rows:
            connection.execute(
                "UPDATE jobs SET lease_until=?, updated_at=? WHERE id=?",
                (lease, now, row["id"]),
            )
            claimed.append(_job_dict(dict(row) | {"lease_until": lease, "updated_at": now}))
        connection.commit()
        return claimed
    except sqlite3.Error as error:
        connection.rollback()
        raise JournalError("busy") from error
    finally:
        connection.close()


def finish_job(
    root: Path, value: str, success: bool, error: str = "",
    now: int | None = None, lease_until: int | None = None,
) -> dict:
    now = int(time.time()) if now is None else int(now)
    connection = _connect(root)
    try:
        with connection:
            item = _find_job(connection, value)
            if (
                item["state"] != "active"
                or not isinstance(lease_until, int)
                or item["lease_until"] != lease_until
                or lease_until <= 0
            ):
                raise JournalError("invalid_action")
            if success:
                if item["schedule_kind"] == "at":
                    state, planned = "completed", None
                else:
                    state = "active"
                    planned = next_run(item["schedule_kind"], item["schedule_value"], now)
                failures, message = 0, ""
            else:
                failures = int(item["failures"]) + 1
                state = "paused" if failures >= 3 else "active"
                planned = None if state == "paused" else now + 60
                message = _redacted(error) or "delivery failed"
            connection.execute(
                """
                UPDATE jobs SET state=?, next_run=?, last_run=?, last_error=?, failures=?,
                                lease_until=0, updated_at=? WHERE id=?
                """,
                (state, planned, now, message, failures, now, item["id"]),
            )
        return get_job(root, item["id"])
    except sqlite3.Error as caught:
        raise JournalError("busy") from caught
    finally:
        connection.close()


def job_counts(root: Path) -> dict[str, int]:
    connection = _connect(root)
    try:
        rows = connection.execute(
            "SELECT state, COUNT(*) AS count FROM jobs GROUP BY state"
        ).fetchall()
        return {row["state"]: row["count"] for row in rows}
    finally:
        connection.close()
