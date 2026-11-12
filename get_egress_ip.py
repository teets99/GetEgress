#!/usr/bin/env python3
from __future__ import annotations  # enables modern type hint syntax on Python 3.7+
"""
pa_egress_ips.py — Retrieve Prisma Access GlobalProtect gateway egress IPs,
display them in a formatted table, and write them to /var/www/html/prisma.txt.

API Used: Prisma Access Datapath API (getPrismaAccessIP/v2)
Auth:     header-api-key (passed via curl-style command string)

Reference:
  https://docs.paloaltonetworks.com/prisma/prisma-access/3-1/prisma-access-panorama-admin/
  prisma-access-overview/retrieve-ip-addresses-for-prisma-access

Usage:
  python3 pa_egress_ips.py

  When prompted, paste the full curl command, e.g.:
    curl -X POST -d @option.txt -H "header-api-key: 1234abcd" \
         "https://api.prod8.datapath.prismaaccess.com/getPrismaAccessIP/v2"
"""

import re
import sys
import requests
from tabulate import tabulate


# ---------------------------------------------------------------------------
# Curl command parsing
# ---------------------------------------------------------------------------

def parse_curl_command(curl_cmd: str) -> tuple[str, str]:
    """
    Extract the API key and URL from a curl command string.

    Looks for:
      - Header flag:  -H "header-api-key: <value>"
      - URL:          the last quoted string that starts with https://

    Args:
        curl_cmd: The raw curl command pasted by the user.

    Returns:
        A (api_key, url) tuple.

    Raises:
        ValueError: If either the API key header or a valid URL cannot be found.
    """
    # Match:  -H "header-api-key: <token>"  or  -H 'header-api-key: <token>'
    key_match = re.search(
        r'-H\s+["\']header-api-key:\s*([^\'"]+)["\']',
        curl_cmd,
        re.IGNORECASE,
    )
    if not key_match:
        raise ValueError(
            "Could not find 'header-api-key' in the curl command.\n"
            "Expected format:  -H \"header-api-key: <your-key>\""
        )
    api_key = key_match.group(1).strip()

    # Match the URL — last quoted https:// string in the command
    url_matches = re.findall(r'["\']?(https://[^\s\'"]+)["\']?', curl_cmd)
    if not url_matches:
        raise ValueError(
            "Could not find a valid https:// URL in the curl command."
        )
    # Take the last match; curl puts the URL at the end
    url = url_matches[-1].strip().strip("\"'")

    return api_key, url


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# Only GlobalProtect gateway addresses are collected
SERVICE_TYPE: str = "gp_gateway"

# Text file the gateway IPs are written to (one address per line)
OUTPUT_FILE: str = "/var/www/html/prisma.txt"


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def fetch_egress_ips(url: str, api_key: str, service_type: str) -> dict:
    """
    POST to the Prisma Access Datapath API and return the parsed JSON response.

    Args:
        url:          Full API endpoint URL extracted from the curl command.
        api_key:      API key extracted from the curl command.
        service_type: One of the valid Prisma Access service type strings.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        SystemExit: On HTTP error or non-JSON response.
    """
    payload = {
        "serviceType": service_type,
        "addrType": "all",
        "location": "all",
    }
    headers = {
        "header-api-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
    except requests.exceptions.ConnectionError as exc:
        sys.exit(f"✗  Connection error — check the URL and your network: {exc}")
    except requests.exceptions.Timeout:
        sys.exit("✗  Request timed out after 30 seconds.")

    # Surface API-level errors clearly
    if response.status_code != 200:
        print(f"✗  HTTP {response.status_code} from API.")
        try:
            # Many PA APIs return JSON error bodies — try to pretty-print them
            print(response.json())
        except Exception:
            print(response.text)
        sys.exit(1)

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError:
        sys.exit(f"✗  Response is not valid JSON:\n{response.text}")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def build_table(json_response: dict) -> list[dict]:
    """
    Flatten the nested API response into a list of row dicts for tabulate.

    Args:
        json_response: Parsed JSON from the Datapath API.

    Returns:
        A list of row dicts, one per address_details entry.
    """
    table: list[dict] = []

    for entry in json_response.get("result", []):
        zone = entry.get("zone", "N/A")
        for addr in entry.get("address_details", []):
            # Skip anything that is not a gateway address
            if addr.get("serviceType", SERVICE_TYPE) != SERVICE_TYPE:
                continue
            row = {
                "Zone":         zone,
                "Address":      addr.get("address", ""),
                "Service Type": addr.get("serviceType", ""),
                "Addr Type":    addr.get("addressType", ""),
                "Create Time":  addr.get("create_time", ""),
                "Allow Listed": addr.get("allow_listed", ""),
                "Node Name":    ", ".join(addr.get("node_name", [])) if addr.get("node_name") else "",
                "Node FQDN":    addr.get("node_fqdn", ""),
            }
            table.append(row)

    return table


def write_ip_file(table: list[dict], path: str = OUTPUT_FILE) -> list[str]:
    """
    Write the unique gateway IP addresses to a text file, one per line.

    Args:
        table: Rows produced by build_table().
        path:  Destination file path.

    Returns:
        The list of addresses written.

    Raises:
        SystemExit: If the file cannot be written (e.g. permission denied).
    """
    # Preserve API order while removing duplicates
    addresses = list(dict.fromkeys(row["Address"] for row in table if row["Address"]))

    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(addresses) + "\n")
    except PermissionError:
        sys.exit(f"✗  Permission denied writing {path} — run with sudo or fix permissions.")
    except OSError as exc:
        sys.exit(f"✗  Could not write {path}: {exc}")

    return addresses


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main workflow:
      1. Prompt user to paste full API command.
      2. Parse API key and URL from that command.
      3. Call the API for GlobalProtect gateway addresses only.
      4. Display results as a formatted table.
      5. Write the gateway IPs to OUTPUT_FILE.
    """
    print("=" * 60)
    print("  Prisma Access — Egress IP Lookup")
    print("=" * 60)
    print()
    print("Paste the API Command from Strata Cloud Manager > Configuration > Prsima Access > Setup > Infrastructure Settings > Egress IP API Key, then press Enter.")
    print()

    curl_cmd = input("curl command: ").strip()

    if not curl_cmd:
        sys.exit("✗  No input provided. Exiting.")

    # --- Parse key + URL from the curl string ---
    try:
        api_key, url = parse_curl_command(curl_cmd)
    except ValueError as exc:
        sys.exit(f"✗  Could not parse curl command:\n   {exc}")

    print(f"\n  ✔  API key parsed  : {api_key[:6]}{'*' * (len(api_key) - 6)}")
    print(f"  ✔  URL parsed      : {url}")

    print(f"\n  Fetching egress IPs for service type: {SERVICE_TYPE} …\n")

    # --- Call the API ---
    json_response = fetch_egress_ips(url, api_key, SERVICE_TYPE)

    # --- Build and print the table ---
    table = build_table(json_response)

    if not table:
        print("  No gateway addresses returned. The tenant may have no GlobalProtect gateway egress IPs.")
        return

    print(tabulate(table, headers="keys", tablefmt="grid"))
    print(f"\n  Total entries: {len(table)}")

    # --- Write gateway IPs to the text file ---
    addresses = write_ip_file(table)
    print(f"  ✔  Wrote {len(addresses)} gateway IP(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()