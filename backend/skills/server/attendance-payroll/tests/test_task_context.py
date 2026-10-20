import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import task_context  # noqa: E402


SCRIPT = Path(task_context.__file__).resolve()
VALID_TASK = "task_Z31vkhvR4B"
VALID_REQ_A = "req_939"
VALID_REQ_B = "req_942"
ATTENDANCE_SHA = "a" * 64
IDENTITY_SHA = "b" * 64


def _turn(repo: Path, task_id: str = VALID_TASK, request_id: str = VALID_REQ_A) -> Path:
    path = repo / ".leros" / "tasks" / task_id / "turns" / request_id / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, check=False)


def test_discover_runtime_task_path_and_confidence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    result = task_context.discover_task_context(str(repo), str(_turn(repo)))

    assert result == {
        "ok": True,
        "task_id": VALID_TASK,
        "source": "runtime_turn_tmp_path",
        "confidence": "context_derived",
        "is_authorization_proof": False,
    }


def test_absolute_normalized_runtime_paths_are_accepted(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    turn = _turn(repo)
    result = task_context.discover_task_context(str(repo / "."), str(turn / "."))
    assert result["task_id"] == VALID_TASK


def test_same_task_across_turns_and_month_has_stable_batch_id(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    batch_ids = []
    for req in [VALID_REQ_A, VALID_REQ_B]:
        discovered = task_context.discover_task_context(str(repo), str(_turn(repo, request_id=req)))
        batch = task_context.derive_batch_context(
            discovered["task_id"], "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [2, 1]
        )
        batch_ids.append(batch["batch_id"])
    assert batch_ids == [f"{VALID_TASK}-2026-06"] * 2


def test_different_tasks_produce_different_batch_ids(tmp_path):
    first = task_context.derive_batch_context(VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1])
    second_task = "task_YwPt8p8v79"
    second = task_context.derive_batch_context(second_task, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1])
    assert first["batch_id"] != second["batch_id"]


@pytest.mark.parametrize(
    ("repo_input", "tmp_input", "error"),
    [
        ("relative/repo", "relative/tmp", "ABSOLUTE_PATH_REQUIRED"),
        ("", "/tmp/path", "PROJECT_ROOT_MISSING"),
    ],
)
def test_missing_or_relative_context_fails_closed(repo_input, tmp_input, error):
    with pytest.raises(task_context.ContextError, match=error):
        task_context.discover_task_context(repo_input, tmp_input)


def test_missing_task_request_and_invalid_path_shapes_fail_closed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    cases = [
        (repo / ".leros" / "tasks" / "bad-id" / "turns" / VALID_REQ_A / "tmp", "TASK_ID_INVALID"),
        (repo / ".leros" / "tasks" / VALID_TASK / "turns" / "bad-req" / "tmp", "REQUEST_ID_INVALID"),
        (repo / ".leros" / "tasks" / VALID_TASK / "wrong" / VALID_REQ_A / "tmp", "TASK_PATH_SHAPE_INVALID"),
        (repo / ".leros" / "tasks" / "turns" / VALID_REQ_A / "tmp", "TASK_PATH_SHAPE_INVALID"),
    ]
    for path, error in cases:
        path.mkdir(parents=True, exist_ok=True)
        with pytest.raises(task_context.ContextError, match=error):
            task_context.discover_task_context(str(repo), str(path))


def test_project_mismatch_and_path_traversal_are_rejected(tmp_path):
    repo = tmp_path / "repo"
    other_repo = tmp_path / "other"
    repo.mkdir()
    other_repo.mkdir()
    turn = _turn(other_repo)
    with pytest.raises(task_context.ContextError, match="TURN_TMP_OUTSIDE_PROJECT"):
        task_context.discover_task_context(str(repo), str(turn))
    with pytest.raises(task_context.ContextError, match="PATH_TRAVERSAL_REJECTED"):
        task_context.discover_task_context(str(repo), str(repo / ".." / "other"))


def test_nonexistent_task_context_fails_closed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(task_context.ContextError, match="PATH_NOT_FOUND"):
        task_context.discover_task_context(str(repo), str(repo / ".leros/tasks/missing/turns/req_123/tmp"))


