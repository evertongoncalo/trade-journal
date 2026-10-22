import pytest

from app import config


@pytest.fixture(autouse=True)
def _no_background_watcher(monkeypatch):
    """Os testes nunca ligam a vigilância de alertas em segundo plano (rede e notificações reais)."""
    monkeypatch.setattr(config, "ALERTS_WATCHER", False)
