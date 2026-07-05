import yaml
import re
from pathlib import Path
from typing import List, Optional
from openai import AsyncOpenAI

class ModerationResult:
    def __init__(self, allowed: bool, categories: List[str], reasons: List[str], blocked_by: str):
        self.allowed = allowed
        self.categories = categories
        self.reasons = reasons
        self.blocked_by = blocked_by

class ModerationService:
    def __init__(self, openai_client: Optional[AsyncOpenAI] = None, keywords_path: Optional[Path] = None):
        self.openai_client = openai_client
        self.keywords = self._load_keywords(keywords_path)

    def _load_keywords(self, path: Path | None) -> List[str]:
        if path is None:
            path = Path(__file__).parent / "keywords.yaml"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("keywords", [])

    async def check_input(self, content: str) -> ModerationResult:
        # 1. Ключевые слова / регулярки
        for kw in self.keywords:
            if re.search(rf"\b{kw}\b", content, re.IGNORECASE):
                return ModerationResult(
                    allowed=False,
                    categories=["keyword_block"],
                    reasons=[f"найдено ключевое слово: {kw}"],
                    blocked_by="keyword"
                )

        # 2. OpenAI Moderation API
        if self.openai_client:
            try:
                response = await self.openai_client.moderations.create(
                    model="omni-moderation-latest",
                    input=content
                )
                result = response.results[0]
                if result.flagged:
                    categories = [cat for cat, val in result.categories.items() if val is True]
                    return ModerationResult(
                        allowed=False,
                        categories=categories,
                        reasons=["OpenAI Moderation API flagged content"],
                        blocked_by="openai_moderation"
                    )
            except Exception:
                pass
        return ModerationResult(allowed=True, categories=[], reasons=[], blocked_by="")

    async def check_output(self, content: str) -> ModerationResult:
        if self.openai_client:
            try:
                response = await self.openai_client.moderations.create(
                    model="omni-moderation-latest",
                    input=content
                )
                result = response.results[0]
                if result.flagged:
                    categories = [cat for cat, val in result.categories.items() if val is True]
                    return ModerationResult(
                        allowed=False,
                        categories=categories,
                        reasons=["OpenAI Moderation API flagged content"],
                        blocked_by="openai_moderation"
                    )
            except Exception:
                pass
        return ModerationResult(allowed=True, categories=[], reasons=[], blocked_by="")