def test_symlinked_task_component_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    outside_turn = _turn(outside)
    tasks = repo / ".leros" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / VALID_TASK).symlink_to(outside_turn.parents[2], target_is_directory=True)
    linked_tmp = tasks / VALID_TASK / "turns" / VALID_REQ_A / "tmp"
    with pytest.raises(task_context.ContextError, match="SYMLINK_PATH_REJECTED"):
        task_context.discover_task_context(str(repo), str(linked_tmp))


def test_batch_context_ids_follow_payroll_contract_and_are_scope_stable():
    first = task_context.derive_batch_context(VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [3, 1, 2])
    same_scope_different_order = task_context.derive_batch_context(
        VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [2, 3, 1]
    )
    changed_scope = task_context.derive_batch_context(VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1, 2])
    changed_identity = task_context.derive_batch_context(VALID_TASK, "2026-06", ATTENDANCE_SHA, "c" * 64, [3, 1, 2])

    assert first["batch_id"] == f"{VALID_TASK}-2026-06"
    assert first["operation_ids"] == {
        "submit": f"submit:{first['batch_id']}",
        "precheck": f"precheck:{first['batch_id']}",
        "calculate": f"calculate:{first['batch_id']}",
    }
    assert first["scope_sha256"] == same_scope_different_order["scope_sha256"]
    assert first["scope_sha256"] != changed_scope["scope_sha256"]
    assert first["scope_sha256"] != changed_identity["scope_sha256"]
    assert first["batch_id"] == changed_scope["batch_id"]
    assert changed_scope["scope_change_requires_stop"] is True
    assert first["is_authorization_proof"] is False
    assert first["is_payroll_receipt"] is False


def test_expected_scope_mismatch_is_rejected_without_creating_alternate_batch():
    previous = task_context.derive_batch_context(VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1, 2])
    with pytest.raises(task_context.ContextError, match="BATCH_SCOPE_CHANGED"):
        task_context.derive_batch_context(
            VALID_TASK, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1], previous["scope_sha256"]
        )


def test_payroll_operation_id_length_limit_is_enforced():
    too_long_task = "task_" + "a" * 100
    with pytest.raises(task_context.ContextError, match="PAYROLL_ID_CONTRACT_EXCEEDED"):
        task_context.derive_batch_context(too_long_task, "2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1])


@pytest.mark.parametrize(
    ("month", "attendance_sha", "identity_sha", "person_ids", "error"),
    [
        ("2026-13", ATTENDANCE_SHA, IDENTITY_SHA, [1], "MONTH_INVALID"),
        ("2026-06", "bad", IDENTITY_SHA, [1], "ATTENDANCE_SHA256_INVALID"),
        ("2026-06", ATTENDANCE_SHA, "bad", [1], "IDENTITY_SHA256_INVALID"),
        ("2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [], "PERSON_IDS_REQUIRED"),
        ("2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [1, 1], "PERSON_ID_DUPLICATE"),
        ("2026-06", ATTENDANCE_SHA, IDENTITY_SHA, [True], "PERSON_ID_INVALID"),
    ],
)
def test_bad_batch_inputs_fail_closed(month, attendance_sha, identity_sha, person_ids, error):
    with pytest.raises(task_context.ContextError, match=error):
        task_context.derive_batch_context(VALID_TASK, month, attendance_sha, identity_sha, person_ids)


def test_cli_returns_machine_readable_context_and_never_authorization(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    turn = _turn(repo)
    result = _cli(
        "batch-id", "--repo-root", str(repo), "--turn-tmp-dir", str(turn), "--month", "2026-06",
        "--attendance-sha256", ATTENDANCE_SHA, "--identity-sha256", IDENTITY_SHA, "--payroll-person-ids", "[1,2]"
    )
    assert result.returncode == 0
    response = json.loads(result.stdout)
    assert response["task_id"] == VALID_TASK
    assert response["batch_id"] == f"{VALID_TASK}-2026-06"
    assert response["is_authorization_proof"] is False
    assert response["is_payroll_receipt"] is False


def test_task_discovery_does_not_call_or_trigger_payroll_writes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    turn = _turn(repo)
    result = _cli("discover", "--repo-root", str(repo), "--turn-tmp-dir", str(turn))
    assert result.returncode == 0
    assert "batch_id" not in json.loads(result.stdout)
