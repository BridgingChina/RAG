import json
import re
from dataclasses import dataclass

from app.core.constants import get_taxonomy_lvl1
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
        lvl2_info = ""
        if self.taxonomy_lvl2:
            lvl2_info = "\n二级分类：\n"
            for lvl1, lvl2s in self.taxonomy_lvl2.items():
                lvl2_info += f"  {lvl1}: {', '.join(lvl2s)}\n"

        prompt = f"""你是桥梁知识分类专家。请分析以下文本，判断它属于哪个知识分类。

一级分类（必选其一）：
1. 形制与技术 - 桥梁的结构、材料、建造技术
2. 地域与环境 - 桥梁所在地理位置、自然环境
3. 功能与社会 - 桥梁的用途、社会意义
4. 历史与演变 - 桥梁的历史、修缮、变迁
{lvl2_info}
如果文本明确提到某座具体桥梁的名称，请提取桥梁名称。

文本：
{chunk_content}

请以JSON格式回答，格式如下：
{{"lvl1": "一级分类", "lvl2": "二级分类或null", "bridge_name": "桥梁名称或null"}}

只输出JSON，不要其他内容。"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        return self._parse_response(response.content)

    def _parse_response(self, content: str) -> TagResult:
        """Parse LLM response to TagResult."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group())
                lvl1 = data.get("lvl1")
                # Validate lvl1
                if lvl1 not in get_taxonomy_lvl1():
                    lvl1 = None
                return TagResult(
                    lvl1=lvl1,
                    lvl2=data.get("lvl2"),
                    lvl3=data.get("lvl3"),  # Extract lvl3 from LLM response
                    bridge_id=data.get("bridge_name"),
                )
        except (json.JSONDecodeError, AttributeError):
            pass

        return TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
