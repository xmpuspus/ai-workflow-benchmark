"""Tests for RepoManager template caching and uv pip support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from awb.core.config import TaskDefinition
from awb.core.repo_manager import _TEMPLATE_DIR, RepoManager, _setup_cache_key


@pytest.fixture
def task(sample_task):
    return sample_task


@pytest.fixture
def manager(tmp_path):
    return RepoManager(workspace_root=tmp_path / "workspaces")


def _template_key_for(task: TaskDefinition) -> str:
    return _setup_cache_key(task.repo.url, task.repo.commit, task.repo.setup_commands)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_init_creates_template_dir(tmp_path):
    with patch.object(Path, "mkdir") as mock_mkdir:
        RepoManager(workspace_root=tmp_path / "ws")
    # mkdir is called for workspace_root, _CACHE_DIR, and _TEMPLATE_DIR
    assert mock_mkdir.call_count >= 3


def test_init_use_uv_stored(tmp_path):
    mgr = RepoManager(workspace_root=tmp_path, use_uv=True)
    assert mgr.use_uv is True


def test_init_use_uv_defaults_false(tmp_path):
    mgr = RepoManager(workspace_root=tmp_path)
    assert mgr.use_uv is False


# ---------------------------------------------------------------------------
# Template key derivation
# ---------------------------------------------------------------------------


def test_template_key_stable(task):
    key1 = _template_key_for(task)
    key2 = _template_key_for(task)
    assert key1 == key2


def test_template_key_changes_on_different_commit(task):
    key1 = _template_key_for(task)
    task.repo.commit = "deadbeef"
    key2 = _template_key_for(task)
    assert key1 != key2


def test_template_key_changes_on_different_url(task):
    key1 = _template_key_for(task)
    task.repo.url = "https://github.com/other/repo"
    key2 = _template_key_for(task)
    assert key1 != key2


def test_template_key_order_sensitive(task):
    """Install order matters; reordering setup_commands must change the cache key.

    Reason: pip install A then pip install B can resolve differently than
    pip install B then pip install A when the two share transitive deps.
    """
    task.repo.setup_commands = ["pip install .", "pip install pytest"]
    key1 = _template_key_for(task)
    task.repo.setup_commands = ["pip install pytest", "pip install ."]
    key2 = _template_key_for(task)
    assert key1 != key2


def test_setup_cache_key_helper_is_order_sensitive():
    """The module-level helper itself is order-sensitive."""
    a = _setup_cache_key("u", "c", ["pip install foo", "pip install bar"])
    b = _setup_cache_key("u", "c", ["pip install bar", "pip install foo"])
    assert a != b


def test_setup_cache_key_helper_is_deterministic():
    cmds = ["pip install foo", "pip install bar"]
    assert _setup_cache_key("u", "c", cmds) == _setup_cache_key("u", "c", list(cmds))


# ---------------------------------------------------------------------------
# prepare() — fast path (template cache hit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_uses_template_on_cache_hit(manager, task, tmp_path):
    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key

    # Simulate an existing ready template
    template_path.mkdir(parents=True, exist_ok=True)
    (template_path / ".ready").touch()
    # Put a sentinel file in the template so we can verify copytree ran
    (template_path / "sentinel.txt").write_text("from-template")

    git_calls = []

    async def fake_run(*args, cwd=None):
        git_calls.append(args)
        return 0, "", ""

    manager._run = fake_run

    workspace = await manager.prepare(task)

    assert (workspace / "sentinel.txt").read_text() == "from-template"
    # Fast path runs git checkout but NOT git clone --local (workspace comes from copytree)
    assert any("checkout" in " ".join(c) for c in git_calls)
    assert not any("--local" in " ".join(c) for c in git_calls)

    # Cleanup
    import shutil
    shutil.rmtree(template_path)


@pytest.mark.asyncio
async def test_prepare_fast_path_does_not_run_setup_commands(manager, task, tmp_path):
    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key
    template_path.mkdir(parents=True, exist_ok=True)
    (template_path / ".ready").touch()

    shell_calls = []

    async def fake_run(*args, cwd=None):
        return 0, "", ""

    async def fake_run_shell(cmd, cwd=None):
        shell_calls.append(cmd)
        return 0, "", ""

    manager._run = fake_run

    # patch subprocess_shell used by setup loop — it should never be called
    with patch("asyncio.create_subprocess_shell") as mock_shell:
        await manager.prepare(task)
        mock_shell.assert_not_called()

    import shutil
    shutil.rmtree(template_path)


# ---------------------------------------------------------------------------
# prepare() — slow path (template cache miss)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_slow_path_creates_template(manager, task, tmp_path):
    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key

    # Ensure no stale template
    if template_path.exists():
        import shutil
        shutil.rmtree(template_path)

    git_responses = {
        ("git", "clone", "--mirror"): (0, "", ""),
        ("git", "clone", "--local"): (0, "", ""),
        ("git", "checkout"): (0, "", ""),
    }

    async def fake_run(*args, cwd=None):
        for key in git_responses:
            if all(k in args for k in key):
                return git_responses[key]
        return 0, "", ""

    manager._run = fake_run

    # Stub out the setup command subprocess so it doesn't actually run pip
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_shell", return_value=mock_proc), patch(
        "asyncio.wait_for", return_value=(b"", b"")
    ):
        await manager.prepare(task)

    assert (template_path / ".ready").exists()

    import shutil
    shutil.rmtree(template_path)


# ---------------------------------------------------------------------------
# uv pip support
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prepare_replaces_pip_install_with_uv(tmp_path, task):
    manager = RepoManager(workspace_root=tmp_path / "ws", use_uv=True)
    task.repo.setup_commands = ["pip install -e ."]

    # Ensure no cached template
    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key
    if template_path.exists():
        import shutil
        shutil.rmtree(template_path)

    async def fake_run(*args, cwd=None):
        return 0, "", ""

    manager._run = fake_run

    captured_cmds = []

    async def fake_create_subprocess_shell(cmd, **kwargs):
        captured_cmds.append(cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.kill = MagicMock()
        return mock_proc

    with patch("asyncio.create_subprocess_shell", side_effect=fake_create_subprocess_shell), patch(
        "asyncio.wait_for", return_value=(b"", b"")
    ):
        await manager.prepare(task)

    assert any("uv pip install" in cmd for cmd in captured_cmds)
    assert not any(cmd.startswith("pip install") for cmd in captured_cmds)

    import shutil
    if template_path.exists():
        shutil.rmtree(template_path)


@pytest.mark.asyncio
async def test_prepare_does_not_replace_pip_when_use_uv_false(tmp_path, task):
    manager = RepoManager(workspace_root=tmp_path / "ws", use_uv=False)
    task.repo.setup_commands = ["pip install -e ."]

    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key
    if template_path.exists():
        import shutil
        shutil.rmtree(template_path)

    async def fake_run(*args, cwd=None):
        return 0, "", ""

    manager._run = fake_run

    captured_cmds = []

    async def fake_create_subprocess_shell(cmd, **kwargs):
        captured_cmds.append(cmd)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.kill = MagicMock()
        return mock_proc

    with patch("asyncio.create_subprocess_shell", side_effect=fake_create_subprocess_shell), patch(
        "asyncio.wait_for", return_value=(b"", b"")
    ):
        await manager.prepare(task)

    assert any("pip install" in cmd for cmd in captured_cmds)
    assert not any("uv pip install" in cmd for cmd in captured_cmds)

    import shutil
    if template_path.exists():
        shutil.rmtree(template_path)


# ---------------------------------------------------------------------------
# clear_templates()
# ---------------------------------------------------------------------------


def test_clear_templates_removes_and_recreates(manager):
    # Put something in the template dir
    sentinel = _TEMPLATE_DIR / "some_template"
    sentinel.mkdir(parents=True, exist_ok=True)
    (sentinel / ".ready").touch()

    manager.clear_templates()

    assert _TEMPLATE_DIR.exists()
    assert not sentinel.exists()


def test_clear_templates_idempotent(manager):
    manager.clear_templates()
    manager.clear_templates()
    assert _TEMPLATE_DIR.exists()


# ---------------------------------------------------------------------------
# cleanup() does NOT touch templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_does_not_remove_templates(manager, tmp_path):
    workspace = tmp_path / "my-workspace"
    workspace.mkdir()

    sentinel = _TEMPLATE_DIR / "should_survive"
    sentinel.mkdir(parents=True, exist_ok=True)

    await manager.cleanup(workspace)

    assert not workspace.exists()
    assert sentinel.exists()

    sentinel.rmdir()


# ---------------------------------------------------------------------------
# workspace_claude_md applied on both fast and slow paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_claude_md_written_on_fast_path(manager, task, tmp_path):
    task.workspace_claude_md = "# Test instructions"

    template_key = _template_key_for(task)
    template_path = _TEMPLATE_DIR / template_key
    template_path.mkdir(parents=True, exist_ok=True)
    (template_path / ".ready").touch()

    async def fake_run(*args, cwd=None):
        return 0, "", ""

    manager._run = fake_run

    workspace = await manager.prepare(task)

    assert (workspace / ".claude" / "CLAUDE.md").read_text() == "# Test instructions"

    import shutil
    shutil.rmtree(template_path)
