"""Testy nigdy nie zapisują analiz ani raportów do bazy użytkownika."""

import pytest

from log_analyzer.storage import sqlite_repo


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_repo, "SCIEZKA_BAZY", tmp_path / "test.sqlite3")
