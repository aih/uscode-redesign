# API tokens

A token raises one caller's rate limits on `/api/v1` (ADR-0096). It grants nothing else: every
route answers the same with or without one. This page covers making a token, storing it on the
box and with the caller, and sending it.

## Generate

`scripts/api_token.py` uses the standard library only, so it runs from any checkout, on a
workstation or on the box:

```bash
python3 scripts/api_token.py reintroductions --scale 20
```

```
token (give to the caller, store nowhere else): usc_kV3…
USC_API_TOKENS entry: {"reintroductions": {"sha256": "4dbd9c92…", "scale": 20.0}}
```

- The **name** (`reintroductions`) identifies the caller. Its budgets are keyed on
  `token:reintroductions`, and the name appears nowhere in a response.
- The **scale** multiplies the burst and the refill rate of every per-caller budget the token
  meets. It defaults to 10 and must be at least 1. At 20, the windowed versions route
  (`/sections/{id}/versions?from=&to=`) goes from 5 a burst and one every 5 seconds to 100 a
  burst and 4 a second. The per-route budgets are in the user guide, chapter 08
  (`/app/guide/08-api`).
- The **token** is printed once. The site keeps only its SHA-256 digest, so a lost token cannot
  be recovered; make a new one.

## Store on the box

The setting is `USC_API_TOKENS` in the box's `.env`, `/home/ec2-user/uscode-redesign/.env`
(mode 600). `docker-compose.prod.yml` passes it to the `api` service. It is one line of JSON,
with every token as one key, in single quotes:

```bash
USC_API_TOKENS='{"reintroductions": {"sha256": "4dbd9c92…", "scale": 20}, "another": {"sha256": "…", "scale": 10}}'
```

The single quotes keep the value literal for both Docker Compose and the `.env` reader the API
uses in development. Reach the box with SSM (`docs/deploy.md` §3), edit the file as `ec2-user`,
then recreate the API so the container picks the new value up:

```bash
sudo -iu ec2-user
cd ~/uscode-redesign
"${EDITOR:-vi}" .env
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate --wait api
```

A `docker restart` keeps the old environment. A malformed entry (a digest that is not 64 hex
characters, a scale below 1, invalid JSON) stops the API at start-up, and `--wait` reports it;
fix the line and run the command again. The next deploy (`deploy/deploy-on-box.sh`) keeps the
setting, since `.env` is not in the repository.

In development, put the same line in the checkout's `.env` and restart `make dev`.

## Store with the caller

The token goes to the caller over a private channel and is kept as a secret: an environment
variable or a secret store, never a committed file. reintroductions-us reads it from
`USCODE_API_TOKEN`; its `docs/api-tokens.md` covers that side.

## Use

Send it on every request as a bearer token:

```bash
curl -H "Authorization: Bearer $USCODE_API_TOKEN" \
  "https://uscode.linkedlegislation.org/api/v1/sections/us/usc/t38/s1562/versions?from=2025-01-03&to=2026-10-30"
```

```python
import httpx

client = httpx.Client(
    base_url="https://uscode.linkedlegislation.org/api/v1",
    headers={"Authorization": f"Bearer {token}"},
)
client.get("/classifications/code/38/1562")
```

| Response | Meaning |
|---|---|
| `200`, `304`, `404` | As without a token |
| `401` with `WWW-Authenticate: Bearer error="invalid_token"` | The token is not configured: mistyped, revoked, or the API was not recreated after the edit |
| `429` with `Retry-After` | The token's scaled budget for that route is spent; wait that many seconds |

A request with no `Authorization` header, or with another scheme such as `Basic`, gets the
anonymous budgets. A token holder does not draw on the budget shared by every outside caller on
routes that pin `?release=`, `?date=` or `?id=`.

To check a token after installing it: the token answers `200` and any other bearer value
answers `401`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $USCODE_API_TOKEN" https://uscode.linkedlegislation.org/api/v1/status
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer wrong" https://uscode.linkedlegislation.org/api/v1/classifications/code/38/1562
```

`/api/v1/status` has no per-caller budget and ignores the header, so the second command uses a
limited route.

## Rotate and revoke

- **Revoke:** delete the token's key from `USC_API_TOKENS` and recreate the API. The next
  request with it answers `401`.
- **Rotate:** generate a token under a new name (`reintroductions-2`), add it beside the old
  one, recreate the API, switch the caller, then remove the old key and recreate again.
- **Change the scale:** edit `scale` and recreate the API. The token stays the same.

Budgets live in the API process, so a recreate also empties every bucket.
