from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, BigInteger, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class StrategyMetadata(Base):
    __tablename__ = "strategy_metadata"
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_code = Column(String(100), unique=True, nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False)
    strategy_type = Column(String(50), nullable=False, index=True)
    default_priority = Column(Integer, default=100)
    default_params = Column(JSON, nullable=False)
    handler_class = Column(String(200), nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    status = Column(String(20), default="inactive") # inactive, running, stopped
    max_run_seconds = Column(Integer, default=0)
    ext_config = Column(JSON, default={})
    started_at = Column(DateTime(timezone=True))
    stopped_at = Column(DateTime(timezone=True))
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class ApiKeyPool(Base):
    __tablename__ = "api_key_pools"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_id = Column(Integer, ForeignKey("api_key_pools.id"), nullable=False)
    api_key = Column(String(100), unique=True, nullable=False)
    status = Column(String(30), default="active")
    balance = Column(DECIMAL(10, 4), default=0)
    expire_at = Column(DateTime(timezone=True))
    total_requests = Column(Integer, default=0)
    remark = Column(String(500))
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class ScenePoolRelation(Base):
    __tablename__ = "scene_pool_relation"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    pool_id = Column(Integer, ForeignKey("api_key_pools.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SceneStrategyRelation(Base):
    __tablename__ = "scene_strategy_relation"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategy_metadata.id"), nullable=False)
    custom_params = Column(JSON, default={})
    custom_priority = Column(Integer)
    is_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class GlobalConfig(Base):
    __tablename__ = "global_config"
    name = Column(String(100), primary_key=True, nullable=False)
    value = Column(String(100))
    value_type = Column(String(100))
    description = Column(Text)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class SensitiveWord(Base):
    __tablename__ = "sensitive_words"
    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(100), unique=True, nullable=False, index=True)
    level = Column(Integer, default=1)  # 1: warning, 2: block, 3: ban
    category = Column(String(50), nullable=False, index=True)
    is_enabled = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False, index=True)
    strategy_id = Column(Integer, ForeignKey("strategy_metadata.id"), index=True)
    report_id = Column(Integer, ForeignKey("test_reports.id"), index=True)
    event_type = Column(String(50), nullable=False, index=True)
    error_code = Column(Integer, index=True)
    api_key = Column(String(100), index=True)
    ip_address = Column(String(50), index=True)
    user_agent = Column(String(500))
    model = Column(String(100), index=True)
    prompt_snippet = Column(String(1000))
    details = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class TestReport(Base):
    __tablename__ = "test_reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False, index=True)
    scene_name = Column(String(100), nullable=False)
    scene_strategy_snapshot = Column(JSON, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    stopped_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    total_requests = Column(Integer, default=0)
    passed_requests = Column(Integer, default=0)
    blocked_requests = Column(Integer, default=0)
    block_rate = Column(DECIMAL(5, 4), default=0)
    total_tokens = Column(BigInteger, default=0)
    error_code_stats = Column(JSON, default={})
    strategy_trigger_stats = Column(JSON, default={})
    key_status_stats = Column(JSON, default={})
    top_events = Column(JSON, default=[])
    is_archived = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
