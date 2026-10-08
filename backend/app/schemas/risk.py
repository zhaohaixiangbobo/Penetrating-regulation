"""风险参数契约：仅开放白名单计算器、同一事件粒度及有限范围运行。"""
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.core.config import VALID_COM_IDS

class Condition(BaseModel):
    indicator: Literal['visit_duration_seconds', 'visit_location_distance_meters']
    version: Literal[1] = 1
    operator: Literal['lt', 'gt']
    value: float = Field(gt=0, le=1000000, allow_inf_nan=False)

class ModelConfig(BaseModel):
    evaluation_unit: Literal['visit_event'] = 'visit_event'
    combination: Literal['ALL', 'ANY', 'AT_LEAST_N'] = 'ALL'
    minimum: int = Field(1, ge=1, le=8)
    conditions: list[Condition] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def validate_combination(self):
        if self.combination == 'AT_LEAST_N' and self.minimum > len(self.conditions):
            raise ValueError('至少满足项数不得超过条件数')
        for i, a in enumerate(self.conditions):
            for b in self.conditions[i+1:]:
                if a.indicator != b.indicator:
                    continue
                if self.combination == 'AT_LEAST_N' or a.operator == b.operator:
                    raise ValueError('同一指标包含或重复条件不能重复计数')
                lower = a.value if a.operator == 'gt' else b.value
                upper = a.value if a.operator == 'lt' else b.value
                if self.combination == 'ALL' and lower >= upper:
                    raise ValueError('全部满足中的上下限条件互相矛盾')
        return self

class CreateModel(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: ModelConfig

class RunRequest(BaseModel):
    version_id: int
    mode: Literal['trial', 'formal', 'compare'] = 'trial'
    start_date: date
    end_date: date
    com_ids: list[str] = Field(min_length=1, max_length=13)
    baseline_version_id: int | None = None

    @model_validator(mode='after')
    def validate_scope(self):
        if self.start_date < date(2024,1,1) or self.end_date < self.start_date:
            raise ValueError('日期需从2024-01-01起，结束日期应晚于或等于开始日期')
        if (self.end_date-self.start_date).days > 365:
            raise ValueError('单个父任务最多366天，系统按公司和日期自动分批')
        if set(self.com_ids)-VALID_COM_IDS:
            raise ValueError('公司代码无效')
        if self.mode == 'compare' and self.baseline_version_id is None:
            raise ValueError('参数对比需选择基准版本')
        return self

class ActionRequest(BaseModel):
    revision: int
    action: Literal['start', 'conclude', 'submit_rectification', 'approve', 'return', 'reopen', 'supplement']
    conclusion: Literal['confirmed', 'reasonable', 'data_quality', 'insufficient', 'normal'] | None = None
    note: str = Field(min_length=2, max_length=5000)
    measures: str | None = Field(None, max_length=5000)


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version_id: int
    com_ids: list[str] = Field(min_length=1, max_length=13)
    frequency: Literal['daily', 'weekly'] = 'daily'
    weekday: int = Field(0, ge=0, le=6)
    hour: int = Field(3, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    lookback_days: int = Field(3, ge=1, le=31)
    batch_size: int = Field(1000, ge=1, le=5000)
    enabled: bool = False
    revision: int | None = None

    @model_validator(mode='after')
    def validate_schedule(self):
        if not self.name.strip() or set(self.com_ids) - VALID_COM_IDS:
            raise ValueError('计划名称或公司代码无效')
        self.name = self.name.strip()
        self.com_ids = list(dict.fromkeys(self.com_ids))
        return self
