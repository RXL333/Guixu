from __future__ import annotations

from guixu.infrastructure.filesystem.grants import SourceRegistry


class DesktopBridge:
    def __init__(self, registry: SourceRegistry) -> None:
        self.registry = registry

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
