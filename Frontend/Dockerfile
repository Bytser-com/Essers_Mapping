# syntax=docker/dockerfile:1

# ==============================================================================
# Stage 1: Build the React (Vite) application
# ==============================================================================
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy application source and build production bundle
COPY . .
ENV NODE_ENV=production
RUN npm run build

# ==============================================================================
# Stage 2: Production runtime using official Nginx Alpine
# ==============================================================================
FROM nginx:1.27-alpine AS production

LABEL org.opencontainers.image.title="Essers Mapping Frontend" \
      org.opencontainers.image.description="Production React 19 frontend and API reverse proxy served via non-root Nginx"

# Default backend URL for /api/proposal (override at runtime via -e or K8s env)
ENV PROPOSAL_API_URL=http://mapping-proposal-service:8000
# Enable Nginx's built-in resolver auto-detection from /etc/resolv.conf (CoreDNS / Docker DNS)
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
# Restrict envsubst to only replace PROPOSAL_* and NGINX_LOCAL_RESOLVERS, preserving Nginx $vars
ENV NGINX_ENVSUBST_FILTER="^(PROPOSAL_|NGINX_LOCAL_RESOLVERS)"

# Apply latest Alpine security patches and configure Nginx for non-root execution (UID/GID 101)
RUN apk upgrade --no-cache \
    && sed -i 's,^\(user .*;\),# \1,' /etc/nginx/nginx.conf \
    && sed -i 's,/run/nginx.pid,/tmp/nginx.pid,' /etc/nginx/nginx.conf \
    && mkdir -p /etc/nginx/templates \
    && rm -rf /etc/nginx/conf.d/default.conf /usr/share/nginx/html/* \
    && chown -R 101:101 /var/cache/nginx /var/log/nginx /etc/nginx/conf.d /etc/nginx/templates /usr/share/nginx/html

# Copy Nginx template (processed via envsubst at container startup) and compiled assets
COPY --chown=101:101 nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html

# Use numeric UID:GID (101:101 = nginx) so Kubernetes `runAsNonRoot: true` works out of the box
USER 101:101

EXPOSE 8080

# SIGQUIT ensures Nginx finishes serving in-flight requests before shutting down
STOPSIGNAL SIGQUIT

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
