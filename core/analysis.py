from typing import Dict, Optional, Any
from dataclasses import dataclass
from .db_store import DBStore


@dataclass
class AnalysisResult:
    peak_value: float
    peak_entity_id: int
    peak_coords: tuple
    tags: Dict[str, str]

    part_no: Optional[str]
    part_name: Optional[str]
    allowable_vm: Optional[float]
    safety_factor: Optional[float]
    allowable: Optional[float]

    passed: bool
    margin: Optional[float]
    ratio: Optional[float]

    message: str


class Analyzer:
    def __init__(self, db: DBStore):
        self.db = db

    def analyze(self, peak_data: Dict[str, Any]) -> AnalysisResult:
        peak_value = peak_data.get('value', 0)
        entity_id = peak_data.get('entity_id', 0)
        coords = tuple(peak_data.get('coords', [0, 0, 0]))
        tags = peak_data.get('tags', {})
        part = self.db.find_part_by_tags(tags)
        if part is None:
            return AnalysisResult(
                peak_value=peak_value,
                peak_entity_id=entity_id,
                peak_coords=coords,
                tags=tags,
                part_no=None,
                part_name=None,
                allowable_vm=None,
                safety_factor=None,
                allowable=None,
                passed=False,
                margin=None,
                ratio=None,
                message="未找到匹配的标准值，请检查映射配置"
            )

        allowable_vm = part['allowable_vm']
        safety_factor = part['safety_factor'] or 1.0
        allowable = allowable_vm / safety_factor
        passed = peak_value <= allowable
        margin = allowable - peak_value
        ratio = peak_value / allowable if allowable > 0 else float('inf')
        if passed:
            messages = f"通过-峰值{peak_value:.2f} MPa ≤ 许用值 {allowable:.2f} Mpa 裕度为{margin:.2f} Mpa"
        else:
            messages = f"通过-峰值{peak_value:.2f} MPa ≥ 许用值 {allowable:.2f} Mpa 超出{margin:.2f} Mpa"
        return AnalysisResult(
            peak_value=peak_value,
            peak_entity_id=entity_id,
            peak_coords=coords,
            tags=tags,
            part_no=part['part_no'],
            part_name=part.get('name', ''),
            allowable_vm=allowable_vm,
            safety_factor=safety_factor,
            allowable=allowable,
            passed=passed,
            margin=margin,
            ratio=ratio,
            message=messages
        )
