import re

from ..models import AnalysisContext, Findings
from ..sql import simple_name


def spring_table_name(class_name: str) -> str:
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


class TablesDetector:
    def detect(self, context: AnalysisContext, findings: Findings) -> None:
        for source in context.files:
            if source.path.suffix.lower() == ".sql":
                findings.tabelas.update(context.sql.tables(source.text))
        for source in context.java:
            for annotation in source.annotations:
                if annotation.name in {"Table", "SecondaryTable", "JoinTable", "CollectionTable"}:
                    value = source.value(annotation, "name") or source.value(annotation)
                    if value:
                        findings.tabelas.add(simple_name(value))
                elif annotation.name == "Entity":
                    owner = source.class_after(annotation.end)
                    tables = [a for a in source.annotations if a.name == "Table"
                              and source.class_after(a.end) == owner
                              and (source.value(a, "name") or source.value(a))]
                    if owner and not tables:
                        findings.tabelas.add(spring_table_name(source.value(annotation, "name") or owner))
            for value in set(source.sql_strings()):
                findings.tabelas.update(context.sql.tables(value))
