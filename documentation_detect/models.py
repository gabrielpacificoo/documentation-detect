from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .configuration import Configuration
    from .java import JavaSource
    from .sql import SqlAnalyzer


@dataclass(frozen=True)
class SourceFile:
    path: Path
    main_root: Path
    text: str


@dataclass
class Findings:
    microsservicos: set[str] = field(default_factory=set)
    tabelas: set[str] = field(default_factory=set)
    procedures: set[str] = field(default_factory=set)

    def as_dict(self, service: str) -> dict:
        return {"servico": service, **{
            key: sorted(getattr(self, key), key=lambda value: (value.casefold(), value))
            for key in ("microsservicos", "tabelas", "procedures")
        }}


class Detector(Protocol):
    def detect(self, context: "AnalysisContext", findings: Findings) -> None: ...


@dataclass
class AnalysisContext:
    files: list[SourceFile]
    java: list["JavaSource"]
    configurations: dict[Path, "Configuration"]
    sql: "SqlAnalyzer"
