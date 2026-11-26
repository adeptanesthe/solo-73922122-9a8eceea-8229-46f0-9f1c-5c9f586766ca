import copy
import unittest

from diagnostics import (
    MAX_SUSPECTS,
    NoSolutionError,
    ValidationError,
    alias_frequency,
    analyze_case,
    fold_frequencies,
    supplement_observation,
)
from examples import EXAMPLE_CASE


class AliasTests(unittest.TestCase):
    def test_folds_to_zero_nyquist_range(self):
        self.assertEqual(alias_frequency(9400, 8000), 1400)
        self.assertEqual(alias_frequency(14000, 8000), 2000)
        self.assertEqual(alias_frequency(17400, 8000), 1400)
        self.assertEqual(alias_frequency(8000, 8000), 0)
        self.assertEqual(alias_frequency(4000, 8000), 4000)
        self.assertEqual(alias_frequency(12000, 8000), 4000)

    def test_fold_deduplicates_coincident_peaks(self):
        self.assertEqual(fold_frequencies([9400, 17400], 8000), [1400])
        self.assertEqual(fold_frequencies([3700, 11700, 19700], 8000), [3700])


class DiagnosisTests(unittest.TestCase):
    def test_built_in_example_has_three_candidates_and_labels(self):
        result = analyze_case(EXAMPLE_CASE)

        self.assertTrue(result["feasible"])
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(
            [c["frequencies"] for c in result["candidates"]],
            [
                [9400, 14000, 18300],
                [14000, 17400, 18300],
                [9400, 14000, 17400, 18300],
            ],
        )
        self.assertEqual(result["mandatory_frequencies"], [14000, 18300])
        self.assertEqual(result["possible_only_frequencies"], [9400, 17400])
        self.assertIn(1700, result["excluded_frequencies"])

    def test_recommends_lowest_discriminating_available_rate(self):
        result = analyze_case(EXAMPLE_CASE)
        recommendation = result["recommendation"]

        self.assertEqual(recommendation["status"], "recommended")
        self.assertEqual(recommendation["sample_rate"], 11025)
        signatures = {
            tuple(item["expected_peaks"]) for item in recommendation["signatures"]
        }
        self.assertEqual(len(signatures), result["candidate_count"])

    def test_no_suitable_gear_when_all_available_rates_collide(self):
        payload = copy.deepcopy(EXAMPLE_CASE)
        payload["available_rates"] = [8000]

        result = analyze_case(payload)
        recommendation = result["recommendation"]

        self.assertEqual(recommendation["status"], "no_suitable_gear")
        self.assertEqual(recommendation["sample_rate"], None)
        self.assertFalse(recommendation["gear_reports"][0]["distinguishes_all"])

    def test_valid_supplement_narrows_to_unique_combination(self):
        payload = copy.deepcopy(EXAMPLE_CASE)
        result = supplement_observation(payload, EXAMPLE_CASE["suggested_observation"])

        self.assertTrue(result["supplement_accepted"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["candidates"][0]["frequencies"],
            EXAMPLE_CASE["actual_frequencies"],
        )
        self.assertEqual(result["recommendation"]["status"], "already_unique")

    def test_conflicting_supplement_is_rejected_with_original_result(self):
        payload = copy.deepcopy(EXAMPLE_CASE)
        original_payload = copy.deepcopy(payload)

        with self.assertRaises(NoSolutionError) as context:
            supplement_observation(payload, EXAMPLE_CASE["invalid_observation"])

        self.assertEqual(context.exception.original_result["candidate_count"], 3)
        self.assertEqual(payload, original_payload)

    def test_inconsistent_initial_table_is_infeasible(self):
        payload = {
            "suspects": [1000, 2000, 3000],
            "observations": [{"sample_rate": 8000, "peaks": [777]}],
            "available_rates": [16000],
        }
        result = analyze_case(payload)
        self.assertFalse(result["feasible"])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["recommendation"]["status"], "no_candidates")

    def test_enumerates_all_combinations_up_to_four(self):
        payload = {
            "suspects": list(range(100, 100 + MAX_SUSPECTS * 100, 100)),
            "observations": [],
            "available_rates": [],
        }
        result = analyze_case(payload)
        # C(32,1) + C(32,2) + C(32,3) + C(32,4)
        self.assertEqual(result["candidate_count"], 41448)

    def test_rejects_too_many_suspects(self):
        payload = {"suspects": list(range(1, 34)), "observations": []}
        with self.assertRaises(ValidationError) as context:
            analyze_case(payload)
        self.assertTrue(any("最多" in issue["message"] for issue in context.exception.issues))

    def test_rejects_peak_above_nyquist_and_non_integer(self):
        with self.assertRaises(ValidationError):
            analyze_case(
                {
                    "suspects": [1000],
                    "observations": [{"sample_rate": 8000, "peaks": [4001]}],
                }
            )

        with self.assertRaises(ValidationError):
            analyze_case(
                {
                    "suspects": [1000.5],
                    "observations": [],
                }
            )

        # Zero is the DC endpoint of the 0-to-Nyquist folding range.
        result = analyze_case({"suspects": [0, 1000], "observations": [], "available_rates": []})
        self.assertEqual(result["suspects"], [0, 1000])


if __name__ == "__main__":
    unittest.main()
