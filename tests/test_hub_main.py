from pathlib import Path

HUB_MAIN = Path(__file__).resolve().parents[1] / "hub" / "__main__.py"


def test_hub_host_default_is_loopback_not_wildcard():
    # Importing hub.__main__ calls uvicorn.run at module scope, so check the source instead.
    source = HUB_MAIN.read_text(encoding="utf-8")
    assert 'os.environ.get("HUB_HOST", "127.0.0.1")' in source
    assert '"0.0.0.0"' not in source
