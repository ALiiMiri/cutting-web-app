import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ServiceResilienceTests(unittest.TestCase):
    def test_health_endpoint_is_public_and_lightweight(self):
        from cutting_web_app import app

        response = app.test_client().get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_gunicorn_uses_timeout_enforced_process_workers(self):
        service = (ROOT / "deploy" / "cutting-web-app.service").read_text(
            encoding="utf-8"
        )

        self.assertIn("--workers 4", service)
        self.assertIn("--worker-class sync", service)
        self.assertIn("--timeout 120", service)
        self.assertIn("--max-requests 500", service)
        self.assertNotIn("--threads", service)

    def test_health_monitor_restarts_active_but_unresponsive_service(self):
        script = (ROOT / "deploy" / "check-cutting-web-health.sh").read_text(
            encoding="utf-8"
        )
        timer = (ROOT / "deploy" / "cutting-web-healthcheck.timer").read_text(
            encoding="utf-8"
        )

        self.assertIn("curl --fail", script)
        self.assertIn('systemctl restart "$SERVICE"', script)
        self.assertIn("OnUnitActiveSec=1min", timer)


if __name__ == "__main__":
    unittest.main()
