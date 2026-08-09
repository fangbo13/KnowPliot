"""Small Obsidian-style query parser compiled to permission-safe Django Q objects."""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import Q

from .graph_service import GraphQueryError


_TOKEN = re.compile(
    r'\s*(?:(OR)\b|(\()|(\))|(-)|((?:[A-Za-z][A-Za-z-]*:)?(?:"(?:\\.|[^"])*"|/(?:\\.|[^/])+/|[^\s()]+)))',
    re.IGNORECASE,
)
_FIELDS = {
    "file",
    "title",
    "content",
    "tag",
    "status",
    "owner",
    "updated",
    "links-to",
    "linked-from",
}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


def _tokens(source: str) -> list[Token]:
    result: list[Token] = []
    cursor = 0
    while cursor < len(source):
        match = _TOKEN.match(source, cursor)
        if not match:
            raise GraphQueryError("invalid_query", "Unexpected query token", cursor)
        if match.end() == cursor:
            break
        kind = next(
            name
            for name, value in zip(("OR", "LPAREN", "RPAREN", "NOT", "TERM"), match.groups())
            if value is not None
        )
        result.append(Token(kind, match.group(0).strip(), match.start()))
        cursor = match.end()
    return result


class Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = _tokens(source)
        self.index = 0

    def current(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> Token:
        token = self.current()
        if token is None:
            raise GraphQueryError("invalid_query", "Expected a query expression", len(self.source))
        self.index += 1
        return token

    def parse(self):
        if not self.tokens:
            return None
        expression = self.parse_or()
        if self.current() is not None:
            token = self.current()
            raise GraphQueryError("invalid_query", "Unexpected query token", token.position)
        return expression

    def parse_or(self):
        left = self.parse_and()
        while self.current() and self.current().kind == "OR":
            self.take()
            left = ("or", left, self.parse_and())
        return left

    def parse_and(self):
        items = [self.parse_factor()]
        while self.current() and self.current().kind not in {"OR", "RPAREN"}:
            items.append(self.parse_factor())
        result = items[0]
        for item in items[1:]:
            result = ("and", result, item)
        return result

    def parse_factor(self):
        token = self.current()
        if token is None:
            raise GraphQueryError("invalid_query", "Expected a query expression", len(self.source))
        if token.kind == "NOT":
            self.take()
            return ("not", self.parse_factor())
        if token.kind == "LPAREN":
            self.take()
            nested = self.parse_or()
            closing = self.current()
            if closing is None or closing.kind != "RPAREN":
                raise GraphQueryError("invalid_query", "Missing closing parenthesis", token.position)
            self.take()
            return nested
        if token.kind != "TERM":
            raise GraphQueryError("invalid_query", "Expected a search term", token.position)
        self.take()
        return ("term", token)


def _value_query(field: str | None, raw: str, position: int) -> Q:
    value = raw
    lookup = "icontains"
    if raw.startswith('"') and raw.endswith('"'):
        value = raw[1:-1].replace('\\"', '"')
    elif raw.startswith("/") and raw.endswith("/"):
        value = raw[1:-1]
        lookup = "regex"
        try:
            re.compile(value)
        except re.error as exc:
            raise GraphQueryError("invalid_regex", str(exc), position)
    if not value:
        raise GraphQueryError("invalid_query", "Search values cannot be empty", position)
    if field in {None, "file", "title"}:
        title_q = Q(**{f"title__{lookup}": value})
        return title_q if field else title_q | Q(**{f"text_content__{lookup}": value})
    if field == "content":
        return Q(**{f"text_content__{lookup}": value})
    if field == "tag":
        return Q(taxonomy_tags__term__code__iexact=value) | Q(
            taxonomy_tags__term__label__icontains=value
        )
    if field == "status":
        return Q(status__iexact=value)
    if field == "owner":
        return (
            Q(uploaded_by__username__icontains=value)
            | Q(uploaded_by__email__icontains=value)
            | Q(updated_by__username__icontains=value)
            | Q(updated_by__email__icontains=value)
        )
    if field == "updated":
        return Q(updated_at__date=value)
    if field == "links-to":
        return Q(outgoing_links__target__title__icontains=value)
    if field == "linked-from":
        return Q(incoming_links__source__title__icontains=value)
    raise GraphQueryError("unsupported_field", f"Unsupported graph query field: {field}", position)


def _compile(node) -> Q:
    kind = node[0]
    if kind == "term":
        token: Token = node[1]
        field = None
        raw = token.value
        if ":" in raw:
            candidate, raw = raw.split(":", 1)
            field = candidate.lower()
            if field == "path" or field not in _FIELDS:
                raise GraphQueryError(
                    "unsupported_field",
                    "KnowPliot spaces do not expose a folder path field; use file: or tag:",
                    token.position,
                    "Replace path: with file: for titles or tag: for taxonomy terms.",
                )
        return _value_query(field, raw, token.position)
    if kind == "not":
        return ~_compile(node[1])
    if kind == "and":
        return _compile(node[1]) & _compile(node[2])
    if kind == "or":
        return _compile(node[1]) | _compile(node[2])
    raise GraphQueryError("invalid_query", "Invalid query expression")


def parse_graph_query(source: str) -> Q:
    tree = Parser(source).parse()
    return _compile(tree) if tree else Q()
