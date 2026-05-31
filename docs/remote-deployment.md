# Remote Deployment via Docker + Tailscale

Deploy the intervals-icu-mcp server on a NAS or remote host for access from Claude Desktop, Claude Code, or any MCP client.

## Architecture

```
Claude Desktop / Claude Code (anywhere)
    |
    v  Tailscale VPN (encrypted)
    |
NAS / Remote Host
    |-- Docker: intervals-icu-mcp (Streamable HTTP on port 8765)
    |-- Tailscale Serve/Funnel (HTTPS termination)
    |
    v
intervals.icu API (HTTPS)
```

## Prerequisites

- Docker host (NAS, VPS, home server, etc.)
- Docker and Docker Compose
- Your Intervals.icu API key and athlete ID
- Tailscale account (free at https://tailscale.com)

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/eddmann/intervals-icu-mcp.git
cd intervals-icu-mcp
```

Create a `.env` file with your credentials (see `.env.example`):

```bash
INTERVALS_ICU_API_KEY=your_api_key_here
INTERVALS_ICU_ATHLETE_ID=your_athlete_id_here
```

### 2. Build and start

```bash
docker compose up -d --build
```

Verify it's running:

```bash
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}},"id":1}'
```

### 3. Expose via Tailscale

Install Tailscale on your Docker host and authenticate.

**For access from your own devices only (Tailscale Serve):**

```bash
tailscale serve --bg --https=8443 http://localhost:8765
```

**For access from cloud services like claude.ai (Tailscale Funnel):**

```bash
tailscale funnel --bg --https=443 http://localhost:8765
```

Funnel exposes the server to the public internet via Tailscale's HTTPS proxy. This is required for services like claude.ai whose servers are not on your Tailnet.

### 4. Connect Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://YOUR-HOST.YOUR-TAILNET.ts.net/mcp"
      ]
    }
  }
}
```

Replace the URL with your Tailscale hostname (find it with `tailscale status`).

## Transport

The server uses Streamable HTTP transport when deployed via Docker (configured via `MCP_TRANSPORT=streamable-http` in `docker-compose.yml`). The default stdio transport is used when running locally.

## Synology NAS Notes

- The DS224+ (Intel J4125) and similar x86_64 NAS models work out of the box
- Use Container Manager's Project feature to manage the docker-compose deployment
- Install Tailscale from Package Center
- Use Task Scheduler to run `tailscale serve` or `tailscale funnel` at boot (user: root)
- The Dockerfile removes `--platform=$TARGETPLATFORM` for compatibility with Synology's Docker version

## Maintenance

```bash
# Update
git pull
docker compose up -d --build

# View logs
docker compose logs -f

# Restart
docker compose restart

# Stop
docker compose down
```
