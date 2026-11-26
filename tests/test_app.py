import unittest

try:
    import flask  # noqa: F401

    from app import app
    from examples import EXAMPLE_CASE
except ModuleNotFoundError:  # pragma: no cover
    flask = None


@unittest.skipIf(flask is None, "Flask is not installed")
class FlaskApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_and_health(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("干扰峰".encode(), response.data)

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "ok"})

    def test_example_endpoint(self):
        response = self.client.get("/api/example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["id"], EXAMPLE_CASE["id"])

    def test_analyze_example_api(self):
        response = self.client.post("/api/analyze", json=EXAMPLE_CASE)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["candidate_count"], 3)
        self.assertEqual(data["recommendation"]["sample_rate"], 11025)

    def test_valid_supplement_api(self):
        response = self.client.post(
            "/api/supplement",
            json={
                **EXAMPLE_CASE,
                "new_observation": EXAMPLE_CASE["suggested_observation"],
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["supplement_accepted"])
        self.assertEqual(data["candidate_count"], 1)

    def test_conflicting_supplement_returns_409_and_original(self):
        response = self.client.post(
            "/api/supplement",
            json={
                **EXAMPLE_CASE,
                "new_observation": EXAMPLE_CASE["invalid_observation"],
            },
        )
        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertFalse(data["accepted"])
        self.assertEqual(data["original"]["candidate_count"], 3)

    def test_validation_error_api(self):
        response = self.client.post("/api/analyze", json={"suspects": list(range(33))})
        self.assertEqual(response.status_code, 400)
        self.assertIn("issues", response.get_json())


if __name__ == "__main__":
    unittest.main()
