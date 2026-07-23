# ruff: noqa: E501
"""
数据中心采购 Agent 意图识别。

三路融合策略：
  1. LLM 语义理解（权重 70%）—— 主力，理解复杂语义和上下文
  2. Embedding 向量相似度（权重 20%）—— 快速匹配常见表达
  3. 关键词模式匹配（权重 10%）—— 零延迟兜底

三路结果通过加权投票合并，置信度低于阈值时降级为 UNKNOWN。
LLM 和 Embedding 并行调用，不串行等待。
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - optional production integration
    AsyncAnthropic = None  # type: ignore[assignment,misc]

from app.modules.agent.llm_utils import extract_text_content

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    """与当前 Agent—采购后端接口契约一致的采购意图。"""

    CREATE_REQUIREMENT = "create_requirement"
    SUPPLEMENT_REQUIREMENT = "supplement_requirement"
    MODIFY_REQUIREMENT = "modify_requirement"
    VIEW_REQUIREMENT = "view_requirement"
    CONFIRM_SUBMISSION = "confirm_submission"
    CANCEL_REQUIREMENT = "cancel_requirement"
    QUERY_STATUS = "query_status"
    LIST_REQUIREMENTS = "list_requirements"
    SEARCH_HISTORICAL_SUPPLIERS = "search_historical_suppliers"
    UNKNOWN = "unknown"


class UrgencyLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class IntentResult:
    intent: IntentCategory
    confidence: float
    urgency: UrgencyLevel
    entities: dict[str, list[str]]  # 从消息中提取的实体
    reasoning: str
    latency_ms: float


# ── Few-shot 模板（同时用于 LLM 示例和 Embedding 匹配）────────────────────────
_TEMPLATES: dict[IntentCategory, list[str]] = {
    IntentCategory.CREATE_REQUIREMENT: [
        "我要给3号楼采购两个UPS功率模块",
        "申请购买一批空调过滤网",
        "新建一个服务器采购需求",
    ],
    IntentCategory.SUPPLEMENT_REQUIREMENT: [
        "补充一下，用在3号楼电力室",
        "品牌是科士达，型号是YMK3350",
        "采购原因是备件库存不足",
    ],
    IntentCategory.MODIFY_REQUIREMENT: [
        "数量改成3台",
        "型号写错了，改为YMK3350-200kVA",
        "不要原来的供应商，换一家新的",
    ],
    IntentCategory.VIEW_REQUIREMENT: [
        "查看当前采购草稿",
        "把采购单完整内容给我看看",
        "显示我刚才填写的申请",
    ],
    IntentCategory.CONFIRM_SUBMISSION: [
        "信息无误，确认提交审批",
        "确认提交",
        "可以提交给楼长了",
    ],
    IntentCategory.CANCEL_REQUIREMENT: [
        "取消这张采购草稿",
        "这个需求不要了",
        "撤销刚才的采购申请",
    ],
    IntentCategory.QUERY_STATUS: [
        "我的采购申请现在什么状态",
        "查询采购进度",
        "审批到哪一步了",
    ],
    IntentCategory.LIST_REQUIREMENTS: [
        "列出我的采购申请",
        "查看我的全部采购单",
        "我的待审批申请有哪些",
    ],
    IntentCategory.SEARCH_HISTORICAL_SUPPLIERS: [
        "推荐这个草稿的历史供应商",
        "查询以前买过这个设备的供应商",
        "查一下相似采购的历史价格",
    ],
    IntentCategory.UNKNOWN: ["你好", "帮帮我", "今天天气怎么样"],
}

# 紧急关键词
_URGENCY_KEYWORDS = {
    UrgencyLevel.CRITICAL: ["紧急", "emergency", "urgent", "asap", "立刻"],
    UrgencyLevel.HIGH: ["今天", "马上", "尽快", "hurry", "now"],
    UrgencyLevel.MEDIUM: ["这周", "soon", "快点"],
}


def _cosine(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度，不依赖 numpy。"""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class IntentRecognizer:
    """
    端到端意图识别器。

    初始化时不加载任何本地模型，所有 AI 能力通过 Anthropic API 调用。
    模板 Embedding 在首次请求时懒加载并缓存，后续复用。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        confidence_threshold: float = 0.5,
    ):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if AsyncAnthropic is None:
            raise RuntimeError("Anthropic support requires the optional 'anthropic' dependency")
        self.client = AsyncAnthropic(**kwargs)
        self.model = model
        self.threshold = confidence_threshold
        # 第三方兼容 API（如 DeepSeek）通常不支持 Embedding，禁用该策略。
        # 官方 Anthropic SDK 当前没有 embeddings 资源，因此下面会使用稳定的
        # 本地字符 n-gram 向量作为轻量兜底，保证三路融合链路真实可跑。
        self._embedding_enabled = not bool(base_url)

        self._tpl_embeddings: dict[IntentCategory, list[list[float]]] = {}
        self._cache: dict[str, IntentResult] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    async def recognize(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> IntentResult:
        """
        识别用户意图。

        history 格式：[{"role": "user"/"assistant", "content": "..."}]
        """
        key = self._cache_key(message, history)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        self.cache_misses += 1

        t0 = time.monotonic()

        # LLM 和 Embedding 并行（Embedding 不可用时跳过）
        llm_task = asyncio.create_task(self._llm_recognize(message, history))
        emb_task = (
            asyncio.create_task(self._embedding_recognize(message))
            if self._embedding_enabled
            else None
        )
        pat = self._pattern_recognize(message)

        if emb_task:
            llm, emb = await asyncio.gather(llm_task, emb_task)
        else:
            llm = await llm_task
            emb = {"intent": IntentCategory.UNKNOWN, "confidence": 0.0}

        intent = self._vote(llm, emb, pat)
        entities = await self._extract_entities(message)
        urgency = self._urgency(message, intent)

        result = IntentResult(
            intent=intent,
            confidence=max(
                (
                    float(item.get("confidence", 0.0))
                    for item in (llm, emb, pat)
                    if item.get("intent") == intent
                ),
                default=0.0,
            ),
            urgency=urgency,
            entities=entities,
            reasoning=llm.get("reasoning", ""),
            latency_ms=(time.monotonic() - t0) * 1000,
        )

        # LRU 缓存
        if len(self._cache) >= 1000:
            for k in list(self._cache)[:500]:
                del self._cache[k]
        self._cache[key] = result
        return result

    def learn(self, message: str, correct: IntentCategory) -> None:
        """在线学习：将纠正样本加入模板，清除对应 Embedding 缓存。"""
        tpls = _TEMPLATES.setdefault(correct, [])
        if message not in tpls:
            tpls.append(message)
            self._tpl_embeddings.pop(correct, None)  # 下次重新计算
            logger.info(f"学习新样本 → {correct.value}: {message[:40]}")

    # ── 三路识别策略 ──────────────────────────────────────────────────────────

    async def _llm_recognize(
        self,
        message: str,
        history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        """策略 1：LLM 语义理解（Few-shot + 上下文）。"""
        message = self._clean_text(message)
        # 构建 Few-shot 示例
        examples = "\n".join(
            f'  消息: "{t}" → 意图: {cat.value}'
            for cat, tpls in _TEMPLATES.items()
            for t in tpls[:1]  # 每类取 1 条，控制 prompt 长度
        )
        # 最近 3 轮对话上下文
        ctx = ""
        if history:
            ctx = "\n最近对话:\n" + "\n".join(
                f"  {self._clean_text(m.get('role', 'user'))}: {self._clean_text(m.get('content', ''))}"
                for m in history[-3:]
            )

        prompt = f"""你是数据中心采购 Agent 的意图分析组件。根据示例和最近对话判断用户当前操作，返回 JSON。

