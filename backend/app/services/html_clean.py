"""보낼 메일 HTML 거르기(AI-32 서식 있는 편집기). 화면이 붙여넣기를 이미 거르지만, API를 바로 부를 수도 있어 보내기 전에 한 번 더.

허용한 태그 · 속성만 다시 쓴다(나머지 태그는 벗기고 글자만 남김). script · style · iframe 같은 태그는 안의 글자까지 버린다.
style은 서식 속성만, 링크는 http · https · mailto만. 표준 라이브러리 html.parser로 다시 쓴다(새 의존성 없음).
ponytail: 표 · 이미지는 아직 허용하지 않는다(편집기에 없다). 넣을 때 TAGS에 더한다.
"""
import html
import re
from html.parser import HTMLParser

TAGS = {"b", "strong", "i", "em", "u", "s", "strike", "del", "br", "p", "div", "span", "ul", "ol", "li", "a", "font",
        "blockquote", "sub", "sup"}
VOID = {"br"}
DROP = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "head", "title", "textarea",
        "select", "button", "form", "input"}
DROP_VOID = {"input", "embed"}  # 닫는 태그가 없다 — 버리기만 하고 drop 깊이를 올리지 않는다(올리면 뒤 본문이 모두 빠진다)
ATTRS = {"style", "href", "color", "face", "size", "align"}
STYLE_PROPS = {"color", "background-color", "font-family", "font-size", "font-weight", "font-style", "text-decoration",
               "text-decoration-line", "text-align", "line-height", "margin-left", "padding-left"}
_BAD_VALUE = re.compile(r"url\s*\(|expression\s*\(|javascript:|[<>\\]", re.I)
_SAFE_HREF = re.compile(r"^(?:https?:|mailto:)", re.I)


def _style(value: str) -> str:
    out = []
    for decl in value.split(";"):
        prop, _, val = decl.partition(":")
        prop, val = prop.strip().lower(), val.strip()
        if prop in STYLE_PROPS and val and not _BAD_VALUE.search(val):
            out.append(f"{prop}: {val}")
    return "; ".join(out)


class _Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.drop = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_VOID:
            return
        if tag in DROP:
            self.drop += 1
            return
        if self.drop or tag not in TAGS:
            return
        kept = []
        for k, v in attrs:
            v = v or ""
            if k not in ATTRS:
                continue
            if k == "style":
                v = _style(v)
            if k == "href" and not _SAFE_HREF.match(v.strip()):
                continue
            if v:
                kept.append(f' {k}="{html.escape(v, quote=True)}"')
        self.out.append(f"<{tag}{''.join(kept)}>")
        if tag not in VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.open and self.open[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in DROP_VOID:
            return
        if tag in DROP:
            self.drop = max(0, self.drop - 1)
            return
        if self.drop or tag not in self.open:
            return
        while self.open:  # 짝이 어긋난 태그는 안쪽부터 닫는다
            t = self.open.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.drop:
            self.out.append(html.escape(data, quote=False))


def clean_html(raw: str) -> str:
    c = _Cleaner()
    c.feed(raw)
    c.close()
    return "".join(c.out) + "".join(f"</{t}>" for t in reversed(c.open))
