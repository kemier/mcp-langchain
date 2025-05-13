import os
import json
import yaml
from typing import Any, Optional

def load_json_or_yaml(source: str) -> Optional[Any]:
    """Load JSON or YAML from a file path or string. Returns the parsed object or None on failure."""
    if os.path.exists(source):
        file_ext = os.path.splitext(source)[1].lower()
        try:
            if file_ext in ['.yaml', '.yml']:
                with open(source, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            elif file_ext == '.json':
                with open(source, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Try parsing as JSON string if extension unknown
                with open(source, 'r', encoding='utf-8') as f:
                    return json.loads(f.read())
        except Exception:
            return None
    else:
        # Not a path, try parsing as JSON string
        try:
            return json.loads(source)
        except Exception:
            return None 