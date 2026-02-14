import importlib.util
import unittest
from unittest.mock import Mock, patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_FILE = ROOT / "app.py"
spec = importlib.util.spec_from_file_location("receipt_tracker_app", APP_FILE)
receipt_tracker_app = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(receipt_tracker_app)
parse_line_items = receipt_tracker_app.parse_line_items


class ReceiptParserTests(unittest.TestCase):
    def test_parses_line_items_when_trailing_marker_exists(self) -> None:
        text = "BANANAS 5.48 X"
        self.assertEqual(parse_line_items(text), [{"name": "BANANAS", "amount": 5.48}])

    def test_fallback_pipe_fragment_parsing(self) -> None:
        text = "Walmart | BANANAS 5.48 | 15:38 | MILK 6.97 X"
        self.assertEqual(
            parse_line_items(text),
            [
                {"name": "BANANAS", "amount": 5.48},
                {"name": "MILK", "amount": 6.97},
            ],
        )


class OpenAiReceiptParserTests(unittest.TestCase):
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False)
    @patch.object(receipt_tracker_app.requests, "post")
    def test_parse_line_items_with_openai(self, post_mock: Mock) -> None:
        post_mock.return_value = Mock(
            raise_for_status=Mock(),
            json=Mock(return_value={
                "output_text": '{"items":[{"name":"BANANAS","amount":5.48}]}'
            }),
        )

        items = receipt_tracker_app.parse_line_items_with_openai(APP_FILE)

        self.assertEqual(items, [{"name": "BANANAS", "amount": 5.48}])
        self.assertTrue(post_mock.called)


if __name__ == "__main__":
    unittest.main()
