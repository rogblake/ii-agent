"""Dockerfile templates, port mappings, and watermark injection for Cloud Run deployments."""

from __future__ import annotations

import os

from ii_agent.projects.cloud_run.schemas import TemplateType

# Dockerfile templates for each project type
# These are injected into user source if no Dockerfile exists
# They use ARG BASE_IMAGE to support prebuilt base images with dependencies pre-installed
# NOTE: npm install is ALWAYS run to handle user-added packages, but it's faster
# when base image already has template dependencies (only delta is installed)
DOCKERFILES = {
    TemplateType.NEXTJS_SHADCN: """# Auto-generated Dockerfile for Next.js deployment
# Uses prebuilt base image with node_modules for faster builds
ARG BASE_IMAGE=node:20-slim
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# Copy package files first for layer caching
COPY package*.json ./

# Install/update dependencies
# If base image has node_modules, npm install only adds new packages (fast)
# If no node_modules, does full install (slower but still works)
RUN npm install

# Copy source code
COPY . .

# Ensure standalone output is enabled
RUN if ! grep -q "output.*standalone" next.config.js 2>/dev/null && \\
       ! grep -q "output.*standalone" next.config.mjs 2>/dev/null; then \\
      if [ -f next.config.js ]; then \\
        sed -i "s/const nextConfig = {/const nextConfig = {\\n  output: 'standalone',/" next.config.js || true; \\
      elif [ -f next.config.mjs ]; then \\
        sed -i "s/const nextConfig = {/const nextConfig = {\\n  output: 'standalone',/" next.config.mjs || true; \\
      fi; \\
    fi

# Build the Next.js application (uses BUILD_DIR=.next-build from package.json)
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
RUN npm run build

# Create public folder if it doesn't exist
RUN mkdir -p public

# Production image - minimal runtime (reuse base image to avoid re-downloading node)
FROM ${BASE_IMAGE} AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 nextjs

# Copy standalone server (includes server.js and node_modules)
COPY --from=builder --chown=nextjs:nodejs /app/.next-build/standalone ./
# Copy static files to .next/static (required path for standalone server)
COPY --from=builder --chown=nextjs:nodejs /app/.next-build/static ./.next-build/static
# Copy public folder
COPY --from=builder /app/public ./public

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
""",
    TemplateType.REACT_VITE_SHADCN: """# Auto-generated Dockerfile for React Vite deployment
# Uses prebuilt base image with node_modules for faster builds
ARG BASE_IMAGE=node:20-slim
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# Copy package files first for layer caching
COPY package*.json ./

# Install/update dependencies
# If base image has node_modules, npm install only adds new packages (fast)
# If no node_modules, does full install (slower but still works)
RUN npm install

# Copy source code
COPY . .

# Build the Vite application
ENV NODE_ENV=production
RUN npm run build

# Production image - serve with nginx
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html

RUN echo 'server { \\
    listen 3000; \\
    root /usr/share/nginx/html; \\
    index index.html; \\
    location / { \\
        try_files $uri $uri/ /index.html; \\
    } \\
    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ { \\
        expires 1y; \\
        add_header Cache-Control "public, immutable"; \\
    } \\
    gzip on; \\
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript; \\
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
""",
    TemplateType.REACT_SHADCN_PYTHON: """# Auto-generated Dockerfile for React + Python fullstack deployment
# Uses prebuilt base image with node_modules for faster builds
ARG BASE_IMAGE=node:20-slim
FROM ${BASE_IMAGE} AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install/update dependencies
# If base image has node_modules, npm install only adds new packages (fast)
# If no node_modules, does full install (slower but still works)
RUN npm install

# Copy frontend source code
COPY frontend/ ./

# Build the Vite frontend
ENV NODE_ENV=production
RUN npm run build

# Production image - Python backend serving static frontend
FROM python:3.11-slim AS runner

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/src ./src

# Copy built frontend to serve as static files
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user for security
RUN addgroup --system --gid 1001 appgroup && \\
    adduser --system --uid 1001 appuser && \\
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000
ENV PORT=8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    TemplateType.REACT_TAILWIND_PYTHON: """# Auto-generated Dockerfile for React + Python fullstack deployment
# Uses prebuilt base image with node_modules for faster builds
ARG BASE_IMAGE=node:20-slim
FROM ${BASE_IMAGE} AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install/update dependencies
# If base image has node_modules, npm install only adds new packages (fast)
# If no node_modules, does full install (slower but still works)
RUN npm install

# Copy frontend source code
COPY frontend/ ./

# Build the Vite frontend
ENV NODE_ENV=production
RUN npm run build

# Production image - Python backend serving static frontend
FROM python:3.11-slim AS runner

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/src ./src

# Copy built frontend to serve as static files
COPY --from=frontend-builder /app/frontend/dist ./static

# Create non-root user for security
RUN addgroup --system --gid 1001 appgroup && \\
    adduser --system --uid 1001 appuser && \\
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000
ENV PORT=8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    TemplateType.UNKNOWN: """# Auto-generated Dockerfile - fallback using buildpacks
# This will be handled by the buildpacks builder
""",
}

