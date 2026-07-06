"""Tests for Phase 0.5 infrastructure: health endpoint used by health check script."""


from src.app import create_app


class TestHealthEndpoint:
    """Test /health endpoint for health check script and alerting."""

    def test_health_returns_200_and_ok(self, test_db):
        """GET /health returns 200 and {\"status\": \"ok\"}."""
        app = create_app()
        client = app.test_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"status": "ok"}
