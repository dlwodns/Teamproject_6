"""메일 HTML 거르기. 보낼 때(AI-32 서식 있는 편집기 — 화면이 붙여넣기를 이미 거르지만 API를 바로 부를 수도 있어 한 번 더)와
받은 메일을 읽기 화면에 보일 때(AI-42) 같이 쓴다.

허용한 태그 · 속성만 다시 쓴다(나머지 태그는 벗기고 글자만 남김). script · style · iframe 같은 태그는 안의 글자까지 버린다.
style은 서식 속성만, 링크는 http · https · mailto만. 표준 라이브러리 html.parser로 다시 쓴다(새 의존성 없음).
표는 받은 메일 모양을 지키려고 허용한다. 이미지는 cid(메일 안에 붙은 그림, 붙여넣은 캡처 등)만 cid 함수로 우리 주소로 바꿔 남기고,
바깥 주소 그림(추적 픽셀 등)은 지운다 — 아웃룩도 바깥 그림은 기본으로 막는다.
"""
import html
import re
from collections.abc import Callable
from html.parser import HTMLParser

TAGS = {"b", "strong", "i", "em", "u", "s", "strike", "del", "br", "p", "div", "span", "ul", "ol", "li", "a", "font",
        "blockquote", "sub", "sup", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "img", "hr"}
VOID = {"br", "img", "hr"}
DROP = {"script", "style", "iframe", "object", "embed", "svg", "math", "template", "noscript", "head", "title", "textarea",
        "select", "button", "form", "input"}
DROP_VOID = {"input", "embed"}  # 닫는 태그가 없다 — 버리기만 하고 drop 깊이를 올리지 않는다(올리면 뒤 본문이 모두 빠진다)
ATTRS = {"style", "href", "color", "face", "size", "align", "colspan", "rowspan", "width", "height", "alt", "border", "src"}
STYLE_PROPS = {"color", "background-color", "font-family", "font-size", "font-weight", "font-style", "text-decoration",
               "text-decoration-line", "text-align", "line-height", "margin-left", "padding-left",
               # AI-39 표 · 사진: 칸 테두리 · 여백, 그림이 본문 폭을 넘지 않게
               "border", "border-collapse", "padding", "width", "max-width"}
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
    def __init__(self, cid: Callable[[str], str] | None):
        super().__init__(convert_charrefs=True)
        self.cid = cid
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
        src = next((v or "" for k, v in attrs if k == "src"), "").strip()
        if tag == "img":
            if not (self.cid and src[:4].lower() == "cid:"):
                return  # 바깥 그림 · data: 주소는 지운다
            attrs = [(k, self.cid(src[4:]) if k == "src" else v) for k, v in attrs]
            if not next((v for k, v in attrs if k == "src"), ""):
                return  # cid 함수가 모르는 그림('')은 지운다(보낼 때 붙이지 않은 cid)
        kept = []
        for k, v in attrs:
            v = v or ""
            if k not in ATTRS:
                continue
            if k == "style":
                v = _style(v)
            if k == "href" and not _SAFE_HREF.match(v.strip()):
                continue
            if k == "src" and tag != "img":
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


def clean_html(raw: str, cid: Callable[[str], str] | None = None) -> str:
    """cid: 'cid:<id>' 그림 주소를 바꿀 함수(읽기 화면 · 보내기의 붙인 그림). ''를 돌려주면 그 그림은 지운다. 없으면 그림을 모두 지운다."""
    c = _Cleaner(cid)
    c.feed(raw)
    c.close()
    return "".join(c.out) + "".join(f"</{t}>" for t in reversed(c.open))