# Port mapping for each template type
TEMPLATE_PORTS = {
    TemplateType.NEXTJS_SHADCN: 3000,
    TemplateType.REACT_VITE_SHADCN: 3000,
    TemplateType.REACT_SHADCN_PYTHON: 8000,
    TemplateType.REACT_TAILWIND_PYTHON: 8000,
    TemplateType.UNKNOWN: 3000,
}


def _load_watermark_component(extension: str = "tsx") -> str:
    """Load the II-Agent watermark component from the assets file.

    Args:
        extension: File extension to load ('tsx' or 'jsx')
    """
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    badge_path = os.path.join(assets_dir, f"IIAgentBadge.{extension}")
    with open(badge_path, "r") as f:
        return f.read()


def get_watermark_component(component_path: str = "") -> str:
    """Get the II-Agent watermark component content.

    Args:
        component_path: The target component path (used to determine tsx vs jsx)
    """
    extension = "jsx" if component_path.endswith(".jsx") else "tsx"
    return _load_watermark_component(extension)


# Watermark injection patterns for different template types
WATERMARK_INJECTION = {
    # For Next.js: inject into layout.tsx body
    TemplateType.NEXTJS_SHADCN: {
        "component_path": "src/components/IIAgentBadge.tsx",
        "entry_file": "src/app/layout.tsx",
        "import_statement": 'import { IIAgentBadge } from "@/components/IIAgentBadge";\n',
        "search_pattern": "</body>",
        "replace_pattern": "<IIAgentBadge /></body>",
    },
    # For React Vite: inject into main.tsx
    TemplateType.REACT_VITE_SHADCN: {
        "component_path": "src/components/IIAgentBadge.tsx",
        "entry_file": "src/main.tsx",
        "import_statement": 'import { IIAgentBadge } from "./components/IIAgentBadge";\n',
        "search_pattern": "<App />",
        "replace_pattern": "<><App /><IIAgentBadge /></>",
    },
    # For React + Python (shadcn): inject into frontend main.tsx
    TemplateType.REACT_SHADCN_PYTHON: {
        "component_path": "frontend/src/components/IIAgentBadge.tsx",
        "entry_file": "frontend/src/main.tsx",
        "import_statement": 'import { IIAgentBadge } from "./components/IIAgentBadge";\n',
        "search_pattern": "<App />",
        "replace_pattern": "<><App /><IIAgentBadge /></>",
    },
    # For React + Python (tailwind): inject into frontend main.jsx
    TemplateType.REACT_TAILWIND_PYTHON: {
        "component_path": "frontend/src/components/IIAgentBadge.jsx",
        "entry_file": "frontend/src/main.jsx",
        "import_statement": 'import { IIAgentBadge } from "./components/IIAgentBadge";\n',
        "search_pattern": "<App />",
        "replace_pattern": "<><App /><IIAgentBadge /></>",
    },
}
