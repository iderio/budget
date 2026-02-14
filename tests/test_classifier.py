import unittest

from app.classifier import _normalize_label

from fastapi.testclient import TestClient

from app.main import app


class ApiRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_root_page_is_available(self) -> None:
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('LLM Classification API', response.text)

    def test_index_html_page_is_available(self) -> None:
        response = self.client.get('/index.html')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Interactive API docs', response.text)


    def test_tracker_route_is_available(self) -> None:
        response = self.client.get('/tracker/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Receipt Budget Tracker', response.text)


class ClassifierTests(unittest.TestCase):
    def test_normalize_label_exact_match(self) -> None:
        labels = ["malicious", "suspicious", "benign", "unknown"]
        self.assertEqual(_normalize_label("Benign", labels), "benign")

    def test_normalize_label_unknown(self) -> None:
        labels = ["a", "b"]
        self.assertEqual(_normalize_label("c", labels), "unknown")


if __name__ == "__main__":
    unittest.main()
