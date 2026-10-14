from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from driveserve.benchmark import aggregate, percentile, request
from driveserve.task import generate


class StreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        events = [json.dumps({"choices": [{"delta": {"content": '{"action":"stop",'}}]}),
                  json.dumps({"choices": [{"delta": {"content": '"speed_band":"stopped","must_yield":true}'},
                                           "finish_reason": "stop"}]}),
                  json.dumps({"choices": [], "usage": {"completion_tokens": 12, "prompt_tokens": 30}}),
                  "[DONE]"]
        if self.path.startswith("/truncated/"):
            events.pop()
        elif self.path.startswith("/no-usage/"):
            events.pop(2)
        elif self.path.startswith("/one-token/"):
            events[2] = json.dumps({"usage": {"completion_tokens": 1, "prompt_tokens": 30}})
        body = "".join("data: " + event + "\n\n" for event in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StreamHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, path=""):
        return request(f"http://127.0.0.1:{self.server.server_port}/{path}", "protocol-test-fixture", generate()[0], timeout=2)

    def test_stream_usage_and_timing(self):
        row = self.call()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["completion_tokens"], 12)
        self.assertEqual(len(row["chunks"]), 3)
        self.assertLessEqual(row["ttft_s"], row["e2e_s"])
        self.assertAlmostEqual(row["tpot_s"], (row["last_content_s"] - row["ttft_s"]) / 11)

    def test_incomplete_and_missing_usage_are_failures(self):
        self.assertEqual(self.call("truncated")["status"], "failed")
        self.assertEqual(self.call("no-usage")["status"], "failed")
        self.assertIsNone(self.call("one-token")["tpot_s"])

    def test_failures_remain_in_denominator(self):
        rows = [self.call(), self.call("truncated")]
        result = aggregate(rows, 2)
        self.assertEqual(result["requests"], 2)
        self.assertEqual(result["completion_rate"], .5)
        self.assertEqual(result["output_token_per_s"], 6)
        self.assertEqual(result["e2e_s"]["n"], 1)
        self.assertEqual(percentile(list(range(100)), .99), 98)

    def test_connection_failure_is_recorded(self):
        row = request("http://127.0.0.1:1/v1", "fixture", generate()[0], timeout=.1)
        self.assertEqual(row["status"], "failed")
        self.assertIsNotNone(row["error"])
