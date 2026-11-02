#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日一书 —— 纯文本邮件发送（复用 ~/.follow-builders/.env 里的 SMTP 凭据）。

用法:
    python3 send_mail.py --subject "今日一书 ·《xxx》" --file /tmp/weread-daily.txt

输出: JSON {"status":"ok"|"error", "message": ...}
"""
import argparse
import json
import os
import re
import smtplib
import sys
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, parseaddr

BASE = os.path.dirname(os.path.abspath(__file__))

# 配置读取顺序：环境变量 > 项目根目录 .env > 兼容旧的 ~/.follow-builders/.env
ENV_CANDIDATES = [
    os.path.join(BASE, ".env"),
    os.path.expanduser("~/.follow-builders/.env"),
]
ENV_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS",
            "SMTP_SECURE", "MAIL_TO")

# 正文字号：默认 24px（= 16px × 1.5）。加大用 --font-scale 2.0，常规字号用 --plain-only。
DEFAULT_FONT_SCALE = 1.5
BASE_PX = 16


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(t):
    t = _esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t


def md_to_html(md, scale=DEFAULT_FONT_SCALE):
    """把 Markdown 正文渲染成 HTML，字号按 scale 倍放大。"""
    body_px = round(BASE_PX * scale)
    h1_px = round(body_px * 1.5)
    h2_px = round(body_px * 1.25)
    h3_px = round(body_px * 1.1)
    color = "#1a1a1a"

    def style(size, weight="normal", extra=""):
        return ("font-size:%dpx;line-height:1.7;color:%s;font-weight:%s;%s"
                % (size, color, weight, extra))

    out = []
    para = []
    quote = []

    def flush_para():
        if para:
            out.append('<p style="%s">%s</p>' % (style(body_px), "<br>".join(para)))
            para.clear()

    def flush_quote():
        if quote:
            out.append('<blockquote style="%s">%s</blockquote>'
                       % (style(body_px, extra="margin:0 0 1em 0;padding-left:1em;"
                                              "border-left:4px solid #d0d0d0;"),
                          "<br>".join(quote)))
            quote.clear()

    for raw in md.split("\n"):
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush_para()
            flush_quote()
            continue
        if s == "---":
            flush_para()
            flush_quote()
            out.append('<hr style="border:none;border-top:1px solid #e0e0e0;margin:2em 0;">')
            continue
        if s.startswith("> "):
            flush_para()
            quote.append(_inline(s[2:]))
            continue
        flush_quote()
        if s.startswith("### "):
            flush_para()
            out.append('<h3 style="%s">%s</h3>'
                       % (style(h3_px, "bold", "margin:1.2em 0 .5em;"), _inline(s[4:])))
        elif s.startswith("## "):
            flush_para()
            out.append('<h2 style="%s">%s</h2>'
                       % (style(h2_px, "bold", "margin:1.4em 0 .6em;"), _inline(s[3:])))
        elif s.startswith("# "):
            flush_para()
            out.append('<h1 style="%s">%s</h1>'
                       % (style(h1_px, "bold", "margin:0 0 .8em;"), _inline(s[2:])))
        else:
            para.append(_inline(s))
    flush_para()
    flush_quote()

    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head>"
            "<body style=\"margin:0;padding:0;background:#ffffff;\">"
            "<div style=\"max-width:1200px;width:100%%;padding:8px 8px;%s\">%s</div>"
            "</body></html>" % (style(body_px), "".join(out)))


def load_env():
    cfg = {}
    for path in ENV_CANDIDATES:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    for k in ENV_KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--font-scale", type=float, default=DEFAULT_FONT_SCALE,
                    help="正文字号倍数（16px × 倍数），默认 1.5 即 24px")
    ap.add_argument("--plain-only", action="store_true",
                    help="只发纯文本，不做 HTML 放大")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(json.dumps({"status": "error", "message": "文件不存在: %s" % args.file},
                         ensure_ascii=False))
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        body = f.read()
    if not body.strip():
        print(json.dumps({"status": "error", "message": "内容为空，未发送"}, ensure_ascii=False))
        sys.exit(1)

    env = load_env()
    host = env.get("SMTP_HOST")
    user = env.get("SMTP_USER")
    pwd = env.get("SMTP_PASS")
    to = env.get("MAIL_TO")
    port = int(env.get("SMTP_PORT") or 465)
    secure = (env.get("SMTP_SECURE", "true").lower() == "true")

    missing = [n for n, v in (("SMTP_HOST", host), ("SMTP_USER", user),
                              ("SMTP_PASS", pwd), ("MAIL_TO", to)) if not v]
    if missing:
        print(json.dumps({"status": "error",
                          "message": "缺少凭据: %s（在项目根目录 .env 或环境变量中配置）" % ", ".join(missing)},
                         ensure_ascii=False))
        sys.exit(1)

    if args.plain_only:
        msg = MIMEText(body, "plain", "utf-8")
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(md_to_html(body, args.font_scale), "html", "utf-8"))
    msg["From"] = formataddr((str(Header("每日一书", "utf-8")), user))
    msg["To"] = to
    msg["Subject"] = Header(args.subject, "utf-8")
    msg["Date"] = formatdate(localtime=True)

    try:
        if secure:
            srv = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            srv = smtplib.SMTP(host, port, timeout=30)
            srv.starttls()
        with srv:
            srv.login(user, pwd)
            srv.sendmail(user, [parseaddr(to)[1] or to], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        print(json.dumps({"status": "error",
                          "message": "SMTP 认证失败（%s）。QQ 邮箱需用 16 位授权码，不是登录密码。" % e.smtp_code},
                         ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": "发送失败: %s" % e}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({"status": "ok",
                      "message": "已发送至 %s（%s，字号 %sx）"
                                 % (to, "纯文本" if args.plain_only else "纯文本+HTML",
                                    args.font_scale),
                      "to": to, "fontScale": args.font_scale},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
