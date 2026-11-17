#!/bin/bash
# ==============================================================================
# NAT & Internet Sharing Setup Script
# Automatically shares internet from one adapter (default: Wi-Fi) to one
# or multiple target network adapters (e.g., Ethernet / USB Ethernet) with
# zero hassle ("without thinking").
# ==============================================================================

STATE_FILE="/run/nat_share.state"
PID_FILE="/run/nat_share_dnsmasq.pid"
LEASE_FILE="/run/nat_share_dnsmasq.leases"
BRIDGE_NAME="natbr0"
POLICY_TABLE=199
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORTS_CONF="${NAT_SHARE_PORTS_CONF:-${SCRIPT_DIR}/nat_share.conf}"

# Terminal formatting
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RED="\033[1;31m"
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"

# Quick help without requiring sudo
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: sudo $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)                 Interactive setup / management menu"
    echo "  --stop, -s                Stop active NAT sharing and restore network settings"
    echo "  --status                  Display current NAT sharing status, port forwards & leases"
    echo "  --monitor, -m             Live monitor for connected devices (DHCP leases)"
    echo "  --check-ports [CIDR]      Validate nat_share-ports.conf JSON, networks, IPs & ports"
    echo "  --help, -h                Show this help message"
    exit 0
fi

# ==============================================================================
# Screen & Visual Formatting Helpers
# ==============================================================================

clear_screen() {
    clear 2>/dev/null || printf "\033[2J\033[H"
}

print_page_header() {
    local title="$1"
    local step_info="$2"
    clear_screen
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    if [ -n "$step_info" ]; then
        printf "${CYAN}${BOLD}  %-44s %20s${RESET}\n" "$title" "$step_info"
    else
        printf "${CYAN}${BOLD}  %-64s${RESET}\n" "$title"
    fi
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo ""
}

print_context_box() {
    local up_if="$1"
    local up_ip="$2"
    local down_ifs="${3:-}"
    
    echo -e "${DIM}Current Configuration:${RESET}"
    if [ -n "$up_if" ]; then
        echo -e "  • ${BOLD}Upstream (Internet):${RESET}  ${CYAN}$up_if${RESET} (${up_ip:-Active})"
    fi
    if [ -n "$down_ifs" ]; then
        echo -e "  • ${BOLD}Target Adapter(s):${RESET}    ${GREEN}$down_ifs${RESET}"
    fi
    echo -e "${DIM}--------------------------------------------------------------------${RESET}"
    echo ""
}

# ==============================================================================
# Helper & Validation Functions
# ==============================================================================

require_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Error: This operation requires root privileges. Please run with sudo:${RESET}"
        if [ $# -gt 0 ]; then
            echo "  sudo $0 $*"
        else
            echo "  sudo $0"
        fi
        exit 1
    fi
}

trim_whitespace() {
    local var="$1"
    var="${var#"${var%%[![:space:]]*}"}"
    var="${var%"${var##*[![:space:]]}"}"
    printf "%s" "$var"
}

validate_ipv4_syntax() {
    local ip="$1"
    if [ -z "$ip" ]; then
        echo "IP address cannot be empty."
        return 1
    fi
    if [[ ! "$ip" =~ ^[0-9.]+$ ]]; then
        echo "contains invalid characters (only decimal numbers and dots allowed)."
        return 1
    fi
    local IFS=.
    local -a octets=($ip)
    if [ "${#octets[@]}" -ne 4 ]; then
        echo "must contain exactly 4 octets separated by dots (found ${#octets[@]})."
        return 1
    fi
    for octet in "${octets[@]}"; do
        if [ -z "$octet" ]; then
            echo "contains an empty octet."
            return 1
        fi
        if [[ "$octet" =~ ^0[0-9]+$ ]]; then
            echo "octet \"$octet\" has invalid leading zeros."
            return 1
        fi
        if (( 10#$octet < 0 || 10#$octet > 255 )); then
            echo "octet \"$octet\" is out of range (must be between 0 and 255)."
            return 1
        fi
    done
    return 0
}

validate_host_ip() {
    local ip="$1"
    local err
    if ! err=$(validate_ipv4_syntax "$ip"); then
        echo "$err"
        return 1
    fi
    IFS=. read -r o1 o2 o3 o4 <<< "$ip"
    o1=$((10#$o1))
    if (( o1 == 0 )); then
        echo "0.0.0.0/8 is reserved and cannot be assigned as a host IP address."
        return 1
    fi
    if (( o1 == 127 )); then
        echo "127.0.0.0/8 is loopback and cannot be assigned to an external interface."
        return 1
    fi
    if (( o1 >= 224 && o1 <= 239 )); then
        echo "multicast addresses (224.0.0.0 - 239.255.255.255) cannot be assigned as a host IP."
        return 1
    fi
    if (( o1 >= 240 )); then
        echo "reserved/broadcast addresses (240.0.0.0 - 255.255.255.255) cannot be assigned."
        return 1
    fi
    return 0
}

parse_and_validate_subnet() {
    local subnet="$1"
    if [[ "$subnet" =~ ^/?([0-9]{1,2})$ ]]; then
        local p="${BASH_REMATCH[1]}"
        if (( 10#$p >= 1 && 10#$p <= 30 )); then
            echo "$((10#$p))"
            return 0
        fi
        return 1
    fi

    case "$subnet" in
        255.255.255.252) echo 30; return 0 ;;
        255.255.255.248) echo 29; return 0 ;;
        255.255.255.240) echo 28; return 0 ;;
        255.255.255.224) echo 27; return 0 ;;
        255.255.255.192) echo 26; return 0 ;;
        255.255.255.128) echo 25; return 0 ;;
        255.255.255.0)   echo 24; return 0 ;;
        255.255.254.0)   echo 23; return 0 ;;
        255.255.252.0)   echo 22; return 0 ;;
        255.255.248.0)   echo 21; return 0 ;;
        255.255.240.0)   echo 20; return 0 ;;
        255.255.224.0)   echo 19; return 0 ;;
        255.255.192.0)   echo 18; return 0 ;;
        255.255.128.0)   echo 17; return 0 ;;
        255.255.0.0)     echo 16; return 0 ;;
        255.0.0.0)       echo 8;  return 0 ;;
        *) return 1 ;;
    esac
}

is_wireless_iface() {
    local iface="$1"
    if [ -d "/sys/class/net/$iface/wireless" ] || [ -d "/sys/class/net/$iface/phy80211" ]; then
        return 0
    fi
    if [[ "$iface" =~ ^wl ]]; then
        return 0
    fi
    return 1
}

is_virtual_iface() {
    local iface="$1"
    if [ "$iface" = "lo" ] || [ "$iface" = "$BRIDGE_NAME" ]; then
        return 0
    fi
    if [ -d "/sys/devices/virtual/net/$iface" ]; then
        return 0
    fi
    return 1
}

# ==============================================================================
# IP Conflict & Subnet Testing Engine
# Mathematically verifies candidate CIDRs against active interfaces & routes
# ==============================================================================

ip_to_int() {
    local ip="$1"
    local a b c d
    IFS=. read -r a b c d <<< "$ip"
    echo "$(( (a << 24) + (b << 16) + (c << 8) + d ))"
}

int_to_ip() {
    local num="$1"
    echo "$(( (num >> 24) & 255 )).$(( (num >> 16) & 255 )).$(( (num >> 8) & 255 )).$(( num & 255 ))"
}

cidr_to_range() {
    local cidr="$1"
    local ip="${cidr%/*}"
    local prefix="${cidr#*/}"
    [ "$prefix" = "$cidr" ] && prefix=32

    local ip_int
    ip_int=$(ip_to_int "$ip")
    local mask=0
    if [ "$prefix" -gt 0 ]; then
        mask=$(( ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF) ))
    fi
    local net_int=$(( ip_int & mask ))
    local end_int=$(( net_int | (~mask & 0xFFFFFFFF) ))
    echo "$net_int $end_int"
}

cidrs_overlap() {
    local cidr1="$1"
    local cidr2="$2"
    local s1 e1 s2 e2
    read -r s1 e1 < <(cidr_to_range "$cidr1")
    read -r s2 e2 < <(cidr_to_range "$cidr2")
    if (( s1 <= e2 && s2 <= e1 )); then
        return 0
    else
        return 1
    fi
}

get_system_cidrs() {
    local ignore_ifs="${1:-lo $BRIDGE_NAME}"

    # 1. Interface addresses
    while read -r _ dev _ cidr _; do
        [[ " $ignore_ifs " =~ " $dev " ]] && continue
        if [[ "$cidr" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$ ]]; then
            [[ "$cidr" != */* ]] && cidr="${cidr}/32"
            echo "$cidr $dev (interface)"
        fi
    done < <(ip -4 -o addr show 2>/dev/null)

    # 2. Routing table subnets
    while read -r prefix _ dev _; do
        [[ " $ignore_ifs " =~ " $dev " ]] && continue
        if [[ "$prefix" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$ ]]; then
            [[ "$prefix" != */* ]] && prefix="${prefix}/32"
            echo "$prefix $dev (route)"
        fi
    done < <(ip -4 -o route show table all 2>/dev/null | grep -E "dev [^ ]+" | awk '{for(i=1;i<=NF;i++) if($i=="dev") {print $1, "dev", $(i+1); break}}')
}

check_cidr_conflict() {
    local cand_cidr="$1"
    local ignore_ifs="${2:-lo $BRIDGE_NAME}"
    local cand_ip="${cand_cidr%/*}"

    # Mathematical overlap check against system interfaces & routes
    while read -r sys_cidr dev desc; do
        if cidrs_overlap "$cand_cidr" "$sys_cidr"; then
            echo "overlaps with $dev ($sys_cidr)"
            return 1
        fi
    done < <(get_system_cidrs "$ignore_ifs")

    # ICMP ping probe: test if an active gateway/host responds
    if ping -c 1 -W 1 "$cand_ip" >/dev/null 2>&1; then
        echo "responds to ICMP ping on existing network"
        return 2
    fi

    # Optional ARP probe if arping is installed and target dev is UP
    if command -v arping >/dev/null 2>&1; then
        for d_if in $ignore_ifs; do
            [ "$d_if" = "lo" ] && continue
            [ "$d_if" = "$BRIDGE_NAME" ] && continue
            if ip link show dev "$d_if" 2>/dev/null | grep -q "state UP"; then
                if arping -c 1 -w 1 -I "$d_if" "$cand_ip" >/dev/null 2>&1; then
                    echo "device on $d_if responded via ARP"
                    return 3
                fi
            fi
        done
    fi

    return 0
}

CANDIDATE_LAN_SUBNETS=(
    "192.168.100.1/24"
    "192.168.10.1/24"
    "192.168.200.1/24"
    "192.168.50.1/24"
    "10.99.0.1/24"
    "10.100.0.1/24"
    "10.50.0.1/24"
    "172.24.0.1/24"
    "172.28.0.1/24"
    "172.30.0.1/24"
)

find_best_lan_subnet() {
    local ignore_ifs="${1:-lo $BRIDGE_NAME}"
    local cand_found=""

    for cand in "${CANDIDATE_LAN_SUBNETS[@]}"; do
        if check_cidr_conflict "$cand" "$ignore_ifs" >/dev/null 2>&1; then
            cand_found="$cand"
            break
        fi
    done

    # Dynamic fallback if all predefined ranges collide
    if [ -z "$cand_found" ]; then
        for oct in $(seq 101 254); do
            local dyn="10.$oct.0.1/24"
            if check_cidr_conflict "$dyn" "$ignore_ifs" >/dev/null 2>&1; then
                cand_found="$dyn"
                break
            fi
        done
    fi

    echo "${cand_found:-192.168.100.1/24}"
}

