"""Trusted behavioral controls for reviewed task contracts.

Run as a script using the task environment's interpreter. Candidate code runs
in that environment; this module is never copied into the editable workspace.
"""

from __future__ import annotations

import importlib
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path


def fastapi_extra_fields(check: str) -> None:
    from fastapi.exceptions import ResponseValidationError
    from fastapi.testclient import TestClient

    namespace = runpy.run_path("tests/test_extra_fields.py")
    app = namespace["app"]
    client = TestClient(app)
    if check == "strict":
        try:
            client.get("/strict")
        except ResponseValidationError as exc:
            assert any(e["type"] == "extra_forbidden" for e in exc.errors())
        else:
            raise AssertionError("Extra response field was not rejected")
    elif check == "permissive":
        response = client.get("/permissive")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "Alice", "email": "alice@example.com"}
    else:
        raise ValueError(check)


def circular_import(check: str) -> None:
    # Separate invocations test both import orders with no warm module cache.
    names = ["models.user", "services.auth"]
    if check == "services-first":
        names.reverse()
    elif check != "models-first":
        raise ValueError(check)
    for name in names:
        importlib.import_module(name)
    auth = importlib.import_module("services.auth")
    model = importlib.import_module("models.user")
    for username, password in [("alice", "pw"), ("bob", "a-different-password")]:
        user = auth.create_user(username, password)
        assert isinstance(user, model.User)
        assert user.username == username
        assert user.password_hash == auth.hash_password(password) == "hashed:" + password


def dependency_audit(check: str) -> None:
    script = Path("audit/check_deps.py").resolve()
    assert script.is_file()
    if check == "detection":
        cases = [
            ("requests==2.31.0\n", 0),
            ("requests\n", 1),
            ("httpx>=0.26.0\n", 1),
            ("alembic~=1.13.0\n", 1),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.txt"
            for content, expected in cases:
                path.write_text(content)
                proc = subprocess.run(
                    [sys.executable, str(script), str(path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                assert proc.returncode == expected, (content, proc.returncode)
                assert ("PASS" if expected == 0 else "FAIL") in proc.stdout
    elif check == "pins":
        import re

        expected = {
            "fastapi",
            "uvicorn",
            "pydantic",
            "httpx",
            "sqlalchemy",
            "alembic",
            "requests",
            "python-dotenv",
        }
        lines = [
            line.strip()
            for line in Path("requirements.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        matches = [re.fullmatch(r"([A-Za-z0-9_-]+)==([0-9]+(?:\.[0-9]+)+)", line) for line in lines]
        assert len(matches) == 8 and all(matches)
        assert {match[1].lower() for match in matches} == expected
    else:
        raise ValueError(check)


if __name__ == "__main__":
    sys.path.insert(0, str(Path.cwd()))
    {"BF-001": fastapi_extra_fields, "BF-009": circular_import, "CR-007": dependency_audit}[
        sys.argv[1]
    ](sys.argv[2])
