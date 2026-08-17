"""Inline autocompletion for #cmdline: suggests a full command from a shared
pool (recent history, most-recent-first, falling back to the curated data
one-liners) whenever the typed text is a prefix of a known command."""
from __future__ import annotations

from textual.suggester import Suggester


class CommandSuggester(Suggester):
    def __init__(self, pool: list[str]) -> None:
        super().__init__(case_sensitive=False)
        # Mutated in place by the app as history grows, so this stays live.
        self.pool = pool

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        lowered = value.casefold()
        for command in self.pool:
            folded = command.casefold()
            if folded.startswith(lowered) and folded != lowered:
                return command
        return None
