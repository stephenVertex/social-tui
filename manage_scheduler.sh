#!/bin/bash
#
# LaunchAgent manager for social-tui update_data.py
# This script helps manage the periodic execution of update_data.py every 6 hours.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.socialtui.updatedata.plist"
PLIST_SOURCE="${SCRIPT_DIR}/${PLIST_NAME}"
PLIST_DEST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"
LOG_DIR="${SCRIPT_DIR}/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure logs directory exists
mkdir -p "${LOG_DIR}"

# Print usage
usage() {
    cat << EOF
Usage: $0 {start|stop|restart|status|logs|tail}

Commands:
  start    - Install and start the LaunchAgent (runs update_data.py every 6 hours)
  stop     - Stop and unload the LaunchAgent
  restart  - Stop and start the LaunchAgent
  status   - Check if the LaunchAgent is running
  logs     - Display recent logs from update_data.py
  tail     - Follow logs in real-time

The LaunchAgent will run update_data.py every 6 hours.

Logs are written to:
  - ${LOG_DIR}/update_data.log (stdout)
  - ${LOG_DIR}/update_data.error.log (stderr)
EOF
}

# Check status
check_status() {
    if launchctl list | grep -q "${PLIST_NAME%.plist}"; then
        echo -e "${GREEN}✓${NC} LaunchAgent is running"
        launchctl list | grep "${PLIST_NAME%.plist}"
        return 0
    else
        echo -e "${YELLOW}✗${NC} LaunchAgent is not running"
        return 1
    fi
}

# Start the LaunchAgent
start_agent() {
    echo "Starting LaunchAgent..."

    # Check if plist file exists
    if [ ! -f "${PLIST_SOURCE}" ]; then
        echo -e "${RED}Error:${NC} Plist file not found: ${PLIST_SOURCE}"
        exit 1
    fi

    # Copy plist to LaunchAgents directory
    echo "Copying plist to ${PLIST_DEST}..."
    cp "${PLIST_SOURCE}" "${PLIST_DEST}"

    # Load the LaunchAgent
    echo "Loading LaunchAgent..."
    launchctl load "${PLIST_DEST}"

    echo -e "${GREEN}✓${NC} LaunchAgent started successfully"
    echo ""
    echo "The update script will run every 6 hours."
    echo "Next run will occur 6 hours from now."
    echo ""
    echo "To check logs, run: $0 logs"
    echo "To follow logs in real-time, run: $0 tail"
}

# Stop the LaunchAgent
stop_agent() {
    echo "Stopping LaunchAgent..."

    if [ -f "${PLIST_DEST}" ]; then
        launchctl unload "${PLIST_DEST}" 2>/dev/null || true
        rm "${PLIST_DEST}"
        echo -e "${GREEN}✓${NC} LaunchAgent stopped and removed"
    else
        echo -e "${YELLOW}✗${NC} LaunchAgent was not installed"
    fi
}

# Show logs
show_logs() {
    local lines=${1:-50}

    echo "=== STDOUT Logs (last ${lines} lines) ==="
    if [ -f "${LOG_DIR}/update_data.log" ]; then
        tail -n "${lines}" "${LOG_DIR}/update_data.log"
    else
        echo "No stdout logs found"
    fi

    echo ""
    echo "=== STDERR Logs (last ${lines} lines) ==="
    if [ -f "${LOG_DIR}/update_data.error.log" ]; then
        tail -n "${lines}" "${LOG_DIR}/update_data.error.log"
    else
        echo "No stderr logs found"
    fi
}

# Tail logs
tail_logs() {
    echo "Following logs (Ctrl+C to stop)..."
    echo ""

    if [ -f "${LOG_DIR}/update_data.log" ]; then
        tail -f "${LOG_DIR}/update_data.log"
    else
        echo -e "${YELLOW}Waiting for logs...${NC}"
        touch "${LOG_DIR}/update_data.log"
        tail -f "${LOG_DIR}/update_data.log"
    fi
}

# Main command handling
case "${1:-}" in
    start)
        start_agent
        ;;
    stop)
        stop_agent
        ;;
    restart)
        stop_agent
        echo ""
        start_agent
        ;;
    status)
        check_status
        ;;
    logs)
        show_logs "${2:-50}"
        ;;
    tail)
        tail_logs
        ;;
    *)
        usage
        exit 1
        ;;
esac
