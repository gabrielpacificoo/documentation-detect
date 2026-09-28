"""Leitura lexical de Java; não executa nem compila o projeto analisado."""

import re
from dataclasses import dataclass

from .models import SourceFile


TOKEN = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/')
IDENTIFIER = r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*"


def blank(value: str) -> str:
    return "".join("\n" if char == "\n" else " " for char in value)


def mask_strings(text: str) -> str:
    return TOKEN.sub(lambda match: blank(match[0]), text)


def decode_string(value: str) -> str:
    body = value[3:-3] if value.startswith('"""') else value[1:-1]
    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
               '"': '"', "'": "'", "\\": "\\", "s": " "}
    return re.sub(r"\\(u[0-9a-fA-F]{4}|[0-7]{1,3}|\r?\n|.)",
                  lambda m: chr(int(m[1][1:], 16)) if m[1].startswith("u")
                  else chr(int(m[1], 8)) if m[1][0] in "01234567"
                  else "" if m[1].endswith("\n") else escapes.get(m[1], m[1]), body)


def split_top_level(text: str, separator: str = ",") -> list[str]:
    masked = mask_strings(text)
    depth = 0
    start = 0
    result = []
    for index, char in enumerate(masked):
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif char == separator and depth == 0:
            result.append(text[start:index].strip())
            start = index + 1
    result.append(text[start:].strip())
    return result


def evaluate(expression: str, constants: dict[str, str]) -> str | None:
    parts = split_top_level(expression.strip(), "+")
    result = []
    for part in parts:
        if part in constants:
            result.append(constants[part])
        elif part.startswith('"') and TOKEN.fullmatch(part):
            result.append(decode_string(part))
        else:
            return None
    return "".join(result)


@dataclass(frozen=True)
class Annotation:
    name: str
    arguments: dict[str, str]
    start: int
    end: int


class JavaSource:
    def __init__(self, source: SourceFile):
        self.source = source
        self.text = TOKEN.sub(lambda m: blank(m[0]) if m[0].startswith(("//", "/*"))
                              else m[0], source.text)
        self.mask = mask_strings(self.text)
        self.constants: dict[str, str] = {}
        self.annotations = list(self._annotations())

    def _annotations(self):
        for match in re.finditer(r"@(" + IDENTIFIER + r")\s*(\()?", self.mask):
            name = match[1].rsplit(".", 1)[-1]
            end = match.end()
            arguments = {}
            if match[2]:
                depth = 1
                while end < len(self.mask) and depth:
                    if self.mask[end] == "(":
                        depth += 1
                    elif self.mask[end] == ")":
                        depth -= 1
                    end += 1
                for argument in split_top_level(self.text[match.end():end - 1]):
                    assignment = re.match(r"^(\w+)\s*=\s*([\s\S]*)$", argument)
                    if assignment:
                        arguments[assignment[1]] = assignment[2]
                    elif argument:
                        arguments["value"] = argument
            yield Annotation(name, arguments, match.start(), end)

    def value(self, annotation: Annotation, key: str = "value") -> str | None:
        return evaluate(annotation.arguments.get(key, ""), self.constants)

    def class_after(self, position: int) -> str | None:
        match = re.search(r"\b(?:class|interface|record|enum)\s+(\w+)", self.mask[position:])
        return match[1] if match else None

    def calls(self, names: tuple[str, ...]):
        """Primeiro argumento estaticamente resolvido dos métodos informados."""
        for match in re.finditer(r"\b(?:" + "|".join(names) + r")\s*\(", self.mask):
            end, depth = match.end(), 1
            while end < len(self.mask) and depth:
                if self.mask[end] == "(":
                    depth += 1
                elif self.mask[end] == ")":
                    depth -= 1
                end += 1
            argument = split_top_level(self.text[match.end():end - 1])[0]
            value = evaluate(argument, self.constants)
            if value is not None:
                yield value

    def sql_strings(self):
        # JPQL usa nomes de entidades; as tabelas são obtidas pelos mapeamentos JPA.
        jpql = [a for a in self.annotations if a.name in {"Query", "NamedQuery"}
                and a.arguments.get("nativeQuery", "false").strip() != "true"]
        excluded = [(a.start, a.end) for a in jpql]
        excluded_values = {self.value(a, "query" if a.name == "NamedQuery" else "value") for a in jpql}
        atom = r'(?:"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|' + IDENTIFIER + r')'
        expressions = re.compile(atom + r'(?:\s*\+\s*' + atom + r')*')
        for match in expressions.finditer(self.text):
            if any(start <= match.start() < end for start, end in excluded):
                continue
            value = evaluate(match[0], self.constants)
            if value and value not in excluded_values:
                yield value


def resolve_constants(sources: list[JavaSource]) -> None:
    definitions = []
    for source in sources:
        for match in re.finditer(r"\b(?:String|java\.lang\.String)\s+(\w+)\s*=([^;]*);", source.mask):
            # Também cobre variáveis locais cujo valor é uma expressão literal.
            definitions.append((source, match[1], source.text[match.start(2):match.end(2)]))
    qualified = {}
    for _ in range(len(definitions) + 1):
        changed = False
        for source, name, expression in definitions:
            value = evaluate(expression, {**qualified, **source.constants})
            if value is not None and source.constants.get(name) != value:
                source.constants[name] = value
                owner = source.class_after(0)
                if owner:
                    qualified[f"{owner}.{name}"] = value
                changed = True
        if not changed:
            break
    for source in sources:
        source.constants = {**qualified, **source.constants}
