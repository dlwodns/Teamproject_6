"""보낼 메일 HTML 거르기(AI-32): 서식은 남기고 스크립트 · 이벤트 · 위험한 링크는 버린다."""
from app.services.html_clean import clean_html


def test_keeps_formatting():
    src = '<p style="text-align: center; line-height: 1.5"><b>굵게</b> <span style="color: #c00; background-color: yellow">색</span></p><ul><li>하나</li></ul>'
    assert clean_html(src) == src.replace("text-align: center; line-height: 1.5", "text-align: center; line-height: 1.5")


def test_drops_script_events_and_bad_links():
    out = clean_html('<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)" onclick="x">링크</a>'
                     '<a href="https://example.com">좋은 링크</a><p style="background: url(http://t/x); color: red">글</p>')
    assert "alert" not in out and "onerror" not in out and "onclick" not in out and "<img" not in out
    assert '<a>링크</a>' in out and '<a href="https://example.com">좋은 링크</a>' in out
    assert '<p style="color: red">글</p>' in out


def test_unknown_tags_keep_text_and_unclosed_tags_close():
    assert clean_html("<article><section>칸</section></article><b>열림") == "칸<b>열림</b>"
    assert clean_html("1 < 2 & 3") == "1 &lt; 2 &amp; 3"


def test_received_mail_keeps_tables_and_cid_images_only():
    """AI-42: 읽기 화면은 표와 메일 안 그림(cid, 붙여넣은 캡처)을 남기고 바깥 그림(추적 픽셀)은 지운다. 보내기(cid 함수 없음)는 그림을 모두 지운다."""
    raw = ('<table border="1"><tr><td colspan="2">칸</td></tr></table><img src="cid:a1" onerror="x()" width="10">'
           '<img src="https://t.example/p.gif"><img src="data:image/png;base64,AA">')
    out = clean_html(raw, cid=lambda c: f"/api/mails/7/inline/{c}")
    assert out == '<table border="1"><tr><td colspan="2">칸</td></tr></table><img src="/api/mails/7/inline/a1" width="10">'
    assert "<img" not in clean_html(raw)
    assert "src" not in clean_html('<a src="x" href="https://a.b">l</a>')
