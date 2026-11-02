# daily-book-feed

每天从自己的微信读书书架里挑几本**没推送过**的书，抓取简介和热门划线，生成一封邮件发到邮箱。

不是书评摘要工具，也不是爬虫：它只处理你自己书架上的书和你自己的 API Key。

## 能做什么

- **书架队列**：把书架上的书随机排队，一本一本推，推过的不重复；全部推完才重新循环
- **书架外推荐**：可指定其中几本来自微信读书的「为你推荐 / 相似推荐」，按真实评分筛选
- **过滤**：小说、漫画、古籍原典、诗词可以整体排除，规则写在 `filters.json`
- **抓取内容**：书名、作者、译者、出版社、分类、评分与评分人数、简介、热门划线（附章节名和划线人数）、章节目录
- **发送**：纯文本 + HTML 双版本，正文字号可放大（默认 24px，桌面端好读）

## 工作流程

三步，彼此解耦：

```
next_book.py  →  JSON（取书 + 取数据）
      ↓
  写作（可选：大模型改写 / render_email.py 直接渲染）
      ↓
send_mail.py  →  邮件
```

第二步是可选的。`render_email.py` 不需要任何模型，直接把简介和划线排成邮件；如果接了大模型，让它基于同一份 JSON 写正文，效果更接近人写的导读。

## 快速开始

```bash
git clone https://github.com/linadong/daily-book-feed.git
cd daily-book-feed

cp .env.example .env          # 填微信读书 Key 和 SMTP
cp state.example.json state.json

python3 next_book.py --count 3 --recommend 1 > /tmp/books.json
python3 render_email.py /tmp/books.json > /tmp/mail.md
python3 send_mail.py --subject "今日三书 · $(date +%F)" --file /tmp/mail.md
```

只依赖 Python 3.8+ 标准库，无需 pip 安装。

## 配置

在项目根目录创建 `.env`（已被 `.gitignore` 忽略）：

| 变量 | 说明 |
|---|---|
| `WEREAD_API_KEY` | 微信读书 API Key，`wrk-` 开头 |
| `SMTP_HOST` | SMTP 服务器，QQ 邮箱为 `smtp.qq.com` |
| `SMTP_PORT` | 端口，SSL 一般 465，STARTTLS 用 587 |
| `SMTP_USER` | 发件邮箱 |
| `SMTP_PASS` | 邮箱**授权码**，不是登录密码 |
| `SMTP_SECURE` | `true` 走 SSL，`false` 走 STARTTLS |
| `MAIL_TO` | 收件地址 |

读取优先级：**环境变量 > 项目 `.env` > `~/.follow-builders/.env`**（最后一项是兼容旧配置保留的）。

### 获取 WEREAD_API_KEY

1. 浏览器打开 <https://weread.qq.com/r/weread-skills>
2. 点「快速配置」→「登录微信读书」，用手机微信扫码
3. 页面生成一串 `wrk-` 开头的 Key，复制填入 `.env`

Key 绑定你的微信读书账号，等于你个人阅读数据的钥匙，不要公开。

## 用法

### next_book.py

| 参数 | 说明 |
|---|---|
| （无参数） | 取 1 本，并从队列中消耗掉 |
| `--count N` | 一共取 N 本 |
| `--recommend K` | 其中 K 本来自书架外的高分推荐 |
| `--peek` | 只看下一本，不消耗队列 |
| `--book <bookId>` | 只取指定书，不动队列（用于重发） |
| `--reset` | 清空已推送记录，重建队列 |

输出 JSON 到 stdout，单本书的结构：

```json
{
  "bookId": "3300059686",
  "title": "夜晚的潜水艇",
  "author": "陈春成",
  "publisher": "上海三联书店",
  "category": "文学-经典作品",
  "rating": 8.87,
  "ratingCount": 21547,
  "intro": "……",
  "deepLink": "https://weread.qq.com/book-detail?...",
  "highlights": [{"text": "……", "count": 21768, "chapter": "夜晚的潜水艇"}],
  "outline": ["夜晚的潜水艇", "竹峰寺", "传彩笔"],
  "source": "shelf"
}
```

`highlights` 最多 12 条（展示用前 5 条），`outline` 是章节目录，两者都是给写作步骤用的素材。

### send_mail.py

| 参数 | 说明 |
|---|---|
| `--subject` | 邮件主题（必填） |
| `--file` | 正文文件，Markdown（必填） |
| `--font-scale` | 字号倍数，`16px × 倍数`，默认 `1.5` 即 24px |
| `--plain-only` | 只发纯文本，不做 HTML 放大 |

正文支持极简 Markdown：`#`/`##`/`###` 标题、`> ` 引用、`---` 分隔线、`**加粗**`。

## 过滤规则

`filters.json` 决定哪些书不推：

| 字段 | 作用 |
|---|---|
| `categoryPrefixes` | 分类以这些字符串开头即排除 |
| `titleKeywords` | 书名包含任一关键词即排除 |
| `authorDynasties` | 作者标注的朝代（如 `[唐]`）命中即排除 |
| `applyToShelf` | `true` 时书架选书也过滤；`false` 只过滤推荐位 |

以 `_` 开头的键是注释，程序会跳过。

## 自动化

本机 cron（每天 8:00）：

```cron
0 8 * * * cd /path/to/daily-book-feed && \
  python3 next_book.py --count 3 --recommend 1 > /tmp/books.json && \
  python3 render_email.py /tmp/books.json > /tmp/mail.md && \
  python3 send_mail.py --subject "今日三书 · $(date +\%F)" --file /tmp/mail.md
```

GitHub Actions 也能跑：把 `WEREAD_API_KEY` 和 SMTP 相关值放进仓库 Secrets，workflow 里 export 成环境变量即可。注意 Actions 的 runner 无法调用大模型写作那一步，除非你自己接 API。

## 隐私与安全

- `.env` 和 `state.json` 都在 `.gitignore` 里。`state.json` 记录了你推过哪些书，等于你的阅读清单，**不要提交**
- 提交前建议跑一次 `git status`，确认没有把 `.env`、`state.json` 加进去
- 邮件正文里只有书籍公开信息，不含个人笔记内容
- 如 Key 泄露，去 <https://weread.qq.com/r/weread-skills> 重新生成

## 文件结构

```
daily-book-feed/
├── next_book.py        # 选书 + 抓数据，输出 JSON
├── render_email.py     # JSON → Markdown（无模型兜底渲染）
├── send_mail.py        # Markdown → HTML/纯文本邮件并发送
├── filters.json        # 排除规则
├── .env.example        # 配置模板
└── state.example.json  # 队列状态模板
```

## 声明

调用的是微信读书 Agent API Gateway，属于非公开接口，随时可能变更或失效；仅供个人使用，请勿用于批量抓取或分发。API Key 绑定个人账号，泄露等同于交出个人阅读数据。
