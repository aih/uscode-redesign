# X-Forwarded-For: what a caller can and cannot choose

*Measured 2026-07-30 against `caddy:2` (digest
`sha256:844f60b64e4724a5aa8245e019dace0d3f199f7433ce6c57676cb30a920dbad9`), for
ADR-0029 §1. Documentation duty 5: a reliability claim is a reproducible
command, not an assertion.*

Both surfaces identify a caller by address — `api/auth.py`'s per-IP login
throttle (ADR-0019), `params.py`'s rate limiters and
`frontend/src/middleware.ts`'s (ADR-0029), and the `login_attempts.ip` column.
All of them are worth exactly as much as the header they rest on, so the
question "can a caller choose their own address?" is answered here by
measurement rather than by reading.

## What was tested

A Caddy container proxying to an upstream that echoes back every
`X-Forwarded-For` header it received, with a request from the host in each of
four configurations. The upstream stands in for uvicorn and for the Node
adapter, which both read the **leftmost** value of that header
(`uvicorn/middleware/proxy_headers.py:176-177` under
`--forwarded-allow-ips "*"`; `astro/dist/core/app/node.js:121-122`
unconditionally).

`192.168.65.1` is the real peer — Docker Desktop's gateway, the address the
request genuinely arrived from. `1.2.3.4` is the forged value.

## Result

| `trusted_proxies` | `header_up X-Forwarded-For` | Request | Upstream received |
|---|---|---|---|
| unset (Caddy default) | absent | no forged header | `192.168.65.1` |
| unset | absent | `X-Forwarded-For: 1.2.3.4` | `192.168.65.1` |
| `static private_ranges` | absent | no forged header | `192.168.65.1` |
| **`static private_ranges`** | **absent** | **`X-Forwarded-For: 1.2.3.4`** | **`1.2.3.4, 192.168.65.1`** |
| `static private_ranges` | `{remote_host}` | no forged header | `192.168.65.1` |
| `static private_ranges` | `{remote_host}` | `X-Forwarded-For: 1.2.3.4` | `192.168.65.1` |

A forged value also survived as leftmost when sent as a two-hop chain
(`1.2.3.4, 5.6.7.8`), in the same configuration and no other.

## What it means

**The bolded row is the vulnerability, and it needs both halves.** Caddy does
not simply append: it preserves an inbound `X-Forwarded-For` only when the peer
is a *trusted proxy*, and replaces it otherwise. `deploy/Caddyfile`'s global
block sets `trusted_proxies static private_ranges` — for `X-Forwarded-Proto`,
which decides the `Secure` cookie — and the effect is that **any peer on a
private network is trusted to name its own client**. Then uvicorn, told to
trust every proxy, reads that leftmost forged value as the client.

The consequence: `MAX_FAILURES_PER_IP = 50` falls to a rotating header, which
defeats precisely the credential-stuffing case ADR-0019 wrote it for, and
`login_attempts.ip` — an unbounded `String` — becomes an attacker-controlled
write.

**The exposure is narrower than "always", and worth stating so.** Facing the
internet directly, as ADR-0020 deploys it, client peers are public addresses,
outside `private_ranges`, untrusted — so Caddy already discarded what they
sent. What was actually exposed is the dev stack, and any shape with a CDN,
load balancer or sidecar in front, which ADR-0018 explicitly anticipates. This
is a latent hole in the deployment most likely to come next rather than a live
one in the deployment that exists, and the ADR says so.

**The fix holds in every row.** `header_up X-Forwarded-For {remote_host}`
overwrites unconditionally, so it does not depend on the `trusted_proxies`
setting staying the way it is — which is the property worth having, given that
the setting lives in a different file from the code that relies on it.

Caddy emits `Unnecessary header_up X-Forwarded-For: the reverse proxy's default
behavior is to pass headers to the upstream` when adapting this config. The
warning is wrong for this use: the last two rows differ from the middle two
only by that directive.

## Reproducing it

