"""Normalizacja naglowka, wydobycie pol i szablony Drain3."""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from log_analyzer.contracts import EventGroup, NormalizedEvent

HDFS = re.compile(
    r"^(?P<date>\d{6}) (?P<time>\d{6})(?P<offset>Z|[+-]\d{2}:?\d{2})? (?P<pid>\d+) "
    r"(?P<level>[A-Z]+) (?P<component>[^:]+): (?P<message>.+)$"
)
SSH = re.compile(
    r"^(?P<date>[A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2}|"
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?) "
    r"(?P<host>\S+) (?P<component>sshd)\[(?P<pid>\d+)\]: (?P<message>.+)$"
)
BLOCK = re.compile(r"blk_-?\d+")
IP = r"(?:\d{1,3}\.){3}\d{1,3}"
SSH_LOGIN = re.compile(
    r"^(?:Failed|Accepted) password for (?:invalid user )?(?P<user>\S+) "
    r"from (?P<source_ip>\S+) port (?P<port>\d+)"
)


def event_details(message: str, log_format: str) -> tuple[str, dict[str, str]]:
    parameters = {}
    if log_format == "ssh":
        login = SSH_LOGIN.match(message)
        if login:
            return ("login_failed" if message.startswith("Failed") else "login_succeeded"), login.groupdict()
        return "other", parameters
    prefix = re.match(rf"(?P<node_ip>{IP}):(?P<node_port>\d+):?\s*(?:Got exception|Served block)", message)
    if prefix:
        parameters.update(prefix.groupdict())
    endpoints = re.search(
        rf"src: /(?P<source_ip>{IP}):(?P<source_port>\d+) dest: /(?P<destination_ip>{IP}):(?P<destination_port>\d+)",
        message,
    )
    if endpoints:
        parameters.update(endpoints.groupdict())
    peer = re.search(rf"(?:to|from) /(?P<peer_ip>{IP})(?::(?P<peer_port>\d+))?", message)
    if peer:
        parameters.update({key: value for key, value in peer.groupdict().items() if value is not None})
    request = re.match(rf"BLOCK\* ask (?P<target_ip>{IP}):(?P<target_port>\d+) to (?P<operation>delete|replicate)\b", message)
    if request:
        parameters.update(request.groupdict())
        return "block_delete_request" if request["operation"] == "delete" else "block_replicate_request", parameters
    categories = [
        ("Got exception while serving", "block_serving_exception"), ("Served block", "block_served"),
        ("Receiving block", "block_receiving"), ("Received block", "block_received"),
        ("Deleting block", "block_deleted"), ("Verification succeeded", "block_verified"),
        ("NameSystem.addStoredBlock", "block_registered"), ("NameSystem.allocateBlock", "block_allocated"),
        ("NameSystem.delete:", "block_deletion_scheduled"), ("Starting thread to transfer block", "block_transfer"),
    ]
    for fragment, category in categories:
        if fragment in message:
            return category, parameters
    if message.startswith("PacketResponder ") and message.endswith(" terminating"):
        return "responder_finished", parameters
    return "other", parameters


def _localize(value: datetime, zone_name: str) -> tuple[datetime | None, str | None]:
    zone = ZoneInfo(zone_name)
    candidates = [value.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
    valid = [item for item in candidates if item.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == value]
    if not valid:
        return None, "nonexistent_local_time"
    if len({item.utcoffset() for item in valid}) > 1:
        return None, "ambiguous_local_time"
    return valid[0], None


def _parse_time(fields: dict, log_format: str, zone_name: str | None, year: int | None):
    if log_format == "hdfs":
        local = datetime.strptime(fields["date"] + fields["time"], "%y%m%d%H%M%S")
        raw_time = local.isoformat() + (fields.get("offset") or "")
        value = datetime.fromisoformat(raw_time)
    else:
        raw_time = fields["date"]
        if re.match(r"\d{4}-", raw_time):
            value = datetime.fromisoformat(raw_time)
        else:
            value = datetime.strptime(f"{year or 2000} {raw_time}", "%Y %b %d %H:%M:%S")
            if year is None:
                return raw_time, None, None, "configuration" if zone_name else "unknown", "missing_year"
    local_text = value.replace(tzinfo=None).isoformat()
    if value.tzinfo is not None:
        return raw_time, local_text, value.astimezone(timezone.utc).isoformat(), "log", None
    if zone_name:
        aware, issue = _localize(value, zone_name)
        return raw_time, local_text, aware.astimezone(timezone.utc).isoformat() if aware else None, "configuration", issue
    return raw_time, local_text, None, "unknown", "missing_timezone"


def parse_logs(
    lines: list[str], log_format: str, analysis_id: str, *,
    source_timezone: str | None = None, source_year: int | None = None,
):
    # Osobny miner dla paczki: brak wspolnego zmiennego stanu miedzy zadaniami.
    config = TemplateMinerConfig()
    config.profiling_enabled = False
    config.masking_instructions = [
        MaskingInstruction(r"blk_-?\d+", "BLOCK"),
        MaskingInstruction(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "IP"),
        MaskingInstruction(r"\b\d+\b", "NUM"),
    ]
    miner = TemplateMiner(config=config)
    parsed = []
    for index, raw in enumerate(lines, start=1):
        match = (HDFS if log_format == "hdfs" else SSH).fullmatch(raw)
        if match is None:
            raise ValueError(f"Wpis {index}: niepoprawny format {log_format}.")
        fields = match.groupdict()
        message = fields["message"]
        try:
            time_data = _parse_time(fields, log_format, source_timezone, source_year)
        except ValueError as error:
            raise ValueError(f"Wpis {index}: niepoprawna data lub czas.") from error
        result = miner.add_log_message(message)
        parameters = {key: fields[key] for key in ("pid", "level") if key in fields}
        category, extracted = event_details(message, log_format)
        parameters.update(extracted)
        parsed.append((fields, raw, time_data, result["cluster_id"], parameters, category))

    events = []
    for index, (fields, raw, time_data, cluster_id, parameters, category) in enumerate(parsed, start=1):
        cluster = miner.drain.id_to_cluster[cluster_id]
        raw_time, local_time, utc_time, time_source, issue = time_data
        events.append(NormalizedEvent(
            event_id=f"{analysis_id}:{index}", source_line=index, raw=raw,
            timestamp=utc_time, timestamp_raw=raw_time, timestamp_local=local_time,
            timezone_source=time_source, time_issue=issue,
            log_level=fields.get("level"), event_type=category,
            host=fields.get("host"), component=fields["component"], message=fields["message"],
            template=cluster.get_template(), template_id=cluster_id,
            block_ids=list(dict.fromkeys(BLOCK.findall(fields["message"]))), parameters=parameters,
        ))
    return events


def group_events(events: list[NormalizedEvent], log_format: str) -> list[EventGroup]:
    groups: dict[str, list[str]] = {}
    for event in events:
        # HDFS: sekwencja po BlockID, nie po hoscie lub pojedynczej linii.
        keys = event.block_ids if log_format == "hdfs" else [event.host or "unknown"]
        for key in keys:
            groups.setdefault(key, []).append(event.event_id)
    return [EventGroup(group_id=key, event_ids=ids) for key, ids in groups.items()]
