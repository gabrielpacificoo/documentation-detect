"""Ponto de extensão para dialetos. A implementação inicial suporta MySQL."""

import logging
import re
from typing import Protocol

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope


logger = logging.getLogger(__name__)
SQL_TOKEN = re.compile(r"'(?:''|\\.|[^'\\])*'|`(?:``|[^`])*`|\"(?:\"\"|[^\"])*\"|--[^\n]*|\#[^\n]*|/\*[\s\S]*?\*/")
IDENTIFIER = r'(?:`[^`]+`|"[^\"]+"|[A-Za-z_][\w$#]*)(?:\s*\.\s*(?:`[^`]+`|"[^\"]+"|[A-Za-z_][\w$#]*))*'


def without_comments(text: str) -> str:
    return SQL_TOKEN.sub(lambda m: " " if m[0].startswith(("--", "#", "/*")) else m[0], text)


def simple_name(name: str) -> str:
    return name.strip().rsplit(".", 1)[-1].strip().strip('`"[]')


def procedure_name(name: str) -> str | None:
    if not re.fullmatch(IDENTIFIER, name.strip()):
        return None
    name = simple_name(name)
    return name if re.match(r"^(?:PSEL|PDEL|PUPD|PINS)[\w$#]*$", name, re.I) else None


class SqlAnalyzer(Protocol):
    def tables(self, sql: str) -> set[str]: ...
    def procedures(self, sql: str) -> set[str]: ...


class MysqlAnalyzer:
    def tables(self, sql: str) -> set[str]:
        sql = without_comments(sql)
        masked = SQL_TOKEN.sub(lambda m: " " * len(m[0]), sql)
        boundaries = [-1] + [m.start() for m in re.finditer(";", masked)] + [len(sql)]
        tables = set()
        for start, end in zip(boundaries, boundaries[1:]):
            statement = sql[start + 1:end].strip()
            if not re.match(r"^(?:SELECT|WITH|INSERT|REPLACE|UPDATE|DELETE)\b", statement, re.I):
                continue
            # Substitui parâmetros JDBC/Spring sem alterar valores entre aspas.
            statement = re.sub(SQL_TOKEN.pattern + r"|(?<!:):[A-Za-z_]\w*",
                               lambda m: "?" if m[0].startswith(":") else m[0], statement)
            # REPLACE acessa os mesmos objetos de um INSERT equivalente.
            statement = re.sub(r"^REPLACE\b", "INSERT", statement, flags=re.I)
            try:
                expression = sqlglot.parse_one(statement, read="mysql")
            except SqlglotError:
                logger.warning("SQL não reconhecido pelo analisador MySQL; uma consulta foi ignorada.")
                continue
            if not isinstance(expression, (exp.Query, exp.Insert, exp.Update, exp.Delete)):
                continue
            virtual_tables = set()
            if isinstance(expression, exp.Delete):
                # DELETE c FROM clientes c: c é alvo por alias, não outra tabela.
                virtual_tables.update(id(table) for table in expression.args.get("tables") or [])
            for scope in traverse_scope(expression):
                for table in scope.tables:
                    if not table.db and isinstance(scope.sources.get(table.alias_or_name), Scope):
                        virtual_tables.add(id(table))
            for table in expression.find_all(exp.Table):
                if id(table) not in virtual_tables and isinstance(table.this, exp.Identifier):
                    tables.add(table.name)
        return tables

    def procedures(self, sql: str) -> set[str]:
        sql = without_comments(sql)
        masked = SQL_TOKEN.sub(lambda m: " " * len(m[0]) if m[0].startswith("'") else m[0], sql)
        result = set()
        for match in re.finditer(r"\bCALL\s+(" + IDENTIFIER + r")\s*\(", masked, re.I):
            name = procedure_name(match[1])
            if name:
                result.add(name)
        return result


def create_sql_analyzer(dialect: str) -> SqlAnalyzer:
    if dialect != "mysql":
        raise ValueError(f"Dialeto ainda não implementado: {dialect}")
    return MysqlAnalyzer()
