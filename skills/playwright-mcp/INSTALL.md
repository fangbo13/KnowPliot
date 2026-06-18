# Installation Guide

The `@playwright/mcp` package is installed globally and ready to use.

## Quick Start

Run the MCP server:

```bash
npx @playwright/mcp --headless
```

## Configuration

Add the MCP server to your Codex configuration (`codex.json` or `.codex/config.json`):

```json
{
  "mcpServers": {
    "playwright-mcp": {
      "command": "npx",
      "args": ["@playwright/mcp", "--headless"]
    }
  }
}
```

## Available Tools

Once configured, Codex will have access to browser automation tools:
- `browser_navigate` - Navigate to a URL
- `browser_click` - Click an element
- `browser_type` - Type text into an input
- `browser_screenshot` - Take a screenshot
- `browser_read` - Read page content
- And more...

## Browser Installation

If you need specific browsers:

```bash
npx playwright install chromium
```
