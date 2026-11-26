"""Aliasing and candidate-diagnosis logic for narrow-band interference peaks.

The module is intentionally independent of Flask so the diagnostic rules can be
unit-tested and reused from the command line.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import re
from typing import Any, Iterable

MAX_SUSPECTS = 32
MAX_INTERFERERS = 4
_INT_RE = re.compile(r"[+-]?\d+")


class ValidationError(ValueError):
    """Raised when the supplied case is not representable as integer Hz data."""

    def __init__(self, message: str, issues: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.issues = issues or []


class NoSolutionError(ValueError):
    """Raised when a supplemental table leaves no consistent combination."""

    def __init__(self, message: str, original_result: dict[str, Any]):
        super().__init__(message)
        self.message = message
        self.original_result = original_result


def coerce_int(value: Any, field: str, *, minimum: int | None = None) -> int:
    """Convert an API value to a strict integer Hz value.

    Booleans and non-integral floats are rejected. Integer strings are accepted
    because HTML forms commonly submit all values as strings.
    """

    if isinstance(value, bool):
        raise ValidationError(f"{field} 必须是整数 Hz，不能是布尔值")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and _INT_RE.fullmatch(value.strip()):
        number = int(value.strip())
    else:
        raise ValidationError(f"{field} 必须是整数 Hz，收到：{value!r}")

    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} 必须不小于 {minimum} Hz，收到 {number}")
    return number


def _parse_frequency_list(value: Any, field: str, issues: list[dict[str, Any]]) -> list[int]:
    if not isinstance(value, list):
        issues.append({"field": field, "message": "必须是整数 Hz 数组"})
        return []
    if len(value) > MAX_SUSPECTS:
        issues.append(
            {
                "field": field,
                "message": f"最多输入 {MAX_SUSPECTS} 个疑似频率，当前有 {len(value)} 个",
            }
        )

    frequencies: list[int] = []
    for index, item in enumerate(value[:MAX_SUSPECTS]):
        try:
            # 0 Hz is retained as the DC endpoint of the folding range.
            frequencies.append(coerce_int(item, f"{field}[{index}]", minimum=0))
        except ValidationError as exc:
            issues.append({"field": f"{field}[{index}]", "message": exc.message})
    return frequencies


def normalize_case(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a diagnosis payload.

    Returned peak lists and frequency lists are sorted and de-duplicated.
    Duplicate input values produce warnings rather than changing the physical
    interpretation of a peak table.
    """

    if not isinstance(payload, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    raw_suspects = payload.get("suspects", payload.get("suspected_frequencies", []))
    suspects = _parse_frequency_list(raw_suspects, "suspects", issues)
    seen: set[int] = set()
    unique_suspects: list[int] = []
    for frequency in suspects:
        if frequency in seen:
            warnings.append({"field": "suspects", "message": f"重复疑似频率 {frequency} Hz 已去重"})
        else:
            seen.add(frequency)
            unique_suspects.append(frequency)
    unique_suspects.sort()

    raw_observations = payload.get("observations", payload.get("measured_gears", []))
    if raw_observations is None:
        raw_observations = []
    if not isinstance(raw_observations, list):
        issues.append({"field": "observations", "message": "必须是观测档位数组"})
        raw_observations = []

    observations: list[dict[str, Any]] = []
    for obs_index, raw_obs in enumerate(raw_observations):
        field = f"observations[{obs_index}]"
        if not isinstance(raw_obs, dict):
            issues.append({"field": field, "message": "每个观测档位必须是对象"})
            continue

        try:
            sample_rate = coerce_int(
                raw_obs.get("sample_rate", raw_obs.get("rate")),
                f"{field}.sample_rate",
                minimum=1,
            )
        except ValidationError as exc:
            issues.append({"field": f"{field}.sample_rate", "message": exc.message})
            continue

        raw_peaks = raw_obs.get("peaks", raw_obs.get("peak_table", []))
        if not isinstance(raw_peaks, list):
            issues.append({"field": f"{field}.peaks", "message": "峰表必须是整数 Hz 数组"})
            continue

        peaks: list[int] = []
        peak_seen: set[int] = set()
        valid = True
        for peak_index, raw_peak in enumerate(raw_peaks):
            peak_field = f"{field}.peaks[{peak_index}]"
            try:
                peak = coerce_int(raw_peak, peak_field, minimum=0)
            except ValidationError as exc:
                issues.append({"field": peak_field, "message": exc.message})
                valid = False
                continue

            if 2 * peak > sample_rate:
                issues.append(
                    {
                        "field": peak_field,
                        "message": (
                            f"峰 {peak} Hz 超出采样率 {sample_rate} Hz 的 "
                            f"0～{sample_rate / 2:g} Hz 范围"
                        ),
                    }
                )
                valid = False
                continue

            if peak in peak_seen:
                warnings.append(
                    {
                        "field": f"{field}.peaks",
                        "message": f"采样率 {sample_rate} Hz 的重复峰 {peak} Hz 已按一个峰处理",
                    }
                )
            else:
                peak_seen.add(peak)
                peaks.append(peak)

        if valid:
            observations.append({"sample_rate": sample_rate, "peaks": sorted(peaks)})

    raw_rates = payload.get("available_rates", payload.get("retest_rates", []))
    if raw_rates is None:
        raw_rates = []
    if not isinstance(raw_rates, list):
        issues.append({"field": "available_rates", "message": "必须是可用采样率整数数组"})
        raw_rates = []

    available_rates: list[int] = []
    for index, raw_rate in enumerate(raw_rates):
        try:
            available_rates.append(
                coerce_int(raw_rate, f"available_rates[{index}]", minimum=1)
            )
        except ValidationError as exc:
            issues.append({"field": f"available_rates[{index}]", "message": exc.message})

    if issues:
        raise ValidationError("输入校验失败", issues)

    return {
        "suspects": unique_suspects,
        "observations": observations,
        "available_rates": sorted(set(available_rates)),
        "warnings": warnings,
    }


def alias_frequency(frequency: int, sample_rate: int) -> int:
    """Fold an absolute Hz frequency into ``[0, sample_rate / 2]``.

    For a sampled real signal the observed alias is the distance to the
    nearest integer multiple of the sample rate.  That distance is always at
    most the Nyquist frequency.
    """

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    remainder = frequency % sample_rate
    return min(remainder, sample_rate - remainder)


def fold_frequencies(frequencies: Iterable[int], sample_rate: int) -> list[int]:
    """Fold frequencies and collapse coincident aliases to one peak."""

    return sorted({alias_frequency(f, sample_rate) for f in frequencies})


def _candidate_matches(
    combo: tuple[int, ...],
    observations: list[dict[str, Any]],
    alias_maps: list[dict[int, int]],
) -> list[dict[str, Any]] | None:
    tables: list[dict[str, Any]] = []
    for observation, alias_map in zip(observations, alias_maps):
        folded = sorted({alias_map[frequency] for frequency in combo})
        if folded != observation["peaks"]:
            return None
        tables.append({"sample_rate": observation["sample_rate"], "peaks": folded})
    return tables


def find_candidates(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Enumerate all 1–4 frequency combinations matching every observation."""

    suspects: list[int] = case["suspects"]
    observations: list[dict[str, Any]] = case["observations"]

    # A combination has at most four source frequencies and therefore at most
    # four distinct peaks, even before alias collisions are considered.
    if any(len(obs["peaks"]) > MAX_INTERFERERS for obs in observations):
        return []

    alias_maps = [
        {frequency: alias_frequency(frequency, obs["sample_rate"]) for frequency in suspects}
        for obs in observations
    ]

    candidates: list[dict[str, Any]] = []
    max_size = min(MAX_INTERFERERS, len(suspects))
    for size in range(1, max_size + 1):
        for combo in combinations(suspects, size):
            tables = _candidate_matches(combo, observations, alias_maps)
            if tables is not None:
                candidates.append(
                    {
                        "frequencies": list(combo),
                        "size": size,
                        "folded_tables": tables,
                    }
                )
    return candidates


def _gear_report(
    sample_rate: int,
    candidates: list[dict[str, Any]],
    *,
    collision_examples: int = 3,
) -> dict[str, Any]:
    buckets: dict[tuple[int, ...], list[list[int]]] = {}
    for candidate in candidates:
        peaks = tuple(fold_frequencies(candidate["frequencies"], sample_rate))
        buckets.setdefault(peaks, []).append(candidate["frequencies"])

    collisions = [
        {"peaks": list(peaks), "candidates": groups}
        for peaks, groups in buckets.items()
        if len(groups) > 1
    ]
    report: dict[str, Any] = {
        "sample_rate": sample_rate,
        "candidate_count": len(candidates),
        "distinct_table_count": len(buckets),
        "distinguishes_all": len(buckets) == len(candidates),
        "collision_group_count": len(collisions),
        "largest_collision_group_size": max(
            (len(item["candidates"]) for item in collisions), default=1
        ),
    }
    if collisions:
        report["sample_collisions"] = [
            {
                "peaks": item["peaks"],
                "candidate_count": len(item["candidates"]),
                "candidates": item["candidates"][:collision_examples],
                "has_more_candidates": len(item["candidates"]) > collision_examples,
            }
            for item in collisions[:collision_examples]
        ]
        report["has_more_collision_groups"] = len(collisions) > collision_examples
    return report


def recommend_rate(
    candidates: list[dict[str, Any]],
    available_rates: list[int],
) -> dict[str, Any]:
    """Find the lowest gear whose folded table is unique for every combination."""

    if not candidates:
        return {
            "status": "no_candidates",
            "message": "当前没有与全部实测峰表一致的候选组合，无法推荐复测档位。",
        }

    if len(candidates) == 1:
        candidate = candidates[0]["frequencies"]
        return {
            "status": "already_unique",
            "sample_rate": None,
            "message": f"候选组合已唯一：{candidate} Hz，无需再次测量。",
        }

    gear_reports = [_gear_report(rate, candidates) for rate in sorted(set(available_rates))]
    suitable = next((report for report in gear_reports if report["distinguishes_all"]), None)

    if suitable is None:
        if not available_rates:
            message = "未提供可用复测档位；当前仍有多个候选组合，无法给出一次测量分辨方案。"
            reason = "no_available_rates"
        else:
            message = (
                "所有可用档位都会让至少两个候选组合折成同一张峰表，"
                "没有能用一次测量分清全部组合的档位。"
            )
            reason = "all_gears_collide"
        return {
            "status": "no_suitable_gear",
            "reason": reason,
            "sample_rate": None,
            "candidate_count": len(candidates),
            "gear_reports": gear_reports,
            "message": message,
        }

    sample_rate = suitable["sample_rate"]
    signatures = [
        {
            "frequencies": candidate["frequencies"],
            "expected_peaks": fold_frequencies(candidate["frequencies"], sample_rate),
        }
        for candidate in candidates
    ]
    return {
        "status": "recommended",
        "sample_rate": sample_rate,
        "candidate_count": len(candidates),
        "distinct_table_count": suitable["distinct_table_count"],
        "gear_reports": gear_reports,
        "signatures": signatures,
        "message": (
            f"推荐最低可用采样率 {sample_rate} Hz；"
            f"在该档位下 {len(candidates)} 个候选组合对应 {len(signatures)} 张不同峰表。"
        ),
    }


def analyze_case(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate input and produce the complete diagnosis/recommendation."""

    case = normalize_case(payload)
    candidates = find_candidates(case)

    result: dict[str, Any] = {
        "feasible": bool(candidates),
        "suspects": case["suspects"],
        "observations": case["observations"],
        "available_rates": case["available_rates"],
        "warnings": case["warnings"],
        "candidate_count": len(candidates),
        "candidates": candidates,
    }

    if not candidates:
        result.update(
            {
                "mandatory_frequencies": [],
                "possible_only_frequencies": [],
                "excluded_frequencies": [],
                "frequency_report": [
                    {"frequency": frequency, "status": "indeterminate", "candidate_count": 0}
                    for frequency in case["suspects"]
                ],
                "recommendation": recommend_rate([], case["available_rates"]),
                "summary": "无解：不存在由 1～4 个疑似频率组成且与全部实测峰表完全一致的组合。",
            }
        )
        return result

    occurrence = {frequency: 0 for frequency in case["suspects"]}
    for candidate in candidates:
        for frequency in candidate["frequencies"]:
            occurrence[frequency] += 1

    mandatory = [f for f, count in occurrence.items() if count == len(candidates)]
    possible_only = [f for f, count in occurrence.items() if 0 < count < len(candidates)]
    excluded = [f for f, count in occurrence.items() if count == 0]

    result.update(
        {
            "mandatory_frequencies": mandatory,
            "possible_only_frequencies": possible_only,
            "excluded_frequencies": excluded,
            "frequency_report": [
                {
                    "frequency": frequency,
                    "candidate_count": occurrence[frequency],
                    "status": (
                        "mandatory"
                        if occurrence[frequency] == len(candidates)
                        else "possible_only"
                        if occurrence[frequency] > 0
                        else "excluded"
                    ),
                }
                for frequency in case["suspects"]
            ],
            "recommendation": recommend_rate(candidates, case["available_rates"]),
        }
    )

    if len(candidates) == 1:
        result["summary"] = f"诊断唯一：干扰频率为 {candidates[0]['frequencies']} Hz。"
    else:
        result["summary"] = (
            f"找到 {len(candidates)} 个可行组合；必有 {len(mandatory)} 个频率，"
            f"仅可能有 {len(possible_only)} 个频率。"
        )
    return result


def supplement_observation(
    payload: dict[str, Any], new_observation: dict[str, Any]
) -> dict[str, Any]:
    """Append a supplemental table only if it retains at least one solution.

    The original diagnosis is returned inside :class:`NoSolutionError` when the
    proposed supplement would make the case inconsistent.  The input payload is
    not modified.
    """

    original_result = analyze_case(payload)

    trial_payload = deepcopy(payload)
    observations = trial_payload.setdefault("observations", [])
    if not isinstance(observations, list):
        # analyze_case will report this as a validation error; keep behavior
        # explicit rather than mutating an unexpected value.
        raise ValidationError("原 payload 的 observations 必须是数组")
    observations.append(new_observation)

    updated_result = analyze_case(trial_payload)
    if not updated_result["feasible"]:
        sample_rate = new_observation.get("sample_rate", new_observation.get("rate", "?"))
        raise NoSolutionError(
            f"采样率 {sample_rate} Hz 的补录峰表与此前实测矛盾；已拒绝补录，原诊断结果保留。",
            original_result,
        )

    updated_result["supplement_accepted"] = True
    return updated_result
