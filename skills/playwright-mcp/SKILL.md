---
name: playwright-mcp
description: Browser automation using Playwright MCP server for web testing, scraping, navigation, and interaction tasks.
metadata:
  short-description: Playwright MCP browser automation
---

# Playwright MCP Skill

Browser automation skill powered by the `@playwright/mcp` server. Provides tools for navigating web pages, interacting with elements, extracting data, taking screenshots, and debugging web applications.

## Setup

Install the MCP server globally:

```bash
npm install -g @anthropic-ai/mcp-client
npx @anthropic-ai/mcp-client install @playwright/mcp
```

Or run it directly via npx:

```bash
npx @playwright/mcp
```

## Usage

Use the Playwright MCP tools for:
- Navigating to URLs
- Clicking buttons and links
- Filling forms and inputs
- Taking screenshots
- Extracting text and data from pages
- Testing web applications
- Debugging UI issues

### Example Commands
```bash
# Navigate to a page
# Fill a form
# Take a screenshot
```

## Configuration

The MCP server can be configured in Codex via the `codex.json` or `.codex` configuration to register the `@playwright/mcp` server as an available tool provider.
---
name: playwright-mcp
description: Browser automation using Playwright MCP server for web testing, scraping, navigation, and interaction tasks.
metadata:
  short-description: Playwright MCP browser automation
---

# Playwright MCP Skill

Browser automation skill powered by the `@playwright/mcp` server. Provides tools for navigating web pages, interacting with elements, extracting data, taking screenshots, and debugging web applications.

## Setup

The MCP server is installed globally. Run it directly via:

```bash
npx @playwright/mcp --headless
```

## Usage

Use the Playwright MCP tools for:
- Navigating to URLs
- Clicking buttons and links
- Filling forms and inputs
- Taking screenshots
- Extracting text and data from pages
- Testing web applications
- Debugging UI issues

## Configuration

Add to your Codex configuration to enable these tools automatically:

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
