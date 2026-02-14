import unittest

from app.classifier import _normalize_label


class ClassifierTests(unittest.TestCase):
    def test_normalize_label_exact_match(self) -> None:
        labels = ["malicious", "suspicious", "benign", "unknown"]
        self.assertEqual(_normalize_label("Benign", labels), "benign")

    def test_normalize_label_unknown(self) -> None:
        labels = ["a", "b"]
        self.assertEqual(_normalize_label("c", labels), "unknown")


if __name__ == "__main__":
    unittest.main()
