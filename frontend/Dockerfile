# V4.6: The frontend image builds from source inside the container. Stage 1
# (builder) runs `vite build`, and Stage 2 (final) copies that dist into nginx.
# The served bundle therefore always matches the source tree and never depends
# on a host-prebuilt dist/ — this removes the prior Windows-BuildKit workaround
# that copied a host dist/ (which could be stale or missing on CI / other
# machines, causing blank capability-console routes and other stale-bundle
# symptoms).
#
# Usage:
#   docker compose build frontend        # builds in-container, reproducible
#   docker compose up -d frontend
#
# Note: Docker BuildKit uses the build context as staged/committed content.
# If you have unstaged frontend changes, commit or stage them before building so
# the in-container `vite build` sees the current source.

# ── Stage 1: Builder (builds dist/ from source) ──
FROM node:20-slim AS builder

# Vite env vars must be present at build time so they are baked into the bundle.
# Pass via docker-compose build args or --build-arg.
ARG VITE_CAPABILITY_NAV=true
ARG VITE_WORKSPACE_PERMANENT_DELETE=true
ARG VITE_DEEP_ANSWER_MODE=false
ARG VITE_THINKING_MODE=false
ARG VITE_WORKSPACE_CREATION_APPROVAL=false
ARG VITE_WORKSPACE_JOIN_V2=true
ENV VITE_CAPABILITY_NAV=$VITE_CAPABILITY_NAV
ENV VITE_WORKSPACE_PERMANENT_DELETE=$VITE_WORKSPACE_PERMANENT_DELETE
ENV VITE_DEEP_ANSWER_MODE=$VITE_DEEP_ANSWER_MODE
ENV VITE_THINKING_MODE=$VITE_THINKING_MODE
ENV VITE_WORKSPACE_CREATION_APPROVAL=$VITE_WORKSPACE_CREATION_APPROVAL
ENV VITE_WORKSPACE_JOIN_V2=$VITE_WORKSPACE_JOIN_V2

WORKDIR /app

COPY package.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set strict-ssl false \
    && PUPPETEER_SKIP_DOWNLOAD=true npm install

COPY . .
RUN npx vite build

# ── Stage 2: Serve the built dist via nginx (reproducible from source) ──
FROM nginx:alpine AS final

# V4.2 SYS-V4.2-011: nginx config for SPA + API proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

# dist/ is produced by Stage 1's `vite build` — never copied from the host.
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