# ==============================================================================
# Network & Port Forwarding Configuration Parser & Strict Validator
# Reads nat_share.conf, verifies JSON format, checks for unique network
# entry, and validates DHCP range, ports, protocols, and device IPs.
# ==============================================================================

VALIDATED_PORT_FORWARDS=()
MATCHED_PORT_CONF_FOUND=0
CONFIG_DHCP_MODE=""
CONFIG_DHCP_START=""
CONFIG_DHCP_END=""

validate_and_load_port_forwards() {
    local target_lan_ip="$1"
    local target_lan_prefix="$2"
    local upstream_ip="${3:-}"
    local conf_file="${4:-$PORTS_CONF}"

    VALIDATED_PORT_FORWARDS=()
    MATCHED_PORT_CONF_FOUND=0
    CONFIG_DHCP_MODE=""
    CONFIG_DHCP_START=""
    CONFIG_DHCP_END=""

    if [ ! -e "$conf_file" ]; then
        return 0
    fi

    if [ ! -f "$conf_file" ] || [ ! -r "$conf_file" ]; then
        echo -e "${RED}${BOLD}Error: Configuration file '$conf_file' is not a readable regular file.${RESET}"
        return 1
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}${BOLD}Error: 'python3' is required to parse and validate '$conf_file'.${RESET}"
        return 1
    fi

    local py_output
    py_output=$(python3 - "$conf_file" "$target_lan_ip" "$target_lan_prefix" "$upstream_ip" << 'PYEOF'
import json
import sys
import re

conf_file = sys.argv[1]
target_lan_ip = sys.argv[2].strip()
target_lan_prefix_str = sys.argv[3].strip()
upstream_ip = sys.argv[4].strip() if len(sys.argv) > 4 else ""

NETMASK_MAP = {
    "255.255.255.252": 30,
    "255.255.255.248": 29,
    "255.255.255.240": 28,
    "255.255.255.224": 27,
    "255.255.255.192": 26,
    "255.255.255.128": 25,
    "255.255.255.0":   24,
    "255.255.254.0":   23,
    "255.255.252.0":   22,
    "255.255.248.0":   21,
    "255.255.240.0":   20,
    "255.255.224.0":   19,
    "255.255.192.0":   18,
    "255.255.128.0":   17,
    "255.255.0.0":     16,
    "255.0.0.0":       8,
}

def validate_ipv4_syntax(ip):
    if not isinstance(ip, str):
        return f"must be a string (got {type(ip).__name__})."
    ip = ip.strip()
    if not ip:
        return "IP address cannot be empty."
    if not re.match(r'^[0-9.]+$', ip):
        return f"'{ip}' contains invalid characters (only decimal digits and dots allowed)."
    octets = ip.split('.')
    if len(octets) != 4:
        return f"'{ip}' must contain exactly 4 octets separated by dots (found {len(octets)})."
    for o in octets:
        if not o:
            return f"'{ip}' contains an empty octet."
        if len(o) > 1 and o.startswith('0'):
            return f"'{ip}' has octet '{o}' with invalid leading zeros."
        val = int(o, 10)
        if val < 0 or val > 255:
            return f"'{ip}' has octet '{o}' out of range (must be between 0 and 255)."
    return None

def validate_host_or_net_ip(ip, allow_net_addr=False):
    err = validate_ipv4_syntax(ip)
    if err:
        return err
    octets = [int(x, 10) for x in ip.strip().split('.')]
    o1 = octets[0]
    if o1 == 0:
        return f"'{ip}' is in reserved range 0.0.0.0/8."
    if o1 == 127:
        return f"'{ip}' is a loopback address (127.0.0.0/8)."
    if 224 <= o1 <= 239:
        return f"'{ip}' is a multicast address (224.0.0.0 - 239.255.255.255)."
    if o1 >= 240:
        return f"'{ip}' is in reserved/broadcast range (240.0.0.0 - 255.255.255.255)."
    return None

def parse_mask(mask_val):
    if isinstance(mask_val, bool) or mask_val is None:
        return None, "mask cannot be boolean or null."
    if isinstance(mask_val, int):
        if 1 <= mask_val <= 30:
            return mask_val, None
        return None, f"mask '{mask_val}' is out of valid CIDR range (must be between 1 and 30)."
    if isinstance(mask_val, str):
        s = mask_val.strip()
        if s.startswith('/'):
            s = s[1:]
        if re.match(r'^[0-9]{1,2}$', s):
            if len(s) > 1 and s.startswith('0'):
                return None, f"mask '{mask_val}' has invalid leading zeros."
            p = int(s, 10)
            if 1 <= p <= 30:
                return p, None
            return None, f"mask '{mask_val}' is out of valid CIDR range (must be between 1 and 30)."
        if s in NETMASK_MAP:
            return NETMASK_MAP[s], None
        return None, f"mask '{mask_val}' is not a valid CIDR prefix (1-30) or subnet mask."
    return None, f"mask must be an integer or string (got {type(mask_val).__name__})."

def parse_port(port_val, field_name):
    if isinstance(port_val, bool) or port_val is None:
        return None, f"'{field_name}' cannot be empty, null, or boolean."
    if isinstance(port_val, int):
        p = port_val
    elif isinstance(port_val, str):
        s = port_val.strip()
        if not s:
            return None, f"'{field_name}' cannot be empty."
        if not re.match(r'^[0-9]+$', s):
            return None, f"'{field_name}' value '{port_val}' must be an integer (digits only)."
        if len(s) > 1 and s.startswith('0'):
            return None, f"'{field_name}' value '{port_val}' has invalid leading zeros."
        p = int(s, 10)
    else:
        return None, f"'{field_name}' must be an integer (got {type(port_val).__name__})."

    if p < 1 or p > 65535:
        return None, f"'{field_name}' value '{p}' is out of valid port range (must be 1 - 65535)."
    return p, None

def ip_to_int(ip):
    parts = [int(x, 10) for x in ip.strip().split('.')]
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]

def int_to_ip(num):
    return f"{(num >> 24) & 255}.{(num >> 16) & 255}.{(num >> 8) & 255}.{num & 255}"

def cidr_bounds(ip, prefix):
    ip_i = ip_to_int(ip)
    mask = ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF) if prefix > 0 else 0
    net_i = ip_i & mask
    bcast_i = net_i | (~mask & 0xFFFFFFFF)
    return net_i, bcast_i

def parse_dhcp(dhcp_val, gw_ip, net_int, bcast_int, prefix):
    if dhcp_val is None or dhcp_val is False:
        return ("none", "", ""), None
    if isinstance(dhcp_val, str):
        s = dhcp_val.strip()
        if not s or s.lower() in ("none", "false", "disabled", "off", "no"):
            return ("none", "", ""), None
        if '-' not in s:
            return None, f"invalid 'dhcp' value '{dhcp_val}' (expected 'START_IP-END_IP', 'START_IP-END_OCTET', or 'none')."
        parts = s.split('-', 1)
        start_part = parts[0].strip()
        end_part = parts[1].strip()
        gw_octets = gw_ip.split('.')

        if '.' in start_part:
            err = validate_host_or_net_ip(start_part, allow_net_addr=False)
            if err:
                return None, f"invalid DHCP start IP — {err}"
            start_ip = start_part
        elif re.match(r'^[0-9]+$', start_part):
            val = int(start_part, 10)
            if val < 1 or val > 254:
                return None, f"DHCP start octet '{start_part}' is out of host range (1-254)."
            start_ip = f"{gw_octets[0]}.{gw_octets[1]}.{gw_octets[2]}.{val}"
        else:
            return None, f"invalid DHCP start value '{start_part}'."

        start_octets = start_ip.split('.')
        if '.' in end_part:
            err = validate_host_or_net_ip(end_part, allow_net_addr=False)
            if err:
                return None, f"invalid DHCP end IP — {err}"
            end_ip = end_part
        elif re.match(r'^[0-9]+$', end_part):
            val = int(end_part, 10)
            if val < 1 or val > 254:
                return None, f"DHCP end octet '{end_part}' is out of host range (1-254)."
            end_ip = f"{start_octets[0]}.{start_octets[1]}.{start_octets[2]}.{val}"
        else:
            return None, f"invalid DHCP end value '{end_part}'."

        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)
        net_ip_str = int_to_ip(net_int)
        first_host = int_to_ip(net_int + 1)
        last_host = int_to_ip(bcast_int - 1)

        if start_int <= net_int or start_int >= bcast_int:
            return None, f"DHCP start IP '{start_ip}' is outside valid host range for {net_ip_str}/{prefix} ({first_host} - {last_host})."
        if end_int <= net_int or end_int >= bcast_int:
            return None, f"DHCP end IP '{end_ip}' is outside valid host range for {net_ip_str}/{prefix} ({first_host} - {last_host})."
        if start_int > end_int:
            return None, f"DHCP start IP '{start_ip}' cannot be greater than end IP '{end_ip}'."
        gw_int = ip_to_int(gw_ip)
        if start_int <= gw_int <= end_int:
            return None, f"DHCP range '{start_ip} - {end_ip}' includes the LAN Gateway IP '{gw_ip}'."

        return ("range", start_ip, end_ip), None
    return None, f"'dhcp' must be a range string (e.g. '192.168.100.50-100') or 'none' (got {type(dhcp_val).__name__})."

try:
    with open(conf_file, 'r', encoding='utf-8') as f:
        raw_text = f.read()
except Exception as e:
    print(f"ERROR|Cannot read '{conf_file}': {e}")
    sys.exit(1)

if not raw_text.strip():
    print(f"ERROR|Configuration file '{conf_file}' is empty. It must contain valid JSON.")
    sys.exit(1)

# Allow unquoted `none` as a convenience in JSON for `"dhcp": none`
normalized_text = re.sub(
    r'("dhcp"\s*:\s*)none(\s*[,}\n\r])',
    r'\1null\2',
    raw_text,
    flags=re.IGNORECASE
)
# Also handle missing comma after `"dhcp": none` before next key
normalized_text = re.sub(
    r'("dhcp"\s*:\s*(?:null|"[^"]*"))\s*(\n\s*"[a-zA-Z0-9_]+"s*:)',
    r'\1,\2',
    normalized_text
)

try:
    data = json.loads(normalized_text)
except json.JSONDecodeError as e:
    print(f"ERROR|Invalid JSON format in '{conf_file}' at line {e.lineno}, column {e.colno}: {e.msg}")
    sys.exit(1)

if isinstance(data, dict):
    if "networks" in data and isinstance(data["networks"], list):
        configs = data["networks"]
    elif "configurations" in data and isinstance(data["configurations"], list):
        configs = data["configurations"]
    else:
        print(f"ERROR|Root JSON element in '{conf_file}' must be a JSON array '[ ... ]' of network objects.")
        sys.exit(1)
elif isinstance(data, list):
    configs = data
else:
    print(f"ERROR|Root JSON element in '{conf_file}' must be a JSON array '[ ... ]' (got {type(data).__name__}).")
    sys.exit(1)

errors = []
ALLOWED_NET_KEYS = {"subnet", "mask", "dhcp", "dhcp_range", "ports", "forwards", "port_forwards", "rules", "comment", "description"}
ALLOWED_RULE_KEYS = {"port", "device_ip", "device_port", "protocol", "comment", "description"}

