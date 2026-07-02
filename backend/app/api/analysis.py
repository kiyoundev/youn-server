import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings

_log = logging.getLogger(__name__)

router = APIRouter()

_GIT_TIMEOUT_SECONDS = 60
_PIP_TIMEOUT_SECONDS = 300


async def _communicate_with_timeout(
    process: asyncio.subprocess.Process, timeout: int, label: str
) -> tuple[int, str]:
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return 1, f"{label} timed out after {timeout}s"
    return process.returncode, (stdout + stderr).decode(errors="replace").strip()


async def _run_git(*args: str) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=settings.tradingagents_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return await _communicate_with_timeout(
        process, _GIT_TIMEOUT_SECONDS, f"git {' '.join(args)}"
    )


@router.get("/api/analysis/tradingagents/version")
async def get_tradingagents_version() -> dict:
    if not os.path.isdir(settings.tradingagents_path):
        return {"available": False}

    fetch_code, fetch_output = await _run_git("fetch", "origin")
    if fetch_code != 0:
        _log.error("tradingagents version: git fetch failed: %s", fetch_output)
        return {"available": False, "error": fetch_output}

    _, current_commit = await _run_git("rev-parse", "HEAD")
    _, latest_commit = await _run_git("rev-parse", "origin/main")
    _, current_date = await _run_git("log", "-1", "--format=%cI", "HEAD")
    _, latest_date = await _run_git("log", "-1", "--format=%cI", "origin/main")
    _, behind_count_raw = await _run_git("rev-list", "HEAD..origin/main", "--count")

    behind_count = int(behind_count_raw)
    return {
        "current_commit": current_commit,
        "current_date": current_date,
        "latest_commit": latest_commit,
        "latest_date": latest_date,
        "behind_count": behind_count,
        "update_available": behind_count > 0,
    }


@router.post("/api/analysis/tradingagents/update")
async def update_tradingagents() -> dict:
    pull_code, pull_output = await _run_git("pull")
    if pull_code != 0:
        _log.error("tradingagents update: git pull failed: %s", pull_output)
        return {"success": False, "new_commit": None, "output": pull_output}

    venv_pip = str(Path(settings.tradingagents_venv_python).parent / "pip")
    pip_process = await asyncio.create_subprocess_exec(
        venv_pip,
        "install",
        "-r",
        "requirements.txt",
        cwd=settings.tradingagents_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    pip_returncode, pip_output = await _communicate_with_timeout(
        pip_process, _PIP_TIMEOUT_SECONDS, "pip install"
    )
    combined_output = f"{pull_output}\n{pip_output}"

    if pip_returncode != 0:
        _log.error("tradingagents update: pip install failed: %s", pip_output)
        return {"success": False, "new_commit": None, "output": combined_output}

    _, new_commit = await _run_git("rev-parse", "HEAD")
    return {"success": True, "new_commit": new_commit, "output": combined_output}
