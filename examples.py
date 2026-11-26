"""Built-in integer-Hz case used by the web demonstration."""

from __future__ import annotations

# The true demo source set is [9400, 14000, 17400, 18300] Hz.
# At 8000 Hz, 9400 and 17400 both alias to 1400 Hz, producing the complete
# three-peak table [1400, 2000, 2300]. Two smaller combinations and the full
# four-frequency combination all match that table. 11025 Hz gives each candidate
# a distinct folded table.
EXAMPLE_CASE = {
    "id": "alias-shift-demo",
    "title": "采样率更换后的窄带峰混叠示例",
    "description": (
        "8000 Hz 档位测得 [1400, 2000, 2300] Hz 三个峰；"
        "9400 与 17400 Hz 在该档位重合。仍有多个候选组合时，"
        "可用补录表单载入 11025 Hz 的演示峰表并观察诊断收敛。"
    ),
    "suspects": [1700, 3900, 9400, 11200, 14000, 14700, 17400, 18300],
    "observations": [
        {"sample_rate": 8000, "peaks": [1400, 2000, 2300]},
    ],
    "available_rates": [11025, 12000, 16000, 22050, 48000],
    "actual_frequencies": [9400, 14000, 17400, 18300],
    "suggested_observation": {
        "sample_rate": 11025,
        "peaks": [1625, 2975, 3750, 4650],
        "label": "有效演示峰表：提交后应唯一确定四频组合",
    },
    "invalid_observation": {
        "sample_rate": 11025,
        "peaks": [1000, 2000, 3000],
        "label": "矛盾演示峰表：提交应被拒绝并保留原诊断",
    },
}
