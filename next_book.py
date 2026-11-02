#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日一书：从微信读书书架按队列取一本未推送过的书，
输出书籍信息 + 热门划线，供上层生成推送文案。

用法:
    python3 next_book.py            # 取下一本（并写入已推送状态）
    python3 next_book.py --peek     # 只看下一本，不消耗队列
    python3 next_book.py --reset    # 清空已推送记录，重建队列

输出: JSON 到 stdout
"""
import json
import os
import random
import sys
import urllib.request
import urllib.error

GATEWAY = "https://i.weread.qq.com/api/agent/gateway"
VERSION = "1.0.4"
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "state.json")
FILTERS = os.path.join(BASE, "filters.json")
TOP_N = 12         # 取前 N 条热门划线（展示用前 5 条，其余供写梗概参考）
OUTLINE_N = 40     # 章节目录最多取多少条
MAX_TRY = 6        # 最多尝试几本书，跳过取不到数据的


def get_key():
    """API Key 优先级：环境变量 > 项目根目录 .env。

    微信读书 API Key 在 https://weread.qq.com/r/weread-skills 扫码登录后生成，
    形如 wrk-xxxxxxxx。
    """
    key = os.environ.get("WEREAD_API_KEY")
    if key:
        return key.strip()
    env_file = os.path.join(BASE, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("WEREAD_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def call(api_name, **params):
    payload = {"api_name": api_name, "skill_version": VERSION}
    payload.update(params)
    req = urllib.request.Request(
        GATEWAY,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_result(bid, info, bm):
    """把 /book/info + /book/bestbookmarks 组装成输出结构。"""
    chapters = bm.get("chapters") or []
    items = bm.get("items") or []      # 可能为空：无热门划线的书
    highlights = []
    for it in items[:TOP_N]:
        highlights.append({
            "text": (it.get("markText") or "").strip(),
            "count": it.get("totalCount", 0),
            "chapter": chapter_title(chapters, it.get("chapterUid")),
        })

    # 章节目录：为写长梗概提供内容骨架，只要一级标题
    outline = []
    chapterCount = 0
    try:
        ci = call("/book/chapterinfo", bookId=bid)
        allchap = ci.get("chapters") or []
        chapterCount = len(allchap)
        tops = [c for c in allchap if (c.get("level") or 1) == 1] or allchap
        noise = ("封面", "版权", "扉页", "目录", "插图", "出版说明")

        def clean(c):
            t = (c.get("title") or "").strip()
            if not t or any(n in t for n in noise):
                return None
            return t

        # 一级标题够多就只给一级；太少（如只有"基础篇/进阶篇"）就往下取到三级，
        # 否则写梗概时没有内容骨架可用
        tops_clean = [t for t in (clean(c) for c in tops) if t]
        if len(tops_clean) >= 6:
            outline = tops_clean[:OUTLINE_N]
        else:
            outline = []
            for c in allchap:
                if (c.get("level") or 1) > 3:
                    continue
                t = clean(c)
                if not t:
                    continue
                outline.append("  " * ((c.get("level") or 1) - 1) + t)
                if len(outline) >= OUTLINE_N:
                    break
    except Exception:
        pass

    progress = None
    try:
        pr = call("/book/getprogress", bookId=bid)
        bk = pr.get("book") or {}
        if bk.get("progress"):
            progress = bk.get("progress")
    except Exception:
        pass

    return {
        "bookId": bid,
        "title": info.get("title"),
        "author": info.get("author"),
        "translator": info.get("translator"),
        "publisher": info.get("publisher"),
        "category": info.get("category"),
        "publishTime": info.get("publishTime"),
        "wordCount": info.get("wordCount"),
        "rating": (info.get("newRating") or 0) / 100.0,
        "ratingCount": info.get("newRatingCount"),
        "intro": (info.get("intro") or "").strip(),
        "deepLink": info.get("deepLink"),
        "cover": info.get("cover"),
        "progress": progress,
        "highlights": highlights,
        "highlightTotal": bm.get("totalCount"),
        "outline": outline,
        "chapterCount": chapterCount,
        "remaining": None,
    }


def load_filters():
    """读取 filters.json；缺失则用内置默认值。"""
    default = {
        "categoryPrefixes": ["精品小说", "小说", "漫画", "青春文学", "网络文学", "文学-小说"],
        "titleKeywords": [],
        "authorDynasties": ["先秦", "春秋", "战国", "秦", "西汉", "东汉", "汉", "三国",
                            "晋", "南北朝", "隋", "唐", "五代", "宋", "元", "明", "清"],
        "applyToShelf": True,
    }
    if os.path.exists(FILTERS):
        try:
            with open(FILTERS, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                if not k.startswith("_"):       # 跳过 _说明 之类的注释字段
                    default[k] = v
        except Exception:
            pass
    return default


def is_excluded(info, filters=None):
    """判断一本书是否属于「不看的类别」（虚构小说 / 古籍）。"""
    f = filters or load_filters()
    cat = (info.get("category") or "").strip()
    for p in f.get("categoryPrefixes") or []:
        if p and cat.startswith(p):
            return "分类：" + cat
    title = (info.get("title") or "").strip()
    for kw in f.get("titleKeywords") or []:
        if kw and kw in title:
            return "书名含「%s」" % kw
    author = (info.get("author") or "").strip()
    if author.startswith("[") and "]" in author:
        dynasty = author[1:author.index("]")].strip()
        for d in f.get("authorDynasties") or []:
            if d and (dynasty == d or dynasty.startswith(d)):
                return "作者为「%s」" % author
    return None


def shelf_index():
    """返回 (bookId 集合, 书名集合)，用于排除已在书架上的书。"""
    ids, titles = set(), set()
    try:
        s = call("/shelf/sync")
        for b in s.get("books") or []:
            if b.get("bookId"):
                ids.add(str(b["bookId"]))
            if b.get("title"):
                titles.add(b["title"].strip())
    except Exception:
        pass
    return ids, titles


def pick_recommendation(state, seed_book_id=None, probe=15):
    """挑一本「书架外 + 评分高」的书。

    候选池 = 个性化推荐(/book/recommend) + 相似推荐(/book/similar，基于今天的书架书)。
    两者都不返回可靠评分，所以对候选逐个调 /book/info 取真实评分后再排序。
    """
    shelf_ids, shelf_titles = shelf_index()
    done = set(state.get("recommended", []))
    cands = {}

    def add(bid, title, reason, src):
        bid = str(bid) if bid else ""
        if not bid or bid in shelf_ids or bid in done or bid in cands:
            return
        if title and title.strip() in shelf_titles:
            return
        cands[bid] = {"bookId": bid, "title": title, "reason": reason, "source": src}

    try:
        r = call("/book/recommend", count=20)
        for b in r.get("books") or []:
            add(b.get("bookId"), b.get("title"), b.get("reason") or "根据你的阅读记录推荐", "为你推荐")
    except Exception:
        pass

    if seed_book_id:
        try:
            sr = call("/book/similar", bookId=seed_book_id, count=12, maxIdx=0)
            for it in (sr.get("booksimilar") or {}).get("books") or []:
                bi = ((it.get("book") or {}).get("bookInfo") or {})
                add(bi.get("bookId"), bi.get("title"), "与今天书架上的书相似", "相似推荐")
        except Exception:
            pass

    if not cands:
        return None

    # 逐个取真实评分（同时过滤掉不看的类别）
    filters = load_filters()
    scored = []
    for bid, c in list(cands.items())[:probe]:
        try:
            info = call("/book/info", bookId=bid)
        except Exception:
            continue
        rating = (info.get("newRating") or 0) / 100.0
        count = info.get("newRatingCount") or 0
        if not info.get("title"):
            continue
        if is_excluded(info, filters):
            continue
        scored.append({
            "bookId": bid,
            "title": info.get("title"),
            "rating": rating,
            "ratingCount": count,
            "reason": c["reason"],
            "source": c["source"],
        })

    if not scored:
        return None
    # 评分高、且评分人数够多（避免小样本高分）的优先
    scored.sort(key=lambda x: (x["rating"] if x["ratingCount"] >= 50 else 0,
                               min(x["ratingCount"], 20000)), reverse=True)
    return scored[0]


def load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"queue": [], "pushed": []}


def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_queue():
    """从书架构建随机队列：排除公众号，随机打乱。"""
    data = call("/shelf/sync")
    books = data.get("books") or []
    picked = []
    for b in books:
        bid = str(b.get("bookId", ""))
        if bid.startswith("MP_WXS_"):
            continue                      # 公众号不是书
        if not b.get("title"):
            continue
        picked.append({"bookId": bid, "title": b.get("title"), "author": b.get("author")})
    random.shuffle(picked)
    return picked


def chapter_title(chapters, uid):
    for c in chapters or []:
        if c.get("chapterUid") == uid:
            return c.get("title", "")
    return ""


def main():
    global KEY
    KEY = get_key()
    if not KEY:
        print(json.dumps({"error": "未找到 WEREAD_API_KEY，无法访问微信读书接口"},
                         ensure_ascii=False))
        sys.exit(1)

    peek = "--peek" in sys.argv
    reset = "--reset" in sys.argv
    filters = load_filters()

    # --book <bookId>：只取指定书籍的数据，不动队列（用于重发/重试）
    if "--book" in sys.argv:
        idx = sys.argv.index("--book")
        if idx + 1 >= len(sys.argv):
            print(json.dumps({"error": "--book 后缺少 bookId"}, ensure_ascii=False))
            sys.exit(1)
        fixed = sys.argv[idx + 1]
        try:
            info = call("/book/info", bookId=fixed)
            bm = call("/book/bestbookmarks", bookId=fixed)
        except Exception as e:
            print(json.dumps({"error": "取书失败: %s" % e}, ensure_ascii=False))
            sys.exit(1)
        if not info.get("title"):
            print(json.dumps({"error": "bookId %s 取不到书籍信息" % fixed}, ensure_ascii=False))
            sys.exit(1)
        st = load_state()
        print(json.dumps({"count": 1, "books": [build_result(fixed, info, bm)]},
                         ensure_ascii=False, indent=2))
        return

    state = load_state()
    if reset:
        state = {"queue": [], "pushed": []}

    if not state.get("queue"):
        # 队列用完：重建，保留推送历史避免近期重复
        try:
            fresh = build_queue()
        except Exception as e:
            print(json.dumps({"error": "书架拉取失败: %s" % e}, ensure_ascii=False))
            sys.exit(1)
        pushed = set(state.get("pushed", []))
        fresh_ids = [x["bookId"] for x in fresh]
        # 若全部推过，则清空历史重新循环
        if pushed and set(fresh_ids).issubset(pushed):
            state["pushed"] = []
            pushed = set()
        skipped = set(state.get("skipped", []))
        state["queue"] = [x for x in fresh
                          if x["bookId"] not in pushed and x["bookId"] not in skipped]

    # --count N：总本数（默认 1）；--recommend K：其中 K 本来自书架外的高分推荐
    want = 1
    if "--count" in sys.argv:
        cidx = sys.argv.index("--count")
        try:
            want = max(1, int(sys.argv[cidx + 1]))
        except Exception:
            want = 1
    rec_k = 0
    if "--recommend" in sys.argv:
        ridx = sys.argv.index("--recommend")
        try:
            rec_k = max(0, int(sys.argv[ridx + 1]))
        except Exception:
            rec_k = 0
    rec_k = min(rec_k, want)
    shelf_want = want - rec_k

    picked = []
    i = 0          # 队列游标；peek 时只前进不弹出，避免打乱真实顺序
    tried = 0
    while i < len(state["queue"]) and len(picked) < shelf_want and tried < MAX_TRY * max(want, 1):
        cand = state["queue"][i]
        tried += 1
        bid = cand["bookId"]
        try:
            info = call("/book/info", bookId=bid)
            bm = call("/book/bestbookmarks", bookId=bid)
        except Exception:
            i += 1
            if not peek:
                state["queue"].pop(i - 1)
            continue

        # 没有热门划线的书也要推送，highlights 为空即可
        if not info.get("title"):
            i += 1
            if not peek:
                state["queue"].pop(i - 1)
            continue

        # 不看的类别（小说/古籍）直接跳过，不占位
        if filters.get("applyToShelf") and is_excluded(info, filters):
            i += 1
            if not peek:
                state["queue"].pop(i - 1)
                state.setdefault("skipped", []).append(bid)
            continue

        r = build_result(bid, info, bm)
        r["remaining"] = len(state["queue"]) - len(picked) - 1
        r["source"] = "shelf"
        picked.append(r)
        if peek:
            i += 1
        else:
            state["queue"].pop(i)
            state.setdefault("pushed", []).append(bid)

    # 书架外的高分推荐
    for _ in range(rec_k):
        seed = picked[0]["bookId"] if picked else None
        cand = pick_recommendation(state, seed_book_id=seed)
        if not cand:
            break
        try:
            info = call("/book/info", bookId=cand["bookId"])
            bm = call("/book/bestbookmarks", bookId=cand["bookId"])
        except Exception:
            continue
        if not info.get("title"):
            continue
        r = build_result(cand["bookId"], info, bm)
        r["source"] = "recommend"
        r["recommendReason"] = cand["reason"]
        r["recommendSource"] = cand["source"]
        r["remaining"] = None
        picked.append(r)
        if not peek:
            state.setdefault("recommended", []).append(cand["bookId"])

    if not picked:
        print(json.dumps({"error": "书架空了或取不到书籍信息"}, ensure_ascii=False))
        save_state(state)
        sys.exit(1)

    save_state(state)
    print(json.dumps({"count": len(picked), "books": picked}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
