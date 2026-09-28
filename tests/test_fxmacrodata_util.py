import importlib.util
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _load_util_func_module():
    path = Path(__file__).parents[1] / "quanttrader" / "util" / "util_func.py"
    spec = importlib.util.spec_from_file_location("quanttrader_util_func", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFXMacroDataUtil(unittest.TestCase):

    def test_read_fxmacrodata_ohlcv(self):
        util_func = _load_util_func_module()

        class MockResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {"date": "2026-01-02", "val": 1.2},
                            {"date": "2026-01-01", "val": 1.1},
                        ]
                    }
                ).encode("utf-8")

        calls = {}

        def mock_urlopen(request, timeout):
            calls["url"] = request.full_url
            calls["api_key"] = request.get_header("X-api-key")
            calls["timeout"] = timeout
            return MockResponse()

        original_urlopen = util_func.urlopen
        try:
            util_func.urlopen = mock_urlopen
            df = util_func.read_fxmacrodata_ohlcv(
                "EUR/USD",
                "2026-01-01",
                "2026-01-02",
                api_key="test-key",
                api_root="https://example.test/api/v1",
            )
        finally:
            util_func.urlopen = original_urlopen

        parsed = urlparse(calls["url"])
        params = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/api/v1/forex/EUR/USD")
        self.assertNotIn("api_key", params)
        self.assertEqual(calls["api_key"], "test-key")
        self.assertEqual(list(df["Close"]), [1.1, 1.2])
        self.assertEqual(list(df.columns), ["Open", "High", "Low", "Close", "Volume"])

    def test_read_fxmacrodata_ohlcv_pages(self):
        util_func = _load_util_func_module()
        pages = {
            0: {
                "data": [
                    {"date": "2026-01-04", "val": 1.4},
                    {"date": "2026-01-03", "val": 1.3},
                ],
                "pagination": {"has_more": True, "next_offset": 2},
            },
            2: {
                "data": [
                    {"date": "2026-01-02", "val": 1.2},
                    {"date": "2026-01-01", "val": 1.1},
                ],
                "pagination": {"has_more": False, "next_offset": None},
            },
        }
        offsets = []

        class MockResponse:
            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.body).encode("utf-8")

        def mock_urlopen(request, timeout):
            params = parse_qs(urlparse(request.full_url).query)
            self.assertEqual(params["limit"], ["100"])
            self.assertEqual(timeout, 30)
            offset = int(params["offset"][0])
            offsets.append(offset)
            return MockResponse(pages[offset])

        original_urlopen = util_func.urlopen
        try:
            util_func.urlopen = mock_urlopen
            df = util_func.read_fxmacrodata_ohlcv("EURUSD", "2026-01-01", "2026-01-04")
        finally:
            util_func.urlopen = original_urlopen

        self.assertEqual(offsets, [0, 2])
        self.assertEqual(list(df["Close"]), [1.1, 1.2, 1.3, 1.4])


if __name__ == "__main__":
    unittest.main()
