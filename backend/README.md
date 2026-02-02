# Open MCP Skills

Cloud-native MCP Server for Claude Skills as a Service.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Run the server
python -m app.main
```

## API Endpoints

- `POST /mcp` - MCP Streamable HTTP endpoint
- `GET /health` - Health check
- `GET /admin/skills` - List all skills
