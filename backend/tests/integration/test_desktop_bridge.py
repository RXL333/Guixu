from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from guixu.desktop.bridge import DesktopBridge
from guixu.infrastructure.filesystem.grants import SourceRegistry


def test_open_current_directory_uses_saved_conversation_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "photos"
    source.mkdir()
    conversations = Mock()
    conversations.get_conversation.return_value = {
        "deleted_at": None, "scopes": [{"source_root": str(source), "revoked_at": None}],
    }
    opened = []
    monkeypatch.setattr("guixu.desktop.bridge.subprocess.Popen", lambda args, **kwargs: opened.append(args))
    bridge = DesktopBridge(SourceRegistry(), conversations)
    assert bridge.open_conversation_directory("c1") == {"opened": True, "path": str(source)}
    assert opened == [["explorer.exe", str(source)]]
    conversations.get_conversation.return_value = {"deleted_at": "now", "scopes": [{"source_root": str(source)}]}
    with pytest.raises(ValueError, match="CONVERSATION_DELETED"):
        bridge.open_conversation_directory("c1")
    assert len(opened) == 1
