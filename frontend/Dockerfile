# The reader (ADR-0011): Astro 5 SSR on Node, behind the Caddy in deploy/.
FROM node:22-alpine AS build

WORKDIR /srv

# A slow or congested registry path (observed on constrained build hosts) can
# trip npm's fetch retry logic hard enough to abort the whole install; widen
# the budget and cap concurrency rather than let one bad connection fail the
# build.
ENV NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    NPM_CONFIG_MAXSOCKETS=3

# Dependencies first, so a source edit does not reinstall node_modules.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-alpine

WORKDIR /srv

ENV HOST=0.0.0.0 \
    PORT=4321 \
    NODE_ENV=production \
    NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    NPM_CONFIG_MAXSOCKETS=3

# dist/server is not self-contained: it imports @xmldom/xmldom, diff-match-patch,
# and astro transitive deps from node_modules at runtime.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /srv/dist ./dist

EXPOSE 4321
CMD ["node", "./dist/server/entry.mjs"]
