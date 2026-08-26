"""OpenAI 兼容 API Provider 测试（不发真实网络请求）。"""

import unittest
from unittest import mock

from bluedeer.providers import OpenAIProvider, get_provider


class ProviderFactoryTest(unittest.TestCase):
    def test_openai_factory(self):
        p = get_provider("openai", api_base="https://x.com/v1", api_key="kk", api_model="m-1")
        self.assertIsInstance(p, OpenAIProvider)
        self.assertEqual(p.api_base, "https://x.com/v1")
        self.assertEqual(p.api_key, "kk")
        self.assertEqual(p.model, "m-1")

    def test_no_base_errors_cleanly(self):
        p = OpenAIProvider(api_base="", api_key="kk", model="m")
        out = p.generate("hi", system="s")
        self.assertIn("api_base", out)


class GenerateTest(unittest.TestCase):
    def _mock_urlopen(self, captured, body=b'{"choices":[{"message":{"content":"hello"}}]}'):
        resp = mock.Mock()
        resp.read.return_value = body
        resp.__enter__ = mock.Mock(return_value=resp)
        resp.__exit__ = mock.Mock(return_value=False)

        def side_effect(req, timeout=None):
            captured.append(req)
            return resp

        return mock.patch("bluedeer.providers.urllib.request.urlopen", side_effect=side_effect)

    def test_generate_parses_choices(self):
        p = OpenAIProvider(api_base="http://fake/v1", api_key="kk", model="m")
        captured = []
        with self._mock_urlopen(captured) as _:
            out = p.generate("你好", system="你是小鹿")
        self.assertEqual(out, "hello")

    def test_request_shape(self):
        p = OpenAIProvider(api_base="http://fake/v1/", api_key="kk", model="m")
        captured = []
        with self._mock_urlopen(captured) as _:
            p.generate("hi", system="sys")
        req = captured[0]
        self.assertTrue(req.full_url.startswith("http://fake/v1/chat/completions"))
        self.assertEqual(req.headers.get("Authorization"), "Bearer kk")


if __name__ == "__main__":
    unittest.main()
