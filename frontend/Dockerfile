# The reader (ADR-0011): Astro 5 SSR on Node, behind the Caddy in deploy/.
FROM node:22-alpine

WORKDIR /srv

# Dependencies first, so a source edit does not reinstall node_modules.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

ENV HOST=0.0.0.0 \
    PORT=4321 \
    NODE_ENV=production

EXPOSE 4321
CMD ["node", "./dist/server/entry.mjs"]