check_all_mode = (target_lan_ip == "__ALL__")
target_prefix = 0
target_net_int = 0
target_bcast_int = 0
target_net_ip = ""

if not check_all_mode:
    target_prefix, mask_err = parse_mask(target_lan_prefix_str)
    if mask_err:
        print(f"ERROR|Invalid target LAN prefix '{target_lan_prefix_str}': {mask_err}")
        sys.exit(1)
    target_net_int, target_bcast_int = cidr_bounds(target_lan_ip, target_prefix)
    target_net_ip = int_to_ip(target_net_int)

matched_entries = []
seen_networks = {}

for idx, entry in enumerate(configs, start=1):
    if not isinstance(entry, dict):
        errors.append(f"Network entry #{idx}: Must be a JSON object '{{ ... }}' (got {type(entry).__name__}).")
        continue

    unknown_keys = set(entry.keys()) - ALLOWED_NET_KEYS
    if unknown_keys:
        errors.append(f"Network entry #{idx}: Contains unrecognized field(s): {', '.join(sorted(unknown_keys))}.")

    if "subnet" not in entry:
        errors.append(f"Network entry #{idx}: Missing required field 'subnet'.")
        continue
    if "mask" not in entry:
        errors.append(f"Network entry #{idx}: Missing required field 'mask'.")
        continue

    subnet_raw = entry["subnet"]
    mask_raw = entry["mask"]

    ip_err = validate_host_or_net_ip(subnet_raw, allow_net_addr=True)
    if ip_err:
        errors.append(f"Network entry #{idx}: Invalid 'subnet' value — {ip_err}")
        continue
    subnet_ip = subnet_raw.strip()

    prefix, m_err = parse_mask(mask_raw)
    if m_err:
        errors.append(f"Network entry #{idx} (subnet {subnet_ip}): Invalid 'mask' — {m_err}")
        continue

    entry_net_int, entry_bcast_int = cidr_bounds(subnet_ip, prefix)
    entry_net_ip = int_to_ip(entry_net_int)
    net_key = f"{entry_net_ip}/{prefix}"

    if net_key in seen_networks:
        prev_idx = seen_networks[net_key]
        if check_all_mode:
            errors.append(
                f"Duplicate network configuration for {subnet_ip}/{prefix} (network {net_key}): "
                f"defined in both entry #{prev_idx} and entry #{idx}. Only 1 configuration per network is allowed."
            )
    else:
        seen_networks[net_key] = idx

    # Parse DHCP configuration if present
    dhcp_info = ("unset", "", "")
    dhcp_key = "dhcp" if "dhcp" in entry else ("dhcp_range" if "dhcp_range" in entry else None)
    if dhcp_key is not None:
        gw_for_dhcp = target_lan_ip if (not check_all_mode and entry_net_int == target_net_int and prefix == target_prefix) else subnet_ip
        parsed_dhcp, dhcp_err = parse_dhcp(entry[dhcp_key], gw_for_dhcp, entry_net_int, entry_bcast_int, prefix)
        if dhcp_err:
            errors.append(f"Network entry #{idx} ({subnet_ip}/{prefix}): Invalid '{dhcp_key}' — {dhcp_err}")
        else:
            dhcp_info = parsed_dhcp

    # Locate ports list key (optional if empty)
    ports_key = None
    for k in ("ports", "forwards", "port_forwards", "rules"):
        if k in entry:
            ports_key = k
            break
    if ports_key is None:
        ports_list = []
    elif not isinstance(entry[ports_key], list):
        errors.append(f"Network entry #{idx} ({subnet_ip}/{prefix}): Field '{ports_key}' must be a JSON array '[ ... ]'.")
        continue
    else:
        ports_list = entry[ports_key]

    if check_all_mode:
        matched_entries.append((idx, subnet_ip, prefix, entry_net_int, entry_bcast_int, ports_list, dhcp_info))
    else:
        # Check if this entry matches or collides with the network currently being set up
        same_network = (entry_net_int == target_net_int and prefix == target_prefix)
        same_subnet_ip_diff_mask = (subnet_ip == target_lan_ip and prefix != target_prefix)
        overlaps_target = (entry_net_int <= target_bcast_int and target_net_int <= entry_bcast_int)

        if same_subnet_ip_diff_mask:
            errors.append(
                f"Network entry #{idx}: Subnet '{subnet_ip}' matches the LAN Gateway IP '{target_lan_ip}', "
                f"but its mask (/{prefix}) does not match the NAT network mask (/{target_prefix})."
            )
        elif same_network:
            # Verify subnet field in config is either the Gateway IP or Network Address
            if subnet_ip != target_lan_ip and subnet_ip != target_net_ip:
                errors.append(
                    f"Network entry #{idx}: Subnet '{subnet_ip}/{prefix}' belongs to network {target_net_ip}/{target_prefix}, "
                    f"but 'subnet' must match the LAN Gateway IP ({target_lan_ip}) or network address ({target_net_ip})."
                )
            matched_entries.append((idx, subnet_ip, prefix, entry_net_int, entry_bcast_int, ports_list, dhcp_info))
        elif overlaps_target:
            errors.append(
                f"Network entry #{idx}: Configured network '{subnet_ip}/{prefix}' overlaps with target network "
                f"'{target_lan_ip}/{target_prefix}' but has a mismatched subnet mask."
            )

if not check_all_mode and len(matched_entries) > 1:
    entry_nums = ", ".join(f"#{m[0]}" for m in matched_entries)
    errors.append(
        f"Multiple configurations ({len(matched_entries)}) found for network {target_lan_ip}/{target_prefix} "
        f"(entries {entry_nums}). Only 1 configuration per network is allowed!"
    )

# Validate rules for matched network(s)
validated_rules = []
entries_to_validate = matched_entries if (check_all_mode or len(matched_entries) == 1) else []

for (idx, subnet_ip, prefix, net_int, bcast_int, rules_list, dhcp_info) in entries_to_validate:
    gw_ip = target_lan_ip if not check_all_mode else subnet_ip
    net_ip_str = int_to_ip(net_int)
    bcast_ip_str = int_to_ip(bcast_int)
    first_host_str = int_to_ip(net_int + 1)
    last_host_str = int_to_ip(bcast_int - 1)

    seen_ext_ports = {}  # (proto, port) -> (rule_idx, dev_ip, dev_port)

    for r_idx, rule in enumerate(rules_list, start=1):
        prefix_label = f"Network #{idx} ({subnet_ip}/{prefix}), Rule #{r_idx}"
        if not isinstance(rule, dict):
            errors.append(f"{prefix_label}: Rule must be a JSON object '{{ ... }}' (got {type(rule).__name__}).")
            continue

        unknown_r_keys = set(rule.keys()) - ALLOWED_RULE_KEYS
        if unknown_r_keys:
            errors.append(f"{prefix_label}: Unrecognized field(s) in rule: {', '.join(sorted(unknown_r_keys))}.")

        missing_r_keys = [k for k in ("port", "device_ip", "device_port") if k not in rule]
        if missing_r_keys:
            errors.append(f"{prefix_label}: Missing required field(s): {', '.join(missing_r_keys)}.")
            continue

        ext_port, p_err = parse_port(rule["port"], "port")
        if p_err:
            errors.append(f"{prefix_label}: Invalid external {p_err}")

        dev_port, dp_err = parse_port(rule["device_port"], "device_port")
        if dp_err:
            errors.append(f"{prefix_label}: Invalid target {dp_err}")

        proto_raw = rule.get("protocol", "both")
        if not isinstance(proto_raw, str) or proto_raw.strip().lower() not in ("tcp", "udp", "both"):
            errors.append(f"{prefix_label}: Invalid 'protocol' value '{proto_raw}' (must be 'tcp', 'udp', or 'both').")
            proto = "both"
        else:
            proto = proto_raw.strip().lower()

        dev_ip_raw = rule["device_ip"]
        dip_err = validate_host_or_net_ip(dev_ip_raw, allow_net_addr=False)
        if dip_err:
            errors.append(f"{prefix_label}: Invalid 'device_ip' — {dip_err}")
        else:
            dev_ip = dev_ip_raw.strip()
            dev_ip_int = ip_to_int(dev_ip)
            if dev_ip_int < net_int or dev_ip_int > bcast_int:
                errors.append(
                    f"{prefix_label} (port {ext_port if ext_port else '?'}): device_ip '{dev_ip}' is outside "
                    f"network {net_ip_str}/{prefix} (valid range: {first_host_str} - {last_host_str})."
                )
            elif dev_ip_int == net_int:
                errors.append(
                    f"{prefix_label} (port {ext_port if ext_port else '?'}): device_ip '{dev_ip}' is the subnet "
                    f"network address ({net_ip_str}) and cannot be assigned to a device."
                )
            elif dev_ip_int == bcast_int:
                errors.append(
                    f"{prefix_label} (port {ext_port if ext_port else '?'}): device_ip '{dev_ip}' is the subnet "
                    f"broadcast address ({bcast_ip_str}) and cannot be assigned to a device."
                )
            elif dev_ip == gw_ip or dev_ip == subnet_ip:
                errors.append(
                    f"{prefix_label} (port {ext_port if ext_port else '?'}): device_ip '{dev_ip}' is the NAT "
                    f"Gateway IP itself ({gw_ip}). Port forwards must target a downstream client device IP."
                )
            elif upstream_ip and dev_ip == upstream_ip:
                errors.append(
                    f"{prefix_label} (port {ext_port if ext_port else '?'}): device_ip '{dev_ip}' conflicts with "
                    f"the host's Upstream IP ({upstream_ip})."
                )

        if ext_port is not None and not dip_err:
            dev_ip = dev_ip_raw.strip()
            expanded_protos = ["tcp", "udp"] if proto == "both" else [proto]
            for ep in expanded_protos:
                key = (ep, ext_port)
                if key in seen_ext_ports:
                    prev_r, prev_ip, prev_dp = seen_ext_ports[key]
                    errors.append(
                        f"{prefix_label}: Duplicate external port {ext_port}/{ep.upper()} — "
                        f"already forwarded in Rule #{prev_r} to {prev_ip}:{prev_dp}."
                    )
                else:
                    seen_ext_ports[key] = (r_idx, dev_ip, dev_port)

        if ext_port is not None and dev_port is not None and not dip_err:
            validated_rules.append(f"RULE|{ext_port}|{dev_ip_raw.strip()}|{dev_port}|{proto}")

if errors:
    for err in errors:
        print(f"ERROR|{err}")
    sys.exit(1)

if not check_all_mode:
    if len(matched_entries) == 0:
        print("NO_MATCH")
    else:
        m_dhcp = matched_entries[0][6]
        print(f"MATCHED|{matched_entries[0][1]}|{matched_entries[0][2]}|{len(validated_rules)}")
        print(f"DHCP|{m_dhcp[0]}|{m_dhcp[1]}|{m_dhcp[2]}")
        for r in validated_rules:
            print(r)
else:
    print(f"ALL_VALID|{len(matched_entries)}|{len(validated_rules)}")
    for r in validated_rules:
        print(r)
