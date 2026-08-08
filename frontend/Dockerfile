# The reader (ADR-0011): Astro 5 SSR on Node, behind the Caddy in deploy/.
FROM node:22-alpine AS build

WORKDIR /srv

# Dependencies first, so a source edit does not reinstall node_modules. The
# retry budget is widened because a congested registry path can otherwise abort
# the whole install; it applies to this RUN only, since npm never runs in the
# stage that ships.
COPY package.json package-lock.json ./
RUN NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    NPM_CONFIG_MAXSOCKETS=3 \
    npm ci

COPY . .

# The commit the footer names. This context is `./frontend`, which holds no
# `.git`, so `astro.config.mjs` cannot read it here and falls back to "unknown"
# unless the build passes it in. `deploy.yml` passes the sha it built; compose
# passes the working tree's HEAD.
ARG COMMIT_SHA=unknown
RUN COMMIT_SHA="$COMMIT_SHA" npm run build

FROM node:22-alpine

WORKDIR /srv

ENV HOST=0.0.0.0 \
    PORT=4321 \
    NODE_ENV=production

# dist/server is not self-contained: it imports @xmldom/xmldom, diff-match-patch,
# and astro transitive deps from node_modules at runtime. @uswds/uswds is not
# among them — it is SCSS the build compiles away — so it is a devDependency
# and 31 MB of it stays out of this stage.
COPY package.json package-lock.json ./
RUN NPM_CONFIG_FETCH_RETRIES=10 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=15000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=60000 \
    NPM_CONFIG_FETCH_TIMEOUT=120000 \
    NPM_CONFIG_MAXSOCKETS=3 \
    npm ci --omit=dev

COPY --from=build /srv/dist ./dist

EXPOSE 4321
CMD ["node", "./dist/server/entry.mjs"]
