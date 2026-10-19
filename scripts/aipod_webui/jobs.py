"""Run automation commands for a UI page and stream their redacted output to a log file."""

from __future__ import annotations

import asyncio
import json
import weakref
import os
import re
import shlex
import signal
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
MASK = "********"


@dataclass
class Job:
    id: str
    page: str
    label: str
    commands: list[list[str]]
    started: float
    log: str
    status: str = "running"
    returncode: int | None = None
    finished: float | None = None

    def display(self) -> str:
        return "\n".join("$ " + shlex.join(command) for command in self.commands)


@dataclass
class _Running:
    job: Job
    task: asyncio.Task
    process: asyncio.subprocess.Process | None = None
    cancelled: bool = False
    redact: list[str] = field(default_factory=list)


class JobManager:
    """One active job per page; history is kept as JSON next to the log files."""

    _instances: "weakref.WeakSet[JobManager]" = weakref.WeakSet()

    def __init__(self, root: Path, history: int = 25):
        self.root = Path(root)
        self.limit = history
        self._running: dict[str, _Running] = {}
        JobManager._instances.add(self)

    @classmethod
    def all_running(cls) -> list[Job]:
        """Jobs running on any page of any environment in this process."""
        return [entry.job for manager in list(cls._instances) for entry in manager._running.values()]

    def _index(self, page: str) -> Path:
        return self.root / page / "history.json"

    def history(self, page: str) -> list[Job]:
        jobs = [entry.job for entry in self._running.values() if entry.job.page == page]
        try:
            jobs += [Job(**item) for item in json.loads(self._index(page).read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            pass
        return jobs

    def running(self, page: str) -> Job | None:
        entry = self._running.get(page)
        return entry.job if entry else None

    def start(self, page: str, label: str, commands: list[list[str]], env: dict[str, str], cwd: Path,
              redact: list[str] = (), cleanup=None) -> Job:
        if page in self._running:
            raise RuntimeError(f"{self._running[page].job.label} is still running on this page")
        if not commands:
            raise ValueError("Nothing to run")
        folder = self.root / page
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        job_id = time.strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]
        job = Job(job_id, page, label, [list(map(str, command)) for command in commands], time.time(),
                  str(folder / f"{job_id}.log"))
        pieces = {part for value in redact for part in [value, *value.splitlines()] if len(part.strip()) >= 4}
        entry = _Running(job, None, redact=sorted(pieces, key=len, reverse=True))
        self._running[page] = entry
        entry.task = asyncio.get_running_loop().create_task(self._run(entry, env, Path(cwd), cleanup))
        return job

    def cancel(self, page: str) -> bool:
        entry = self._running.get(page)
        if not entry:
            return False
        entry.cancelled = True
        if entry.process and entry.process.returncode is None:
            try:
                os.killpg(entry.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        return True

    @staticmethod
    def read(job: Job, offset: int = 0, limit: int = 2_000_000) -> tuple[str, int]:
        try:
            with open(job.log, "rb") as stream:
                size = stream.seek(0, os.SEEK_END)
                start = max(offset, size - limit) if offset == 0 else offset
                stream.seek(start)
                data = stream.read()
        except OSError:
            return "", offset
        return data.decode("utf-8", "replace"), start + len(data)

    def _clean(self, entry: _Running, text: str) -> str:
        text = ANSI.sub("", text).replace("\r", "")
        for secret in entry.redact:
            text = text.replace(secret, MASK)
        return text

    async def _run(self, entry: _Running, env: dict[str, str], cwd: Path, cleanup) -> None:
        job = entry.job
        returncode = 0
        with open(job.log, "w", encoding="utf-8", buffering=1) as log:
            os.chmod(job.log, 0o600)
            log.write(f"# {job.label}\n# started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            try:
                for command in job.commands:
                    if entry.cancelled:
                        break
                    log.write(self._clean(entry, f"\n$ {shlex.join(command)}\n"))
                    try:
                        entry.process = await asyncio.create_subprocess_exec(
                            *command, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                            start_new_session=True, limit=1 << 20)
                    except OSError as error:
                        log.write(f"cannot start {command[0]}: {error}\n")
                        returncode = 127
                        break
                    while line := await entry.process.stdout.readline():
                        log.write(self._clean(entry, line.decode("utf-8", "replace")))
                    returncode = await entry.process.wait()
                    if returncode:
                        break
            except Exception as error:  # keep the UI alive and record why the job stopped
                log.write(f"\nrunner error: {error}\n")
                returncode = returncode or 1
            finally:
                if cleanup:
                    cleanup()
            job.status = "cancelled" if entry.cancelled else "succeeded" if returncode == 0 else "failed"
            job.returncode = returncode
            job.finished = time.time()
            log.write(f"\n# {job.status} (exit {returncode}) after {job.finished - job.started:.0f}s\n")
        self._running.pop(job.page, None)
        self._save(job)

    def _save(self, job: Job) -> None:
        index = self._index(job.page)
        try:
            items = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        items.insert(0, asdict(job))
        for stale in items[self.limit:]:
            Path(stale.get("log", "")).unlink(missing_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=index.parent, prefix=".history-")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(items[:self.limit], stream, indent=1)
        os.replace(temporary, index)
