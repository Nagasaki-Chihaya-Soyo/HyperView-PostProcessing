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
        return AnalysisResult(
            peak_value=peak_value,
            peak_entity_id=entity_id,
            peak_coords=coords,
            tags={},
            part_no=None,
            part_name=None,
            allowable_vm=None,
            safety_factor=None,
            allowable=None,
            passed=False,
            margin=None,
            ratio=None,
            message=f"Peak: {peak_value:.4f}",
        )

    def analyze_direct(self, peak_value: float, entity_id: Any, part: Dict) -> AnalysisResult:
        """Directly compare peak_value to the given part standard (no tag/mapping lookup)."""
        allowable_vm = part['allowable_vm']
        safety_factor = part['safety_factor'] or 1.0
        allowable = allowable_vm / safety_factor
        passed = peak_value <= allowable
        margin = allowable - peak_value
        ratio = peak_value / allowable if allowable > 0 else float('inf')
        if passed:
            message = (f"PASS — Peak {peak_value:.2f} ≤ Allowable {allowable:.2f}, "
                       f"Margin {margin:.2f}")
        else:
            message = (f"FAIL — Peak {peak_value:.2f} > Allowable {allowable:.2f}, "
                       f"Exceeded by {-margin:.2f}")
        return AnalysisResult(
            peak_value=peak_value,
            peak_entity_id=entity_id,
            peak_coords=(0, 0, 0),
            tags={},
            part_no=part['part_no'],
            part_name=part.get('name', ''),
            allowable_vm=allowable_vm,
            safety_factor=safety_factor,
            allowable=allowable,
            passed=passed,
            margin=margin,
            ratio=ratio,
            message=message,
        )
