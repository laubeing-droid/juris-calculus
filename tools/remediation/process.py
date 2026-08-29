"""UTF-8 strict subprocess execution for the V4 remediation runner.

Every child is captured as bytes and decoded with UTF-8 strictly, so Windows
locale code pages (for example GBK) can never reinterpret UTF-8 output from
Git or pytest, including repositories whose tracked paths contain Chinese.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import sys
import time

_CHILD_ENCODING = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
EXIT_COMMAND_NOT_FOUND = 127


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    duration_seconds: float
    utf8_valid: bool = True

    @property
    def passed(self) -> bool:
        return self.utf8_valid and not self.timed_out and self.exit_code == 0


def child_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return the parent environment plus deterministic UTF-8 child settings."""

    environment = os.environ.copy()
    environment.update(_CHILD_ENCODING)
    if extra:
        environment.update(extra)
    return environment


def expand_argv(
    argv: list[str] | tuple[str, ...], *, python: str, root: str, temp: str,
) -> list[str]:
    """Expand the runtime placeholders used by task plans."""

    return [
        item.replace("{python}", python).replace("{root}", root).replace("{temp}", temp)
        for item in argv
    ]


def run_command(
    argv: list[str] | tuple[str, ...],
    *,
    cwd: str | os.PathLike[str],
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run one command, capture bytes, and decode both streams as strict UTF-8."""

    started = time.monotonic()
    environment = env if env is not None else child_environment()
    try:
        completed = subprocess.run(
            list(argv), cwd=os.fspath(cwd), env=environment,
            capture_output=True, check=False, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        return CommandResult(
            argv=tuple(argv), exit_code=None, timed_out=True,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            duration_seconds=time.monotonic() - started,
        )
    except OSError as exc:
        return CommandResult(
            argv=tuple(argv), exit_code=EXIT_COMMAND_NOT_FOUND, timed_out=False,
            stdout="", stderr=f"{type(exc).__name__}: {exc}",
            duration_seconds=time.monotonic() - started,
        )
    try:
        stdout = completed.stdout.decode("utf-8", errors="strict")
        stderr = completed.stderr.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return CommandResult(
            argv=tuple(argv), exit_code=completed.returncode, timed_out=False,
            stdout=completed.stdout.decode("utf-8", errors="replace"),
            stderr=(
                f"child output is not strict UTF-8: {exc}\n"
                + completed.stderr.decode("utf-8", errors="replace")
            ),
            duration_seconds=time.monotonic() - started,
            utf8_valid=False,
        )
    return CommandResult(
        argv=tuple(argv), exit_code=completed.returncode, timed_out=False,
        stdout=stdout, stderr=stderr,
        duration_seconds=time.monotonic() - started,
    )


def git_text(root: str | os.PathLike[str], *args: str) -> str:
    """Run a Git command in root and return its strict UTF-8 stdout."""

    result = run_command(
        ["git", *args], cwd=root, timeout_seconds=120,
        env=child_environment({"GIT_CONFIG_NOSYSTEM": "1"}),
    )
    if result.exit_code != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.exit_code}): {result.stderr.strip()}"
        )
    return result.stdout


def git_tracked_paths(root: str | os.PathLike[str], *spec: str) -> list[str]:
    """List tracked paths with core.quotepath disabled, decoded as UTF-8."""

    payload = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z", "--", *spec],
        cwd=os.fspath(root), capture_output=True, check=True,
    ).stdout
    return sorted(
        item.decode("utf-8", errors="strict").replace("\\", "/")
        for item in payload.split(b"\0") if item
    )
