# Setup script for Playwright MCP skill (Windows)
Write-Host "Installing @anthropic-ai/mcp-client..." -ForegroundColor Cyan
npm install -g @anthropic-ai/mcp-client

Write-Host "Installing Playwright MCP server..." -ForegroundColor Cyan
npx @anthropic-ai/mcp-client install @playwright/mcp

Write-Host "Installing Playwright browsers..." -ForegroundColor Cyan
npx playwright install chromium

Write-Host "Playwright MCP skill setup complete." -ForegroundColor Green
