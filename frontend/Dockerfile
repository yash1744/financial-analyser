# ---- build stage ----
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- runtime stage: standalone server, non-root ----
FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

# standalone bundle + the static assets it serves
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000

# BACKEND_URL is read at request time by the /api/v1 rewrite
CMD ["node", "server.js"]
