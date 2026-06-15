from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class StrategyMetadataBase(BaseModel):
    strategy_code: str = Field(..., max_length=100)
    strategy_name: str = Field(..., max_length=100)
    strategy_type: str = Field(..., max_length=50)
    default_priority: int = 100
    default_params: Dict[str, Any] = {}
    handler_class: str = Field(..., max_length=200)
    description: Optional[str] = None
    is_system: bool = True
    is_enabled: bool = True

class StrategyMetadataCreate(StrategyMetadataBase):
    pass

class StrategyMetadataUpdate(BaseModel):
    strategy_name: Optional[str] = None
    default_priority: Optional[int] = None
    default_params: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None

class StrategyMetadataResponse(StrategyMetadataBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
