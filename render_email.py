#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 next_book.py 的输出（JSON）渲染成邮件正文（Markdown）。

这是「不开大模型也能跑」的兜底渲染：只用书籍简介 + 热门划线，
不生成读后感。如果你接了大模型，可以让它基于同一份 JSON 重写正文，
再交给 send_mail.py 发送。

用法:
    python3 next_book.py --count 3 > /tmp/books.json
    python3 render_email.py /tmp/books.json > /tmp/mail.md
    python3 send_mail.py --subject "今日三书 · 2026-11-02" --file /tmp/mail.md
"""
import argparse
import datetime
import json
import sys


def fmt_rating(book):
    rating = book.get("rating") or 0
    count = book.get("ratingCount") or 0
    if not rating:
        return ""
    return "微信读书评分 %.2f/10（%d人评）" % (rating, count) if count else "微信读书评分 %.2f/10" % rating


def fmt_meta(book):
    parts = [book.get("author") or ""]
    if book.get("translator"):
        parts[-1] += "（译者：%s）" % book["translator"]
    for key in ("publisher", "category"):
        if book.get(key):
            parts.append(book[key])
    rating = fmt_rating(book)
    if rating:
        parts.append(rating)
    return " · ".join(p for p in parts if p)


def render_book(book, idx, total):
    lines = []
    lines.append("## %d／%d ·《%s》" % (idx, total, book.get("title") or "未知"))
    meta = fmt_meta(book)
    if meta:
        lines.append(meta)
    if book.get("source") == "recommend":
        reason = book.get("recommendReason") or "根据你的阅读记录推荐"
        lines.append("书架外推荐：%s" % reason)
    lines.append("")

    intro = (book.get("intro") or "").strip()
    if intro:
        lines.append("### 内容简介")
        lines.append("")
        lines.append(intro)
        lines.append("")

    highlights = book.get("highlights") or []
    if highlights:
        lines.append("### 热门划线")
        lines.append("")
        for h in highlights[:5]:
            # 接口返回的划线有时从句子中间截断，开头会带一个孤立的标点
            text = (h.get("text") or "").strip().lstrip("。，、；：！？… ")
            if not text:
                continue
            lines.append("> " + text.replace("\n", " "))
            lines.append("")
            tail = []
            if h.get("chapter"):
                tail.append(h["chapter"])
            if h.get("count"):
                tail.append("%d人划线" % h["count"])
            if tail:
                lines.append("—— " + " · ".join(tail))
                lines.append("")

    link = book.get("deepLink")
    if link:
        lines.append("[在微信读书中打开](%s)" % link)
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", nargs="?", help="next_book.py 输出的 JSON 文件，默认读 stdin")
    ap.add_argument("--title", default="今日三书", help="邮件抬头，默认「今日三书」")
    args = ap.parse_args()

    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    if data.get("error"):
        print("生成失败：%s" % data["error"], file=sys.stderr)
        sys.exit(1)

    books = data.get("books") or []
    if not books:
        print("没有可推送的书", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today().strftime("%Y-%m-%d")
    out = ["# %s · %s" % (args.title, today), ""]
    for i, book in enumerate(books, 1):
        out.append(render_book(book, i, len(books)))
        out.append("---")
        out.append("")

    print("\n".join(out).rstrip() + "\n")


if __name__ == "__main__":
    main()
