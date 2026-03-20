FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/ .

RUN if [ -f yarn.lock ]; then yarn --frozen-lockfile && yarn build; \
    elif [ -f package-lock.json ]; then npm ci && npm run build; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm i --frozen-lockfile && pnpm run build; \
    else echo "Lockfile not found." && exit 1; \
    fi

FROM node:22-alpine AS runner
WORKDIR /app
RUN npm install -g serve
COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "3000"]