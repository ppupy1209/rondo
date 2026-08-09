"""벤더별 어댑터. 벤더 경로·스키마를 아는 곳은 여기뿐이다."""
from .base import Adapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .gemini import GeminiAdapter

__all__ = ["Adapter", "ClaudeAdapter", "CodexAdapter", "GeminiAdapter"]
