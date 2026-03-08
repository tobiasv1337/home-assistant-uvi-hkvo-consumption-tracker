"""Unit tests for API helpers."""

from __future__ import annotations

from custom_components.uvi.api import UviApiClient


def test_extract_csrf_token_from_meta_tag() -> None:
    html = '<html><head><meta name="csrf-token" content="abc123"></head></html>'
    assert UviApiClient._extract_csrf_token(html) == "abc123"


def test_extract_csrf_token_from_hidden_input() -> None:
    html = '<input type="hidden" name="authenticity_token" value="xyz987">'
    assert UviApiClient._extract_csrf_token(html) == "xyz987"


def test_extract_csrf_token_returns_none_when_missing() -> None:
    html = "<html><body>No token here</body></html>"
    assert UviApiClient._extract_csrf_token(html) is None


def test_extract_csrf_token_verbose_report(pytestconfig) -> None:
    """Optionally print CSRF extraction behavior in verbose mode."""
    if not getattr(pytestconfig, "uvi_verbose", False):
        return

    html_meta = '<meta name="csrf-token" content="meta-token">'
    html_hidden = '<input type="hidden" name="authenticity_token" value="hidden-token">'
    html_none = "<html><body>none</body></html>"

    print("\n=== UVI CSRF Extraction Report ===")
    print("meta:", UviApiClient._extract_csrf_token(html_meta))
    print("hidden:", UviApiClient._extract_csrf_token(html_hidden))
    print("none:", UviApiClient._extract_csrf_token(html_none))
