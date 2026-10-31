"""Message Readability Engine: converts Librus HTML messages into clean Markdown and plain text.

Uses BeautifulSoup4 when available, with a built-in standard-library `html.parser` fallback
so message sanitization works reliably in any Python environment.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser
import re

_MULTIPLE_SPACES_RE = re.compile(r"[ \t\u00a0]+")
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")
_URL_RE = re.compile(r"(?<!\]\()(?<!\[)(https?://[^\s<>)\]]+)")
_IGNORED_TAGS = {"script", "style", "head", "meta", "noscript"}


def format_sender_name(raw_sender: str) -> str:
    """Clean and normalize a Librus sender string.

    Examples:
        "Nowak Anna (Nowak Anna) [Nauczyciel]" -> "Nowak Anna (Nauczyciel)"
        "  Kowalski Jan  " -> "Kowalski Jan"
    """
    if not raw_sender:
        return "Nieznany nadawca"

    cleaned = _MULTIPLE_SPACES_RE.sub(" ", html.unescape(raw_sender)).strip()

    # Remove duplicate parenthetical name like "Nowak Anna (Nowak Anna)"
    dup_match = re.match(r"^([^(]+?)\s*\(\1\)\s*(.*)$", cleaned)
    if dup_match:
        name_part = dup_match.group(1).strip()
        rest_part = dup_match.group(2).strip()
        cleaned = f"{name_part} {rest_part}".strip()

    # Normalize square brackets role "[Wychowawca]" -> "(Wychowawca)"
    cleaned = re.sub(r"\[([^\]]+)\]", r"(\1)", cleaned)
    cleaned = _MULTIPLE_SPACES_RE.sub(" ", cleaned).strip()
    return cleaned


class _DOMNode:
    """Lightweight DOM node for HTML-to-Markdown conversion without external dependencies."""

    __slots__ = ("tag", "attrs", "children")

    def __init__(
        self,
        tag: str | None = None,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_DOMNode | str] = []

    def get_text(self, separator: str = "", strip: bool = False) -> str:
        """Extract all text recursively from this node."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in _IGNORED_TAGS:
                parts.append(child.get_text(separator=separator, strip=strip))
        joined = separator.join(p for p in parts if p)
        return joined.strip() if strip else joined


