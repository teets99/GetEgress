"""Tests for get_egress_ip.py. Runs main() end to end with the API and input() faked."""
import builtins
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

# Requires: pip install requests tabulate
# Run:      python3 test_get_egress_ip.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import get_egress_ip as g  # noqa: E402

CURL = ('curl -X POST -d @option.txt -H "header-api-key: abcdef123456" '
        '"https://api.prod8.datapath.prismaaccess.com/getPrismaAccessIP/v2"')

API_JSON = {"status": "success", "result": [
    {"zone": "US East", "address_details": [
        {"address": "34.1.1.1", "serviceType": "gp_gateway", "addressType": "active"},
        {"address": "34.2.2.2", "serviceType": "gp_portal", "addressType": "active"},
        {"address": "34.1.1.1", "serviceType": "gp_gateway", "addressType": "active"},
    ]},
    {"zone": "Europe", "address_details": [
        {"address": "35.3.3.3", "serviceType": "gp_gateway", "addressType": "reserved",
         "node_name": ["n1", "n2"]},
        {"address": "35.4.4.4", "serviceType": "remote_network", "addressType": "active"},
    ]},
]}


def fake_response(status=200, body=None):
    r = mock.Mock(status_code=status, text=str(body))
    r.json.return_value = body
    return r


class TestEgress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "prisma.txt")

    def run_main(self, response, inputs=(CURL,)):
        buf = io.StringIO()
        with mock.patch.object(g, "OUTPUT_FILE", self.out), \
             mock.patch.object(g.write_ip_file, "__defaults__", (self.out,)), \
             mock.patch.object(g.requests, "post", return_value=response) as post, \
             mock.patch.object(builtins, "input", side_effect=list(inputs)), \
             redirect_stdout(buf):
            try:
                g.main()
                code = None
            except SystemExit as e:
                code = e.code
        return post, buf.getvalue(), code

    def read_out(self):
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    # --- parsing ---
    def test_parse_curl(self):
        self.assertEqual(g.parse_curl_command(CURL),
                         ("abcdef123456", "https://api.prod8.datapath.prismaaccess.com/getPrismaAccessIP/v2"))

    def test_parse_curl_missing_key(self):
        with self.assertRaises(ValueError):
            g.parse_curl_command('curl "https://x.example.com/"')

    # --- end to end ---
    def test_main_writes_gateway_ips_only(self):
        post, out, code = self.run_main(fake_response(200, API_JSON))
        self.assertIsNone(code)
        self.assertEqual(post.call_args.kwargs["json"]["serviceType"], "gp_gateway")
        self.assertEqual(self.read_out(), "34.1.1.1\n35.3.3.3\n")
        self.assertIn("Wrote 2 gateway IP(s)", out)
        self.assertNotIn("34.2.2.2", out)
        self.assertNotIn("35.4.4.4", out)

    def test_main_overwrites_previous_file(self):
        with open(self.out, "w") as fh:
            fh.write("9.9.9.9\n")
        self.run_main(fake_response(200, API_JSON))
        self.assertEqual(self.read_out(), "34.1.1.1\n35.3.3.3\n")

    def test_main_no_results_leaves_file_alone(self):
        with open(self.out, "w") as fh:
            fh.write("9.9.9.9\n")
        _, out, code = self.run_main(fake_response(200, {"result": []}))
        self.assertIsNone(code)
        self.assertIn("No gateway addresses returned", out)
        self.assertEqual(self.read_out(), "9.9.9.9\n")

    def test_main_http_error_exits(self):
        _, out, code = self.run_main(fake_response(403, {"error": "forbidden"}))
        self.assertEqual(code, 1)
        self.assertIn("HTTP 403", out)
        self.assertFalse(os.path.exists(self.out))

    def test_main_empty_input_exits(self):
        _, _, code = self.run_main(fake_response(200, API_JSON), inputs=("",))
        self.assertIn("No input", code)

    def test_write_permission_error(self):
        with mock.patch("builtins.open", side_effect=PermissionError):
            with self.assertRaises(SystemExit) as cm:
                g.write_ip_file([{"Address": "1.1.1.1"}], self.out)
        self.assertIn("Permission denied", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main(verbosity=2)
