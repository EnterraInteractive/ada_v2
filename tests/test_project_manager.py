"""Workspace safety and context tests."""
import pytest

from project_manager import ProjectManager


def test_open_external_workspace_and_resolve_relative_files(tmp_path):
    workspace = tmp_path / "EnterraOnline"
    workspace.mkdir()
    (workspace / "Source").mkdir()
    (workspace / "Source" / "Game.cpp").write_text("void Game() {}", encoding="utf-8")

    manager = ProjectManager(str(tmp_path / "ada"))
    ok, message = manager.open_workspace(str(workspace))

    assert ok
    assert manager.current_project == "EnterraOnline"
    assert manager.resolve_path("Source/Game.cpp").read_text(encoding="utf-8") == "void Game() {}"


def test_workspace_path_escape_is_rejected(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    manager = ProjectManager(str(tmp_path / "ada"))
    manager.open_workspace(str(workspace))

    with pytest.raises(PermissionError):
        manager.resolve_path("../outside.txt")


def test_context_includes_source_but_skips_generated_folders(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "Source").mkdir()
    (workspace / "Source" / "Game.cpp").write_text("class GameSubsystem {};", encoding="utf-8")
    (workspace / "Binaries").mkdir()
    (workspace / "Binaries" / "noise.txt").write_text("do not index", encoding="utf-8")

    manager = ProjectManager(str(tmp_path / "ada"))
    manager.open_workspace(str(workspace))
    context = manager.get_project_context()

    assert "GameSubsystem" in context
    assert "noise.txt" not in context


def test_memory_persists_in_workspace_private_folder(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    manager = ProjectManager(str(tmp_path / "ada"))
    manager.open_workspace(str(workspace))

    manager.save_memory("The user is building a game.")
    assert "building a game" in manager.get_memory_context()
