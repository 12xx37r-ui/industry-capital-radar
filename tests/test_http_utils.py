import unittest

from src.http_utils import redact_url


class HttpUtilsTests(unittest.TestCase):
    def test_redacts_api_key(self):
        url = "https://example.com/api?apiKey=secret-value&format=json"
        safe = redact_url(url)
        self.assertNotIn("secret-value", safe)
        self.assertIn("apiKey=%2A%2A%2A", safe)
        self.assertIn("format=json", safe)


if __name__ == "__main__":
    unittest.main()
