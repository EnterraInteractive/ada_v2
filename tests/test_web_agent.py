"""Unit tests for the Playwright browser controller."""
import asyncio

import pytest

from web_agent import WebAgent


def test_browser_controller_initializes_without_cloud_model():
    agent = WebAgent()
    assert agent.browser is None
    assert agent.page is None
    assert agent.context is None


def test_non_http_urls_are_rejected_before_launch():
    agent = WebAgent()
    with pytest.raises(ValueError):
        agent.normalize_url("file:///C:/Windows/win.ini")


def test_missing_scheme_defaults_to_https_validation():
    agent = WebAgent()
    with pytest.raises(Exception):
        agent.normalize_url("http://")


def test_local_development_server_address_is_normalized_to_http():
    assert WebAgent.normalize_url("localhost:3000") == "http://localhost:3000"
    assert WebAgent.normalize_url("127.0.0.1:8000/api") == "http://127.0.0.1:8000/api"
