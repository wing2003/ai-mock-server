import ahocorasick
from typing import Tuple, Dict, Any
from app.strategies.base import BaseRiskStrategy
from app.risk.context import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.base import SensitiveWord
from app.core.database import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)

class ContentSafetyStrategy(BaseRiskStrategy):
    strategy_code = "content_safety_check"
    strategy_name = "内容安全审核"
    strategy_type = "content"
    default_priority = 85
    default_params = {
        "block_level": [2, 3],  # 拦截的风险等级
        "stream_cut_off": True   # 流式响应是否中途截断
    }

    def __init__(self, custom_params: Dict[str, Any] = None):
        super().__init__(custom_params)
        self.automaton = ahocorasick.Automaton()
        self.words_map = {}
        self._initialized = False

    async def _ensure_initialized(self):
        if not self._initialized:
            await self._load_sensitive_words()
            self._initialized = True

    async def _load_sensitive_words(self):
        """从数据库加载敏感词并构建 AC 自动机"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SensitiveWord).where(SensitiveWord.is_enabled == True))
            words = result.scalars().all()
            
            for word_obj in words:
                self.automaton.add_word(word_obj.word, word_obj.id)
                self.words_map[word_obj.id] = word_obj
            
            self.automaton.make_automaton()
            logger.info(f"Content safety automaton initialized with {len(words)} words.")

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        await self._ensure_initialized()
        
        if not ctx.prompt_content:
            return False, {}

        found_words = []
        for end_index, word_id in self.automaton.iter(ctx.prompt_content):
            word_obj = self.words_map.get(word_id)
            if word_obj and word_obj.level in self.params.get("block_level", [2, 3]):
                found_words.append({
                    "word": word_obj.word,
                    "level": word_obj.level,
                    "category": word_obj.category
                })

        if found_words:
            return True, {
                "matched_words": found_words,
                "action": "stream_cut_off" if ctx.is_stream else "block"
            }
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        ctx.response_code = 400
        ctx.response_error = {
            "error": {
                "message": "Content security check failed.",
                "type": "content_filter",
                "param": None,
                "code": "content_filter_violation"
            },
            "content_filter_result": {
                "flagged": True,
                "categories": list(set(w["category"] for w in ctx.trigger_details.get("matched_words", [])))
            }
        }


class PromptSensitiveStrategy(BaseRiskStrategy):
    """Prompt 敏感内容检测策略"""
    strategy_code = "prompt_sensitive_check"
    strategy_name = "Prompt 敏感内容检测"
    strategy_type = "content"
    default_priority = 82
    default_params = {
        "max_prompt_length": 10000,  # 最大 Prompt 长度
        "blocked_keywords": []       # 额外的阻止关键词列表
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """检查 Prompt 是否包含敏感内容或过长"""
        if not ctx.prompt_content:
            return False, {}
        
        max_length = self.params.get("max_prompt_length", 10000)
        blocked_keywords = self.params.get("blocked_keywords", [])
        
        # 检查长度
        if len(ctx.prompt_content) > max_length:
            return True, {
                "message": f"Prompt length {len(ctx.prompt_content)} exceeds limit {max_length}",
                "reason": "too_long",
                "length": len(ctx.prompt_content),
                "max_allowed": max_length
            }
        
        # 检查关键词
        prompt_lower = ctx.prompt_content.lower()
        for keyword in blocked_keywords:
            if keyword.lower() in prompt_lower:
                return True, {
                    "message": f"Prompt contains blocked keyword: {keyword}",
                    "reason": "blocked_keyword",
                    "keyword": keyword
                }
        
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """Prompt 敏感内容检测失败，返回 400"""
        ctx.response_code = 400
        reason = ctx.trigger_details.get("reason", "unknown")
        
        if reason == "too_long":
            ctx.response_error = {
                "error": {
                    "message": "Your prompt is too long. Please reduce the length and try again.",
                    "type": "invalid_request_error",
                    "code": "prompt_too_long",
                    "param": "prompt"
                }
            }
        else:
            ctx.response_error = {
                "error": {
                    "message": "Your prompt contains sensitive or blocked content.",
                    "type": "content_filter",
                    "code": "prompt_blocked"
                }
            }


class ResponseLengthStrategy(BaseRiskStrategy):
    """响应长度限制策略"""
    strategy_code = "response_length_check"
    strategy_name = "响应长度限制"
    strategy_type = "content"
    default_priority = 88
    default_params = {
        "max_tokens": 4096,  # 最大输出 Token 数
        "max_characters": 16384  # 最大字符数
    }

    async def execute(self, ctx: RequestContext) -> Tuple[bool, Dict[str, Any]]:
        """
        检查请求的输出长度限制
        
        注意：此策略主要用于模拟上游厂商的响应长度限制
        实际实现中需要在 Mock 响应生成时进行检查
        """
        # 当前为框架占位，实际需要在响应生成阶段集成
        # 这里仅作为策略注册和配置管理的入口
        return False, {}

    async def after_trigger(self, ctx: RequestContext):
        """响应长度超限，返回 400"""
        ctx.response_code = 400
        ctx.response_error = {
            "error": {
                "message": "The requested response length exceeds the maximum allowed limit.",
                "type": "invalid_request_error",
                "code": "response_too_long",
                "param": "max_tokens"
            }
        }
