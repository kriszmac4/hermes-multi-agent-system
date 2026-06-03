#!/usr/bin/env bash
# Gateway Health Monitor — no_agent watchdog cron
# ====================================================
# Checks all Hermes gateway services, restarts any that are down,
# and reports only when something was wrong (watchdog = silent on OK).
#
# Exit codes:
#   0 = all gateways healthy (silent)
#   1 = at least one was restarted (reports which)
#   2 = fatal — service won't start (reports error)
#
# Cron: */5 * * * *
# Deliver: origin platform (auto back to source chat)

set -uo pipefail

HERMES_PROFILES_DIR="${HERMES_HOME_DIR:-/home/artofphotogrphyy/.hermes}/profiles"

RESTARTED=()
FATAL=()

# ── Helper: check a profile's Discord gateway ──
check_service() {
    local service_name="$1"
    local profile_name="$2"
    local display_name="$3"

    local state
    state=$(systemctl is-active "${service_name}" 2>/dev/null || echo "not-found")

    if [ "$state" = "active" ]; then
        return 0
    fi

    # Gateway is down — try to restart
    echo "⚠️  ${display_name} (${service_name}) is ${state}. Attempting restart..."

    if ! sudo systemctl restart "${service_name}" 2>/dev/null; then
        echo "❌ FATAL: ${display_name} — cannot restart ${service_name}"
        FATAL+=("${display_name}")
        return 2
    fi

    # Wait and verify
    sleep 5
    local new_state
    new_state=$(systemctl is-active "${service_name}" 2>/dev/null || echo "not-found")
    if [ "$new_state" = "active" ]; then
        echo "✅ ${display_name} restarted successfully (${service_name} → ${new_state})"
        RESTARTED+=("${display_name}")
        return 1
    else
        echo "❌ FATAL: ${display_name} restart failed (state=${new_state})"
        FATAL+=("${display_name}")
        return 2
    fi
}

# ── Helper: discover instantiated template services ──
discover_instances() {
    local template="$1"  # e.g. "hermes-discord@"
    systemctl list-unit-files --type=service 2>/dev/null \
        | grep "^${template}" \
        | grep -v "^${template}\.service\b" \
        | awk '{print $1}'
}

# ── Main: check all known gateway services ──

# Main Telegram gateway
check_service "hermes-telegram.service" "main" "Main (Telegram)"

# Discord profile services (instantiated from template)
while IFS= read -r svc_name; do
    [ -z "$svc_name" ] && continue
    profile="${svc_name#hermes-discord@}"
    profile="${profile%.service}"
    check_service "${svc_name}" "${profile}" "Discord/${profile}"
done < <(discover_instances "hermes-discord@")

# Main Discord gateway (standalone service, not a template)
# Check if the custom service file exists
if [ -f "/etc/systemd/system/hermes-discord-main.service" ]; then
    check_service "hermes-discord-main.service" "main-discord" "Main (Discord)"
fi

# Tutor services (voice agent)
for svc in hermes-tutor-agent.service hermes-tutor-web.service; do
    if systemctl list-unit-files --type=service 2>/dev/null | grep -q "^${svc}\b"; then
        check_service "${svc}" "${svc%.service}" "Tutor/${svc%.service}"
    fi
done

# ── Summary ──
# ── Silent watchdog: only speak when something changed ──
if [ ${#FATAL[@]} -gt 0 ]; then
    echo "🚨 FATAL — manual intervention needed: ${FATAL[*]}"
    exit 2
fi
if [ ${#RESTARTED[@]} -gt 0 ]; then
    echo "🔄 Restarted: ${RESTARTED[*]}"
    exit 1
fi
# Silent exit 0 = all healthy, nothing to report
exit 0
