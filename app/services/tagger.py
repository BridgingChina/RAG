import json
import re
from dataclasses import dataclass

from app.core.constants import get_taxonomy_lvl1, get_taxonomy_lvl2, get_taxonomy_lvl3, load_taxonomy
from app.providers import ChatMessage, LLMProvider


@dataclass
class TagResult:
    lvl1: str | None
    lvl2: str | None
    lvl3: str | None
    bridge_id: str | None


class MetadataTagger:
    def __init__(self, provider: LLMProvider, taxonomy_lvl2: dict[str, list[str]] | None = None):
        self.provider = provider
        self.taxonomy_lvl2 = taxonomy_lvl2 or {}

    async def tag(self, chunk_content: str) -> TagResult:
        """Tag a chunk with taxonomy metadata."""
        taxonomy_prompt = self._build_taxonomy_prompt()

        prompt = f"""你是桥梁知识分类专家。请分析以下文本，判断它属于哪个知识分类。

{taxonomy_prompt}

如果文本明确提到某座具体桥梁的名称，请提取桥梁名称（不要猜测）。

文本：
{chunk_content}

请以JSON格式回答，格式如下：
{{"lvl1": "一级分类", "lvl2": "二级分类或null", "lvl3": "三级分类或null", "bridge_name": "桥梁名称或null"}}

规则：
1) lvl1 必须是上面列出的一级分类之一
2) lvl2 必须属于对应 lvl1（不确定写 null）
3) lvl3 必须属于对应 lvl1 + lvl2（不确定写 null）
4) 只输出JSON，不要其他内容。"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _build_taxonomy_prompt(self) -> str:
        """Build a prompt section describing the 3-level taxonomy."""
        taxonomy = load_taxonomy()
        lvl1_list = get_taxonomy_lvl1()

        lines: list[str] = []
        lines.append("一级分类（必选其一）：")
        for i, lvl1 in enumerate(lvl1_list, start=1):
            lines.append(f"{i}. {lvl1}")

        lines.append("")
        lines.append("二级/三级分类（可选，需与上级匹配）：")
        for lvl1 in lvl1_list:
            lvl2_list = self.taxonomy_lvl2.get(lvl1) or list(taxonomy.get(lvl1, {}).keys())
            if not lvl2_list:
                continue
            lines.append(f"- {lvl1}:")
            for lvl2 in lvl2_list:
                lvl3_list = taxonomy.get(lvl1, {}).get(lvl2, [])
                if lvl3_list:
                    lines.append(f"  - {lvl2}: {', '.join(lvl3_list)}")
                else:
                    lines.append(f"  - {lvl2}")
        return "\n".join(lines)

    @staticmethod
    def _normalize_value(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        if s.lower() in {"null", "none", "n/a", "na"}:
            return None
        if s in {"无", "未知", "不确定", "无法确定"}:
            return None
        return s

    def _parse_response(self, content: str) -> TagResult:
        """Parse LLM response to TagResult."""
        try:
            # Extract JSON from response
            json_match = re.search(r"\{.*\}", content, flags=re.S)
            if not json_match:
                raise ValueError("No JSON object found in response")

            data = json.loads(json_match.group())
            lvl1 = self._normalize_value(data.get("lvl1"))
            lvl2 = self._normalize_value(data.get("lvl2"))
            lvl3 = self._normalize_value(data.get("lvl3"))
            bridge_name = self._normalize_value(data.get("bridge_name"))

            if lvl1 not in get_taxonomy_lvl1():
                lvl1 = None
                lvl2 = None
                lvl3 = None
            else:
                allowed_lvl2 = self.taxonomy_lvl2.get(lvl1) or get_taxonomy_lvl2(lvl1)
                if lvl2 not in allowed_lvl2:
                    lvl2 = None
                    lvl3 = None
                else:
                    allowed_lvl3 = get_taxonomy_lvl3(lvl1, lvl2)
                    if lvl3 not in allowed_lvl3:
                        lvl3 = None

            return TagResult(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3, bridge_id=bridge_name)
        except (json.JSONDecodeError, AttributeError):
            pass
        except Exception:
            pass

        return TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
