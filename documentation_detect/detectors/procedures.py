import re

from ..models import AnalysisContext, Findings
from ..sql import procedure_name


class ProceduresDetector:
    def detect(self, context: AnalysisContext, findings: Findings) -> None:
        for source in context.files:
            if source.path.suffix.lower() == ".sql":
                # O nome do arquivo não representa uma procedure do banco.
                findings.procedures.update(context.sql.procedures(source.text))
        for source in context.java:
            for value in source.sql_strings():
                findings.procedures.update(context.sql.procedures(value))
            for value in source.calls(("withProcedureName", "createStoredProcedureQuery", "createStoredProcedureCall")):
                name = procedure_name(value)
                if name:
                    findings.procedures.add(name)
            for annotation in source.annotations:
                if annotation.name not in {"Procedure", "NamedStoredProcedureQuery"}:
                    continue
                keys = ("procedureName",) if annotation.name == "NamedStoredProcedureQuery" else ("procedureName", "value")
                for key in keys:
                    value = source.value(annotation, key)
                    name = procedure_name(value) if value else None
                    if name:
                        findings.procedures.add(name)
                if annotation.name == "Procedure" and not annotation.arguments:
                    method = re.search(r"\b([A-Za-z_]\w*)\s*\(", source.mask[annotation.end:])
                    name = procedure_name(method[1]) if method else None
                    if name:
                        findings.procedures.add(name)
