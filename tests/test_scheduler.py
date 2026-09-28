"""Tests for the scheduler module."""
import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from showrenamer.scheduler import Scheduler
from showrenamer.renamer import NO_TARGET_DIR_REASON


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.processed = []
        self.handler_results = {}
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def make_file(self, name="video.mkv", content=b"content") -> Path:
        path = Path(self.tmpdir.name) / name
        path.write_bytes(content)
        return path

    def file_handler(self, path: str):
        self.processed.append(path)
        return self.handler_results.get(path, (True, None))

    def make_scheduler(self, **kwargs) -> Scheduler:
        defaults = {
            "file_handler": self.file_handler,
            "watch_paths": [self.tmpdir.name],
            "video_extensions": {".mkv", ".mp4"},
            "stability_period": 1,
            "retry_interval": 60,
            "full_rescan_interval": 300,
            "no_target_dir_retry_interval": 1,
            "max_retries": 2,
        }
        defaults.update(kwargs)
        return Scheduler(**defaults)

    def test_add_file_is_processed_after_stability(self):
        scheduler = self.make_scheduler(stability_period=1)
        scheduler.start()
        try:
            video = self.make_file("test.mkv")
            scheduler.add_file(video)
            # Wait for stability period + processing margin.
            time.sleep(2.5)
            self.assertIn(str(video), self.processed)
        finally:
            scheduler.stop()

    def test_remove_file_cancels_processing(self):
        # Use a long stability period so removal happens well before processing
        # could start, making the test deterministic.
        scheduler = self.make_scheduler(stability_period=10)
        scheduler.start()
        try:
            video = self.make_file("test.mkv")
            scheduler.add_file(video)
            scheduler.remove_file(video)
            time.sleep(2)
            self.assertNotIn(str(video), self.processed)
        finally:
            scheduler.stop()

    def test_failed_file_is_retried(self):
        scheduler = self.make_scheduler(stability_period=1, retry_interval=1)
        video = self.make_file("retry.mkv")
        self.handler_results[str(video)] = (False, "some error")
        scheduler.start()
        try:
            scheduler.add_file(video)
            # First processing attempt + first retry.
            time.sleep(4)
            self.assertGreaterEqual(self.processed.count(str(video)), 2)
        finally:
            scheduler.stop()

    def test_no_target_dir_failure_uses_short_retry(self):
        scheduler = self.make_scheduler(stability_period=1, no_target_dir_retry_interval=1)
        video = self.make_file("notarget.mkv")
        self.handler_results[str(video)] = (False, NO_TARGET_DIR_REASON)
        scheduler.start()
        try:
            scheduler.add_file(video)
            # Short interval allows multiple attempts quickly.
            time.sleep(6)
            self.assertGreaterEqual(self.processed.count(str(video)), 3)
        finally:
            scheduler.stop()

    def test_config_rescan_reprocesses_existing_files(self):
        scheduler = self.make_scheduler(stability_period=1)
        video = self.make_file("existing.mkv")
        scheduler.start()
        try:
            time.sleep(0.5)
            scheduler.schedule_config_rescan()
            time.sleep(2.5)
            self.assertIn(str(video), self.processed)
        finally:
            scheduler.stop()

    def test_config_rescan_resets_retry_backoff(self):
        scheduler = self.make_scheduler(stability_period=1, retry_interval=600, no_target_dir_retry_interval=60)
        video = self.make_file("reset.mkv")
        path_str = str(video)
        self.handler_results[path_str] = (False, "hard error")

        scheduler.start()
        try:
            scheduler.add_file(video)
            # Let the first attempt fail and queue a long backoff.
            time.sleep(2.5)
            with scheduler.condition:
                self.assertEqual(scheduler.pending_retries[path_str][1], 1)
                next_retry = scheduler.pending_retries[path_str][0]
                # The default retry interval is 600s; with exponential backoff
                # the first retry should be scheduled several minutes away.
                self.assertGreater(next_retry, datetime.now() + timedelta(seconds=250))

            # Config change should reset backoff and retry immediately.
            scheduler.schedule_config_rescan()
            time.sleep(2.5)
            self.assertGreaterEqual(self.processed.count(path_str), 2)
            with scheduler.condition:
                self.assertIn(path_str, scheduler.pending_retries)
                # The file was retried once after the reset, so the count is now 1
                # again. The next retry is re-scheduled using the normal backoff.
                self.assertEqual(scheduler.pending_retries[path_str][1], 1)
        finally:
            scheduler.stop()

    def test_full_rescan_discovers_untracked_files(self):
        scheduler = self.make_scheduler(stability_period=1, full_rescan_interval=1)
        scheduler.start()
        try:
            # Create a file after the scheduler has started.
            video = self.make_file("missed.mkv")
            # Wait for the periodic full re-scan to pick it up.
            time.sleep(3.5)
            self.assertIn(str(video), self.processed)
        finally:
            scheduler.stop()


if __name__ == "__main__":
    unittest.main()
