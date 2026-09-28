import json
import os
import tempfile
from pathlib import Path

from .models import Findings


def write_report(findings: Findings, service: str, project_root: Path) -> Path:
    output = project_root / f"{service}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=project_root,
                                         prefix=".report-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(findings.as_dict(service), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output
