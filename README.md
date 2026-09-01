# git-digest

Fetch latest git updates (recent commits and releases/tags) from repositories you provide and generate a concise text, Markdown, or JSON digest. Designed to run as a **cron job** so you control how often it runs.

## Features

- **Configurable repos**: Provide a YAML config or a plain list of repo URLs.
- **Recent commits**: Per-repo list of last N commits with date, author, and subject.
- **Releases/tags**: Optional list of recent tags with date and message.
- **Cron-friendly**: Prints a single report to stdout (or to a file); you can pipe to `mail` or append to a log.
- **Caching**: Repos are cloned once into a cache directory; subsequent runs only `git fetch` and show the latest.
- **Changes-only mode** (`--changes-only`): When running daily (or on a schedule), only show **new** commits and **new** tags/releases since last run. Repos with no new activity show "No new commits since last run." and "No new tags since last run." instead of repeating the same recent lists. State (last-seen commit and tag names per repo) is stored in the cache directory.
- **AI summary** (`--ai-summary`): Use [Ollama](https://ollama.com/) on your Mac (or any host) to generate a short natural-language digest instead of a raw commit list. If Ollama is unreachable or the model is missing, the tool falls back to the plain report.
- **Automation-ready output**: Render text, Markdown, or stable versioned JSON; optionally POST the final report to a webhook.
- **MCP server** ([FastMCP v4](https://gofastmcp.com)): Expose **get_git_updates** and **list_tracked_repos** as MCP tools so any MCP-capable AI (Cursor, Claude Desktop, etc.) can fetch your git update summary on demand, locally over stdio or remotely over Streamable HTTP.

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

Create a commented starter config without overwriting an existing file:

```bash
uv run git-digest --init
# To use a different location: uv run git-digest --init /path/to/repos.yaml
# Replacing an existing file requires: uv run git-digest --init --force
```

Configuration is validated before fetching: repository URLs must be non-empty, commit
limits and timeouts must be positive, and the same repository cannot appear twice.

### Environment / .env (optional)

Copy `.env.example` to `.env` in the project directory or to `~/.config/git-digest/.env`. These override options in `repos.yaml` (CLI flags still override env):

| Variable | Purpose |
|----------|--------|
| `OLLAMA_BASE_URL` | Ollama API URL (default: `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | Model name for AI summary (default: `gemma3n`) |
| `OLLAMA_TIMEOUT` | Request timeout in seconds (default: `120`) |
| `GIT_DIGEST_CACHE_DIR` | Cache directory for clones |
| `GIT_DIGEST_DEFAULT_TITLE` | Default report title |

### Private repositories and secrets

Use Git's normal authentication rather than embedding credentials in `repos.yaml`.
For SSH URLs, ensure the scheduled user can access the appropriate SSH key. For HTTPS,
use a credential helper or a token supplied by your Git provider. Keep `.env` and any
credential files out of version control; `.env.example` contains only non-secret defaults.

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

# Render Markdown for chat or JSON for automation
uv run git-digest --format markdown
uv run git-digest --format json --output ~/git-summary.json

# Deliver the completed report to any HTTP webhook
uv run git-digest --changes-only --format json --webhook-url https://example.invalid/hooks/git-digest

# Let cron fail when a repository cannot be fetched
uv run git-digest --fail-on-error

# Custom report title and verbose logging
uv run git-digest --title "Daily repo digest" --verbose

# Only show commits and tags new since last run (for daily cron: no repeated "recent" lists)
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

- **get_git_updates** – Fetches latest git updates from your configured repos and returns the full report. Options: `config_path`, `changes_only`, `use_ai_summary`, `ollama_model`, `title`, `output_format`.
- **list_tracked_repos** – Returns the list of repo URLs from your config.
- **get_git_updates_data** – Returns the same update data as a structured FastMCP result for programmatic clients.
- **get_tracked_repositories** – Returns configured repository details as structured data.

**Resources:**

- `git-digest://tracked-repositories` – JSON snapshot of configured repositories.
- `git-digest://configuration-status` – JSON status confirming whether the active config can be loaded.

### Local stdio server

Stdio is the default transport and is the right choice when a desktop client starts and manages the server process.

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
fastmcp run src/git_updates/mcp/server.py:mcp
```

Then ask your AI: *"What are my git updates?"* or *"Summarize my tracked repos."* The AI will call **get_git_updates** and use the returned report in its reply (and can summarize it further if you like).

### Streamable HTTP server

FastMCP v4's `http` transport serves the Streamable HTTP MCP protocol. It is useful for a long-running local service, Docker, or a shared internal deployment. Start it with the FastMCP CLI:

```bash
cd /path/to/git-digest
fastmcp run src/git_updates/mcp/server.py:mcp --transport http --host 127.0.0.1 --port 8000
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. For example, a FastMCP client can connect with:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        result = await client.call_tool("list_tracked_repos", {})
        print(result)

asyncio.run(main())
```

FastMCP's `sse` transport is legacy; use `http` for new remote connections.

### Docker

Build the included image, then mount your configuration and a persistent cache directory. The image runs the Streamable HTTP server on port 8000.

```bash
docker build -t git-digest-mcp .
docker run --rm -p 8000:8000 \
  -v /path/to/repos.yaml:/data/repos.yaml:ro \
  -v git-digest-cache:/data/cache \
  git-digest-mcp
```

Call `get_git_updates` with `config_path` set to `/data/repos.yaml`. To persist change-tracking state, set `cache_dir: /data/cache` in that config. The server is then available at `http://localhost:8000/mcp`.

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
Repos with no new activity show "No new commits since last run." and "No new tags since last run." instead of repeating the same recent commits and tags every time.

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

**With `--changes-only`** (e.g. second run, no new commits or tags):

```
## owner/repo
  URL: https://github.com/owner/repo.git
  Branch: HEAD
  No new commits since last run.
  No new tags since last run.
```

## License

MIT
