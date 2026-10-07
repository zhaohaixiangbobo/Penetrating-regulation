"""两项内置指标及三值组合判断；计算结果与业务事实分开留存。"""
import math
from app.schemas.risk import ModelConfig

INDICATORS = [
    dict(code='visit_duration_seconds', name='拜访时长', unit='秒', version=1, evaluation_unit='单次拜访',
         source='crm_mcs_cust_visit_plan.visit_time', formula='有效拜访原始时长',
         quality='状态03且未删除；缺失、非数值或负值不可计算。零值保留为原始事实。'),
    dict(code='visit_location_distance_meters', name='定位偏差距离', unit='米', version=1, evaluation_unit='单次拜访',
         source='r_license_info.longitude/latitude；crm_mcs_cust_visit_plan.gis_long/gis_lat',
         formula='ST_Distance_Sphere(经营经度, 经营纬度, 签到经度, 签到纬度)',
         quality='坐标缺失、越界、(0,0)或许可证关联不唯一时不可计算。使用当前许可证位置，坐标系及历史地址需业务核实。'),
]
DEFAULT_CONFIG = ModelConfig(conditions=[
    dict(indicator='visit_duration_seconds', operator='lt', value=60),
    dict(indicator='visit_location_distance_meters', operator='gt', value=200),
]).model_dump()

def evaluate(config: dict, values: dict):
    parsed = ModelConfig.model_validate(config)
    reasons = []
    for condition in parsed.conditions:
        value = values.get(condition.indicator)
        if value is None or not math.isfinite(float(value)) or value < 0:
            outcome = 'unknown'
        else:
            hit = value < condition.value if condition.operator == 'lt' else value > condition.value
            outcome = 'hit' if hit else 'clear'
        reasons.append(dict(**condition.model_dump(), actual=value, outcome=outcome))
    hits = sum(r['outcome']=='hit' for r in reasons)
    unknown = sum(r['outcome']=='unknown' for r in reasons)
    target = len(reasons) if parsed.combination=='ALL' else 1 if parsed.combination=='ANY' else parsed.minimum
    outcome = 'hit' if hits >= target else 'clear' if hits + unknown < target else 'unknown'
    return outcome, reasons
