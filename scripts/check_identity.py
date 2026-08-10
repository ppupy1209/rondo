#!/usr/bin/env python3
"""Reject Git identities that do not belong to the Rondo maintainer."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

ALLOWED_NAME = "Yeonwoo Kim"
ALLOWED_EMAIL = "ppupy1209@naver.com"


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def identity(value: str) -> tuple[str, str]:
    match = re.match(r"^(.*?) <([^<>]+)>", value.strip())
    if not match:
        return "", ""
    return match.group(1).strip(), match.group(2).strip().casefold()


def current_errors() -> list[str]:
    errors: list[str] = []
    for label, variable in (("author", "GIT_AUTHOR_IDENT"), ("committer", "GIT_COMMITTER_IDENT")):
        name, email = identity(git("var", variable))
        if name != ALLOWED_NAME or email != ALLOWED_EMAIL:
            errors.append(f"current {label}: {name or '?'} <{email or '?'}>")
    local_email = git("config", "--local", "--get", "user.email").strip().casefold()
    if local_email != ALLOWED_EMAIL:
        errors.append(f"repository user.email: {local_email or 'not set'}")
    return errors


def history_errors() -> list[str]:
    errors: list[str] = []
    output = git("log", "--all", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce")
    for line in output.splitlines():
        fields = line.split("\x1f")
        if len(fields) != 5:
            errors.append("unparseable commit identity")
            continue
        sha, author, author_email, committer, committer_email = fields
        if author != ALLOWED_NAME or author_email.casefold() != ALLOWED_EMAIL:
            errors.append(f"commit {sha[:12]} author: {author} <{author_email}>")
        if committer != ALLOWED_NAME or committer_email.casefold() != ALLOWED_EMAIL:
            errors.append(f"commit {sha[:12]} committer: {committer} <{committer_email}>")

    tags = git(
        "for-each-ref", "refs/tags",
        "--format=%(refname:short)%09%(objecttype)%09%(taggername)%09%(taggeremail)",
    )
    for line in tags.splitlines():
        tag, kind, tagger, email = (line.split("\t", 3) + ["", "", "", ""])[:4]
        if kind != "tag":
            continue
        email = email.strip().removeprefix("<").removesuffix(">").casefold()
        if tagger != ALLOWED_NAME or email != ALLOWED_EMAIL:
            errors.append(f"tag {tag} tagger: {tagger} <{email}>")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    checks = current_errors if args.current and not args.all else history_errors
    try:
        errors = checks()
    except (OSError, RuntimeError) as error:
        print(f"identity check failed: {error}", file=sys.stderr)
        return 2
    if errors:
        print(f"Rondo commits must use {ALLOWED_NAME} <{ALLOWED_EMAIL}>.", file=sys.stderr)
        for error in errors[:20]:
            print(f"  - {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  - and {len(errors) - 20} more", file=sys.stderr)
        return 1
    print(f"commit identity: {ALLOWED_NAME} <{ALLOWED_EMAIL}>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
