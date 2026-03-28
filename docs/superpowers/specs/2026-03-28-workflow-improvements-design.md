# AWB-Driven Workflow Improvements Design

## Overview

Data-driven improvements to Xavier's Claude Code workflow based on analysis of 100-task AWB benchmark results. Custom scores 87.2% avg vs vanilla 45.8%, but 41 tasks don't reach 100%. Five failure modes identified, five improvements designed to push custom from 87% to 93-96%.

## Data Source

AWB v1.0.3 benchmark on awb-playground: 100 tasks (8 categories), 1 run each for vanilla and custom Claude Code with Opus. Custom pass rate 59%, vanilla 23%. Custom wins 56 tasks, vanilla wins 5, ties 39.

## Failure Mode Analysis

| Mode | Tasks | % | Root Cause |
|---|---|---|---|
| INCOMPLETE_FIX | 14 | 34% | Fixes N-1 of N items. Doesn't verify all instances handled. |
| SCOPE_DISCIPLINE | 9 | 22% | Modifies red herring files, over-engineers, violates "fix only X" constraints. |
| CONTEXT_MISSING | 8 | 20% | Doesn't read tests/docs before coding. Misses codebase structure. |
| TEST_MISMATCH | 7 | 17% | Code correct but tests fail. No iterative test-fix loop. |
| FRAMEWORK_GAP | 3 | 7% | dict.get None semantics, Pydantic v2 field stripping, asyncio gather safety. |

### 5 Tasks Where Vanilla Beat Custom (diagnostic)

| Task | V | C | Cause |
|---|---|---|---|
| DB-002 | 100 | 40 | dict.get returns None not default when key exists with None value |
| DB-003 | 100 | 75 | Pydantic response_model silently strips undeclared fields |
| LC-012 | 20 | 5 | Custom didn't navigate 20-file codebase; dove in without reading structure |
| RF-012 | 80 | 65 | Custom modified files outside task scope (GitHub Actions task) |
| WF-012 | 75 | 50 | Custom fixed bug but didn't run tests to validate; vanilla did |

Common thread: custom workflow lacks tight feedback loops. Writes code without validating, doesn't re-read error output, doesn't check scope.

## Improvements

### P0: CLAUDE.md — Test-Driven Feedback Loop

Add to "Coding Execution Discipline" section in `~/.claude/CLAUDE.md`:

```markdown
## Test-Driven Feedback Loop
- Run the project's test suite after EVERY file edit. Do not move to the next file until tests pass or you've read the full error output.
- If tests fail 3 times on the same issue, stop editing and re-read the task description from scratch.
```

### P1: CLAUDE.md — Completeness Counting

```markdown
## Completeness Counting
- When a task says "fix all N", "replace all X", or lists N items: grep for all instances FIRST, count them, fix each one, then re-count to verify zero remaining.
```

### P2: CLAUDE.md — Scope Discipline

```markdown
## Scope Discipline
- When a task says "do not modify X" or "fix only Y", treat that as a hard constraint. Check `git diff --name-only` before declaring done.
```

### P3: CLAUDE.md — Read Before Write

```markdown
## Read Before Write
- Read ALL test files before writing any production code. Tests define the contract.
```

### P4: Rules File — Framework Gotchas

Create `~/.claude/rules/framework-gotchas.md`:

```markdown
# Python & Framework Gotchas

## dict.get Semantics
dict.get(key, default) returns default only if key is ABSENT.
If key exists with value None, it returns None, NOT the default.
- dict.get("amount", 0) where amount=None returns None, not 0
- Fix: data.get("amount") or 0  OR  if data.get("amount") is None

## Pydantic v2 Response Models
response_model on FastAPI endpoints filters output to declared fields only.
If handler returns {id, name, email, role} but model only declares {id, name, email},
role is silently stripped. Use ConfigDict(extra="forbid") to catch this.

## asyncio.gather with Shared State
SQLAlchemy AsyncSession is NOT safe for concurrent use in gather().
Each coroutine must get its own session instance.
httpx.AsyncClient with cookies is NOT safe for concurrent requests.

## Late-Binding Closures
for i in range(5): fns.append(lambda x: i * x) — all fns use i=4.
Fix: lambda x, i=i: i * x (capture with default arg).

## Float Equality
Never use == for floats. Use math.isclose(a, b) or abs(a-b) < tolerance.
```

### P5: Rules File — Scope Boundaries

Create `~/.claude/rules/scope-discipline.md`:

```markdown
# Scope Discipline

When a task specifies file boundaries:
1. Parse the constraint FIRST: "fix only X", "do not modify Y", "files_to_examine: [...]"
2. Before declaring done: git diff --name-only
3. If you modified a file not in scope, revert it
4. Red herring files exist in some tasks — files that look related but aren't the fix target
5. "Minimal fix" means ONE change, not improvements, not refactoring, not added comments
```

### P6: Rules File — Completeness Verification

Create `~/.claude/rules/completeness-verification.md`:

```markdown
# Completeness Verification

When a task lists N items to fix/replace/update:
1. GREP for all instances before starting: grep -rn 'pattern' .
2. Record the count: "Found 8 instances across 4 files"
3. Fix each one individually
4. RE-GREP after all fixes: grep -rn 'pattern' . must return 0
5. If count doesn't match, you missed one — find it before declaring done
```

### P7: Hook — Post-edit test runner

Add to `~/.claude/settings.json` hooks:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "bash -c 'if [ -f pytest.ini ] || [ -f pyproject.toml ] || [ -f setup.py ]; then python3 -m pytest --tb=short -q 2>&1 | tail -20; fi'",
        "timeout": 30000,
        "description": "Auto-run tests after file edits"
      }
    ]
  }
}
```

Design decisions:
- Only fires on Edit/Write (file-changing tools), not Read/Grep/Bash
- Only runs if Python project detected (pytest.ini/pyproject.toml/setup.py)
- 30s timeout prevents blocking on slow suites
- tail -20 keeps output manageable

### P8: Hook — Pre-commit scope check

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "command": "bash -c 'if echo \"$TOOL_INPUT\" | grep -q \"git commit\"; then changed=$(git diff --cached --name-only 2>/dev/null | wc -l); if [ \"$changed\" -gt 5 ]; then echo \"[WARN] Committing $changed files. Verify scope discipline.\"; fi; fi'",
        "timeout": 5000,
        "description": "Scope check before large commits"
      }
    ]
  }
}
```

## Expected Impact

| Improvement | Tasks Fixed | Projected Lift |
|---|---|---|
| P0-P3: CLAUDE.md principles | 25+ tasks | +15-20 avg pts |
| P4: Framework gotchas | DB-002, DB-003, BF-009 | +3-5 avg pts |
| P5-P6: Rules files | 10+ tasks | +5-8 avg pts |
| P7: Test loop hook | WF-010, WF-012, RF-003, MF-001 | +10-15 avg pts |
| P8: Scope check hook | RF-012, WF-024, WF-012 | +3-5 avg pts |

**Projected custom score: 87.2% to 93-96%**

## Non-Goals

- No changes to AWB benchmark tasks (those are fixed separately)
- No new skills or slash commands (principles + hooks are sufficient)
- No agent-level changes (subagent patterns not needed for these failure modes)
- No model changes (all improvements are workflow-level)

## Verification

After implementing, re-run AWB workflow category:

```bash
cd ~/Desktop/awb-playground
pip install --upgrade awb
rm -rf results/runs/
awb run --category workflow --runs 1
```

Then full 100-task benchmark:

```bash
awb run --runs 1
```

Compare custom score before (87.2%) vs after. Target: 93%+.
