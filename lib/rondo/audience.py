"""사용자의 기술 배경에 맞춘 공통 설명 지침."""
from __future__ import annotations

import os
from pathlib import Path

MODES = ("default", "nondev", "guided")

INSTRUCTIONS = {
    "nondev": (
        "[Rondo audience: non-developer] Adapt explanations, not engineering rigor. "
        "Answer in the user's language. Start with the practical outcome in everyday words. "
        "Avoid unexplained jargon; define any necessary technical term once. Use a concrete "
        "example and a short before-to-after flow when they help. Explain visible impact, risk, "
        "and the next action. Do not hide safety limits or uncertainty. A later user message "
        "tagged [Rondo audience update] replaces this explanation mode."
    ),
    "guided": (
        "[Rondo audience: developer, unfamiliar topic] Adapt explanations, not engineering rigor. "
        "Answer in the user's language. Assume general software-development knowledge but no "
        "familiarity with the current technology. Keep precise technical names, and briefly add "
        "the component's role, the request or data flow, why this approach was chosen, and one "
        "important tradeoff or pitfall. Skip unrelated programming basics. A later user message "
        "tagged [Rondo audience update] replaces this explanation mode."
    ),
}


def selected(config: Path | None = None) -> str:
    forced = os.environ.get("RONDO_AUDIENCE", "").lower()
    if forced in MODES:
        return forced
    if config is None:
        config = Path(os.environ.get(
            "XDG_CONFIG_HOME", Path.home() / ".config"
        )) / "rondo"
    path = config / "audience"
    try:
        saved = path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        saved = ""
    return saved if saved in MODES else "default"


def instruction(mode: str) -> str:
    return INSTRUCTIONS.get(mode, "")


def update_prompt(mode: str) -> str:
    if mode == "default":
        rule = "Return to your normal explanation style without extra audience adaptation."
    else:
        rule = instruction(mode)
    return (
        "[Rondo audience update] " + rule
        + " Apply this to future replies without a separate acknowledgment; wait for the next task."
    )
