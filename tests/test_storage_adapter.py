"""Tests for StorageAdapter — FileStorageAdapter and SQLiteStorageAdapter skeleton."""

import pytest
import tempfile
from pathlib import Path

from lynkmesh_ai.storage.adapters import (
    StorageAdapter, StorageRecord,
    FileStorageAdapter, SQLiteStorageAdapter,
)


class TestFileStorageAdapter:
    """FileStorageAdapter: put, get, delete, exists, list, count, clear."""

    @pytest.fixture
    def adapter(self):
        d = tempfile.mkdtemp()
        a = FileStorageAdapter(Path(d))
        yield a
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_put_and_get(self, adapter):
        adapter.put("key1", {"name": "test", "value": 42})
        rec = adapter.get("key1")
        assert rec is not None
        assert rec.key == "key1"
        assert rec.data["name"] == "test"
        assert rec.data["value"] == 42
        assert rec.created_at
        assert rec.updated_at

    def test_get_nonexistent(self, adapter):
        assert adapter.get("nonexistent") is None

    def test_put_overwrites(self, adapter):
        adapter.put("key1", {"version": 1})
        adapter.put("key1", {"version": 2})
        rec = adapter.get("key1")
        assert rec.data["version"] == 2

    def test_exists(self, adapter):
        assert not adapter.exists("key1")
        adapter.put("key1", {})
        assert adapter.exists("key1")

    def test_delete(self, adapter):
        adapter.put("key1", {})
        assert adapter.delete("key1") is True
        assert adapter.delete("key1") is False

    def test_list_keys(self, adapter):
        adapter.put("aaa", {})
        adapter.put("aab", {})
        adapter.put("abc", {})
        adapter.put("xyz", {})
        all_keys = adapter.list_keys()
        assert len(all_keys) == 4
        aa_keys = adapter.list_keys(prefix="aa")
        assert len(aa_keys) == 2
        assert "aaa" in aa_keys

    def test_count(self, adapter):
        assert adapter.count() == 0
        adapter.put("a", {})
        adapter.put("b", {})
        assert adapter.count() == 2

    def test_clear(self, adapter):
        adapter.put("a", {})
        adapter.put("b", {})
        adapter.clear()
        assert adapter.count() == 0

    def test_iter_records(self, adapter):
        adapter.put("a", {"x": 1})
        adapter.put("b", {"x": 2})
        records = list(adapter.iter_records())
        assert len(records) == 2
        assert {r.key for r in records} == {"a", "b"}

    def test_repr(self, adapter):
        assert "FileStorageAdapter" in repr(adapter)


class TestStorageRecord:
    """StorageRecord serialization."""

    def test_to_dict(self):
        r = StorageRecord(key="k", data={"a": 1}, created_at="t1", updated_at="t2")
        d = r.to_dict()
        assert d["key"] == "k"
        assert d["data"] == {"a": 1}

    def test_from_dict(self):
        r = StorageRecord.from_dict({"key": "k", "data": {"b": 2}, "created_at": "t1", "updated_at": "t2"})
        assert r.key == "k"
        assert r.data == {"b": 2}

    def test_roundtrip(self):
        r1 = StorageRecord(key="k", data={"c": 3}, created_at="t1", updated_at="t2")
        r2 = StorageRecord.from_dict(r1.to_dict())
        assert r2.key == r1.key
        assert r2.data == r1.data


class TestSQLiteStorageAdapter:
    """SQLiteStorageAdapter skeleton — all methods raise NotImplementedError."""

    @pytest.fixture
    def adapter(self):
        d = tempfile.mkdtemp()
        return SQLiteStorageAdapter(Path(d) / "test.db")

    def test_put_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.put("k", {})

    def test_get_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.get("k")

    def test_delete_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.delete("k")

    def test_exists_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.exists("k")

    def test_list_keys_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.list_keys()

    def test_count_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.count()

    def test_clear_raises(self, adapter):
        with pytest.raises(NotImplementedError):
            adapter.clear()

    def test_repr(self, adapter):
        assert "SQLiteStorageAdapter" in repr(adapter)
        assert "SKELETON" in repr(adapter)
