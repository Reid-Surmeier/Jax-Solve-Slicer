#!/usr/bin/env node
// Project .ruler/AGENTS.md into the committed root AGENTS.md and CLAUDE.md with the pinned Ruler.
//   node scripts/gates.mjs          # write AGENTS.md and CLAUDE.md          (npm run gates:apply)
//   node scripts/gates.mjs --check  # exit 1 if either is stale, write nothing (npm run gates:check)
// Both modes render into a scratch folder that holds only a copy of .ruler/, so the root files are
// never read back in as a source and the same bytes come out every time. Ruler's other features are
// switched off on the command line here and in .ruler/ruler.toml; it must not own backups, .gitignore,
// MCP config, skills, subagents, or nested rules in a repository that follows the agentic-workflow pattern.
import { spawnSync } from "node:child_process"
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { createRequire } from "node:module"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"

const SOURCE_DIR = ".ruler"
const GENERATED = ["AGENTS.md", "CLAUDE.md"]
const RULER_FLAGS = ["--local-only", "--agents", "agentsmd,claude", "--no-nested", "--no-mcp", "--no-skills",
  "--no-subagents", "--no-backup", "--no-gitignore"]
const rulerCli = join(dirname(createRequire(import.meta.url).resolve("@intellectronica/ruler/package.json")), "dist/cli/index.js")

function render() {
  if (!existsSync(join(SOURCE_DIR, "AGENTS.md"))) throw new Error(`${SOURCE_DIR}/AGENTS.md is missing — it is the source of the gates`)
  const scratch = mkdtempSync(join(tmpdir(), "gates-"))
  try {
    cpSync(SOURCE_DIR, join(scratch, SOURCE_DIR), { recursive: true })
    const run = spawnSync(process.execPath, [rulerCli, "apply", "--project-root", scratch, ...RULER_FLAGS], { encoding: "utf8" })
    if (run.status !== 0) throw new Error(`ruler apply failed (exit ${run.status})\n${run.stdout}${run.stderr}`)
    return Object.fromEntries(GENERATED.map((name) => [name, readFileSync(join(scratch, name))]))
  } finally {
    rmSync(scratch, { recursive: true, force: true })
  }
}

const rendered = render()
if (process.argv.includes("--check")) {
  const stale = GENERATED.filter((name) => !existsSync(name) || !readFileSync(name).equals(rendered[name]))
  if (stale.length) { console.error(`${stale.join(" and ")} stale — run \`npm run gates:apply\``); process.exit(1) }
  console.log(`${GENERATED.join(" and ")} are current`)
} else {
  for (const name of GENERATED) writeFileSync(name, rendered[name])
  console.log(`wrote ${GENERATED.join(" and ")} from ${SOURCE_DIR}/`)
}