判断规则：
1. 新建采购需求使用 create_requirement。
2. 回答上一轮缺失项、继续补充草稿使用 supplement_requirement。
3. 明确纠正或替换已有字段使用 modify_requirement。
4. 要求查看当前草稿或申请详情使用 view_requirement。
5. 只有明确表达“确认提交审批”才使用 confirm_submission。
6. 明确取消尚未审批的采购草稿使用 cancel_requirement。
7. 查询本人申请或审批进度使用 query_status。
8. 无法确定时使用 unknown；不要把普通问候判断为采购操作。

示例:
{examples}

{ctx}
用户消息: "{message}"

返回格式（仅 JSON，不要其他文字）:
{{"intent": "<意图值>", "confidence": <0-1>, "reasoning": "<一句话说明>"}}

可选意图: {", ".join(c.value for c in IntentCategory)}"""
        prompt = self._clean_text(prompt)

        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = extract_text_content(resp.content)
            s, e = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[s:e])
            try:
                data["intent"] = IntentCategory(data["intent"])
            except ValueError:
                data["intent"] = IntentCategory.UNKNOWN
            return data
        except Exception as ex:
            logger.warning(f"LLM 识别失败: {ex}")
            return {
                "intent": IntentCategory.UNKNOWN,
                "confidence": 0.0,
                "reasoning": "LLM 失败",
                "failed": True,
            }

    async def _embedding_recognize(self, message: str) -> dict[str, Any]:
        """策略 2：Embedding 向量相似度匹配。"""
        try:
            await self._load_template_embeddings()
            msg_vec = await self._embed_text(message)

            best_cat, best_score = IntentCategory.UNKNOWN, 0.0
            for cat, vecs in self._tpl_embeddings.items():
                score = max(_cosine(msg_vec, v) for v in vecs)
                if score > best_score:
                    best_score, best_cat = score, cat

            return {"intent": best_cat, "confidence": best_score}
        except Exception as ex:
            logger.warning(f"Embedding 识别失败: {ex}")
            return {"intent": IntentCategory.UNKNOWN, "confidence": 0.0}

    def _pattern_recognize(self, message: str) -> dict[str, Any]:
        """策略 3：采购关键词规则，按高风险/强动作优先级匹配。"""
        msg = self._clean_text(message).lower().strip()
        ordered_patterns = [
            (
                IntentCategory.CONFIRM_SUBMISSION,
                ["确认提交", "提交审批", "信息无误", "可以提交", "确认无误"],
            ),
            (
                IntentCategory.CANCEL_REQUIREMENT,
                ["取消采购", "取消申请", "取消草稿", "撤销申请", "不要了", "不买了"],
            ),
            (
                IntentCategory.SEARCH_HISTORICAL_SUPPLIERS,
                ["历史供应商", "供应商推荐", "推荐供应商", "历史价格", "以前买过"],
            ),
            (
                IntentCategory.QUERY_STATUS,
                ["采购进度", "申请进度", "审批进度", "采购状态", "申请状态", "审批到哪"],
            ),
            (
                IntentCategory.LIST_REQUIREMENTS,
                ["列出我的", "我的采购申请", "我的采购单", "待审批申请", "全部采购单"],
            ),
            (
                IntentCategory.VIEW_REQUIREMENT,
                ["查看草稿", "看看草稿", "查看采购单", "显示采购单", "当前草稿", "采购草稿"],
            ),
            (
                IntentCategory.MODIFY_REQUIREMENT,
                ["改成", "修改", "更正", "写错了", "换成", "不要原来"],
            ),
            (
                IntentCategory.SUPPLEMENT_REQUIREMENT,
                ["补充", "再加上", "品牌是", "型号是", "供应商是", "采购原因是", "地点是"],
            ),
            (
                IntentCategory.CREATE_REQUIREMENT,
                [
                    "我要采购",
                    "需要采购",
                    "申请采购",
                    "采购需求",
                    "申请购买",
                    "需要购买",
                    "新建采购",
                    "采购",
                ],
            ),
        ]
        for intent, keywords in ordered_patterns:
            hits = sum(1 for keyword in keywords if keyword in msg)
            if hits:
                return {
                    "intent": intent,
                    "confidence": min(0.7 + 0.1 * (hits - 1), 0.95),
                }
        if re.search(
            r"(?:想|要|需要|申请|帮我)?(?:采购|购买|买)(?:[一二两三四五六七八九十]|\d)", msg
        ):
            return {"intent": IntentCategory.CREATE_REQUIREMENT, "confidence": 0.75}
        return {"intent": IntentCategory.UNKNOWN, "confidence": 0.0}

    # ── 投票合并 ──────────────────────────────────────────────────────────────

    def _vote(self, llm: dict, emb: dict, pat: dict) -> IntentCategory:
        """加权投票。embedding 不可用时权重自动转移到 LLM 和 Pattern。"""
        if llm.get("failed"):
            fallbacks = [
                result
                for result in (emb, pat)
                if result.get("intent") != IntentCategory.UNKNOWN
                and result.get("confidence", 0.0) > 0
            ]
            return (
                max(fallbacks, key=lambda item: item.get("confidence", 0.0))["intent"]
                if fallbacks
                else IntentCategory.UNKNOWN
            )

        if self._embedding_enabled:
            weights = [(llm, 0.7), (emb, 0.2), (pat, 0.1)]
        else:
            weights = [(llm, 0.85), (pat, 0.15)]
        scores: dict[IntentCategory, float] = {}
        for result, w in weights:
            cat = result.get("intent", IntentCategory.UNKNOWN)
            conf = result.get("confidence", 0.0)
            scores[cat] = scores.get(cat, 0.0) + w * conf

        best = max(scores, key=scores.get)  # type: ignore
        return best if scores[best] >= self.threshold else IntentCategory.UNKNOWN

    # ── 实体提取 ──────────────────────────────────────────────────────────────

    async def _extract_entities(self, message: str) -> dict[str, list[str]]:
        """从采购消息中提取便于日志和路由使用的轻量实体。"""
        message = self._clean_text(message)
        prompt = f"""从数据中心采购消息中提取实体，返回 JSON（字段值为列表，没有则为空列表）。
