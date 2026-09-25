import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from pentimento import cache


def _restore_env(key, previous):
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


def _isolate_cache_dir(test, directory):
    previous = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = str(directory)
    test.addCleanup(_restore_env, "XDG_CACHE_HOME", previous)


class KeyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_key_changes_when_size_changes(self):
        path = self.directory / "log.jsonl"
        path.write_text("a")
        first = cache.key(path)
        path.write_text("ab")
        self.assertNotEqual(first, cache.key(path))

    def test_key_is_stable_for_an_unchanged_file(self):
        path = self.directory / "log.jsonl"
        path.write_text("a")
        self.assertEqual(cache.key(path), cache.key(path))


class ReadWriteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)
        _isolate_cache_dir(self, self.directory)

    def test_read_of_missing_namespace_is_empty(self):
        self.assertEqual(cache.read("sessions"), {})

    def test_write_then_read_roundtrips(self):
        entries = {"a:1:2": {"x": 1}}
        cache.write("sessions", entries)
        self.assertEqual(cache.read("sessions"), entries)

    def test_version_mismatch_discards_the_file(self):
        cache.write("sessions", {"a:1:2": {"x": 1}})
        cache_path = cache.cache_dir() / "sessions.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["version"] = cache.VERSION + 1
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(cache.read("sessions"), {})

    def test_version_2_file_is_discarded(self):
        cache.write("touches", {"a:1:2": {"x": 1}})
        cache_path = cache.cache_dir() / "touches.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["version"] = 2
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(cache.read("touches"), {})

    def test_corrupt_file_reads_as_empty(self):
        cache.cache_dir().mkdir(parents=True, exist_ok=True)
        (cache.cache_dir() / "sessions.json").write_text("not json", encoding="utf-8")
        self.assertEqual(cache.read("sessions"), {})

    def test_unwritable_directory_degrades_silently(self):
        target = self.directory / "pentimento"
        target.mkdir(parents=True)
        target.chmod(stat.S_IREAD)
        self.addCleanup(target.chmod, stat.S_IRWXU)
        cache.write("sessions", {"a:1:2": {"x": 1}})
        self.assertEqual(cache.read("sessions"), {})


if __name__ == "__main__":
    unittest.main()
