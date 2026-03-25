# Production Dockerfile for React Vite with shadcn/ui
# Uses prebuilt base image for faster builds

# Build stage - uses base image with node_modules pre-installed
ARG BASE_IMAGE=node:20-slim
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# Copy package files first for better layer caching
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

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Configure nginx for SPA routing
RUN echo 'server { \
    listen 3000; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ { \
        expires 1y; \
        add_header Cache-Control "public, immutable"; \
    } \
    gzip on; \
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript; \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
