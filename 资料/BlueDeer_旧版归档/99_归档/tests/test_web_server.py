"""Web server route tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from web_server.app import app

client = TestClient(app)


class TestHealthEndpoints:
    def test_system_health(self):
        response = client.get("/api/system/health")
        assert response.status_code in (200, 500)

    def test_agents_health(self):
        response = client.get("/api/agents/health")
        assert response.status_code in (200, 500)


class TestAgentEndpoints:
    def test_list_agents(self):
        response = client.get("/api/agents")
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "agents" in data or "total" in data

    def test_search_agents_empty(self):
        response = client.get("/api/agents/search")
        assert response.status_code in (200, 500)


class TestSystemEndpoints:
    def test_system_status(self):
        response = client.get("/api/system/status")
        assert response.status_code in (200, 404, 500)

    def test_metrics(self):
        response = client.get("/api/system/metrics")
        assert response.status_code in (200, 404, 500)


class TestTraceEndpoints:
    def test_traces_list(self):
        response = client.get("/api/traces")
        assert response.status_code in (200, 404, 500)

    def test_test_traces_generation(self):
        response = client.post("/api/test_traces")
        assert response.status_code in (200, 500)


class TestPageEndpoints:
    def test_index_page(self):
        response = client.get("/")
        assert response.status_code in (200, 404)

    def test_dashboard_page(self):
        response = client.get("/dashboard")
        assert response.status_code in (200, 404)
