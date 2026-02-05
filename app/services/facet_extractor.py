import json
from dataclasses import dataclass

from app.core.constants import load_facets
from app.providers import ChatMessage, LLMProvider


@dataclass
class Facet:
    """Extracted facets from a query."""
    bridge_type: str | list[str] | None = None
    material: str | list[str] | None = None
    era: str | list[str] | None = None
    region: str | list[str] | None = None
    function: str | list[str] | None = None

    def to_lists(self) -> dict[str, list[str]]:
        """Normalize all facets to lists for SQL queries."""
        result = {}
        for key in ["bridge_type", "material", "era", "region", "function"]:
            value = getattr(self, key)
            if value is None:
                result[key] = []
            elif isinstance(value, list):
                result[key] = value
            else:
                result[key] = [value]
        return result

    def is_empty(self) -> bool:
        """Check if all facets are empty."""
        lists = self.to_lists()
        return all(len(v) == 0 for v in lists.values())


class FacetExtractor:
    """Extract query facets using LLM with enum constraints."""

    PROMPT_TEMPLATE = """分析以下关于桥梁的问题，提取涉及的桥梁属性。

【问题】{query}

【枚举值约束 - 只能从以下选项中选择，可多选】
- bridge_type: {bridge_types}
- material: {materials}
- era: {eras}
- region: {regions}
- function: {functions}

输出 JSON（无关维度填 null，相关维度可以是单值或数组）：
{{
  "bridge_type": "石拱桥" 或 ["石拱桥", "木拱桥"] 或 null,
  "material": null,
  "era": null,
  "region": null,
  "function": null
}}
"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def extract(self, query: str) -> Facet:
        """Extract facets from a query."""
        facets = load_facets()
        prompt = self.PROMPT_TEMPLATE.format(
            query=query,
            bridge_types=", ".join(facets["bridge_types"]),
            materials=", ".join(facets["materials"]),
            eras=", ".join(facets["eras"]),
            regions=", ".join(facets["regions"]),
            functions=", ".join(facets["functions"]),
        )

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> Facet:
        """Parse LLM response into Facet."""
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
                data = json.loads(json_str)
                facets = load_facets()
                return Facet(
                    bridge_type=self._validate_facet(data.get("bridge_type"), facets["bridge_types"]),
                    material=self._validate_facet(data.get("material"), facets["materials"]),
                    era=self._validate_facet(data.get("era"), facets["eras"]),
                    region=self._validate_facet(data.get("region"), facets["regions"]),
                    function=self._validate_facet(data.get("function"), facets["functions"]),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        return Facet()

    def _validate_facet(
        self, value: str | list[str] | None, allowed: list[str]
    ) -> str | list[str] | None:
        """Validate facet value against allowed list."""
        if value is None:
            return None
        if isinstance(value, list):
            return [v for v in value if v in allowed] or None
        if value in allowed:
            return value
        return None
