import pytest


@pytest.fixture(autouse=True)
def _no_network_models(monkeypatch):
    # Keep tests offline: the idea engine only runs with a GitHub token.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
