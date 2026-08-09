#!/usr/bin/env python3
"""Tiny line-oriented terminal used only by the real Zellij smoke test."""
from __future__ import annotations

print("FAKE_AGENT_READY", flush=True)
while True:
    try:
        message = input("fake> ")
    except (EOFError, KeyboardInterrupt):
        break
    print("RECEIVED:" + message, flush=True)
