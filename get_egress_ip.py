#!/usr/bin/env python3
from __future__ import annotations  # enables modern type hint syntax on Python 3.7+
"""
pa_egress_ips.py — Retrieve and display Prisma Access Egress IPs in a formatted table.

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
# Service type selection
# ---------------------------------------------------------------------------

SERVICE_TYPES: list[str] = [
    "all",
    "remote_network",
    "gp_gateway",
    "gp_portal",
    "clean_pipe",
    "swg_proxy",
]


def prompt_service_type() -> str:
    """
    Present a numbered menu of service types and return the user's choice.

    Returns:
        The selected service type string.
    """
    print("\nSelect a service type:")
    print("-" * 25)
    for i, svc in enumerate(SERVICE_TYPES, start=1):
        print(f"  {i}. {svc}")
    print()

    while True:
        raw = input("Enter the number for your choice: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(SERVICE_TYPES):
            return SERVICE_TYPES[int(raw) - 1]
        print(f"  ✗  Please enter a number between 1 and {len(SERVICE_TYPES)}.")


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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main workflow:
      1. Prompt user to paste full API command.
      2. Parse API key and URL from that command.
      3. Prompt for service type.
      4. Call the API and display results as a formatted table.
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

    # --- Choose service type ---
    service_type = prompt_service_type()
    print(f"\n  Fetching egress IPs for service type: {service_type} …\n")

    # --- Call the API ---
    json_response = fetch_egress_ips(url, api_key, service_type)

    # --- Build and print the table ---
    table = build_table(json_response)

    if not table:
        print("  No results returned. The tenant may have no egress IPs for that service type.")
        return

    print(tabulate(table, headers="keys", tablefmt="grid"))
    print(f"\n  Total entries: {len(table)}")


if __name__ == "__main__":
    main()