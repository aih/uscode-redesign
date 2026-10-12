# ADR-0092 — A deploy holds requests while the backends restart

**Status:** accepted (2026-10-12)

**Related:** ADR-0035 (deploys from Actions), ADR-0073 (the proxy's transport timeouts),
ADR-0088 (the reader's cookie gate).

## Context

The deploy of 6913087e (PR #94) ran on the box from 20:30:23 to 20:31:17 UTC on 2026-10-12 and
reported success. The site was reported down at 20:32. A probe from a GitHub Actions runner
from 20:32:51 found every route answering: `/health` 200, `/api/v1/status` 200, `/app/` 200
with the gate cookie. The outage was the deploy itself.

`deploy-on-box.sh` brings the stack up with `docker compose up -d --wait`. Its own log shows
what that does when the api and frontend images change:

1. stops and removes `frontend` and `api`;
2. starts `api` and waits for its healthcheck, which first runs 10s after start;
3. starts `frontend`.

Between 1 and 3 there is no reader, and between 1 and 2 no API. The proxy dialled a name that
did not resolve and answered 502. The frontend runs `node` as PID 1, which has no default
SIGTERM handler, so step 1 also waited out Docker's 10s grace period before SIGKILL. The script
then force-recreated the proxy, which left the edge with nothing to dial for a moment more,
although `deploy/Caddyfile` had not changed.

The deploy's last check fetched `/robots.txt` through the edge. The proxy answers that path
itself, so the check passed whether or not either backend was up.

The box had capacity to spare throughout: the outage used no resource.

## Decision

1. The proxy retries a failed dial to `frontend` or `api` every 250ms for up to 25s
   (`lb_try_duration`, `lb_try_interval`). A request made while a backend is being recreated
   waits for the new container. A backend that accepted a connection and hung still meets
   ADR-0073's `response_header_timeout`. 25s is under the edge's 30s `response_header_timeout`.
2. `api` and `frontend` run with `init: true`, so SIGTERM reaches the process through tini and
   the old container stops at once.
3. The proxy is recreated only when the Caddyfile the running container sees differs from the
   repository's (sha256 of each).
4. After the robots.txt check, the deploy fetches `/health` and `/app/us/usc/t16/s45f` through
   the edge with the gate cookie, retrying for about 30s, and fails if either does not answer
   200.

## Consequences

- A deploy delays requests by the length of the recreate (about 12s for the reader with the
  stop no longer waiting 10s) instead of failing them.
- A deploy that changes the Caddyfile still recreates the proxy, and requests through the edge
  in that second still fail. The edge (the statutes repository's `deploy/edge/Caddyfile`) could
  carry the same retry for `uscode-proxy`; that is not done here.
- The reader's own calls to the API from inside `frontend` are not retried. While `api` is
  restarting, no `frontend` container exists, so none are made.
- A Caddyfile edited in place on the box, rather than replaced by `git checkout`, would match
  the running container's view and not be picked up. The deploy only changes it through git.
