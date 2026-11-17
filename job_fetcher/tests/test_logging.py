import io
import json
import logging
import unittest

from job_fetcher.logging_utils import configure_logging, log_event


class LoggingTests(unittest.TestCase):
    def test_events_are_json_with_run_and_site_context(self):
        stream = io.StringIO()
        logger = configure_logging(stream)

        log_event(
            logger,
            logging.ERROR,
            "site_failed",
            run_id="run-1",
            company="Acme",
            site_url="https://careers.acme.example",
            phase="fetch",
        )

        record = json.loads(stream.getvalue())
        self.assertEqual(record["event"], "site_failed")
        self.assertEqual(record["level"], "error")
        self.assertEqual(record["context"]["run_id"], "run-1")
        self.assertEqual(record["context"]["company"], "Acme")
        self.assertEqual(record["context"]["phase"], "fetch")


if __name__ == "__main__":
    unittest.main()
