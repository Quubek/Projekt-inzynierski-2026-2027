"""Role IP wynikające z komunikatów. Bez DNS i zgadywania hosta źródłowego."""

import re
from ipaddress import ip_address

IPV4 = r"(?:\d{1,3}\.){3}\d{1,3}"
ROLES = ("source_ip", "destination_ip", "node_ip", "target_ip")


def valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ip_address(value.strip("[]")))
    except ValueError:
        return None


def find_ips(text: str) -> list[str]:
    # IPv6 przed IPv4: adres mapowany ::ffff:192.0.2.1 jest jednym adresem.
    ipv6 = [(match, valid_ip(match.group(0))) for match in re.finditer(
        r"(?<![\w:])[0-9a-fA-F:]*:[0-9a-fA-F:.]+(?:%[\w.-]+)?", text)]
    found = [(match.start(), value) for match, value in ipv6 if value]
    for match in re.finditer(rf"(?<![\w.]){IPV4}(?![\w.])", text):
        if any(value and start.start() <= match.start() < start.end() for start, value in ipv6):
            continue
        if value := valid_ip(match.group(0)):
            found.append((match.start(), value))
    return list(dict.fromkeys(value for _, value in sorted(found)))


def extract_addresses(message: str, event_type: str, parameters: dict, host: str | None = None) -> dict:
    roles = {key: valid_ip(parameters.get(key)) for key in ROLES}
    endpoints = re.search(rf"src: /(?P<source_ip>{IPV4}):\d+ dest: /(?P<destination_ip>{IPV4}):\d+", message)
    if endpoints:
        roles.update({key: valid_ip(value) for key, value in endpoints.groupdict().items()})
    prefix = re.match(rf"(?P<node>{IPV4}):\d+:?\s*(?:Got exception while serving|Served block|Starting thread to transfer block)", message)
    if prefix:
        roles["node_ip"] = valid_ip(prefix["node"])
        roles["source_ip"] = roles["node_ip"]
        recipient = re.search(rf"\bto /?(?P<ip>{IPV4})(?::\d+)?", message)
        if recipient:
            roles["destination_ip"] = valid_ip(recipient["ip"])
    if message.startswith("Received block ") and " from /" in message:
        sender = re.search(rf"\bfrom /(?P<ip>{IPV4})(?::\d+)?", message)
        if sender:
            roles["source_ip"] = valid_ip(sender["ip"])
    request = re.match(rf"BLOCK\* ask (?P<ip>{IPV4}):\d+ to (?:delete|replicate)\b", message)
    if request:
        roles["target_ip"] = valid_ip(request["ip"])
    storage_node = re.search(rf"(?:blockMap updated: |is added to invalidSet of )(?P<ip>{IPV4}):\d+", message)
    if storage_node:
        roles["node_ip"] = valid_ip(storage_node["ip"])
    if event_type in ("login_failed", "login_succeeded"):
        # Nazwa hosta SSH nie jest adresem IP. Nie wykonujemy jej rozwiązywania.
        roles["destination_ip"] = valid_ip(host)
    if valid_ip(host):
        roles["node_ip"] = valid_ip(host)
    known = {value for value in roles.values() if value}
    return {**roles, "other_ips": [value for value in find_ips(message) if value not in known]}


def addresses_for_event(event) -> dict:
    """Odczyt starszych analiz korzysta z rozpoznanych parametrów i oryginalnej treści."""
    result = extract_addresses(event.message, event.event_type, event.parameters, event.host)
    for role in ROLES:
        if value := valid_ip(getattr(event, role, None)):
            result[role] = value
    known = {result[key] for key in ROLES if result[key]}
    result["other_ips"] = list(dict.fromkeys(
        ip for candidate in [*result["other_ips"], *getattr(event, "other_ips", [])]
        if (ip := valid_ip(candidate)) and ip not in known
    ))
    return result


def all_addresses(addresses: dict) -> list[str]:
    return list(dict.fromkeys(value for value in [*(addresses[key] for key in ROLES), *addresses["other_ips"]] if value))
