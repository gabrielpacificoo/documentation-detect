from pathlib import Path

from .configuration import load_configurations
from .detectors import default_detectors
from .java import JavaSource, resolve_constants
from .models import AnalysisContext, Detector, Findings
from .source import read_sources
from .sql import create_sql_analyzer


def analyze(repository: Path, *, profile: str | None = None, dialect: str = "mysql",
            detectors: list[Detector] | None = None) -> Findings:
    sources = read_sources(repository)
    if not sources:
        raise ValueError("Nenhum arquivo Java, SQL ou de configuração encontrado em src/main.")
    java = [JavaSource(source) for source in sources if source.path.suffix == ".java"]
    for root in {source.main_root for source in sources}:
        resolve_constants([item for item in java if item.source.main_root == root])
    context = AnalysisContext(sources, java, load_configurations(sources, profile), create_sql_analyzer(dialect))
    findings = Findings()
    for detector in default_detectors() if detectors is None else detectors:
        detector.detect(context, findings)
    return findings
