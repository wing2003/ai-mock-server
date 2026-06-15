from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class RequestContext(BaseModel):
    """请求上下文，全链路传递"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # 基础请求信息
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    request_path: str
    request_method: str
    request_time: datetime = Field(default_factory=datetime.utcnow)
    
    # 身份与网络特征
    api_key: Optional[str] = None
    client_ip: str
    user_agent: Optional[str] = None
    tls_fingerprint: Optional[str] = None
    
    # 请求内容特征
    model: Optional[str] = None
    prompt_content: Optional[str] = None
    input_tokens: int = 0
    is_stream: bool = False
    
    # 运行时配置
    scene_id: Optional[int] = None
    enabled_strategies: Dict[int, Dict[str, Any]] = {}
    
    # 数据库对象引用（用于状态更新）
    api_key_obj: Optional[Any] = None
    
    # 风控结果
    risk_triggered: bool = False
    trigger_strategy_code: Optional[str] = None
    trigger_details: Dict[str, Any] = {}
    response_code: Optional[int] = None
    response_error: Dict[str, Any] = {}
