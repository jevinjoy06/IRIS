"""Web search tool backed by Tavily."""
import os


def search(query: str, max_results: int = 5) -> dict:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return {
            "ok": False,
            "error": "TAVILY_API_KEY not set — add it to hub/.env to enable web search",
        }
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=max_results)
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in response.get("results", [])
        ]
        return {"ok": True, "query": query, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}
