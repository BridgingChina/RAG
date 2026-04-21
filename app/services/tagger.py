import json
import logging
import re
from dataclasses import dataclass

from app.llm import ChatMessage, chat_for_task

logger = logging.getLogger(__name__)


@dataclass
class TagResult:
    lvl1: str | None
    lvl2: str | None
    lvl3: str | None
    bridge_id: str | None


class MetadataTagger:
    """LLM-backed chunk metadata tagger.

    The full taxonomy snapshot must be provided at construction time — the
    tagger never reads YAML or touches the DB on its own. Callers (ingest
    pipeline, scripts, tests) pass a fresh snapshot so admin-side taxonomy
    edits propagate on the next task without any cache invalidation dance.

    Phase C: LLM dispatch goes through :func:`app.llm.chat_for_task` with
    task_key ``"ingest_tagger"``. No more injected provider — the task
    router owns provider/model selection.
    """

    TASK_KEY = "ingest_tagger"

    def __init__(
        self,
        taxonomy: dict[str, dict[str, list[str]]],
    ):
        self.taxonomy = taxonomy

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
        response = await chat_for_task(self.TASK_KEY, messages)

        return self._parse_response(response.content)

    def _build_taxonomy_prompt(self) -> str:
        """Build a prompt section describing the 3-level taxonomy."""
        lines: list[str] = ["一级分类（必选其一）："]
        for i, lvl1 in enumerate(self.taxonomy.keys(), start=1):
            lines.append(f"{i}. {lvl1}")

        lines.append("")
        lines.append("二级/三级分类（可选，需与上级匹配）：")
        for lvl1, lvl2_dict in self.taxonomy.items():
            if not lvl2_dict:
                continue
            lines.append(f"- {lvl1}:")
            for lvl2, lvl3_list in lvl2_dict.items():
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

            if lvl1 not in self.taxonomy:
                lvl1 = None
                lvl2 = None
                lvl3 = None
            else:
                lvl2_dict = self.taxonomy[lvl1]
                if lvl2 not in lvl2_dict:
                    lvl2 = None
                    lvl3 = None
                else:
                    allowed_lvl3 = lvl2_dict.get(lvl2, [])
                    if lvl3 not in allowed_lvl3:
                        lvl3 = None

            return TagResult(lvl1=lvl1, lvl2=lvl2, lvl3=lvl3, bridge_id=bridge_name)
        except Exception:
            logger.warning("Failed to parse tagger response: %s", content, exc_info=True)

        return TagResult(lvl1=None, lvl2=None, lvl3=None, bridge_id=None)
