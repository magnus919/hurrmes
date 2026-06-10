"""Tests for hurrmes.client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from hurrmes.client import HermesClient
from hurrmes.config import Config


@pytest.fixture
def client() -> HermesClient:
    """Create a HermesClient with default config for testing."""
    cfg = Config()
    cfg.server.host = "127.0.0.1"
    cfg.server.port = 8642
    return HermesClient(cfg)


def _mock_async_client() -> AsyncMock:
    """Build an AsyncMock for httpx.AsyncClient with proper async context manager wiring."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.__aenter__.return_value = mock_client
    return mock_client


class _StreamContextManager:
    """Helper: async context manager for mocking httpx client.stream()."""

    def __init__(self, response: MagicMock) -> None:
        self._response = response

    async def __aenter__(self) -> MagicMock:
        return self._response

    async def __aexit__(self, *args: object) -> None:
        pass


class TestHermesClient:
    """Tests for HermesClient."""

    def test_initialization(self, client: HermesClient) -> None:
        """Client should initialize with config values."""
        assert client.base_url == "http://127.0.0.1:8642"
        assert client.session_id is None

    def test_headers_no_auth(self, client: HermesClient) -> None:
        """Headers should not include Authorization when no API key."""
        headers = client._headers()
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    def test_headers_with_auth(self) -> None:
        """Headers should include Bearer token when API key is set."""
        cfg = Config()
        cfg.server.api_key = "test-key"
        c = HermesClient(cfg)
        headers = c._headers()
        assert headers["Authorization"] == "Bearer test-key"

    def test_headers_with_session(self, client: HermesClient) -> None:
        """Headers should include session ID when set."""
        client.session_id = "sess-123"
        headers = client._headers()
        assert headers["X-Hermes-Session-Id"] == "sess-123"

    @pytest.mark.asyncio
    async def test_chat_stream_connect_error(self, client: HermesClient) -> None:
        """Chat stream should yield error on connection failure."""
        results = []
        mock_client = _mock_async_client()
        mock_client.stream.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        assert len(results) == 1
        assert results[0]["type"] == "error"
        assert "Cannot connect" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_chat_stream_timeout_error(self, client: HermesClient) -> None:
        """Chat stream should yield error on timeout."""
        results = []
        mock_client = _mock_async_client()
        mock_client.stream.side_effect = httpx.TimeoutException("Request timed out")

        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        assert len(results) == 1
        assert results[0]["type"] == "error"

    def test_session_id_property(self, client: HermesClient) -> None:
        """Session ID should be gettable/settable."""
        assert client.session_id is None
        client.session_id = "sess-456"
        assert client.session_id == "sess-456"

    @pytest.mark.asyncio
    async def test_chat_error_response(self, client: HermesClient) -> None:
        """chat() should return error dict on HTTP error."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat([{"role": "user", "content": "hello"}])
            assert "error" in result

    @pytest.mark.asyncio
    async def test_session_id_from_response_headers(self, client: HermesClient) -> None:
        """Session ID should be extracted from response headers."""
        mock_client = _mock_async_client()

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"X-Hermes-Session-Id": "sess-789"}

        async def mock_aiter_lines():
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines

        mock_client.stream = MagicMock(return_value=_StreamContextManager(mock_response))

        with patch("httpx.AsyncClient", return_value=mock_client):
            async for _ in client.chat_stream([{"role": "user", "content": "hello"}]):
                pass
            assert client.session_id == "sess-789"

    @pytest.mark.asyncio
    async def test_chat_stream_http_error(self, client: HermesClient) -> None:
        """Chat stream should yield error on non-200 HTTP response."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b"Unauthorized")

        mock_client.stream = MagicMock(return_value=_StreamContextManager(mock_response))

        results = []
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        assert len(results) == 1
        assert results[0]["type"] == "error"
        assert "401" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_chat_stream_with_delta_and_usage(self, client: HermesClient) -> None:
        """Chat stream should yield delta events and final usage."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}

        async def mock_aiter_lines():
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: {"choices":[{"delta":{"content":" world"}}]}'
            yield 'data: {"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}'
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines
        mock_client.stream = MagicMock(return_value=_StreamContextManager(mock_response))

        results = []
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        assert len(results) == 3
        assert results[0] == {"type": "delta", "content": "Hello"}
        assert results[1] == {"type": "delta", "content": " world"}
        assert results[2]["type"] == "done"
        assert results[2]["usage"]["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_chat_stream_json_decode_skips_bad_data(self, client: HermesClient) -> None:
        """Chat stream should skip lines with invalid JSON."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}

        async def mock_aiter_lines():
            yield "data: {invalid json}"
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines
        mock_client.stream = MagicMock(return_value=_StreamContextManager(mock_response))

        results = []
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        # Only the done event, no delta (bad JSON was skipped)
        assert len(results) == 1
        assert results[0]["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_stream_skips_non_data_lines(self, client: HermesClient) -> None:
        """Chat stream should skip lines not starting with 'data:'."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {}

        async def mock_aiter_lines():
            yield ": keep-alive comment"
            yield "data: [DONE]"

        mock_response.aiter_lines = mock_aiter_lines
        mock_client.stream = MagicMock(return_value=_StreamContextManager(mock_response))

        results = []
        with patch("httpx.AsyncClient", return_value=mock_client):
            async for event in client.chat_stream([{"role": "user", "content": "hello"}]):
                results.append(event)

        assert len(results) == 1
        assert results[0]["type"] == "done"

    @pytest.mark.asyncio
    async def test_chat_connect_error(self, client: HermesClient) -> None:
        """chat() should return error dict on connection error."""
        mock_client = _mock_async_client()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat([{"role": "user", "content": "hello"}])
            assert "error" in result
            assert "Cannot connect" in result["error"]

    @pytest.mark.asyncio
    async def test_chat_http_200_success(self, client: HermesClient) -> None:
        """chat() should return JSON data on 200 with session ID."""
        mock_client = _mock_async_client()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        mock_response.headers = {"X-Hermes-Session-Id": "sess-999"}
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat([{"role": "user", "content": "hello"}])
            assert result == {"choices": [{"message": {"content": "Hello"}}]}
            assert client.session_id == "sess-999"