PYEOF
    )
    local py_status=$?

    if [ $py_status -ne 0 ]; then
        echo ""
        echo -e "${RED}${BOLD}====================================================================${RESET}"
        echo -e "${RED}${BOLD}        Configuration Error (${conf_file##*/})                      ${RESET}"
        echo -e "${RED}${BOLD}====================================================================${RESET}"
        echo -e "  File: ${YELLOW}${conf_file}${RESET}"
        if [ "$target_lan_ip" != "__ALL__" ]; then
            echo -e "  Target Network: ${CYAN}${target_lan_ip}/${target_lan_prefix}${RESET}"
        fi
        echo ""
        echo -e "  ${BOLD}The following error(s) must be resolved before continuing:${RESET}"
        while IFS='|' read -r tag msg; do
            if [ "$tag" = "ERROR" ]; then
                echo -e "    ${RED}✗${RESET} $msg"
            fi
        done <<< "$py_output"
        echo ""
        echo -e "${RED}${BOLD}====================================================================${RESET}"
        echo ""
        return 1
    fi

    while IFS='|' read -r tag f1 f2 f3 f4; do
        case "$tag" in
            NO_MATCH)
                MATCHED_PORT_CONF_FOUND=0
                ;;
            MATCHED)
                MATCHED_PORT_CONF_FOUND=1
                ;;
            DHCP)
                CONFIG_DHCP_MODE="$f1"
                CONFIG_DHCP_START="$f2"
                CONFIG_DHCP_END="$f3"
                ;;
            RULE)
                VALIDATED_PORT_FORWARDS+=("${f1}|${f2}|${f3}|${f4}")
                ;;
        esac
    done <<< "$py_output"

    return 0
}

check_ports_cli() {
    local target_arg="${1:-}"
    local conf_file="${PORTS_CONF}"

    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e "${CYAN}${BOLD}           Port Forwarding Configuration Validator                  ${RESET}"
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e "  Configuration File: ${CYAN}${conf_file}${RESET}"

    if [ ! -e "$conf_file" ]; then
        echo -e "  Status: ${RED}File does not exist!${RESET}"
        return 1
    fi

    if [ -n "$target_arg" ]; then
        local t_ip="${target_arg%/*}"
        local t_sub="${target_arg#*/}"
        [ "$t_sub" = "$target_arg" ] && t_sub="24"
        local t_prefix
        if ! t_prefix=$(parse_and_validate_subnet "$t_sub"); then
            echo -e "  ${RED}Error: Invalid subnet mask/prefix '$t_sub'.${RESET}"
            return 1
        fi
        local ip_err
        if ! ip_err=$(validate_host_ip "$t_ip"); then
            echo -e "  ${RED}Error: Invalid IP '$t_ip' - $ip_err${RESET}"
            return 1
        fi
        if ! validate_and_load_port_forwards "$t_ip" "$t_prefix" "" "$conf_file"; then
            return 1
        fi
        echo ""
        if [ "$MATCHED_PORT_CONF_FOUND" -eq 1 ]; then
            echo -e "  ${GREEN}✓ Valid configuration found for ${t_ip}/${t_prefix}:${RESET}"
            if [ "$CONFIG_DHCP_MODE" = "range" ]; then
                echo -e "    • DHCP Range:       ${CYAN}${CONFIG_DHCP_START} - ${CONFIG_DHCP_END}${RESET}"
            elif [ "$CONFIG_DHCP_MODE" = "none" ]; then
                echo -e "    • DHCP Range:       ${YELLOW}Disabled (none)${RESET}"
            else
                echo -e "    • DHCP Range:       ${DIM}Not specified in config (will prompt / use default)${RESET}"
            fi
            echo -e "    • Port Forwards:    ${BOLD}${#VALIDATED_PORT_FORWARDS[@]}${RESET} rule(s)"
            for rule in "${VALIDATED_PORT_FORWARDS[@]}"; do
                IFS='|' read -r r_port r_dip r_dport r_proto <<< "$rule"
                local proto_disp="TCP/UDP"
                [ "$r_proto" = "tcp" ] && proto_disp="TCP"
                [ "$r_proto" = "udp" ] && proto_disp="UDP"
                printf "      - External Port %-6s (%-7s)  -->  %s:%s\n" "$r_port" "$proto_disp" "$r_dip" "$r_dport"
            done
        else
            echo -e "  ${YELLOW}ℹ JSON syntax is valid, but no configuration entry matches network ${t_ip}/${t_prefix}.${RESET}"
        fi
        echo ""
        return 0
    else
        if ! validate_and_load_port_forwards "__ALL__" "24" "" "$conf_file"; then
            return 1
        fi
        echo ""
        echo -e "  ${GREEN}✓ All network configurations, DHCP ranges, and port rules in '$conf_file' are valid!${RESET}"
        echo -e "  Total validated port forward rules across all networks: ${BOLD}${#VALIDATED_PORT_FORWARDS[@]}${RESET}"
        echo ""
        return 0
    fi
}

# ==============================================================================
# Status & Connected Devices Display
# ==============================================================================

