#!/usr/bin/env bash
# Setup script for Playwright MCP skill
set -euo pipefail

echo "Installing @anthropic-ai/mcp-client..."
npm install -g @anthropic-ai/mcp-client

echo "Installing Playwright MCP server..."
npx @anthropic-ai/mcp-client install @playwright/mcp

echo "Installing Playwright browsers..."
npx playwright install chromium

echo "Playwright MCP skill setup complete."
