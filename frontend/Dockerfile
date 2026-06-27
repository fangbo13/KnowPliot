# V4.6 FIX: Docker BuildKit on Windows uses git-tracked content as build context,
# ignoring unstaged working-directory changes → vite build inside Docker always
# produces stale JS bundles.  Fix: pre-build on host, just copy dist into nginx.
#
# Usage:
#   cd frontend && npx vite build          # build locally first
#   docker compose build frontend          # then build image (fast, no npm install)
#   docker compose up -d frontend          # deploy
#
# Old multi-stage builder is kept as a fallback (stage name "builder") so CI
# pipelines that prefer in-container builds can still use:
#   docker build --target final-alt frontend/

# ── Stage 1: Builder (fallback for CI — NOT used by default) ──
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set strict-ssl false \
    && PUPPETEER_SKIP_DOWNLOAD=true npm install

COPY . .
RUN npx vite build

# ── Stage 2: Serve pre-built dist (primary — fast, reliable) ──
FROM nginx:alpine AS final

# V4.2 SYS-V4.2-011: nginx config for SPA + API proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy locally pre-built dist/ — this is the primary path.
# Requires `npx vite build` to have been run on the host beforehand.
COPY dist/ /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

# ── Stage 3: Serve in-container build (fallback for CI) ──
FROM nginx:alpine AS final-alt

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
