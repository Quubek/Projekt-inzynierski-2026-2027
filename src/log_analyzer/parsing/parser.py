"""Normalizacja naglowka, wydobycie pol i szablony Drain3."""

import re
from datetime import datetime

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from log_analyzer.contracts import EventGroup, NormalizedEvent

HDFS = re.compile(
    r"^(?P<date>\d{6}) (?P<time>\d{6}) (?P<pid>\d+) "
    r"(?P<level>[A-Z]+) (?P<component>[^:]+): (?P<message>.+)$"
)
SSH = re.compile(
    r"^(?P<date>[A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2}) "
    r"(?P<host>\S+) (?P<component>sshd)\[(?P<pid>\d+)\]: (?P<message>.+)$"
)
BLOCK = re.compile(r"blk_-?\d+")
SSH_LOGIN = re.compile(
    r"^(?:Failed|Accepted) password for (?:invalid user )?(?P<user>\S+) "
    r"from (?P<source_ip>\S+) port (?P<port>\d+)"
)


def parse_logs(lines: list[str], log_format: str, analysis_id: str):
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
        if log_format == "hdfs":
            try:
                local_time = datetime.strptime(fields["date"] + fields["time"], "%y%m%d%H%M%S")
            except ValueError as error:
                raise ValueError(f"Wpis {index}: niepoprawna data lub czas.") from error
            timestamp_raw = local_time.isoformat()
        else:
            # Syslog nie podaje roku. Nie uzupelniamy go aktualnym rokiem.
            timestamp_raw = fields["date"]
            try:
                datetime.strptime("2000 " + timestamp_raw, "%Y %b %d %H:%M:%S")
            except ValueError as error:
                raise ValueError(f"Wpis {index}: niepoprawna data lub czas.") from error
        result = miner.add_log_message(message)
        parameters = {key: fields[key] for key in ("pid", "level") if key in fields}
        login = SSH_LOGIN.match(message) if log_format == "ssh" else None
        if login:
            parameters.update(login.groupdict())
        parsed.append((fields, raw, timestamp_raw, result["cluster_id"], parameters))

    events = []
    for index, (fields, raw, time_raw, cluster_id, parameters) in enumerate(parsed, start=1):
        cluster = miner.drain.id_to_cluster[cluster_id]
        events.append(NormalizedEvent(
            event_id=f"{analysis_id}:{index}", raw=raw, timestamp_raw=time_raw,
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