show_status() {
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo -e "${CYAN}${BOLD}                    NAT Internet Sharing Status                     ${RESET}"
    echo -e "${CYAN}${BOLD}====================================================================${RESET}"
    echo ""

    if [ ! -f "$STATE_FILE" ]; then
        echo -e "  Status:                 ${YELLOW}INACTIVE${RESET} (NAT sharing is not currently running)"
        echo ""
        return 1
    fi

    # Read state
    # shellcheck disable=SC1090
    source "$STATE_FILE"

    echo -e "  Status:                 ${GREEN}ACTIVE${RESET}"
    echo -e "  Upstream (Internet):    ${CYAN}${STATE_UPSTREAM_IF}${RESET} (${STATE_UPSTREAM_IP:-No IP})"
    echo -e "  Downstream Target(s):   ${CYAN}${STATE_DOWNSTREAM_IFS}${RESET}"
    if [ "$STATE_IS_BRIDGE" = "1" ]; then
        echo -e "  Bridge Interface:       ${CYAN}${STATE_LAN_DEV}${RESET} (combines downstream adapters)"
    fi
    echo -e "  LAN Gateway IP:         ${GREEN}${STATE_LAN_IP}/${STATE_LAN_PREFIX}${RESET}"

    # DHCP status
    if [ -n "$STATE_DHCP_PID" ] && [ -d "/proc/$STATE_DHCP_PID" ]; then
        echo -e "  DHCP Server:            ${GREEN}RUNNING${RESET} (PID: ${STATE_DHCP_PID})"
        echo -e "  DHCP Pool:              ${STATE_DHCP_START} - ${STATE_DHCP_END}"
    else
        echo -e "  DHCP Server:            ${YELLOW}DISABLED / NOT RUNNING${RESET}"
    fi

    # Display active Port Forwards
    echo ""
    echo -e "${BOLD}Active Port Forwards:${RESET}"
    if [ -n "${STATE_PORT_FORWARDS:-}" ]; then
        printf "  %-14s  %-10s  %-22s  %s\n" "Host Port" "Protocol" "Target Device IP:Port" "Status"
        printf "  %-14s  %-10s  %-22s  %s\n" "--------------" "----------" "----------------------" "--------"
        local pf_entries=()
        IFS=',' read -ra pf_entries <<< "$STATE_PORT_FORWARDS"
        for pf_entry in "${pf_entries[@]}"; do
            local r_port r_dip r_dport r_proto
            IFS='|' read -r r_port r_dip r_dport r_proto <<< "$pf_entry"
            local proto_disp="TCP/UDP"
            [ "$r_proto" = "tcp" ] && proto_disp="TCP"
            [ "$r_proto" = "udp" ] && proto_disp="UDP"
            printf "  %-14s  %-10s  %-22s  %b\n" "$r_port" "$proto_disp" "${r_dip}:${r_dport}" "${GREEN}ACTIVE${RESET}"
        done
    else
        echo "  (No port forwards configured for ${STATE_LAN_IP}/${STATE_LAN_PREFIX})"
    fi

    # Build a lookup map of recent DHCP hostnames/leases from syslog (if readable) and LEASE_FILE
    # This recovers leases that were granted before a service restart or held by active clients
    local -A lease_mac_to_ip=()
    local -A lease_mac_to_name=()
    local -A lease_mac_to_exp=()
    local -a ordered_macs=()

    if [ -f "$LEASE_FILE" ] && [ -s "$LEASE_FILE" ]; then
        while read -r exp mac ip name client_id; do
            [ -z "$mac" ] || [ -z "$ip" ] && continue
            local mac_lc="${mac,,}"
            lease_mac_to_ip["$mac_lc"]="$ip"
            if [ -n "$name" ] && [ "$name" != "*" ]; then
                lease_mac_to_name["$mac_lc"]="$name"
            else
                lease_mac_to_name["$mac_lc"]="<Unknown>"
            fi
            if [ "$exp" = "0" ]; then
                lease_mac_to_exp["$mac_lc"]="Static / Infinite"
            else
                lease_mac_to_exp["$mac_lc"]=$(date -d "@$exp" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "Active")
            fi
            ordered_macs+=("$mac_lc")
        done < "$LEASE_FILE"
    fi

    # Also check syslog / journal for recent DHCPACKs on this interface & subnet
    if [ -n "${STATE_LAN_DEV:-}" ]; then
        local log_lines=""
        if [ -r /var/log/syslog ]; then
            log_lines=$(grep -E "DHCPACK\(${STATE_LAN_DEV}\)" /var/log/syslog 2>/dev/null | tail -n 100)
        elif command -v journalctl >/dev/null 2>&1; then
            log_lines=$(journalctl -t dnsmasq-dhcp -n 100 --no-pager 2>/dev/null | grep -E "DHCPACK\(${STATE_LAN_DEV}\)")
        fi
        if [ -n "$log_lines" ]; then
            while read -r line; do
                [ -z "$line" ] && continue
                # Format: ... DHCPACK(iface) <IP> <MAC> [hostname]
                local ack_part
                ack_part="${line#*DHCPACK("${STATE_LAN_DEV}") }"
                local l_ip l_mac l_name
                read -r l_ip l_mac l_name <<< "$ack_part"
                [ -z "$l_ip" ] || [ -z "$l_mac" ] && continue
                if ! cidrs_overlap "${l_ip}/32" "${STATE_LAN_IP}/${STATE_LAN_PREFIX}"; then
                    continue
                fi
                local mac_lc="${l_mac,,}"
                if [ -z "${lease_mac_to_ip[$mac_lc]:-}" ]; then
                    # Only include from log if not already in LEASE_FILE and within DHCP pool or active in ARP
                    local in_arp=0
                    if ip -4 neigh show dev "$STATE_LAN_DEV" 2>/dev/null | grep -qi "$mac_lc"; then
                        in_arp=1
                    fi
                    if [ "$in_arp" -eq 1 ]; then
                        lease_mac_to_ip["$mac_lc"]="$l_ip"
                        lease_mac_to_name["$mac_lc"]="${l_name:-<Unknown>}"
                        lease_mac_to_exp["$mac_lc"]="Active (DHCP)"
                        ordered_macs+=("$mac_lc")
                    fi
                elif [ "${lease_mac_to_name[$mac_lc]:-<Unknown>}" = "<Unknown>" ] && [ -n "$l_name" ]; then
                    lease_mac_to_name["$mac_lc"]="$l_name"
                fi
            done <<< "$log_lines"
        fi
    fi

    # Also check active ARP/Neighbor table on STATE_LAN_DEV for any devices not yet listed
    if [ -n "${STATE_LAN_DEV:-}" ]; then
        while read -r n_ip _ n_mac n_state; do
            [ -z "$n_ip" ] || [ -z "$n_mac" ] && continue
            local mac_lc="${n_mac,,}"
            if [ -z "${lease_mac_to_ip[$mac_lc]:-}" ]; then
                lease_mac_to_ip["$mac_lc"]="$n_ip"
                lease_mac_to_name["$mac_lc"]="<Static / ARP>"
                # Check if IP falls inside the configured DHCP range
                if [ -n "${STATE_DHCP_START:-}" ] && [ -n "${STATE_DHCP_END:-}" ]; then
                    local ip_i s_i e_i
                    ip_i=$(ip_to_int "$n_ip")
                    s_i=$(ip_to_int "$STATE_DHCP_START")
                    e_i=$(ip_to_int "$STATE_DHCP_END")
                    if (( ip_i >= s_i && ip_i <= e_i )); then
                        lease_mac_to_name["$mac_lc"]="<DHCP Client>"
                        lease_mac_to_exp["$mac_lc"]="Active ($n_state)"
                    else
                        lease_mac_to_exp["$mac_lc"]="Static IP ($n_state)"
                    fi
                else
                    lease_mac_to_exp["$mac_lc"]="Static IP ($n_state)"
                fi
                ordered_macs+=("$mac_lc")
            fi
        done < <(ip -4 neigh show dev "$STATE_LAN_DEV" 2>/dev/null | awk '$2 == "lladdr" && $4 ~ /^(REACHABLE|STALE|DELAY|PROBE|PERMANENT)$/ {print $1, $2, $3, $4}')
    fi

    # Display active DHCP leases & connected LAN devices
    echo ""
    echo -e "${BOLD}Connected Devices (DHCP Leases & Active LAN Clients):${RESET}"
    if [ ${#ordered_macs[@]} -gt 0 ]; then
        printf "  %-17s  %-15s  %-20s  %-20s\n" "MAC Address" "IP Address" "Hostname / Type" "Status / Lease Expiry"
        printf "  %-17s  %-15s  %-20s  %-20s\n" "-----------------" "---------------" "--------------------" "---------------------"
        for mac_lc in "${ordered_macs[@]}"; do
            printf "  %-17s  %-15s  %-20s  %-20s\n" \
                "$mac_lc" \
                "${lease_mac_to_ip[$mac_lc]}" \
                "${lease_mac_to_name[$mac_lc]}" \
                "${lease_mac_to_exp[$mac_lc]}"
        done
    else
        echo "  (No connected DHCP clients detected yet. Plug in a client device to connect.)"
    fi
    echo ""
    return 0
}

monitor_leases() {
    clear_screen
    echo -e "${CYAN}Starting live lease monitor... (Press Ctrl+C to exit monitor)${RESET}\n"
    trap 'echo -e "\nMonitor closed. NAT sharing remains running in the background."; return 0' INT
    local last_content="__INITIAL__"
    while true; do
        local current_content=""
        if [ -f "$LEASE_FILE" ]; then
            current_content=$(cat "$LEASE_FILE" 2>/dev/null)
        fi
        if [ -f "$STATE_FILE" ]; then
            local mon_lan_dev
            mon_lan_dev=$(awk -F'=' '/^STATE_LAN_DEV=/ {gsub(/"/, "", $2); print $2}' "$STATE_FILE" 2>/dev/null)
            if [ -n "$mon_lan_dev" ]; then
                current_content="${current_content}"$'\n'"$(ip -4 neigh show dev "$mon_lan_dev" 2>/dev/null | awk '$2 == "lladdr" && $4 ~ /^(REACHABLE|STALE|DELAY|PROBE|PERMANENT)$/ {print $1, $3, $4}' | sort)"
            fi
        fi

        if [ "$current_content" != "$last_content" ]; then
            clear_screen
            show_status
            echo -e "${DIM}--------------------------------------------------------------------${RESET}"
            echo -e "${CYAN}Live Lease Monitor active. (Press Ctrl+C to exit monitor)${RESET}"
            last_content="$current_content"
        fi
        sleep 2
    done
}

# ==============================================================================
# Stop & Cleanup Function
# ==============================================================================

stop_nat() {
    require_root "$@"
    clear_screen
    echo -e "${YELLOW}${BOLD}====================================================================${RESET}"
    echo -e "${YELLOW}${BOLD}             Stopping NAT Sharing & Restoring Network               ${RESET}"
    echo -e "${YELLOW}${BOLD}====================================================================${RESET}"
    echo ""

    if [ -f "$STATE_FILE" ]; then
        # shellcheck disable=SC1090
        source "$STATE_FILE"
    fi

    local UP_IF="${STATE_UPSTREAM_IF:-}"
    local LAN_DEV="${STATE_LAN_DEV:-}"
    local DOWN_IFS="${STATE_DOWNSTREAM_IFS:-}"
    local IS_BR="${STATE_IS_BRIDGE:-0}"
    local DHCP_P="${STATE_DHCP_PID:-}"
    local PREV_FWD="${STATE_PREV_IP_FORWARD:-0}"

    # 1. Stop dnsmasq DHCP server
    echo -n "  - Stopping DHCP server... "
    if [ -n "$DHCP_P" ] && kill -0 "$DHCP_P" 2>/dev/null; then
        kill "$DHCP_P" 2>/dev/null || true
    fi
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
    local keep_leases="${1:-0}"
    if [ "$keep_leases" != "1" ]; then
        rm -f "$LEASE_FILE"
    fi
    echo -e "${GREEN}[DONE]${RESET}"

    # 2. Remove iptables rules tagged with NAT_SHARE_RULE
    echo -n "  - Removing iptables NAT and FORWARD rules... "
    if [ -n "$UP_IF" ]; then
        iptables -t nat -D POSTROUTING -o "$UP_IF" -j MASQUERADE -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
    fi
    if [ -n "$LAN_DEV" ] && [ -n "$UP_IF" ]; then
        iptables -D FORWARD -i "$LAN_DEV" -o "$UP_IF" -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
        iptables -D FORWARD -i "$UP_IF" -o "$LAN_DEV" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
        iptables -D FORWARD -i "$UP_IF" -o "$LAN_DEV" -m state --state RELATED,ESTABLISHED -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
    fi
    if [ -n "$LAN_DEV" ]; then
        iptables -D INPUT -i "$LAN_DEV" -p udp --dport 67 -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
        iptables -D INPUT -i "$LAN_DEV" -p udp --dport 53 -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
        iptables -D INPUT -i "$LAN_DEV" -p tcp --dport 53 -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
        iptables -D INPUT -i "$LAN_DEV" -p icmp -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
    fi

    # Broad sweep for any lingering rules with our comment
    while iptables-save 2>/dev/null | grep -q "NAT_SHARE_RULE"; do
        local nat_del
        nat_del=$(iptables-save -t nat 2>/dev/null | grep "NAT_SHARE_RULE" | head -n1 | sed 's/^-A //')
        if [ -n "$nat_del" ]; then
            # shellcheck disable=SC2086
            iptables -t nat -D $nat_del 2>/dev/null || break
        fi
        local filter_del
        filter_del=$(iptables-save -t filter 2>/dev/null | grep "NAT_SHARE_RULE" | head -n1 | sed 's/^-A //')
        if [ -n "$filter_del" ]; then
            # shellcheck disable=SC2086
            iptables -t filter -D $filter_del 2>/dev/null || break
        fi
    done
    echo -e "${GREEN}[DONE]${RESET}"

    # 3. Clean up policy routing if used
    echo -n "  - Flushing policy routing rules... "
    if [ -n "$LAN_DEV" ]; then
        ip rule del iif "$LAN_DEV" table "$POLICY_TABLE" 2>/dev/null || true
        ip route flush table "$POLICY_TABLE" 2>/dev/null || true
    fi
    echo -e "${GREEN}[DONE]${RESET}"

    # 4. Clean up interfaces
    echo -n "  - Restoring downstream interface(s)... "
    if [ "$IS_BR" = "1" ] || ip link show dev "$BRIDGE_NAME" >/dev/null 2>&1; then
        ip link set dev "$BRIDGE_NAME" down 2>/dev/null || true
        for slave in $DOWN_IFS; do
            ip link set dev "$slave" nomaster 2>/dev/null || true
            ip link set dev "$slave" down 2>/dev/null || true
            ip addr flush dev "$slave" 2>/dev/null || true
            nmcli dev set "$slave" managed yes 2>/dev/null || true
            nmcli dev connect "$slave" >/dev/null 2>&1 || true
        done
        ip link delete "$BRIDGE_NAME" type bridge 2>/dev/null || true
    else
        for dev in $DOWN_IFS; do
            ip addr flush dev "$dev" 2>/dev/null || true
            nmcli dev set "$dev" managed yes 2>/dev/null || true
            nmcli dev connect "$dev" >/dev/null 2>&1 || true
        done
    fi
    echo -e "${GREEN}[DONE]${RESET}"

    # 5. Restore IP forwarding sysctl
    echo -n "  - Restoring net.ipv4.ip_forward sysctl... "
    if [ "$PREV_FWD" = "0" ]; then
        sysctl -w net.ipv4.ip_forward=0 >/dev/null 2>&1 || true
    fi
    echo -e "${GREEN}[DONE]${RESET}"

    # 6. Remove state file
    rm -f "$STATE_FILE"

    echo ""
    echo -e "${GREEN}${BOLD}NAT Internet Sharing successfully disabled and network restored!${RESET}\n"
    return 0
}

# ==============================================================================
# Start NAT Setup Function (Clean Wizard)
# ==============================================================================

start_nat() {
    require_root "$@"

    # If already running, clean up previous session first (keep leases so active clients remain tracked)
    if [ -f "$STATE_FILE" ]; then
        echo -e "${YELLOW}An existing NAT sharing session was detected. Cleaning it up first...${RESET}"
        stop_nat 1
        sleep 1
    fi

    # --------------------------------------------------------------------------
    # Step 1: Discover & Select Upstream (Internet Source) Interface
    # --------------------------------------------------------------------------
    mapfile -t ALL_IFACES < <(ip -o link show | awk -F': ' '{print $2}' | awk -F'@' '{print $1}' | grep -v '^lo$' | grep -v "^${BRIDGE_NAME}$" | sort -u)

    if [ ${#ALL_IFACES[@]} -eq 0 ]; then
        echo -e "${RED}Error: No network interfaces found on this system.${RESET}"
        exit 1
    fi

    DEFAULT_ROUTE_IF=$(ip -4 route show default 2>/dev/null | awk '/default/ {print $5}' | head -n1)

    # Preferred default upstream candidate: wireless adapter or default route
    DEFAULT_UPSTREAM_IF=""
    for iface in "${ALL_IFACES[@]}"; do
        if is_wireless_iface "$iface"; then
            local ip_addr
            ip_addr=$(ip -4 -o addr show dev "$iface" 2>/dev/null | awk '{print $4}' | head -n1)
            if [ -n "$ip_addr" ] || [ "$iface" = "$DEFAULT_ROUTE_IF" ]; then
                DEFAULT_UPSTREAM_IF="$iface"
                break
            fi
        fi
    done

    if [ -z "$DEFAULT_UPSTREAM_IF" ]; then
        for iface in "${ALL_IFACES[@]}"; do
            if is_wireless_iface "$iface"; then
                DEFAULT_UPSTREAM_IF="$iface"
                break
            fi
        done
    fi

    if [ -z "$DEFAULT_UPSTREAM_IF" ] && [ -n "$DEFAULT_ROUTE_IF" ]; then
        DEFAULT_UPSTREAM_IF="$DEFAULT_ROUTE_IF"
    fi

    if [ -z "$DEFAULT_UPSTREAM_IF" ]; then
        DEFAULT_UPSTREAM_IF="${ALL_IFACES[0]}"
    fi

    # Display Step 1 Page
    print_page_header "NAT Internet Sharing Setup" "Step 1 of 3"
    echo "Select the network adapter providing your Internet connection (WAN source):"
    echo ""
    printf "  %-4s %-15s %-16s %-6s %-20s %s\n" "#" "Interface" "Type" "Link" "Current IP" "Notes"
    printf "  %-4s %-15s %-16s %-6s %-20s %s\n" "----" "---------------" "----------------" "------" "--------------------" "----------------"

    DEFAULT_UPSTREAM_IDX=1
    for idx in "${!ALL_IFACES[@]}"; do
        local iface="${ALL_IFACES[idx]}"
        local num=$((idx + 1))
        local if_type="Ethernet"
        if is_wireless_iface "$iface"; then
            if_type="Wireless/Wi-Fi"
        elif is_virtual_iface "$iface"; then
            if_type="Virtual"
        fi

        local ip_info
        ip_info=$(ip -4 -o addr show dev "$iface" 2>/dev/null | awk '{print $4}' | head -n1)
        [ -z "$ip_info" ] && ip_info="No IP assigned"

        local status_str="DOWN"
        if ip link show dev "$iface" 2>/dev/null | grep -q "state UP"; then
            status_str="UP"
        fi

        local tag=""
        if [ "$iface" = "$DEFAULT_UPSTREAM_IF" ]; then
            DEFAULT_UPSTREAM_IDX=$num
            tag=" ${GREEN}[DEFAULT]${RESET}"
        fi
        if [ "$iface" = "$DEFAULT_ROUTE_IF" ]; then
            tag="${tag} (Default Route)"
        fi

        printf "  %-4s %-15s %-16s %-6s %-20s %b\n" "$num)" "$iface" "$if_type" "$status_str" "$ip_info" "$tag"
    done

    echo ""
    read -p "Select upstream interface [$DEFAULT_UPSTREAM_IDX]: " UPSTREAM_CHOICE
    UPSTREAM_CHOICE="$(trim_whitespace "$UPSTREAM_CHOICE")"
    UPSTREAM_CHOICE=${UPSTREAM_CHOICE:-$DEFAULT_UPSTREAM_IDX}

    UPSTREAM_IF=""
    if [[ "$UPSTREAM_CHOICE" =~ ^[0-9]+$ ]] && [ "$UPSTREAM_CHOICE" -ge 1 ] && [ "$UPSTREAM_CHOICE" -le "${#ALL_IFACES[@]}" ]; then
        UPSTREAM_IF="${ALL_IFACES[$((UPSTREAM_CHOICE - 1))]}"
    else
        for candidate in "${ALL_IFACES[@]}"; do
            if [ "$UPSTREAM_CHOICE" = "$candidate" ]; then
                UPSTREAM_IF="$candidate"
                break
            fi
        done
    fi

    if [ -z "$UPSTREAM_IF" ] || ! ip link show dev "$UPSTREAM_IF" >/dev/null 2>&1; then
        echo -e "${RED}Error: Invalid upstream interface selected: '$UPSTREAM_CHOICE'.${RESET}"
        exit 1
    fi

    # --------------------------------------------------------------------------
    # Step 2: Discover & Select Downstream (Target) Interface(s)
    # --------------------------------------------------------------------------
    UPSTREAM_IP_FULL=$(ip -4 -o addr show dev "$UPSTREAM_IF" 2>/dev/null | awk '{print $4}' | head -n1)
    UPSTREAM_IP="${UPSTREAM_IP_FULL%/*}"

    # Downstream candidates: sort physical adapters first so Ethernet is default
    DOWNSTREAM_CANDIDATES=()
    for iface in "${ALL_IFACES[@]}"; do
        if [ "$iface" != "$UPSTREAM_IF" ] && [ "$iface" != "lo" ] && [ "$iface" != "$BRIDGE_NAME" ]; then
            if ! is_virtual_iface "$iface"; then
                DOWNSTREAM_CANDIDATES+=("$iface")
            fi
        fi
    done
    for iface in "${ALL_IFACES[@]}"; do
        if [ "$iface" != "$UPSTREAM_IF" ] && [ "$iface" != "lo" ] && [ "$iface" != "$BRIDGE_NAME" ]; then
            if is_virtual_iface "$iface"; then
                DOWNSTREAM_CANDIDATES+=("$iface")
            fi
        fi
    done

    if [ ${#DOWNSTREAM_CANDIDATES[@]} -eq 0 ]; then
        echo -e "${RED}Error: No additional network adapters available to share internet to.${RESET}"
        echo "Please plug in an Ethernet cable, USB Ethernet adapter, or other network card."
        exit 1
    fi

    print_page_header "NAT Internet Sharing Setup" "Step 2 of 3"
    print_context_box "$UPSTREAM_IF" "$UPSTREAM_IP"
    echo "Select the target adapter(s) to share internet with (LAN / Clients):"
    echo ""
    printf "  %-4s %-15s %-16s %-6s %-20s\n" "#" "Interface" "Type" "Link" "Current IP"
    printf "  %-4s %-15s %-16s %-6s %-20s\n" "----" "---------------" "----------------" "------" "--------------------"

    for idx in "${!DOWNSTREAM_CANDIDATES[@]}"; do
        local iface="${DOWNSTREAM_CANDIDATES[idx]}"
        local num=$((idx + 1))
        local if_type="Ethernet"
        if is_wireless_iface "$iface"; then
            if_type="Wireless"
        elif is_virtual_iface "$iface"; then
            if_type="Virtual"
        fi

        local ip_info
        ip_info=$(ip -4 -o addr show dev "$iface" 2>/dev/null | awk '{print $4}' | head -n1)
        [ -z "$ip_info" ] && ip_info="No IP assigned"

        local status_str="DOWN"
        if ip link show dev "$iface" 2>/dev/null | grep -q "state UP"; then
            status_str="UP"
        fi

        printf "  %-4s %-15s %-16s %-6s %-20s\n" "$num)" "$iface" "$if_type" "$status_str" "$ip_info"
    done

    echo ""
    echo -e "${DIM}Tip: You can select one, multiple (e.g. '1,2'), or 'all'.${RESET}"
    read -p "Select downstream adapter(s) [1]: " DOWNSTREAM_INPUT
    DOWNSTREAM_INPUT="$(trim_whitespace "$DOWNSTREAM_INPUT")"
    DOWNSTREAM_INPUT=${DOWNSTREAM_INPUT:-1}

    SELECTED_DOWNSTREAM_IFS=()
    if [ "${DOWNSTREAM_INPUT,,}" = "all" ]; then
        SELECTED_DOWNSTREAM_IFS=("${DOWNSTREAM_CANDIDATES[@]}")
    else
        local tokens
        tokens=$(echo "$DOWNSTREAM_INPUT" | tr ',' ' ')
        for token in $tokens; do
            token="$(trim_whitespace "$token")"
            if [[ "$token" =~ ^[0-9]+$ ]] && [ "$token" -ge 1 ] && [ "$token" -le "${#DOWNSTREAM_CANDIDATES[@]}" ]; then
                local chosen_if="${DOWNSTREAM_CANDIDATES[$((token - 1))]}"
                local already_added=0
                for existing in "${SELECTED_DOWNSTREAM_IFS[@]}"; do
                    if [ "$existing" = "$chosen_if" ]; then
                        already_added=1
                        break
                    fi
                done
                [ "$already_added" -eq 0 ] && SELECTED_DOWNSTREAM_IFS+=("$chosen_if")
            else
                for candidate in "${DOWNSTREAM_CANDIDATES[@]}"; do
                    if [ "$token" = "$candidate" ]; then
                        local already_added=0
                        for existing in "${SELECTED_DOWNSTREAM_IFS[@]}"; do
                            if [ "$existing" = "$candidate" ]; then
                                already_added=1
                                break
                            fi
                        done
                        [ "$already_added" -eq 0 ] && SELECTED_DOWNSTREAM_IFS+=("$candidate")
                        break
                    fi
                done
            fi
        done
    fi

    if [ ${#SELECTED_DOWNSTREAM_IFS[@]} -eq 0 ]; then
        echo -e "${RED}Error: No valid downstream interface(s) selected from input: '$DOWNSTREAM_INPUT'.${RESET}"
        exit 1
    fi

    # --------------------------------------------------------------------------
    # Step 3: IP Subnet & DHCP Configuration (Conflict Testing Engine)
    # --------------------------------------------------------------------------
    print_page_header "NAT Internet Sharing Setup" "Step 3 of 3"
    print_context_box "$UPSTREAM_IF" "$UPSTREAM_IP" "${SELECTED_DOWNSTREAM_IFS[*]}"

    echo -e "${BOLD}Scanning System Routes & Network Adapters for Conflicts...${RESET}"

    # Gather system routes for transparency
    mapfile -t DETECTED_SUBNETS < <(get_system_cidrs "lo $BRIDGE_NAME ${SELECTED_DOWNSTREAM_IFS[*]}" | awk '{print $1 " (" $2 ")"}' | sort -u)
    if [ ${#DETECTED_SUBNETS[@]} -gt 0 ]; then
        echo -e "  • ${DIM}Existing network routes checked:${RESET} ${DETECTED_SUBNETS[*]}"
    fi

    echo -n "  • Testing candidate subnets for routing collisions... "
    BEST_CANDIDATE=$(find_best_lan_subnet "lo $BRIDGE_NAME ${SELECTED_DOWNSTREAM_IFS[*]}")
    echo -e "${GREEN}[VERIFIED FREE]${RESET}"
    echo -e "  • Verified Gateway IP: ${GREEN}${BEST_CANDIDATE}${RESET} (0 collisions, no active host response)"
    echo ""

    DEFAULT_LAN_IP="${BEST_CANDIDATE%/*}"
    DEFAULT_LAN_PREFIX="${BEST_CANDIDATE#*/}"

    while true; do
        read -p "Enter LAN Gateway IP [${DEFAULT_LAN_IP}/${DEFAULT_LAN_PREFIX}]: " LAN_IP_INPUT
        LAN_IP_INPUT="$(trim_whitespace "$LAN_IP_INPUT")"

        if [ -z "$LAN_IP_INPUT" ]; then
            LAN_IP="$DEFAULT_LAN_IP"
            LAN_PREFIX="$DEFAULT_LAN_PREFIX"
            break
        elif [[ "$LAN_IP_INPUT" == */* ]]; then
            LAN_IP="${LAN_IP_INPUT%/*}"
            local sub="${LAN_IP_INPUT#*/}"
            LAN_IP="$(trim_whitespace "$LAN_IP")"
            if ! LAN_PREFIX=$(parse_and_validate_subnet "$sub"); then
                echo -e "${RED}Error: Invalid subnet prefix '$sub'.${RESET}"
                continue
            fi
        else
            LAN_IP="$LAN_IP_INPUT"
            LAN_PREFIX="24"
        fi

        local val_err=""
        if ! val_err=$(validate_host_ip "$LAN_IP"); then
            echo -e "${RED}Error: Invalid LAN IP address '$LAN_IP' - $val_err${RESET}"
            continue
        fi

        # If user entered custom IP, test for conflicts in real time
        if [ "$LAN_IP" != "$DEFAULT_LAN_IP" ] || [ "$LAN_PREFIX" != "$DEFAULT_LAN_PREFIX" ]; then
            local conflict_reason
            if conflict_reason=$(check_cidr_conflict "${LAN_IP}/${LAN_PREFIX}" "lo $BRIDGE_NAME ${SELECTED_DOWNSTREAM_IFS[*]}"); then
                echo -e "  --> ${GREEN}Custom subnet ${LAN_IP}/${LAN_PREFIX} verified free of conflicts!${RESET}"
                break
            else
                echo -e "  ${YELLOW}Warning: Custom subnet ${LAN_IP}/${LAN_PREFIX} $conflict_reason!${RESET}"
                read -p "  Do you want to force use this subnet anyway? [y/N]: " FORCE_CHOICE
                FORCE_CHOICE="$(trim_whitespace "$FORCE_CHOICE")"
                if [[ "${FORCE_CHOICE,,}" =~ ^y ]]; then
                    break
                fi
                echo "  Please choose a non-conflicting IP or press Enter for the verified default."
            fi
        else
            break
        fi
    done

    # Check & Validate Port Forwarding Configuration for this network
    echo ""
    echo -e "${BOLD}Port Forwarding Configuration (${PORTS_CONF##*/}):${RESET}"
    if [ -e "$PORTS_CONF" ]; then
        if ! validate_and_load_port_forwards "$LAN_IP" "$LAN_PREFIX" "$UPSTREAM_IP" "$PORTS_CONF"; then
            echo -e "${RED}${BOLD}Aborted: Please fix the configuration error(s) in '${PORTS_CONF}' and run again.${RESET}"
            exit 1
        fi
        if [ "$MATCHED_PORT_CONF_FOUND" -eq 1 ]; then
            if [ ${#VALIDATED_PORT_FORWARDS[@]} -gt 0 ]; then
                echo -e "  • ${GREEN}✓ Verified 1 configuration for ${LAN_IP}/${LAN_PREFIX} (${#VALIDATED_PORT_FORWARDS[@]} port forward(s)):${RESET}"
                for rule in "${VALIDATED_PORT_FORWARDS[@]}"; do
                    local r_port r_dip r_dport r_proto
                    IFS='|' read -r r_port r_dip r_dport r_proto <<< "$rule"
                    local proto_disp="TCP/UDP"
                    [ "$r_proto" = "tcp" ] && proto_disp="TCP"
                    [ "$r_proto" = "udp" ] && proto_disp="UDP"
                    printf "    - Host Port %-6s (%-7s)  -->  %s:%s\n" "$r_port" "$proto_disp" "$r_dip" "$r_dport"
                done
            else
                echo -e "  • ${YELLOW}ℹ Configuration found for ${LAN_IP}/${LAN_PREFIX}, but no port rules are defined.${RESET}"
            fi
        else
            echo -e "  • ${DIM}No configuration entry for ${LAN_IP}/${LAN_PREFIX} in ${PORTS_CONF##*/} (port forwarding skipped).${RESET}"
        fi
    else
        echo -e "  • ${DIM}File '${PORTS_CONF##*/}' not found (port forwarding skipped).${RESET}"
    fi

    echo ""
    echo -e "${BOLD}DHCP Server Configuration:${RESET}"
    if [ "$MATCHED_PORT_CONF_FOUND" -eq 1 ] && [ "$CONFIG_DHCP_MODE" = "none" ]; then
        USE_DHCP=false
        DHCP_START=""
        DHCP_END=""
        echo -e "  • Configured in ${PORTS_CONF##*/}: ${YELLOW}none (DHCP disabled)${RESET}"
        echo -e "  • Connected devices must configure a static IP."
    elif [ "$MATCHED_PORT_CONF_FOUND" -eq 1 ] && [ "$CONFIG_DHCP_MODE" = "range" ]; then
        DHCP_START="$CONFIG_DHCP_START"
        DHCP_END="$CONFIG_DHCP_END"
        echo -e "  • DHCP IP Range (from ${PORTS_CONF##*/}): ${CYAN}${DHCP_START} - ${DHCP_END}${RESET}"
        read -p "Enable automatic DHCP server with this range? [Y/n]: " ENABLE_DHCP_CHOICE
        ENABLE_DHCP_CHOICE="$(trim_whitespace "$ENABLE_DHCP_CHOICE")"
        ENABLE_DHCP_CHOICE=${ENABLE_DHCP_CHOICE:-Y}

        USE_DHCP=true
        if [[ "${ENABLE_DHCP_CHOICE,,}" =~ ^n ]]; then
            USE_DHCP=false
            echo -e "  DHCP server disabled. Connected devices must configure static IP."
        else
            echo -e "  DHCP server enabled (${DHCP_START} - ${DHCP_END})."
        fi
    else
        IFS=. read -r l1 l2 l3 l4 <<< "$LAN_IP"
        DHCP_START="${l1}.${l2}.${l3}.50"
        DHCP_END="${l1}.${l2}.${l3}.200"
        echo -e "  • DHCP IP Range (default): ${CYAN}${DHCP_START} - ${DHCP_END}${RESET}"
        read -p "Enable automatic DHCP server for connected devices? [Y/n]: " ENABLE_DHCP_CHOICE
        ENABLE_DHCP_CHOICE="$(trim_whitespace "$ENABLE_DHCP_CHOICE")"
        ENABLE_DHCP_CHOICE=${ENABLE_DHCP_CHOICE:-Y}

        USE_DHCP=true
        if [[ "${ENABLE_DHCP_CHOICE,,}" =~ ^n ]]; then
            USE_DHCP=false
            echo -e "  DHCP server disabled. Connected devices must configure static IP."
        else
            echo -e "  DHCP server enabled (${DHCP_START} - ${DHCP_END})."
        fi
    fi

    # --------------------------------------------------------------------------
    # Step 4: Applying Network Configuration
    # --------------------------------------------------------------------------
    print_page_header "Applying NAT Configuration" "Please wait..."
    print_context_box "$UPSTREAM_IF" "$UPSTREAM_IP" "${SELECTED_DOWNSTREAM_IFS[*]}"

    echo -e "${BOLD}Applying network adapter and firewall configuration...${RESET}\n"

    IS_BRIDGE=0
    LAN_DEV=""

    if [ ${#SELECTED_DOWNSTREAM_IFS[@]} -gt 1 ]; then
        IS_BRIDGE=1
        LAN_DEV="$BRIDGE_NAME"
        echo -n "  [1/6] Creating bridge '$BRIDGE_NAME' for target adapters... "

        if ip link show dev "$BRIDGE_NAME" >/dev/null 2>&1; then
            ip link set dev "$BRIDGE_NAME" down 2>/dev/null || true
            ip link delete "$BRIDGE_NAME" type bridge 2>/dev/null || true
        fi

        ip link add name "$BRIDGE_NAME" type bridge

        for dev in "${SELECTED_DOWNSTREAM_IFS[@]}"; do
            nmcli dev set "$dev" managed no 2>/dev/null || true
            ip link set dev "$dev" down 2>/dev/null || true
            ip addr flush dev "$dev" 2>/dev/null || true
            ip link set dev "$dev" master "$BRIDGE_NAME" 2>/dev/null || true
            ip link set dev "$dev" up 2>/dev/null || true
        done

        ip link set dev "$BRIDGE_NAME" up
        ip addr flush dev "$BRIDGE_NAME" 2>/dev/null || true
        ip addr add "${LAN_IP}/${LAN_PREFIX}" dev "$BRIDGE_NAME"
        echo -e "${GREEN}[DONE]${RESET}"
    else
        IS_BRIDGE=0
        LAN_DEV="${SELECTED_DOWNSTREAM_IFS[0]}"
        echo -n "  [1/6] Configuring adapter '$LAN_DEV' (${LAN_IP}/${LAN_PREFIX})... "

        nmcli dev set "$LAN_DEV" managed no 2>/dev/null || true
        ip link set dev "$LAN_DEV" down 2>/dev/null || true
        ip addr flush dev "$LAN_DEV" 2>/dev/null || true
        ip addr add "${LAN_IP}/${LAN_PREFIX}" dev "$LAN_DEV"
        ip link set dev "$LAN_DEV" up 2>/dev/null || true
        echo -e "${GREEN}[DONE]${RESET}"
    fi

    # 2. IP Forwarding
    echo -n "  [2/6] Enabling IPv4 packet forwarding (sysctl)... "
    PREV_IP_FORWARD=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo "0")
    sysctl -w net.ipv4.ip_forward=1 >/dev/null
    echo -e "${GREEN}[DONE]${RESET}"

    # 3. IPTables Rules
    echo -n "  [3/6] Applying iptables NAT Masquerade & Firewall rules... "
    iptables -t nat -I POSTROUTING 1 -o "$UPSTREAM_IF" -j MASQUERADE -m comment --comment "NAT_SHARE_RULE"
    iptables -I FORWARD 1 -i "$LAN_DEV" -o "$UPSTREAM_IF" -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    if iptables -m conntrack --help >/dev/null 2>&1; then
        iptables -I FORWARD 2 -i "$UPSTREAM_IF" -o "$LAN_DEV" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    else
        iptables -I FORWARD 2 -i "$UPSTREAM_IF" -o "$LAN_DEV" -m state --state RELATED,ESTABLISHED -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    fi
    iptables -I INPUT 1 -i "$LAN_DEV" -p udp --dport 67 -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    iptables -I INPUT 2 -i "$LAN_DEV" -p udp --dport 53 -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    iptables -I INPUT 3 -i "$LAN_DEV" -p tcp --dport 53 -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    iptables -I INPUT 4 -i "$LAN_DEV" -p icmp -j ACCEPT -m comment --comment "NAT_SHARE_RULE"
    echo -e "${GREEN}[DONE]${RESET}"

    # 4. Port Forwarding Rules (DNAT + FORWARD + Hairpin)
    PORT_FORWARDS_SERIALIZED=""
    if [ ${#VALIDATED_PORT_FORWARDS[@]} -gt 0 ]; then
        echo -n "  [4/6] Setting up ${#VALIDATED_PORT_FORWARDS[@]} port forward rule(s) (${PORTS_CONF##*/})... "
        for rule in "${VALIDATED_PORT_FORWARDS[@]}"; do
            local r_port r_dip r_dport r_proto
            IFS='|' read -r r_port r_dip r_dport r_proto <<< "$rule"
            local protos=("tcp" "udp")
            [ "$r_proto" = "tcp" ] && protos=("tcp")
            [ "$r_proto" = "udp" ] && protos=("udp")

            for p in "${protos[@]}"; do
                # Incoming traffic from Upstream (WAN) interface -> DNAT to target LAN device
                if ! iptables -t nat -A PREROUTING -i "$UPSTREAM_IF" -p "$p" --dport "$r_port" -j DNAT --to-destination "${r_dip}:${r_dport}" -m comment --comment "NAT_SHARE_RULE"; then
                    echo -e "${RED}[FAILED]${RESET}"
                    echo -e "${RED}Error: Failed to apply iptables PREROUTING DNAT rule for port $r_port/$p -> ${r_dip}:${r_dport}.${RESET}"
                    stop_nat
                    exit 1
                fi
                # Allow forwarded traffic from Upstream to target LAN device
                if ! iptables -I FORWARD 1 -i "$UPSTREAM_IF" -o "$LAN_DEV" -p "$p" -d "$r_dip" --dport "$r_dport" -j ACCEPT -m comment --comment "NAT_SHARE_RULE"; then
                    echo -e "${RED}[FAILED]${RESET}"
                    echo -e "${RED}Error: Failed to apply iptables FORWARD rule for port $r_port/$p -> ${r_dip}:${r_dport}.${RESET}"
                    stop_nat
                    exit 1
                fi
                # Host-local and LAN hairpin access via Upstream IP (if Upstream IP is assigned)
                if [ -n "$UPSTREAM_IP" ]; then
                    iptables -t nat -A PREROUTING -i "$LAN_DEV" -d "$UPSTREAM_IP" -p "$p" --dport "$r_port" -j DNAT --to-destination "${r_dip}:${r_dport}" -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
                    iptables -I FORWARD 1 -i "$LAN_DEV" -o "$LAN_DEV" -p "$p" -d "$r_dip" --dport "$r_dport" -j ACCEPT -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
                    iptables -t nat -A POSTROUTING -o "$LAN_DEV" -p "$p" -d "$r_dip" --dport "$r_dport" -j MASQUERADE -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
                    iptables -t nat -A OUTPUT -d "$UPSTREAM_IP" -p "$p" --dport "$r_port" -j DNAT --to-destination "${r_dip}:${r_dport}" -m comment --comment "NAT_SHARE_RULE" 2>/dev/null || true
                fi
            done

            if [ -z "$PORT_FORWARDS_SERIALIZED" ]; then
                PORT_FORWARDS_SERIALIZED="$rule"
            else
                PORT_FORWARDS_SERIALIZED="${PORT_FORWARDS_SERIALIZED},${rule}"
            fi
        done
        echo -e "${GREEN}[DONE]${RESET}"
    else
        echo -e "  [4/6] Port forwarding: no rules configured for ${LAN_IP}/${LAN_PREFIX}. ${DIM}[SKIPPED]${RESET}"
    fi

    # 5. Policy Routing
    echo -n "  [5/6] Checking default gateway policy routing... "
    CURR_DEF_IF=$(ip -4 route show default 2>/dev/null | awk '/default/ {print $5}' | head -n1)
    if [ "$UPSTREAM_IF" != "$CURR_DEF_IF" ]; then
        UPSTREAM_GW=$(ip -4 route show dev "$UPSTREAM_IF" 2>/dev/null | awk '/default/ {print $3}' | head -n1)
        if [ -n "$UPSTREAM_GW" ]; then
            ip rule add iif "$LAN_DEV" table "$POLICY_TABLE" 2>/dev/null || true
            ip route replace default via "$UPSTREAM_GW" dev "$UPSTREAM_IF" table "$POLICY_TABLE" 2>/dev/null || true
        fi
    fi
    echo -e "${GREEN}[DONE]${RESET}"

    # 6. DHCP Server (dnsmasq)
    DHCP_PID=""
    if [ "$USE_DHCP" = true ]; then
        if command -v dnsmasq >/dev/null 2>&1; then
            echo -n "  [6/6] Launching DHCP service (dnsmasq)... "

            UPSTREAM_DNS_RAW=$(resolvectl dns "$UPSTREAM_IF" 2>/dev/null | awk -F':' '{print $2}' || true)
            DNS_SERVERS="1.1.1.1,8.8.8.8"
            for d in $UPSTREAM_DNS_RAW; do
                if [[ "$d" =~ ^[0-9.]+$ ]]; then
                    DNS_SERVERS="$d,$DNS_SERVERS"
                fi
            done

            touch "$LEASE_FILE" && chmod 666 "$LEASE_FILE"
            # Prune any stale leases that do not belong to the selected LAN subnet
            if [ -s "$LEASE_FILE" ]; then
                local keep_lines=""
                while read -r l_exp l_mac l_ip l_name l_cid; do
                    [ -z "$l_ip" ] && continue
                    if cidrs_overlap "${l_ip}/32" "${LAN_IP}/${LAN_PREFIX}"; then
                        keep_lines="${keep_lines}${l_exp} ${l_mac} ${l_ip} ${l_name} ${l_cid}"$'\n'
                    fi
                done < "$LEASE_FILE"
                printf "%s" "$keep_lines" > "$LEASE_FILE"
            fi
            rm -f "$PID_FILE"

            local dhcp_netmask
            dhcp_netmask=$(int_to_ip "$(( (0xFFFFFFFF << (32 - LAN_PREFIX)) & 0xFFFFFFFF ))")

            if ! dnsmasq \
                --conf-file=/dev/null \
                --no-hosts \
                --user=root \
                --bind-interfaces \
                --interface="$LAN_DEV" \
                --except-interface=lo \
                --listen-address="$LAN_IP" \
                --dhcp-range="$DHCP_START,$DHCP_END,$dhcp_netmask,12h" \
                --dhcp-option=3,"$LAN_IP" \
                --dhcp-option=6,"$DNS_SERVERS" \
                --dhcp-leasefile="$LEASE_FILE" \
                --pid-file="$PID_FILE" >/dev/null 2>&1; then
                
                # Fallback to port=0 (DHCP only mode)
                dnsmasq \
                    --conf-file=/dev/null \
                    --port=0 \
                    --user=root \
                    --no-hosts \
                    --bind-interfaces \
                    --interface="$LAN_DEV" \
                    --except-interface=lo \
                    --listen-address="$LAN_IP" \
                    --dhcp-range="$DHCP_START,$DHCP_END,$dhcp_netmask,12h" \
                    --dhcp-option=3,"$LAN_IP" \
                    --dhcp-option=6,"$DNS_SERVERS" \
                    --dhcp-leasefile="$LEASE_FILE" \
                    --pid-file="$PID_FILE" >/dev/null 2>&1 || true
            fi

            if [ -f "$PID_FILE" ]; then
                DHCP_PID=$(cat "$PID_FILE" 2>/dev/null)
                echo -e "${GREEN}[DONE]${RESET} (PID: $DHCP_PID)"
            else
                echo -e "${YELLOW}[FAILED] (Clients will require static IP)${RESET}"
            fi
        else
            echo -e "  [6/6] ${YELLOW}Warning: 'dnsmasq' not installed. Clients must use static IP.${RESET}"
        fi
    else
        echo -e "  [6/6] DHCP server disabled."
    fi

    # Save state
    cat <<EOF > "$STATE_FILE"
STATE_UPSTREAM_IF="$UPSTREAM_IF"
STATE_UPSTREAM_IP="$UPSTREAM_IP"
STATE_DOWNSTREAM_IFS="${SELECTED_DOWNSTREAM_IFS[*]}"
STATE_LAN_DEV="$LAN_DEV"
STATE_IS_BRIDGE="$IS_BRIDGE"
STATE_LAN_IP="$LAN_IP"
STATE_LAN_PREFIX="$LAN_PREFIX"
STATE_DHCP_PID="$DHCP_PID"
STATE_DHCP_START="$DHCP_START"
STATE_DHCP_END="$DHCP_END"
STATE_PREV_IP_FORWARD="$PREV_IP_FORWARD"
STATE_PORT_FORWARDS="$PORT_FORWARDS_SERIALIZED"
EOF

    # Brief pause before showing clean dashboard
    sleep 1

    # --------------------------------------------------------------------------
    # Final Active Dashboard
    # --------------------------------------------------------------------------
    clear_screen
    echo -e "${GREEN}${BOLD}====================================================================${RESET}"
    echo -e "${GREEN}${BOLD}       NAT Internet Sharing Successfully Configured & ACTIVE!       ${RESET}"
    echo -e "${GREEN}${BOLD}====================================================================${RESET}"
    echo ""
    echo -e "  ${BOLD}Upstream (Internet Source):${RESET} ${CYAN}${UPSTREAM_IF}${RESET} (${UPSTREAM_IP:-Active})"
    echo -e "  ${BOLD}Downstream Target(s):${RESET}       ${CYAN}${SELECTED_DOWNSTREAM_IFS[*]}${RESET}"
    if [ "$IS_BRIDGE" = "1" ]; then
        echo -e "  ${BOLD}Bridge Interface:${RESET}           ${CYAN}${LAN_DEV}${RESET}"
    fi
    echo -e "  ${BOLD}LAN Gateway IP:${RESET}             ${GREEN}${LAN_IP}/${LAN_PREFIX}${RESET}"
    if [ -n "$DHCP_PID" ]; then
        echo -e "  ${BOLD}DHCP Server:${RESET}                ${GREEN}Active${RESET} (Pool: ${DHCP_START} - ${DHCP_END})"
        echo -e "  ${BOLD}DNS Forwarders:${RESET}             ${DNS_SERVERS}"
    fi
    echo ""
    echo -e "${BOLD}Active Port Forwards:${RESET}"
    if [ ${#VALIDATED_PORT_FORWARDS[@]} -gt 0 ]; then
        for rule in "${VALIDATED_PORT_FORWARDS[@]}"; do
            local r_port r_dip r_dport r_proto
            IFS='|' read -r r_port r_dip r_dport r_proto <<< "$rule"
            local proto_disp="TCP/UDP"
            [ "$r_proto" = "tcp" ] && proto_disp="TCP"
            [ "$r_proto" = "udp" ] && proto_disp="UDP"
            printf "  • Host Port %-6s (%-7s)  -->  ${GREEN}%s:%s${RESET}\n" "$r_port" "$proto_disp" "$r_dip" "$r_dport"
        done
    else
        echo "  (None configured for ${LAN_IP}/${LAN_PREFIX})"
    fi
    echo ""
    echo -e "${BOLD}Connected Devices:${RESET}"
    echo "  Plug in any device via Ethernet / target adapter; it will automatically"
    echo "  receive an IP address and immediate internet access."
    echo ""
    echo -e "${BOLD}Quick Commands:${RESET}"
    echo "  • Check status:        sudo $0 --status"
    echo "  • Monitor leases live: sudo $0 --monitor"
    echo "  • Validate port conf:  $0 --check-ports"
    echo "  • Stop sharing:        sudo $0 --stop"
    echo ""
    echo -e "${CYAN}====================================================================${RESET}"
    echo ""

    if [ -n "$DHCP_PID" ]; then
        read -p "Would you like to monitor connected devices in real time? [y/N]: " MON_CHOICE
        MON_CHOICE="$(trim_whitespace "$MON_CHOICE")"
        if [[ "${MON_CHOICE,,}" =~ ^y ]]; then
            monitor_leases
        fi
    fi
}

# ==============================================================================
# Main Entry Point & CLI Arguments
# ==============================================================================

case "$1" in
    --stop|-s|stop)
        stop_nat
        exit 0
        ;;
    --status|status)
        show_status
        exit 0
        ;;
    --monitor|-m)
        if [ ! -f "$STATE_FILE" ]; then
            echo -e "${YELLOW}NAT sharing is not currently running.${RESET}"
            exit 1
        fi
        monitor_leases
        exit 0
        ;;
    --check-ports|--validate-ports|check-ports)
        check_ports_cli "$2"
        exit $?
        ;;
    --start|start)
        start_nat
        exit 0
        ;;
    *)
        # Interactive Mode
        if [ -f "$STATE_FILE" ]; then
            clear_screen
            show_status
            echo -e "${BOLD}Select Action:${RESET}"
            echo "  1) Stop NAT sharing and restore network"
            echo "  2) Restart / Reconfigure NAT sharing"
            echo "  3) Monitor connected devices live (leases)"
            echo "  4) Exit"
            echo ""
            read -p "Enter choice [1]: " ACTION_CHOICE
            ACTION_CHOICE="$(trim_whitespace "$ACTION_CHOICE")"
            ACTION_CHOICE=${ACTION_CHOICE:-1}

            case "$ACTION_CHOICE" in
                1) stop_nat ;;
                2) start_nat ;;
                3) monitor_leases ;;
                4) exit 0 ;;
                *) echo "Invalid option."; exit 1 ;;
            esac
        else
            start_nat
        fi
        ;;
esac
