#!/usr/bin/env python3
"""
Pipeline: fetch MR → run code review agent in mr-bot → copy review to target repo
→ checkout branch → run fix agent in target repo → prompt to review changes.

Configure via pipeline_config.yaml (see pipeline_config.yaml.example).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]

from rich.console import Console  # type: ignore[import-untyped]
from rich.panel import Panel  # type: ignore[import-untyped]
from rich.rule import Rule  # type: ignore[import-untyped]

console = Console()
console_stderr = Console(file=sys.stderr)


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load pipeline config from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}. Copy pipeline_config.yaml.example to pipeline_config.yaml.")
    if yaml is None:
        raise ImportError("PyYAML is required for the pipeline. Install with: uv add pyyaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML object.")
    return data


def resolve_path(raw: str) -> Path:
    """Expand user and resolve to absolute path."""
    return Path(raw).expanduser().resolve()


def get_repo_name_from_project_id(project_id: str) -> str:
    """Derive repo directory name from GitLab project ID (last segment)."""
    return project_id.strip().rstrip("/").split("/")[-1]


def get_branch_from_mr_info(output_dir: Path, mr: int) -> str | None:
    """Parse source branch from output/MR_{mr}_info.md."""
    info_path = output_dir / f"MR_{mr}_info.md"
    if not info_path.exists():
        return None
    text = info_path.read_text(encoding="utf-8")
    match = re.search(r"\*\*Source Branch\*\*:\s*`([^`]+)`", text)
    return match.group(1).strip() if match else None


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command; raise on non-zero exit if check=True."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        cwd=cwd or None,
        env=full_env,
        check=check,
        text=True,
    )


def _format_path(path: str, max_len: int = 60) -> str:
    """Truncate path for display."""
    if len(path) <= max_len:
        return path
    return "..." + path[-(max_len - 3) :]


def _handle_stream_event(event: dict[str, Any]) -> bool:  # noqa: C901
    """Handle one stream-json event; print progress. Return True if result/success (done)."""
    event_type = event.get("type")
    subtype = event.get("subtype")

    if event_type == "system" and subtype == "init":
        model = event.get("model", "agent")
        console.print(f"  [dim]Agent started[/] ([cyan]{model}[/])")
    elif event_type == "tool_call" and subtype == "started":
        tc = event.get("tool_call") or {}
        if "readToolCall" in tc:
            path = (tc["readToolCall"].get("args") or {}).get("path", "?")
            console.print(f"  [dim]📖 Reading[/] [cyan]{_format_path(path)}[/]")
        elif "writeToolCall" in tc:
            path = (tc["writeToolCall"].get("args") or {}).get("path", "?")
            console.print(f"  [dim]✏️  Writing[/] [cyan]{_format_path(path)}[/]")
        else:
            console.print("  [dim]🔧 Tool call…[/]")
    elif event_type == "tool_call" and subtype == "completed":
        tc = event.get("tool_call") or {}
        if "writeToolCall" in tc:
            res = (tc["writeToolCall"].get("result") or {}).get("success")
            if isinstance(res, dict) and res.get("linesCreated") is not None:
                console.print(f"     [green]✓[/] [dim]{res['linesCreated']} lines[/]")
            else:
                console.print("     [green]✓[/]")
        else:
            console.print("     [green]✓[/]")
    elif event_type == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    preview = text[:80].replace("\n", " ")
                    if len(text) > 80:
                        preview += "…"
                    console.print(f"  [dim]💬[/] [dim]{preview}[/]")
                break
    elif event_type == "result" and subtype == "success":
        duration_ms = event.get("duration_ms") or 0
        console.print(f"  [green]✓[/] [dim]Complete ({duration_ms / 1000:.1f}s)[/]")
        return True
    return False


def run_agent_with_progress(
    cursor_cli: str,
    prompt: str,
    cwd: Path,
    *,
    apply_force: bool = True,
) -> None:
    """Run Cursor agent with stream-json and print human-readable progress."""
    cmd = [cursor_cli, "-p", "--output-format", "stream-json"]
    if apply_force:
        cmd.append("--force")
    cmd.append(prompt)

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=os.environ,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None

    with proc:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                _handle_stream_event(event)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "pipeline_config.yaml"
    config = load_config(config_path)

    project_id = config.get("project_id")
    mr = config.get("mr")
    if not project_id or mr is None:
        console_stderr.print("[bold red]Error:[/] config must set [cyan]project_id[/] and [cyan]mr[/].")
        sys.exit(1)

    output_dir_raw = config.get("output", "./output")
    workspace_root = resolve_path(config.get("workspace_root", "~/workspace"))
    repo_name = config.get("repo_name") or get_repo_name_from_project_id(project_id)
    branch = config.get("branch")
    cursor_cli = config.get("cursor_cli", "agent")
    apply_fixes = config.get("apply_fixes", True)

    output_dir = (script_dir / output_dir_raw).resolve()
    target_repo = workspace_root / repo_name
    code_review_src = output_dir / "code_review.md"

    console.print()
    console.print(Rule("[bold blue]MR Bot Pipeline[/]", style="blue"))
    console.print()

    # wipe output dir so we start fresh each run
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"  [dim]Cleared output directory:[/] [cyan]{output_dir}[/]\n")

    # 1) Run main.py
    console.print(
        Panel(
            "[bold cyan]Step 1[/] Running [cyan]main.py[/] to fetch MR and generate diffs…",
            style="dim",
            border_style="cyan",
        )
    )
    run_cmd(
        [sys.executable, "main.py", "--project-id", project_id, "--mr", str(mr), "--output", str(output_dir)],
        cwd=script_dir,
    )
    console.print("  [green]✓[/] Diffs and review prompt generated\n")

    # 2) Resolve branch if not in config
    if not branch:
        branch = get_branch_from_mr_info(output_dir, mr)
        if not branch:
            console.print(
                "[bold red]Error:[/] Could not determine source branch. Set [cyan]branch[/] in pipeline_config.yaml."
            )
            sys.exit(1)
        console.print(f"  [dim]Using source branch from MR info:[/] [bold]{branch}[/]\n")
    else:
        console.print(f"  [dim]Using branch from config:[/] [bold]{branch}[/]\n")

    # 3) Run Cursor agent in mr-bot for code review
    review_prompt = (
        "Do a code review per @output/review_prompt.md. Note that the diff files are in the @output/diffs folder."
    )
    console.print(
        Panel(
            "[bold cyan]Step 2[/] Running Cursor agent in mr-bot for code review…",
            style="dim",
            border_style="cyan",
        )
    )
    run_agent_with_progress(cursor_cli, review_prompt, script_dir, apply_force=True)
    console.print("")

    if not code_review_src.exists():
        console.print("[bold red]Error:[/] [cyan]code_review.md[/] was not created. Check agent output.")
        sys.exit(1)

    # 4) Copy code_review.md to target repo
    console.print(
        Panel(
            "[bold cyan]Step 3[/] Copying [cyan]code_review.md[/] to target repo…",
            style="dim",
            border_style="cyan",
        )
    )
    target_repo.mkdir(parents=True, exist_ok=True)
    code_review_dst = target_repo / "code_review.md"
    shutil.copy2(code_review_src, code_review_dst)
    console.print(f"  [green]→[/] [dim]{code_review_dst}[/]\n")

    # 5) Checkout branch in target repo (stash local changes if any)
    console.print(
        Panel(
            "[bold cyan]Step 4[/] Checking out MR branch in target repo…",
            style="dim",
            border_style="cyan",
        )
    )
    if not (target_repo / ".git").exists():
        console.print(f"[bold red]Error:[/] Target repo is not a git repo: [cyan]{target_repo}[/]")
        sys.exit(1)
    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=target_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    had_changes = bool(status_result.stdout.strip())
    actually_stashed = False
    if had_changes:
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "mr-bot pipeline: stashed before checkout"],
            cwd=target_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        # git stash push prints "No local changes to save" when there was nothing to stash (e.g. only untracked)
        combined = (stash_result.stdout or "") + (stash_result.stderr or "")
        actually_stashed = "No local changes to save" not in combined
        if actually_stashed:
            console.print("  [yellow]⚠[/] Local changes were [yellow]stashed[/] so the branch could be checked out.")
    run_cmd(["git", "fetch", "origin", branch], cwd=target_repo, check=False)
    run_cmd(["git", "checkout", branch], cwd=target_repo)
    if actually_stashed:
        console.print("  [dim]To restore later:[/] [cyan]git stash pop[/]\n")
    else:
        console.print("  [green]✓[/] Checked out [bold]{0}[/]\n".format(branch))

    # 6) Run Cursor agent in target repo to fix code
    fix_prompt = "Fix the code per @code_review.md"
    console.print(
        Panel(
            "[bold cyan]Step 5[/] Running Cursor agent in target repo to apply fixes…",
            style="dim",
            border_style="cyan",
        )
    )
    run_agent_with_progress(cursor_cli, fix_prompt, target_repo, apply_force=apply_fixes)
    console.print("")

    # 7) Instructions for manual review
    review_lines = [
        "[bold]Review suggested changes:[/]",
        "",
        f"  [cyan]cd[/] [green]{target_repo}[/]",
        "  [cyan]git status[/]",
        "  [cyan]git diff[/]",
    ]
    if actually_stashed:
        review_lines.append("")
        review_lines.append("  [dim](Your earlier local changes were stashed. Restore with: [cyan]git stash pop[/])")
    review_lines.append("")
    review_lines.append("[dim]Then commit, amend, or revert as needed.[/]")

    console.print(
        Panel(
            "\n".join(review_lines),
            title="[bold green]Pipeline complete[/]",
            border_style="green",
        )
    )
    console.print()


if __name__ == "__main__":
    main()
