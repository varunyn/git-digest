FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

# FastMCP's HTTP transport implements the Streamable HTTP MCP protocol at /mcp.
CMD ["fastmcp", "run", "src/git_updates/mcp/server.py:mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
