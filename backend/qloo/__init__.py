"""Qloo Taste AI client package.

Run the app with backend/ as the working directory so top-level modules
(config, models) import cleanly.
"""
from config import settings

from .client import QlooClient, QlooError
from .mock import MockQlooClient

__all__ = ["QlooClient", "QlooError", "MockQlooClient", "get_qloo_client"]


def get_qloo_client(**kwargs):
    """Return the real client when a key is configured, else the synthetic mock.

    Lets the whole pipeline run before the hackathon key arrives. USE_MOCK_QLOO=1
    forces the mock even when a key is present.
    """
    if settings.use_mock_qloo or not settings.qloo_api_key:
        return MockQlooClient(**kwargs)
    return QlooClient(**kwargs)
