"""Adversarial and reference controls exercise shipped task graders."""

import sys

import pytest

from awb.core.task_loader import load_all_tasks
from awb.verification.partial_credit import evaluate_partial_credit


@pytest.mark.asyncio
@pytest.mark.parametrize("task_id", ["BF-001", "BF-009", "CR-007"])
async def test_empty_workspace_earns_no_credit(task_id, tmp_path):
    task = next(t for t in load_all_tasks() if t.id == task_id)
    earned, possible, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert possible == 100
    assert earned == 0


def test_bundled_security_checks_do_not_mask_tool_errors():
    commands = [
        command for task in load_all_tasks() for command in task.verification.security_commands
    ]
    assert len(commands) == 4
    assert not any("|| true" in command or "2>/dev/null" in command for command in commands)


@pytest.mark.asyncio
async def test_bf001_comments_and_placeholder_earn_no_credit(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_extra_fields.py").write_text(
        '# ConfigDict(extra="forbid") ValidationError\ndef test_placeholder():\n    assert True\n'
    )
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/python").symlink_to(sys.executable)
    (tmp_path / ".venv/bin/activate").write_text("")
    task = next(t for t in load_all_tasks() if t.id == "BF-001")
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 0


@pytest.mark.asyncio
async def test_cr007_unconditional_script_is_not_detection(tmp_path):
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit/check_deps.py").write_text('print("PASS FAIL not pinned")\n')
    task = next(t for t in load_all_tasks() if t.id == "CR-007")
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 0


@pytest.mark.asyncio
async def test_bf009_reference_passes_behavior(tmp_path):
    for d in ("models", "services"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "__init__.py").write_text("")
    (tmp_path / "models/base.py").write_text(
        "class User:\n    def __init__(self, username, password):\n"
        '        self.username = username\n        self.password_hash = "hashed:" + password\n'
    )
    (tmp_path / "models/user.py").write_text("from models.base import User\n")
    (tmp_path / "services/auth.py").write_text(
        "from models.base import User\ndef hash_password(password):\n"
        '    return "hashed:" + password\ndef create_user(username, password):\n'
        "    return User(username, password)\n"
    )
    task = next(t for t in load_all_tasks() if t.id == "BF-009")
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 100


@pytest.mark.asyncio
async def test_bf001_reference_and_strict_mutation(tmp_path):
    pytest.importorskip("fastapi")
    (tmp_path / "tests").mkdir()
    source = """from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict
app = FastAPI()
class Normal(BaseModel):
    id: int
    name: str
    email: str
class Strict(Normal):
    model_config = ConfigDict(extra="forbid")
@app.get("/strict", response_model=Strict)
def strict():
    return dict(id=1, name="Alice", email="alice@example.com", role="admin")
@app.get("/permissive", response_model=Normal)
def permissive():
    return strict()
"""
    path = tmp_path / "tests/test_extra_fields.py"
    path.write_text(source)
    task = next(t for t in load_all_tasks() if t.id == "BF-001")
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 100
    path.write_text(source.replace('extra="forbid"', 'extra="ignore"'))
    earned, _, breakdown = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 50
    assert not breakdown[0].passed


@pytest.mark.asyncio
async def test_cr007_reference_passes_and_unpinned_mutation_fails(tmp_path):
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit/check_deps.py").write_text("""import re
import sys
from pathlib import Path
failed = False
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    pinned = bool(re.fullmatch(r"[\\w-]+==[0-9]+(?:\\.[0-9]+)+", line.strip()))
    print("PASS" if pinned else "FAIL", line)
    failed |= not pinned
sys.exit(int(failed))
""")
    path = tmp_path / "requirements.txt"
    path.write_text(
        "\n".join(
            f"{p}==1.2.3"
            for p in [
                "fastapi",
                "uvicorn",
                "pydantic",
                "httpx",
                "sqlalchemy",
                "alembic",
                "requests",
                "python-dotenv",
            ]
        )
    )
    task = next(t for t in load_all_tasks() if t.id == "CR-007")
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 100
    path.write_text(path.read_text().replace("requests==1.2.3", "requests>=1.2.3"))
    earned, _, _ = await evaluate_partial_credit(task.verification.partial_credit, tmp_path)
    assert earned == 50
