import json
import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models import Bridge
from app.providers import ChatMessage, LLMProvider

BindingStatus = Literal["none", "primary", "ambiguous"]
LinkRole = Literal["primary", "secondary", "candidate"]
LinkMethod = Literal["hint", "rule", "llm"]


@dataclass
class BridgeLink:
    bridge_id: int
    bridge_name: str
    role: LinkRole
    confidence: float
    method: LinkMethod


@dataclass
class BridgeLinkingResult:
    primary_bridge_name: str | None
    secondary_bridge_names: list[str]
    candidate_bridge_names: list[str]
    binding_status: BindingStatus
    auto_created_bridge_names: list[str]
    links: list[BridgeLink]


class BridgeLinker:
    """Chunk-level bridge entity linker for mixed-bridge documents."""

    PROMPT_TEMPLATE = """你是桥梁实体链接助手。请根据文本片段判断主桥、次要桥和候选桥。

【文本片段】
{content}

【候选桥（可为空）】
{candidates}

输出 JSON（仅输出 JSON）：
{{
  "primary_bridge": "桥名或null",
  "primary_confidence": 0.0,
  "secondary_bridges": ["桥名1", "桥名2"],
  "candidate_bridges": ["桥名A", "桥名B"]
}}

要求：
1) 若无法确定主桥，primary_bridge 填 null
2) primary_confidence 取值 0-1
3) 仅输出桥名，不要解释
"""

    def __init__(
        self,
        provider: LLMProvider,
        min_primary_confidence: float = 0.75,
        enable_auto_bridge_detection: bool = True,
    ):
        self.provider = provider
        self.min_primary_confidence = min_primary_confidence
        self.enable_auto_bridge_detection = enable_auto_bridge_detection
        self._bridge_by_id: dict[int, Bridge] | None = None
        self._bridge_alias_map: dict[str, Bridge] | None = None
        self._alias_entries: list[tuple[str, int]] | None = None

    async def link_chunk(
        self,
        db: Session,
        content: str,
        hint_bridge_names: list[str] | None = None,
        bridge_candidates: list[str] | None = None,
        min_primary_confidence: float | None = None,
        enable_auto_bridge_detection: bool | None = None,
    ) -> BridgeLinkingResult:
        threshold = (
            min_primary_confidence
            if min_primary_confidence is not None
            else self.min_primary_confidence
        )
        auto_detection = (
            enable_auto_bridge_detection
            if enable_auto_bridge_detection is not None
            else self.enable_auto_bridge_detection
        )

        auto_created: list[str] = []
        links: list[BridgeLink] = []

        hint_bridges = self._resolve_existing_bridges(db, hint_bridge_names or [])
        hint_bridge_ids = {bridge.id for bridge in hint_bridges}

        candidate_names = self._dedupe_names(
            self._normalize_name_list(bridge_candidates or [])
        )

        rule_hits = self._rule_match_bridges(db, content)
        hint_rule_hits = [
            (bridge, score) for bridge, score in rule_hits if bridge.id in hint_bridge_ids
        ]

        # Hint-assisted path: use hints only when they are actually hit in chunk content.
        if hint_rule_hits:
            primary, _ = hint_rule_hits[0]
            links.append(
                BridgeLink(
                    bridge_id=primary.id,
                    bridge_name=primary.name,
                    role="primary",
                    confidence=0.98,
                    method="hint",
                )
            )

            for bridge, _ in hint_rule_hits[1:]:
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="secondary",
                        confidence=0.9,
                        method="hint",
                    )
                )

            for bridge, score in rule_hits:
                if bridge.id == primary.id or any(l.bridge_id == bridge.id for l in links):
                    continue
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="secondary",
                        confidence=self._rule_confidence(score),
                        method="rule",
                    )
                )

            return self._to_result(links, auto_created, threshold)

        if len(rule_hits) == 1 and not hint_bridges:
            bridge, score = rule_hits[0]
            conf = self._rule_confidence(score)
            role: LinkRole = "primary" if conf >= threshold else "candidate"
            links.append(
                BridgeLink(
                    bridge_id=bridge.id,
                    bridge_name=bridge.name,
                    role=role,
                    confidence=conf,
                    method="rule",
                )
            )
            return self._to_result(links, auto_created, threshold)

        if not auto_detection:
            for bridge in hint_bridges:
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="candidate",
                        confidence=0.6,
                        method="hint",
                    )
                )
            for bridge, score in rule_hits:
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="candidate",
                        confidence=self._rule_confidence(score),
                        method="rule",
                    )
                )
            return self._to_result(links, auto_created, threshold)

        llm_seed_names = [bridge.name for bridge in hint_bridges]
        llm_seed_names.extend(candidate_names)
        llm_seed_names.extend([bridge.name for bridge, _ in rule_hits])
        llm_seed_names = self._dedupe_names(llm_seed_names)

        llm_result = await self._llm_link(content, llm_seed_names)
        llm_primary = self._normalize_name(llm_result.get("primary_bridge"))
        llm_confidence = self._to_float(llm_result.get("primary_confidence"))
        llm_secondary = self._normalize_name_list(llm_result.get("secondary_bridges"))
        llm_candidates = self._normalize_name_list(llm_result.get("candidate_bridges"))

        names_to_resolve = []
        if llm_primary:
            names_to_resolve.append(llm_primary)
        names_to_resolve.extend(llm_secondary)
        names_to_resolve.extend(llm_candidates)

        resolved_map: dict[str, Bridge] = {}
        _, created = self._resolve_or_create_bridges(
            db,
            names_to_resolve,
            allow_create=True,
        )
        auto_created.extend(created)

        # Preserve both alias and canonical keys so later lookups using raw
        # LLM names still resolve after alias matching.
        self._ensure_bridge_index(db)
        assert self._bridge_alias_map is not None
        for name in self._dedupe_names(names_to_resolve):
            bridge = self._bridge_alias_map.get(name)
            if not bridge:
                continue
            resolved_map[name] = bridge
            resolved_map[bridge.name] = bridge

        if llm_primary and llm_primary in resolved_map:
            role: LinkRole = "primary" if llm_confidence >= threshold else "candidate"
            bridge = resolved_map[llm_primary]
            links.append(
                BridgeLink(
                    bridge_id=bridge.id,
                    bridge_name=bridge.name,
                    role=role,
                    confidence=llm_confidence,
                    method="llm",
                )
            )

        for name in llm_secondary:
            bridge = resolved_map.get(name)
            if not bridge:
                continue
            if any(l.bridge_id == bridge.id for l in links):
                continue
            links.append(
                BridgeLink(
                    bridge_id=bridge.id,
                    bridge_name=bridge.name,
                    role="secondary",
                    confidence=0.7,
                    method="llm",
                )
            )

        for name in llm_candidates:
            bridge = resolved_map.get(name)
            if not bridge:
                continue
            if any(l.bridge_id == bridge.id for l in links):
                continue
            links.append(
                BridgeLink(
                    bridge_id=bridge.id,
                    bridge_name=bridge.name,
                    role="candidate",
                    confidence=0.55,
                    method="llm",
                )
            )

        if not links:
            for bridge in hint_bridges:
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="candidate",
                        confidence=0.6,
                        method="hint",
                    )
                )
            for bridge, score in rule_hits:
                links.append(
                    BridgeLink(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        role="candidate",
                        confidence=self._rule_confidence(score),
                        method="rule",
                    )
                )

        return self._to_result(links, auto_created, threshold)

    def _rule_match_bridges(self, db: Session, content: str) -> list[tuple[Bridge, int]]:
        if not content.strip():
            return []

        self._ensure_bridge_index(db)
        assert self._alias_entries is not None
        assert self._bridge_by_id is not None

        score_by_bridge: dict[int, int] = {}
        for alias, bridge_id in self._alias_entries:
            count = content.count(alias)
            if count <= 0:
                continue
            score = count * max(1, len(alias))
            score_by_bridge[bridge_id] = score_by_bridge.get(bridge_id, 0) + score

        items = sorted(score_by_bridge.items(), key=lambda x: -x[1])
        return [(self._bridge_by_id[bid], score) for bid, score in items]

    async def _llm_link(self, content: str, candidates: list[str]) -> dict:
        prompt = self.PROMPT_TEMPLATE.format(
            content=content,
            candidates=", ".join(candidates) if candidates else "无",
        )
        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.provider.chat(messages)

        try:
            start = response.content.find("{")
            end = response.content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response.content[start:end])
        except json.JSONDecodeError:
            pass
        return {}

    def _resolve_or_create_bridges(
        self,
        db: Session,
        names: list[str],
        *,
        allow_create: bool,
    ) -> tuple[list[Bridge], list[str]]:
        self._ensure_bridge_index(db)
        assert self._bridge_alias_map is not None

        normalized = self._dedupe_names(names)
        if not normalized:
            return [], []

        result: list[Bridge] = []
        created: list[str] = []
        seen_ids: set[int] = set()

        for name in normalized:
            bridge = self._bridge_alias_map.get(name)
            if bridge is None and allow_create:
                bridge = Bridge(name=name)
                db.add(bridge)
                db.flush()
                created.append(name)
                self._register_bridge(bridge)
            if bridge is None:
                continue

            if bridge.id in seen_ids:
                continue
            seen_ids.add(bridge.id)
            result.append(bridge)

        return result, created

    def _resolve_existing_bridges(self, db: Session, names: list[str]) -> list[Bridge]:
        bridges, _ = self._resolve_or_create_bridges(db, names, allow_create=False)
        return bridges

    def _to_result(
        self,
        links: list[BridgeLink],
        auto_created: list[str],
        threshold: float,
    ) -> BridgeLinkingResult:
        deduped_links: list[BridgeLink] = []
        seen: set[tuple[int, str]] = set()
        for link in links:
            key = (link.bridge_id, link.role)
            if key in seen:
                continue
            seen.add(key)
            deduped_links.append(link)

        primary_link = next((l for l in deduped_links if l.role == "primary"), None)
        if primary_link is None:
            candidate_primary = next(
                (l for l in deduped_links if l.role == "candidate" and l.confidence >= threshold),
                None,
            )
            if candidate_primary is not None:
                deduped_links = [
                    BridgeLink(
                        bridge_id=l.bridge_id,
                        bridge_name=l.bridge_name,
                        role="primary" if l.bridge_id == candidate_primary.bridge_id else l.role,
                        confidence=l.confidence,
                        method=l.method,
                    )
                    for l in deduped_links
                ]
                primary_link = next((l for l in deduped_links if l.role == "primary"), None)

        secondary = [l.bridge_name for l in deduped_links if l.role == "secondary"]
        candidates = [l.bridge_name for l in deduped_links if l.role == "candidate"]

        if primary_link is not None:
            status: BindingStatus = "primary"
        elif candidates:
            status = "ambiguous"
        else:
            status = "none"

        return BridgeLinkingResult(
            primary_bridge_name=primary_link.bridge_name if primary_link else None,
            secondary_bridge_names=self._dedupe_names(secondary),
            candidate_bridge_names=self._dedupe_names(candidates),
            binding_status=status,
            auto_created_bridge_names=self._dedupe_names(auto_created),
            links=deduped_links,
        )

    @staticmethod
    def _rule_confidence(score: int) -> float:
        # Treat exact rule hits as reasonably strong evidence.
        return min(0.95, 0.75 + min(0.2, score * 0.01))

    @staticmethod
    def _split_aliases(aliases: str | None) -> list[str]:
        if not aliases:
            return []
        parts = re.split(r"[,\n，、;；|]+", aliases)
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def _normalize_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        if s.lower() in {"null", "none", "unknown", "n/a"}:
            return None
        return s

    def _normalize_name_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            name = self._normalize_name(value)
            return [name] if name else []
        if isinstance(value, list):
            result = []
            for item in value:
                name = self._normalize_name(item)
                if name:
                    result.append(name)
            return self._dedupe_names(result)
        return []

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            v = float(value)
            if v < 0:
                return 0.0
            if v > 1:
                return 1.0
            return v
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _dedupe_names(names: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result

    def _ensure_bridge_index(self, db: Session) -> None:
        if self._bridge_by_id is not None and self._bridge_alias_map is not None and self._alias_entries is not None:
            return

        rows = db.query(Bridge).all()
        self._bridge_by_id = {}
        self._bridge_alias_map = {}
        self._alias_entries = []
        for bridge in rows:
            self._register_bridge(bridge, rebuild=False)
        self._rebuild_alias_entries()

    def _register_bridge(self, bridge: Bridge, *, rebuild: bool = True) -> None:
        assert self._bridge_by_id is not None
        assert self._bridge_alias_map is not None

        self._bridge_by_id[bridge.id] = bridge
        names = [bridge.name]
        names.extend(self._split_aliases(bridge.aliases))
        for name in names:
            normalized = self._normalize_name(name)
            if normalized:
                self._bridge_alias_map[normalized] = bridge

        if rebuild:
            self._rebuild_alias_entries()

    def _rebuild_alias_entries(self) -> None:
        assert self._bridge_alias_map is not None
        self._alias_entries = [
            (alias, bridge.id) for alias, bridge in self._bridge_alias_map.items()
        ]
        self._alias_entries.sort(key=lambda x: len(x[0]), reverse=True)
