#!/usr/bin/env python3
"""Switch per-project skills, MCP servers and GitNexus on or off from `project-sets.json`.

    python3 scripts/project_sets.py        # npm run sets:apply (then gates:apply re-renders the rule)

`project-sets.json` holds three switches. `gitnexus: true` is the code-repo switch: the GitNexus
server, its two skills and one relaxed rule in `.ruler/AGENTS.md`. `skills` names skill sets
(folders under the record's `skills/`, e.g. `cad-kicad`, `figma`, `image-pipeline`); `mcp` names
project servers (`mcp/<server>/project.toml` in the record, e.g. `kicad`, `figma`).

What it writes, and removes again when a switch goes off:
  .claude/skills/<skill>, .agents/skills/<skill>   links into the record, for Claude Code and Codex
  .mcp.json                                        Claude Code's project servers
  .codex/config.toml                               Codex's project servers (loaded once the project is trusted)
  .ruler/AGENTS.md                                 the GitNexus rule between its two markers
The record is ~/agentic-workflow (AGENTIC_WORKFLOW overrides it). Hand-made links and files outside
these are left alone.
"""
import json
import os
import sys
import tomllib
from pathlib import Path

SWITCHES = Path("project-sets.json")
SKILL_ROOTS = (Path(".claude/skills"), Path(".agents/skills"))
CLAUDE_MCP = Path(".mcp.json")
CODEX_CONFIG = Path(".codex/config.toml")
RULER_SOURCE = Path(".ruler/AGENTS.md")
RULE_START = "<!-- gitnexus:start — written by scripts/project_sets.py from project-sets.json -->"
RULE_END = "<!-- gitnexus:end -->"
RULE = (
    "## GitNexus\n\n"
    "This repository is indexed by GitNexus: use it to find your way in unfamiliar code, and check with it "
    "before renaming, deleting or moving something other code depends on. "
    "`node .gitnexus/run.cjs analyze --index-only` refreshes the index.\n"
)


def read_switches(root: Path) -> tuple[list[str], list[str], bool]:
    switches = json.loads((root / SWITCHES).read_text())
    gitnexus = bool(switches.get("gitnexus", False))
    skills = list(switches.get("skills", [])) + (["gitnexus"] if gitnexus else [])
    mcp = list(switches.get("mcp", [])) + (["gitnexus"] if gitnexus else [])
    return skills, mcp, gitnexus


def skill_sets(record: Path) -> dict[str, list[Path]]:
    sets = {}
    for folder in sorted(p for p in (record / "skills").iterdir() if p.is_dir()):
        skills = sorted(p for p in folder.iterdir() if (p / "SKILL.md").exists())
        if skills:  # `upstream-locks/` and the like hold no skill, so they name no set
            sets[folder.name] = skills
    return sets


def project_servers(record: Path) -> dict[str, dict]:
    return {p.parent.name: tomllib.loads(p.read_text())["mcp_servers"][p.parent.name]
            for p in sorted((record / "mcp").glob("*/project.toml"))}


def check_names(kind: str, wanted: list[str], known: dict) -> None:
    unknown = sorted(set(wanted) - set(known))
    if unknown:
        sys.exit(f"{kind}: unknown {', '.join(unknown)}; the record has {', '.join(sorted(known))}")


def prune_empty(*folders: Path) -> None:
    """Remove each folder nothing is left in, innermost first; a folder with anything in it stays."""
    for folder in folders:
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()


def link_skills(root: Path, record: Path, wanted: list[Path]) -> None:
    for skill_root in SKILL_ROOTS:
        folder = root / skill_root
        if folder.exists():
            for link in folder.iterdir():  # ours go; a hand-made link or folder stays
                if link.is_symlink() and (record / "skills") in link.resolve().parents:
                    link.unlink()
        if wanted:
            folder.mkdir(parents=True, exist_ok=True)
        for skill in wanted:
            (folder / skill.name).symlink_to(skill)
        prune_empty(folder, folder.parent)  # `.claude/skills`, then `.claude`


def claude_form(server: dict) -> dict:
    return {"type": "http", **server} if "url" in server else {"type": "stdio", **server}


def toml_value(value) -> str:
    return json.dumps(value)  # strings and string arrays: JSON is valid TOML for both


def write_servers(root: Path, wanted: dict[str, dict]) -> None:
    claude = root / CLAUDE_MCP
    codex = root / CODEX_CONFIG
    if not wanted:
        claude.unlink(missing_ok=True)
        codex.unlink(missing_ok=True)
        prune_empty(codex.parent)  # `.codex`
        return
    claude.write_text(json.dumps({"mcpServers": {name: claude_form(s) for name, s in wanted.items()}}, indent=2) + "\n")
    lines = ["# Written by scripts/project_sets.py from project-sets.json; edit that file, not this one."]
    for name, server in wanted.items():
        lines += ["", f"[mcp_servers.{name}]"]
        lines += [f"{key} = {toml_value(value)}" for key, value in server.items() if key != "env"]
        if "env" in server:
            lines += ["", f"[mcp_servers.{name}.env]"]
            lines += [f"{key} = {toml_value(value)}" for key, value in server["env"].items()]
    codex.parent.mkdir(parents=True, exist_ok=True)
    codex.write_text("\n".join(lines) + "\n")


def write_rule(root: Path, on: bool) -> None:
    source = root / RULER_SOURCE
    text = source.read_text()
    if RULE_START in text:
        head, _, tail = text.partition(RULE_START)
        text = head.rstrip("\n") + "\n" + tail.partition(RULE_END)[2].lstrip("\n")
    if on:
        text = text.rstrip("\n") + f"\n\n{RULE_START}\n{RULE}{RULE_END}\n"
    source.write_text(text)


def apply(root: Path, record: Path) -> None:
    record = record.resolve()  # links are compared against their resolved target, so the record must be one too
    skills, mcp, gitnexus = read_switches(root)
    sets, servers = skill_sets(record), project_servers(record)
    check_names("skills", skills, sets)
    check_names("mcp", mcp, servers)
    link_skills(root, record, [skill for name in skills for skill in sets[name]])
    write_servers(root, {name: servers[name] for name in mcp})
    write_rule(root, gitnexus)


if __name__ == "__main__":
    apply(Path.cwd(), Path(os.environ.get("AGENTIC_WORKFLOW", "~/agentic-workflow")).expanduser())
    print("project sets applied; `npm run gates:apply` re-renders AGENTS.md and CLAUDE.md")
