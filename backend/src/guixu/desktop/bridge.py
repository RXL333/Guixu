from __future__ import annotations

import os
import subprocess

from guixu.application.conversations import ConversationService
from guixu.infrastructure.filesystem.grants import SourceRegistry, canonicalize_directory


class DesktopBridge:
    def __init__(self, registry: SourceRegistry, conversations: ConversationService) -> None:
        self.registry = registry
        self.conversations = conversations

    def open_conversation_directory(self, conversation_id: str) -> dict[str, object]:
        conversation = self.conversations.get_conversation(conversation_id)
        if conversation.get("deleted_at"):
            raise ValueError("CONVERSATION_DELETED")
        scopes = [scope for scope in conversation.get("scopes", []) if not scope.get("revoked_at")]
        if not scopes:
            raise ValueError("CONVERSATION_SCOPE_REQUIRED")
        root = canonicalize_directory(scopes[0]["source_root"])
        if os.name != "nt":
            raise ValueError("DESKTOP_WINDOWS_REQUIRED")
        subprocess.Popen(["explorer.exe", str(root)], close_fds=True)
        return {"opened": True, "path": str(root)}

    def select_directory(self, purpose: str) -> dict[str, object]:
        import webview

        window = webview.windows[0]
        # pywebview 6 keeps FOLDER_DIALOG as a compatibility alias but emits a
        # deprecation warning.  Use the namespaced enum so the desktop runner
        # starts cleanly on current and future pywebview releases.
        selected = window.create_file_dialog(webview.FileDialog.FOLDER)
        if not selected:
            return {"cancelled": True}
        grant = self.registry.register_typed_directory(selected[0], purpose)
        return {
            "cancelled": False,
            "grant_id": grant.grant_id,
            "display_path": grant.display_path,
            "exists": True,
            "writable": grant.writable,
            "warnings": [],
        }

    def register_typed_directory(self, path: str, purpose: str) -> dict[str, object]:
        grant = self.registry.register_typed_directory(path, purpose)
        return {
            "cancelled": False,
            "grant_id": grant.grant_id,
            "display_path": grant.display_path,
            "exists": True,
            "writable": grant.writable,
            "warnings": [],
        }