```bash
cat > /tmp/echo.py <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("XFF: " + repr(self.headers.get_all("X-Forwarded-For") or ["<absent>"]) + "\n").encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
HTTPServer(("0.0.0.0", 8000), H).serve_forever()
PY

cat > /tmp/Caddyfile <<'CADDY'
{
	servers {
		trusted_proxies static private_ranges
	}
}
:8080 {
	handle {
		reverse_proxy xff-echo:8000 {
			header_up X-Forwarded-For {remote_host}
		}
	}
}
CADDY

docker network create xfftest
docker run -d --name xff-echo --network xfftest -v /tmp/echo.py:/echo.py:ro \
    python:3.12-slim python /echo.py
docker run -d --name xff-caddy --network xfftest -p 8099:8080 \
    -v /tmp/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2

curl -s -H 'X-Forwarded-For: 1.2.3.4' http://localhost:8099/
# with header_up:    XFF: ['192.168.65.1']
# without it:        XFF: ['1.2.3.4, 192.168.65.1']

docker rm -f xff-echo xff-caddy && docker network rm xfftest
```

The regression tests in `tests/test_auth.py` cover the same property from the
other end: a forged header does not open a fresh throttle bucket, and nothing a
caller sends reaches `login_attempts.ip`.

## Measured 2026-09-08: `trusted_proxies static 10.83.0.0/24` with `{client_ip}`

For ADR-0029's amendment: the site now sits behind a shared edge on the `edge` network
(`10.83.0.0/24`), and `deploy/Caddyfile` trusts that range and writes `{client_ip}`. A
`caddy:2-alpine` container running the branch's Caddyfile (`SITE_ADDRESS=http://uscode.localhost:8000`)
on the `edge` network and on a scratch network holding an echo upstream at `api:8001`, probed with
`curlimages/curl` from a peer on each network.

| Peer | Request headers | `client_ip` in the access log | Upstream received |
|---|---|---|---|
| `10.83.0.4` (edge network, trusted) | `X-Forwarded-For: 203.0.113.9`, `X-Forwarded-Proto: https` | `203.0.113.9` | `X-Forwarded-For: 203.0.113.9`, `X-Forwarded-Proto: https` |
| `10.83.0.4` (trusted) | `X-Forwarded-For: 203.0.113.9, 198.51.100.7` | `203.0.113.9` | `X-Forwarded-For: 203.0.113.9`, `X-Forwarded-Proto: http` |
| `172.27.0.4` (another Docker network, untrusted) | `X-Forwarded-For: 203.0.113.9`, `X-Forwarded-Proto: https` | `172.27.0.4` | `X-Forwarded-For: 172.27.0.4`, `X-Forwarded-Proto: http` |
| `172.27.0.4` (untrusted) | none | `172.27.0.4` | `X-Forwarded-For: 172.27.0.4`, `X-Forwarded-Proto: http` |

The same run against the dev stack's networks (`uscode-redesign_default`, `172.23.0.0/16`) gave the
same two answers: `client_ip` `203.0.113.9` from `10.83.0.3`, `172.23.0.9` from `172.23.0.9`.

Reproducing it:

```bash
docker network create --subnet 10.83.0.0/24 edge      # if deploy/edge/up.sh has not
docker network create scratch
docker run --rm -d --name echo --network scratch --network-alias api \
  -v "$PWD/echo.py:/echo.py:ro" python:3.12-alpine python /echo.py     # the echo.py above, on 8001
docker run --rm -d --name inner --network edge -e SITE_ADDRESS=http://uscode.localhost:8000 \
  -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2-alpine
docker network connect scratch inner
docker run --rm --network edge    curlimages/curl -s -H 'Host: uscode.localhost' \
  -H 'X-Forwarded-For: 203.0.113.9' -H 'X-Forwarded-Proto: https' http://inner:8000/api/v1/x
docker run --rm --network scratch curlimages/curl -s -H 'Host: uscode.localhost' \
  -H 'X-Forwarded-For: 203.0.113.9' -H 'X-Forwarded-Proto: https' http://inner:8000/api/v1/x
docker logs echo; docker logs inner | grep http.log.access   # request.client_ip
```
