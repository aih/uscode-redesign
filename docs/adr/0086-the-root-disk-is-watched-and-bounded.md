# ADR-0086 — The root disk is watched, and the logs that fill it are bounded

**Status:** accepted (2026-09-18)

**Task:** `uscode.linkedlegislation.org` served 502 for about four hours. The box could not be
reached to be repaired: SSM Run Command failed on it in a millisecond with no output, and Session
Manager was denied by IAM.

**Amends:** ADR-0020 (the box's volumes and their monitoring); ADR-0073 (which put a watchdog on
"does the site answer" and left the resource alarms as they were).

## Context

Docker's default `json-file` driver keeps container logs forever.
`docker-compose.prod.yml` set no limits on any of its six services and neither did the box's Docker
daemon, so six weeks of logs filled the 20 GB root volume:

| container | log | project |
|---|---|---|
| `edge-caddy-1` | 4.66 GB | statutes |
| `uscode-redesign-proxy-1` | 1.45 GB | this one |
| `uscode-redesign-api-1` | 0.82 GB | this one |
| `uscode-redesign-frontend-1` | 0.41 GB | this one |
| **total, 12 files** | **7.36 GB** | |

with `/var/lib/docker/overlay2` at 7.6 GB and `/var/log/journal` at 2.0 GB beside them. The
filesystem reached 100% with 52 KB free.

A full root disk does not only stop the site. It stops the SSM agent writing the script for a Run
Command document, and it stops the session worker starting — so the outage and the loss of every
remote way in had one cause, and the second is what turned four hours into eight. Cron kept
running throughout, because the watchdog writes to the *data* volume; it probed, published
`SiteUp=0`, and restarted the HTTP services about twenty times into a disk that could not take a
write.

**Nothing alarmed on the disk, and nothing ever had.** `uscode-disk-high` watched
`path=/var/lib/uscode` — the corpus volume, the one people think about — and never `/`, which is a
fifth the size and holds every image, container layer and log. The CloudWatch agent was installed
and publishing `mem_used_percent`, so the box looked monitored; it had published **no disk metric
at all for the life of the box**, because the agent was configured by hand and the disk section was
never written. The alarm treated missing data as `notBreaching`, so fifteen months of no data read
as health. This is ADR-0073's lesson again in a different place: every alarm was green and the
thing they were meant to watch was not being watched.

Two things were found on the way out, both of which had been true and latent for months:

**`ssm:StartSession` authorizes against two resources.** `deploy/admin-grant.sh` allowed it on the
instance and not on the session document, so every session was denied. `SendCommand` is scoped the
same way and got it right, which is why nobody noticed: every routine deploy uses `SendCommand`.
The document must be named in both the AWS-owned form and the account-owned one — granting only the
former still denied every session here.

**The data volume was mounted by device name.** `deploy/bootstrap-box.sh` finds the volume by
elimination *because* "NVMe device order is not guaranteed", and then wrote the name it found into
`/etc/fstab`, freezing one boot's ordering into permanent configuration. Repairing the root volume
meant detaching and reattaching it; the two data volumes came back in the other order; and
`/dev/nvme1n1` mounted the **statutes** volume at `/var/lib/uscode`. The uscode database then
started on the statutes cluster — `role "uscode" does not exist` — while the statutes database was
already running on it. Two postmasters shared one data directory for about thirty seconds, which
`postmaster.pid`'s own guard failed to prevent because each container has its own PID namespace and
the pid it found looked alive to neither. It wrote three buffers and shut down cleanly; the
statutes cluster was checked afterwards and reads correctly.

## Decision

1. **Bound every container's logs, in two places.** `docker-compose.prod.yml` gains an `x-logging`
   anchor — `json-file`, `max-size: 50m`, `max-file: 3` — on all six services, and the box's
   `/etc/docker/daemon.json` carries the same as the daemon default. The compose setting is the
   record; the daemon default is what catches a container this repository does not define, which is
   how the single largest log on the box belonged to another project.

2. **Watch the root volume, and treat a missing disk metric as breaching.** A new
   `uscode-root-disk-high` on `path=/`, and `uscode-disk-high` changed from `notBreaching` to
   `breaching`. A disk alarm with no data is not a quiet alarm, it is an unmonitored disk.

3. **Put the CloudWatch agent's configuration in the repository.** `deploy/cloudwatch-agent.json`
   and `deploy/install-cloudwatch-agent.sh`, called from `bootstrap-box.sh`, so a rebuilt box
   arrives with disk monitoring rather than arriving without it and looking fine.

4. **Mount by UUID and verify the mount.** `bootstrap-box.sh` resolves the UUID and writes that,
   then refuses to continue if `$DATA_ROOT` is not the volume it meant. A wrong-volume mount looks
   like a working box until something writes to it.

5. **Prune tagged images on deploy.** `docker image prune -f` removes only *dangling* images, and
   every deploy tags what it pulls with a sha, so each previous deploy's images stayed. Now
   `prune -af --filter until=168h`, which keeps a week for the rollback in docs/deploy.md §9.

6. **Grant `ssm:StartSession` on the session document**, both ARN forms, in
   `deploy/admin-grant.sh`.

## Consequences

The root volume was grown 20 GB → 40 GB in the repair and stays there; 20 GB for a Docker host
running six services with image history was undersized, and the resize is not reversible — EBS
volumes cannot shrink.

**The `growpart` that should have taken the new size could not run.** cloud-init crashes on
`ENOSPC` writing its own `status.json` before it reaches the resize module, so a full disk cannot
grow itself: the repair needed the volume attached to a rescue instance in the same availability
zone. That is the shape of this failure in general — a full root disk removes the tools you would
use on a full root disk — and it is the argument for the alarm rather than for a better runbook.

**Five statutes containers still have unbounded logs.** They are another project's compose file;
the daemon default applies to them only when they are next recreated, and `edge-caddy` — the one
that mattered — was recreated here. The statutes repository needs the same `x-logging` anchor.

The 50m × 3 cap means **the oldest log lines are now discarded**, per container, at 150 MB. The
box keeps no central log store, so an investigation reaching further back than that has nothing to
read. That is accepted: the alternative was measured at 7.36 GB and an outage.

The alarms now fire on `treat-missing-data: breaching`, so an agent that dies, a config that is
lost, or a box that stops publishing will page a human — including for the ~15 minutes after any
reboot before the first datapoint lands. That is the intended trade and the opposite of the
setting that hid this.