class _DOMBuilder(HTMLParser):
    """Standard-library HTML tree builder."""

    _VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "col", "area", "base"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _DOMNode("root")
        self._stack: list[_DOMNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        node = _DOMNode(tag_lower, attr_dict)
        self._stack[-1].children.append(node)
        if tag_lower not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        node = _DOMNode(tag_lower, attr_dict)
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        for idx in range(len(self._stack) - 1, 0, -1):
            if self._stack[idx].tag == tag_lower:
                del self._stack[idx:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def _parse_html_tree(raw_html: str) -> _DOMNode:
    """Parse HTML string into a lightweight `_DOMNode` tree."""
    builder = _DOMBuilder()
    builder.feed(raw_html)
    builder.close()
    return builder.root


def _find_all_nodes(node: _DOMNode, tags: set[str], recursive: bool = True) -> list[_DOMNode]:
    """Find descendant `_DOMNode` elements matching any tag in `tags`."""
    matches: list[_DOMNode] = []
    for child in node.children:
        if isinstance(child, _DOMNode):
            if child.tag in tags:
                matches.append(child)
            if recursive:
                matches.extend(_find_all_nodes(child, tags, recursive=True))
    return matches


def _convert_dom_to_markdown(node: _DOMNode | str) -> str:
    """Recursively convert a `_DOMNode` or text string into clean Markdown."""
    if isinstance(node, str):
        text = node.replace("\xa0", " ")
        return _MULTIPLE_SPACES_RE.sub(" ", text)

    tag_name = node.tag or ""
    if tag_name in _IGNORED_TAGS:
        return ""

    if tag_name == "br":
        return "\n"

    if tag_name == "hr":
        return "\n\n---\n\n"

    children_md = "".join(_convert_dom_to_markdown(child) for child in node.children)

    if tag_name in {"b", "strong"}:
        stripped = children_md.strip()
        return f" **{stripped}** " if stripped else ""

    if tag_name in {"i", "em"}:
        stripped = children_md.strip()
        return f" *{stripped}* " if stripped else ""

    if tag_name in {"u", "ins"}:
        return children_md.strip()

    if tag_name == "a":
        href = node.attrs.get("href", "").strip()
        label = children_md.strip()
        if not href or href.lower().startswith("javascript:"):
            return label
        if not label or label == href:
            return href
        return f"[{label}]({href})"

    if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag_name[1])
        stripped = children_md.strip()
        if not stripped:
            return ""
        return f"\n\n{'#' * level} {stripped}\n\n"

    if tag_name == "li":
        stripped = children_md.strip()
        return f"\n- {stripped}" if stripped else ""

    if tag_name in {"ul", "ol"}:
        return f"\n{children_md}\n\n"

    if tag_name == "blockquote":
        lines = [line.strip() for line in children_md.strip().splitlines()]
        quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
        return f"\n\n{quoted}\n\n"

    if tag_name == "tr":
        cells = [
            _convert_dom_to_markdown(cell).strip().replace("\n", " ")
            for cell in _find_all_nodes(node, {"td", "th"}, recursive=False)
        ]
        if not any(cells):
            return ""
        return "| " + " | ".join(cells) + " |\n"

    if tag_name == "table":
        tr_nodes = _find_all_nodes(node, {"tr"}, recursive=True)
        rows = [_convert_dom_to_markdown(tr) for tr in tr_nodes]
        rows = [r for r in rows if r.strip()]
        if not rows:
            return ""
        first_row_cols = rows[0].count("|") - 1
        if first_row_cols > 0:
            separator = "| " + " | ".join(["---"] * first_row_cols) + " |\n"
            table_md = rows[0] + separator + "".join(rows[1:])
            return f"\n\n{table_md}\n"
        return "\n\n" + "".join(rows) + "\n"

    if tag_name in {"p", "div", "section", "article"}:
        stripped = children_md.strip()
        if not stripped:
            return ""
        return f"\n\n{stripped}\n\n"

    return children_md


def html_to_clean_markdown(raw_html: str) -> str:
    """Convert raw Librus message HTML or plain text into clean, readable Markdown."""
    if not raw_html or not raw_html.strip():
        return ""

    root = _parse_html_tree(raw_html)
    markdown_raw = _convert_dom_to_markdown(root)

    cleaned_lines: list[str] = []
    for line in markdown_raw.splitlines():
        compact_line = _MULTIPLE_SPACES_RE.sub(" ", line).strip()
        cleaned_lines.append(compact_line)

    result = "\n".join(cleaned_lines).strip()
    result = _EXCESS_NEWLINES_RE.sub("\n\n", result)

    # Convert bare URLs into clickable Markdown links where not already wrapped
    result = _URL_RE.sub(r"[\1](\1)", result)
    return result


def _convert_dom_to_plain_text(node: _DOMNode | str) -> str:
    """Recursively convert a `_DOMNode` into plain text."""
    if isinstance(node, str):
        return node.replace("\xa0", " ")

    tag_name = node.tag or ""
    if tag_name in _IGNORED_TAGS:
        return ""

    if tag_name == "br":
        return "\n"

    children_txt = "".join(_convert_dom_to_plain_text(child) for child in node.children)

    if tag_name in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6"}:
        return f"\n{children_txt.strip()}\n\n"

    if tag_name in {"li", "tr"}:
        return f"{children_txt.strip()}\n"

    return children_txt


def html_to_plain_text(raw_html: str, max_length: int | None = None) -> str:
    """Convert raw Librus message HTML into clean plain text suitable for push notifications."""
    if not raw_html or not raw_html.strip():
        return ""

    root = _parse_html_tree(raw_html)
    raw_text = _convert_dom_to_plain_text(root)
    lines = [_MULTIPLE_SPACES_RE.sub(" ", line).strip() for line in raw_text.splitlines()]
    text = "\n".join(lines).strip()
    text = _EXCESS_NEWLINES_RE.sub("\n\n", text)

    if max_length is not None and len(text) > max_length:
        return text[: max_length - 1].rstrip() + "…"
    return text


def format_message_markdown(
    *,
    sender: str,
    subject: str,
    sent_at: str,
    body_html: str,
    attachments: list[str] | None = None,
) -> str:
    """Create a complete, structured Markdown representation of an incoming message."""
    clean_sender = format_sender_name(sender)
    clean_subject = (subject or "(Brak tematu)").strip()
    clean_body = html_to_clean_markdown(body_html)

    header_lines = [
        f"### 📩 {clean_subject}",
        f"**Od:** {clean_sender}  ",
        f"**Data:** {sent_at}",
    ]
    if attachments:
        files_str = ", ".join(attachments)
        header_lines.append(f"**Załączniki ({len(attachments)}):** 📎 {files_str}")

    header = "\n".join(header_lines)
    if clean_body:
        return f"{header}\n\n---\n\n{clean_body}"
    return header
