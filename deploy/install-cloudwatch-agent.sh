#!/usr/bin/env bash
# The CloudWatch agent and its configuration, as a file in the repository
# rather than as something somebody once typed on the box.
#
#   sudo bash deploy/install-cloudwatch-agent.sh
#
# Idempotent: installs the package if missing, writes the config whole, and
# restarts the agent. bootstrap-box.sh calls it, so a rebuilt box arrives with
# disk monitoring instead of arriving without it and looking fine.
#
# It exists because of 2026-09-18. `uscode-disk-high` had read OK since the box
# was built, and `deploy/alarms.sh` said why it might not: the alarm reads
# `CWAgent/disk_used_percent`, which exists only if this agent is installed and
# configured to publish it. The agent was installed and publishing
# `mem_used_percent` — so the box looked monitored — and no disk metric had been
# published for the life of the box. The alarm treated missing data as not
# breaching, so the gap read as health. Meanwhile Docker's unbounded container
# logs filled the 20 GB root volume, the site served 502, and the same full disk
# stopped the SSM agent writing a Run Command script, which is how a monitoring
# gap became an outage that could not be reached to be fixed.
#
# Two things about the config that are easy to get wrong, both load-bearing for
# the alarms in deploy/alarms.sh:
#
#   * The root volume is `/`, and it is the one that was never watched. The
#     corpus lives on `/var/lib/uscode` and that is the volume people think
#     about; the root volume is where Docker keeps images, container writable
#     layers and logs, and it is a fifth the size.
#   * The disk plugin dimensions each metric by `path`, `device` and `fstype`,
#     so a metric published plainly does NOT match an alarm keyed on
#     InstanceId+path — it has a third dimension and the alarm silently finds
#     nothing. `drop_device` removes one and `aggregation_dimensions` publishes
#     the InstanceId+path rollup the alarms actually name.
set -euo pipefail

CONFIG_SRC="$(cd "$(dirname "$0")" && pwd)/cloudwatch-agent.json"
CONFIG_DEST=/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
CTL=/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl

if [ "$(id -u)" -ne 0 ]; then
    echo "run this as root — it installs a package and writes $CONFIG_DEST" >&2
    exit 1
fi

if [ ! -f "$CONFIG_SRC" ]; then
    echo "missing $CONFIG_SRC" >&2
    exit 1
fi

if [ ! -x "$CTL" ]; then
    echo "==> installing amazon-cloudwatch-agent"
    dnf install -y amazon-cloudwatch-agent
fi

echo "==> writing $CONFIG_DEST"
install -D -m 0644 "$CONFIG_SRC" "$CONFIG_DEST"

echo "==> starting the agent with that config"
"$CTL" -a fetch-config -m ec2 -s -c "file:${CONFIG_DEST}"

echo
echo "==> agent status"
"$CTL" -a status

cat <<'EOF'

The metrics take a minute or two to appear. Confirm the two the alarms need —
both should print datapoints rather than an empty list:

  aws cloudwatch get-metric-data --region us-east-1 \
    --start-time "$(date -u -d '30 minutes ago' +%FT%TZ)" \
    --end-time "$(date -u +%FT%TZ)" \
    --metric-data-queries '[
      {"Id":"root","MetricStat":{"Metric":{"Namespace":"CWAgent","MetricName":"disk_used_percent",
        "Dimensions":[{"Name":"InstanceId","Value":"INSTANCE_ID"},{"Name":"path","Value":"/"}]},
        "Period":300,"Stat":"Maximum"}},
      {"Id":"data","MetricStat":{"Metric":{"Namespace":"CWAgent","MetricName":"disk_used_percent",
        "Dimensions":[{"Name":"InstanceId","Value":"INSTANCE_ID"},{"Name":"path","Value":"/var/lib/uscode"}]},
        "Period":300,"Stat":"Maximum"}}]'
EOF
