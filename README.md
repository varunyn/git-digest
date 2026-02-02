# git-digest

Fetch latest git updates (recent commits and releases/tags) from repositories you provide and generate a text summary. Designed to run as a **cron job** so you control how often it runs.

## Features

- **Configurable repos**: Provide a YAML config or a plain list of repo URLs.
- **Recent commits**: Per-repo list of last N commits with date, author, and subject.
- **Releases/tags**: Optional list of recent tags with date and message.
- **Cron-friendly**: Prints a single report to stdout (or to a file); you can pipe to `mail` or append to a log.
- **Caching**: Repos are cloned once into a cache directory; subsequent runs only `git fetch` and show the latest.
- **Changes-only mode** (`--changes-only`): When running daily (or on a schedule), only show **new** commits since last run. Repos with no new activity show "No new commits since last run." instead of repeating the same recent commits. State is stored in the cache directory.
- **AI summary** (`--ai-summary`): Use [Ollama](https://ollama.com/) on your Mac (or any host) to generate a short natural-language digest instead of a raw commit list. If Ollama is unreachable or the model is missing, the tool falls back to the plain report.
- **MCP server** ([FastMCP](https://github.com/jlowin/fastmcp)): Expose **get_git_updates** and **list_tracked_repos** as MCP tools so any MCP-capable AI (Cursor, Claude Desktop, etc.) can fetch your git update summary on demand.

## Install

From the project root (with [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

Then run:

```bash
uv run git-digest
# or
uv run python -m git_updates
```

To install the CLI globally in your environment:

```bash
uv pip install -e .
git-digest --help
```

## Configuration

Precedence: **CLI flags** > **environment / .env** > **repos.yaml** > built-in defaults.

### YAML config (recommended)

Create `repos.yaml` in the current directory or `~/.config/git-digest/repos.yaml` (see `repos.yaml.example`):

```yaml
# Optional: where to cache clones (default: ~/.cache/git-digest)
# cache_dir: ~/.cache/git-digest
# max_commits: 10
# default_title: My repo digest
# ollama_url: http://127.0.0.1:11434
# ollama_model: gemma3n
# ollama_timeout: 120

repos:
  - https://github.com/owner/repo.git
  - url: https://github.com/owner/other.git
    branch: main
    max_commits: 5
    include_tags: true
```

Or point to a config file:

```bash
uv run git-digest --config /path/to/repos.yaml
```

### Environment / .env (optional)

Copy `.env.example` to `.env` in the project directory or to `~/.config/git-digest/.env`. These override options in `repos.yaml` (CLI flags still override env):

| Variable | Purpose |
|----------|--------|
| `OLLAMA_BASE_URL` | Ollama API URL (default: `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | Model name for AI summary (default: `gemma3n`) |
| `OLLAMA_TIMEOUT` | Request timeout in seconds (default: `120`) |
| `GIT_DIGEST_CACHE_DIR` | Cache directory for clones |
| `GIT_DIGEST_DEFAULT_TITLE` | Default report title |

### Plain list of URLs

One repo URL per line in a text file:

```bash
uv run git-digest --repos repos.txt
uv run git-digest --repos repos1.txt --repos repos2.txt
```

## Usage

```bash
# Use default config (repos.yaml or ~/.config/git-digest/repos.yaml)
uv run git-digest

# Custom config and cache directory
uv run git-digest --config repos.yaml --cache-dir /tmp/git-cache

# Write report to a file
uv run git-digest --output ~/git-summary.txt

# Custom report title and verbose logging
uv run git-digest --title "Daily repo digest" --verbose

# Only show commits new since last run (for daily cron: no repeated "recent" lists)
uv run git-digest --changes-only

# AI digest via Ollama (requires Ollama running locally, e.g. ollama serve)
uv run git-digest --ai-summary
uv run git-digest --ai-summary --ollama-model mistral
uv run git-digest --ai-summary --ollama-url http://127.0.0.1:11434 --ollama-timeout 60
```
Default model is `gemma3n`. Use `ollama list` to see installed models; if the default is missing, use `--ollama-model <name>` or pull one: `ollama pull gemma3n`.

## MCP server

Run git-digest as an [MCP](https://modelcontextprotocol.io) server so any AI (Cursor, Claude Desktop, etc.) can call your summary on demand.

**Tools:**

- **get_git_updates** – Fetches latest git updates from your configured repos and returns the full report. Options: `config_path`, `changes_only`, `use_ai_summary`, `ollama_model`, `title`.
- **list_tracked_repos** – Returns the list of repo URLs from your config.

**Run the server:**

```bash
uv run git-digest-mcp
# or
uv run python -m git_updates.mcp
```

**Add to Cursor:** This repo includes **project-level** MCP config in [`.cursor/mcp.json`](.cursor/mcp.json). When you open the git-digest project in Cursor, the **git-digest** MCP server is available automatically (see [Cursor MCP docs](https://cursor.com/docs/context/mcp) — project config uses the folder that contains `.cursor/mcp.json`).

To add it **globally** (any workspace), edit `~/.cursor/mcp.json` and add:

```json
"git-digest": {
  "command": "uv",
  "args": ["--directory", "/path/to/git-digest", "run", "git-digest-mcp"]
}
```

Or use the FastMCP CLI from the project directory:

```bash
cd /path/to/git-digest
fastmcp run src/git_updates/mcp/server.py
```

Then ask your AI: *"What are my git updates?"* or *"Summarize my tracked repos."* The AI will call **get_git_updates** and use the returned report in its reply (and can summarize it further if you like).

## Cron setup

Run the script on a schedule and either append to a log or email the report.

**Example: run every day at 8:00 and append to a log**

```cron
0 8 * * * cd /path/to/git-digest && uv run git-digest --output /tmp/git-digest.txt && cat /tmp/git-digest.txt >> ~/logs/git-digest.log
```

**Example: daily run with only new commits** (recommended for daily cron)

```cron
0 8 * * * cd /path/to/git-digest && uv run git-digest --changes-only --output ~/git-digest.txt
```
Repos with no new activity show "No new commits since last run." instead of the same recent-commits list every time.

**Example: run every 6 hours and email the report** (requires `mail` or similar)

```cron
0 */6 * * * cd /path/to/git-digest && uv run git-digest | mail -s "Git digest" you@example.com
```

**Example: run weekly on Sunday at 9:00**

```cron
0 9 * * 0 cd /path/to/git-digest && uv run git-digest --output ~/weekly-git-summary.txt
```

Adjust the path to your project and how often you want updates (e.g. `0 * * * *` for every hour). The script is safe to run frequently; after the first clone it only runs `git fetch` and then formats the summary.

## Output example

**Default (recent commits):**

```
Git updates summary
===================

Generated: 2025-02-02 14:30

## owner/repo
  URL: https://github.com/owner/repo.git
  Branch: HEAD
  Recent commits:
    - 2025-02-02 14:00  abc1234  Jane: Bump version
    - 2025-02-01 10:22  def5678  Bob: Fix typo in README
  Recent tags/releases:
    - 2025-01-15 12:00  v1.2.0 (a1b2c3d)  — Release 1.2.0
```

**With `--changes-only`** (e.g. second run, no new commits):

```
## owner/repo
  URL: https://github.com/owner/repo.git
  Branch: HEAD
  No new commits since last run.
  Recent tags/releases:
    - 2025-01-15 12:00  v1.2.0 (a1b2c3d)  — Release 1.2.0
```

## License

MIT
