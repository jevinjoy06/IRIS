"""Tests for hub/tools/web_search.py."""
from unittest.mock import MagicMock, patch

from hub.tools import web_search


class TestWebSearch:
    def test_no_api_key_returns_clear_error(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = web_search.search("python tutorials")
        assert result["ok"] is False
        assert "TAVILY_API_KEY" in result["error"]

    def test_empty_api_key_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "")
        result = web_search.search("anything")
        assert result["ok"] is False

    def test_success_shapes_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {
            "results": [
                {"title": "A", "url": "https://a.example", "content": "snippet a"},
                {"title": "B", "url": "https://b.example", "content": "snippet b"},
            ]
        }
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("query", max_results=2)
        assert result["ok"] is True
        assert result["query"] == "query"
        assert result["results"] == [
            {"title": "A", "url": "https://a.example", "snippet": "snippet a"},
            {"title": "B", "url": "https://b.example", "snippet": "snippet b"},
        ]
        fake_client.search.assert_called_once_with("query", max_results=2)

    def test_missing_fields_in_raw_result_default_to_empty_string(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {"results": [{}]}
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("query")
        assert result["ok"] is True
        assert result["results"] == [{"title": "", "url": "", "snippet": ""}]

    def test_empty_results_list(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {"results": []}
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("query with no hits")
        assert result == {"ok": True, "query": "query with no hits", "results": []}

    def test_missing_results_key_entirely(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {}
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("query")
        assert result["ok"] is True
        assert result["results"] == []

    def test_network_exception_is_caught_and_reported(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.side_effect = ConnectionError("network unreachable")
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("query")
        assert result["ok"] is False
        assert "network unreachable" in result["error"]

    def test_empty_query_string_still_dispatched(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {"results": []}
        with patch("tavily.TavilyClient", return_value=fake_client):
            result = web_search.search("")
        assert result["ok"] is True
        fake_client.search.assert_called_once_with("", max_results=5)

    def test_default_max_results_is_5(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
        fake_client = MagicMock()
        fake_client.search.return_value = {"results": []}
        with patch("tavily.TavilyClient", return_value=fake_client):
            web_search.search("query")
        fake_client.search.assert_called_once_with("query", max_results=5)
