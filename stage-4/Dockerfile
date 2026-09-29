# Pocketful stage 1: a single self-contained image. Node.js standard library
# only, so nothing is fetched at run time.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

ENV NODE_ENV=production \
    PORT=8080 \
    UV_THREADPOOL_SIZE=4

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY src ./src

USER node
EXPOSE 8080
CMD ["node", "src/server.js"]