不得编造用户未提供的信息；数量和单价也以字符串列表返回。
消息: "{message}"
格式: {{"requirement_no":[],"product_name":[],"brand":[],"model":[],"quantity":[],"unit":[],"supplier_name":[],"application_location":[]}}"""
        prompt = self._clean_text(prompt)
        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = extract_text_content(resp.content)
            s, e = raw.find("{"), raw.rfind("}") + 1
            return json.loads(raw[s:e])
        except Exception:
            return {
                "requirement_no": [],
                "product_name": [],
                "brand": [],
                "model": [],
                "quantity": [],
                "unit": [],
                "supplier_name": [],
                "application_location": [],
            }

    # ── 辅助 ──────────────────────────────────────────────────────────────────

    async def _load_template_embeddings(self) -> None:
        """懒加载所有模板的 Embedding（只在首次调用时执行）。"""
        missing = [cat for cat in _TEMPLATES if cat not in self._tpl_embeddings]
        if not missing:
            return

        all_texts = [t for cat in missing for t in _TEMPLATES[cat]]
        vecs = [await self._embed_text(text) for text in all_texts]
        idx = 0
        for cat in missing:
            n = len(_TEMPLATES[cat])
            self._tpl_embeddings[cat] = vecs[idx : idx + n]
            idx += n

    async def _embed_text(self, text: str) -> list[float]:
        """
        生成文本向量。

        如果未来接入的官方/兼容客户端提供 embeddings.create，会优先使用远端向量；
        当前 Anthropic SDK 没有该资源时，退化为字符 n-gram 哈希向量。这样不会因为
        Embedding 服务缺失导致三路融合中断。
        """
        embeddings = getattr(self.client, "embeddings", None)
        if embeddings is not None:
            try:
                resp = await embeddings.create(model="voyage-3-lite", input=[text])
                return list(resp.data[0].embedding)
            except Exception as ex:
                logger.warning(f"远端 Embedding 失败，使用本地向量兜底: {ex}")

        return self._local_embedding(text)

    @staticmethod
    def _local_embedding(text: str, dims: int = 256) -> list[float]:
        """稳定的字符 n-gram 哈希向量，用于无远端 Embedding 时的语义近似匹配。"""
        normalized = text.lower().strip()
        vec = [0.0] * dims
        tokens = set()
        for n in (1, 2, 3):
            if len(normalized) >= n:
                tokens.update(normalized[i : i + n] for i in range(len(normalized) - n + 1))
        if not tokens:
            tokens.add(normalized)

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dims
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        return vec

    def _urgency(self, message: str, intent: IntentCategory) -> UrgencyLevel:
        msg = message.lower()
        for level, kws in _URGENCY_KEYWORDS.items():
            if any(kw in msg for kw in kws):
                return level
        return UrgencyLevel.LOW

    def _cache_key(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        """采购短句依赖上下文，缓存键包含最近两轮以避免跨阶段误命中。"""
        recent = history[-2:] if history else []
        context = "|".join(
            f"{item.get('role', '')}:{self._clean_text(item.get('content', ''))[:120]}"
            for item in recent
        )
        return f"{context}|{self._clean_text(message)[:200]}"

    @staticmethod
    def _clean_text(value: Any) -> str:
        """移除 Unicode 代理字符，避免 HTTP 客户端编码 prompt 时崩溃。"""
        if value is None:
            return ""
        if not isinstance(value, str):
            value = str(value)
        return value.encode("utf-8", errors="ignore").decode("utf-8")

    @property
    def cache_stats(self) -> dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        return {
            "size": len(self._cache),
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "hit_rate": self.cache_hits / total if total else 0.0,
        }
