import io
import os
import queue
import threading
import unittest
from unittest.mock import Mock, patch

import codex_usage_widget as widget


SNAPSHOT = {"rateLimits": {"planType": "plus", "primary": {
    "usedPercent": 25, "windowDurationMins": 300, "resetsAt": 1800000000,
}}}


class WidgetTests(unittest.TestCase):
    def client(self):
        with patch.object(widget.CodexAppServer, "_find_codex", return_value="codex"):
            return widget.CodexAppServer()

    def handler(self, path, token="test-token"):
        handler = object.__new__(widget.WidgetHandler)
        handler.path = path
        handler.headers = {"X-Widget-Token": token}
        handler.shutdown_token = "test-token"
        handler.wfile = io.BytesIO()
        handler._headers = Mock()
        handler.server = Mock()
        handler.cache = Mock()
        return handler

    def test_system_proxies_are_forwarded_without_overriding_environment(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "https://explicit", "NO_PROXY": "localhost"}, clear=True):
            with patch.object(widget, "getproxies", return_value={
                "http": "http://system:8080", "https": "http://system:8080", "no": "*.local",
            }):
                env = widget.app_server_environment()
        self.assertEqual(env["HTTPS_PROXY"], "https://explicit")
        self.assertEqual(env["HTTP_PROXY"], "http://system:8080")
        self.assertEqual(env["NO_PROXY"], "localhost")

    def test_lowercase_explicit_proxy_is_preserved(self):
        with patch.dict(os.environ, {"https_proxy": "http://explicit"}, clear=True):
            with patch.object(widget, "getproxies", return_value={"https": "http://system"}):
                env = widget.app_server_environment()
        self.assertEqual(env["https_proxy"], "http://explicit")
        self.assertNotIn("HTTPS_PROXY", env)

    def test_manual_refresh_bypasses_cache(self):
        app = Mock()
        app.get_rate_limits.return_value = SNAPSHOT
        cache = widget.UsageCache(app)
        self.assertEqual(cache.get()["windows"][0]["remainingPercent"], 75)
        cache.get()
        self.assertEqual(app.get_rate_limits.call_count, 1)
        cache.get(force=True)
        self.assertEqual(app.get_rate_limits.call_count, 2)

    def test_failed_refresh_preserves_previous_timestamp_and_data(self):
        app = Mock()
        app.get_rate_limits.side_effect = [SNAPSHOT, RuntimeError("offline")]
        cache = widget.UsageCache(app)
        previous = cache.get()
        at = cache.at
        with self.assertRaisesRegex(RuntimeError, "offline"):
            cache.get(force=True)
        self.assertIs(cache.data, previous)
        self.assertEqual(cache.at, at)

    def test_network_error_retries_after_reconnect(self):
        client = self.client()
        client.start = Mock()
        client.close = Mock()
        client._rpc = Mock(side_effect=[RuntimeError("error sending request"), SNAPSHOT])
        with patch.object(widget, "RETRY_DELAY", 0):
            self.assertEqual(client.get_rate_limits(), SNAPSHOT)
        self.assertEqual(client.start.call_count, 2)
        client.close.assert_called_once()

    def test_persistent_failure_has_actionable_error_and_bounded_retries(self):
        client = self.client()
        client.start = Mock()
        client.close = Mock()
        client._rpc = Mock(side_effect=RuntimeError("error sending request for url (https://chatgpt.com/backend-api/wham/usage)"))
        with patch.object(widget, "RETRY_DELAY", 0):
            with self.assertRaisesRegex(RuntimeError, "VPN/proxy"):
                client.get_rate_limits()
        self.assertEqual(client._rpc.call_count, 2)

    def test_account_authentication_required_explains_cli_login(self):
        message = widget.usage_error_message(RuntimeError(
            "codex account authentication required to read rate limits"
        ))
        self.assertIn("codex login", message)
        self.assertIn("CLI helper", message)

    def test_stop_interrupts_owned_helper_and_prevents_restart(self):
        client = self.client()
        client.proc = Mock()
        client.proc.poll.return_value = None
        client.request_stop()
        client.proc.terminate.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, "stopping"):
            client.start()

    def test_reader_does_not_block_on_duplicate_reply(self):
        client = self.client()
        pending = queue.Queue(maxsize=1)
        client._pending[1] = pending
        proc = Mock(stdout=io.StringIO('{"id":1,"result":{}}\n{"id":1,"result":{}}\n'))
        reader = threading.Thread(target=client._reader_loop, args=(proc,), daemon=True)
        reader.start()
        reader.join(timeout=1)
        self.assertFalse(reader.is_alive())
        self.assertEqual(pending.get_nowait()["result"], {})

    def test_shutdown_rejects_missing_or_invalid_token(self):
        for token in ("", "wrong"):
            h = self.handler("/api/shutdown", token)
            h.do_POST()
            self.assertEqual(h._headers.call_args.args[0], 403)
            h.cache.app_server.request_stop.assert_not_called()
            h.server.shutdown.assert_not_called()

    def test_shutdown_stops_helper_and_http_server(self):
        h = self.handler("/api/shutdown")
        done = threading.Event()
        h.server.shutdown.side_effect = done.set
        h.do_POST()
        self.assertTrue(done.wait(timeout=1))
        self.assertEqual(h._headers.call_args.args[0], 200)
        self.assertEqual(h.wfile.getvalue(), b'{"stopped":true}')
        h.cache.app_server.request_stop.assert_called_once()

    def test_get_cannot_shutdown_server(self):
        h = self.handler("/api/shutdown")
        h.do_GET()
        self.assertEqual(h._headers.call_args.args[0], 404)
        h.server.shutdown.assert_not_called()

    def test_refresh_query_and_page_token(self):
        h = self.handler("/api/usage?refresh=1")
        h.cache.get.return_value = {}
        h.do_GET()
        h.cache.get.assert_called_once_with(force=True)
        h = self.handler("/")
        h.do_GET()
        page = h.wfile.getvalue().decode()
        self.assertIn("Kill process", page)
        self.assertIn("'X-Widget-Token':'test-token'", page)
        self.assertNotIn("__SHUTDOWN_TOKEN__", page)


if __name__ == "__main__":
    unittest.main()
