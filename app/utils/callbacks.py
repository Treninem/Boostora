def pack_callback(version: int, action: str, value: str = '') -> str:
    safe_action = action.replace('|', '_').strip()
    safe_value = value.replace('|', '_').strip()
    if safe_value:
        return f'v{version}|{safe_action}|{safe_value}'
    return f'v{version}|{safe_action}'


class ParsedCallback:
    def __init__(self, version: int, action: str, value: str = '') -> None:
        self.version = version
        self.action = action
        self.value = value



def parse_callback(data: str) -> ParsedCallback | None:
    if not data or '|' not in data:
        return None
    parts = data.split('|', 2)
    if len(parts) < 2 or not parts[0].startswith('v'):
        return None
    version_part = parts[0][1:]
    if not version_part.isdigit():
        return None
    action = parts[1].strip()
    value = parts[2].strip() if len(parts) > 2 else ''
    if not action:
        return None
    return ParsedCallback(version=int(version_part), action=action, value=value)
