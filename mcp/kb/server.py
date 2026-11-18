"""项目 docs 知识库检索 MCP server（纯只读, 纯标准库 + mcp SDK）。

把各 mod 项目工作区的 docs/（尤其 evidence/ 已定案调查与验证记录）做成
可按项目区分的检索库。设计对应 docs 的落盘分位制度：

  三工具:
    kb_list    清单 + 章节标题树（轻量目录, 供模型自我路由, 不整读大文件）
    kb_search  章节级关键词检索（标题加权 + 中文 2-gram 兜底, 只回摘录+行号）
    kb_read    按 heading 定向取节（86KB 调查文件只取需要的 2KB）

  登记制注册表（检索池只含登记项目, 路径契约: 登记工作区根, 解析为其下 docs）:
    registry  ~/.zcode/kb/registry.json（KB_REGISTRY env 可改路径）
              libraries 别名/工作区根 + exclude 排除 + scan_roots 扫描根
    env       KB_LIBRARY 分号分隔（"工作区根"或 "别名=工作区根"）,
              workspace scope 注入; 同名时 registry 覆盖 env
    扫描发现  约定根（KB_SCAN_ROOTS > registry.scan_roots > D:\\DeepSeek）
              下的 */docs 只做"未登记发现", 不进检索池（kb_list 尾部列出,
              登记后才可检索——避免临时目录混入跨项目检索）

  scope 分位过滤（对应落盘纪律, 默认只搜现行认知层）:
    current（默认）  docs 根现行主题文档 + evidence/（正向现状 + 已定案证据）
    all              另加 history,review（传递/待回复层）
    显式分位组合     root,evidence,history,review,archive 按需组合
    archive 永远需显式传入（过时结论默认不暴露）

  状态行置顶: 落盘纪律要求被推翻结论在节头写 "> [状态：…] " 固定格式状态行
  （可行性 / 代价条件 / 现行定案指针）。本 server 解析状态行, 检索命中被推翻
  节时摘录必含且置顶, 保证读取者先见状态再读正文。

索引不持久化: 进程内按 (path, mtime, size) 增量切块, heading 边界即 chunk。
只读, 永不写用户文件。"""

import os
import re
import sys
import time
import json

from mcp.server.fastmcp import FastMCP

sys.stdout.reconfigure(encoding="utf-8")

mcp = FastMCP("re-mod-kb")

# ---------- 配置 ----------

DEFAULT_SCAN_ROOT = r"D:\DeepSeek"
REGISTRY_PATH = os.environ.get(
    "KB_REGISTRY", os.path.expanduser("~/.zcode/kb/registry.json"))

# 防御阈值: 超过则只索引标题树不索引正文（打分退化为标题命中）
BODY_INDEX_MAX_BYTES = 2 * 1024 * 1024
# 单文件超过则 kb_read 拒绝无 heading 整读, 返回标题树 + 提示
WHOLE_READ_MAX_BYTES = 30 * 1024

# 状态行: "> [状态：已推翻] ..." 固定格式（落盘纪律约定）
RE_STATUS = re.compile(r"^\s*>\s*\[状态[：:](?P<st>[^\]]+)\]\s*(?P<rest>.*)$")
RE_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
RE_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
RE_SECNO_QUERY = re.compile(r"^\d+(?:\.\d+)*\.?$")       # 查询是纯节号: "2" / "2." / "8.1"
RE_TITLE_SECNO = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")     # 标题开头的节号: "2. xxx" / "8.1 xxx"
RE_HAN = re.compile(r"[\u4e00-\u9fff]+")
RE_SPLIT_Q = re.compile(r"[,，;；\s]+")


def _scan_roots():
    env = os.environ.get("KB_SCAN_ROOTS", "").strip()
    if env:
        return [p for p in (s.strip() for s in env.split(";")) if p]
    reg = _load_registry()
    roots = reg.get("scan_roots")
    if isinstance(roots, list) and roots:
        return [str(p) for p in roots]
    return [DEFAULT_SCAN_ROOT]


def _load_registry():
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# ---------- 库发现（登记制: registry/env 为检索池, 扫描仅用于发现） ----------

def _resolve_docs_path(root):
    """路径契约: 登记工作区根, 统一解析为其下 docs。

    仅两种接受形态: 工作区根（其下存在 docs 目录）; 真实存在的 docs 目录
    本身（非标准, 告警提示建议登记工作区根）。返回 (docs路径, 告警)。"""
    p = os.path.normpath(str(root))
    d = os.path.join(p, "docs")
    if os.path.isdir(d):
        return d, ""
    if os.path.isdir(p) and os.path.basename(p).lower() == "docs":
        return p, "（非标准: 路径直接指向 docs, 建议登记工作区根）"
    return None, f"路径无效: {p}（其下无 docs 目录）"


def _kb_state():
    """返回 (libs, sources, warnings, discovered)。

    libs:   {别名: docs绝对路径} —— 检索池, 仅 registry + env 两层登记来源
    sources:{别名: "registry"/"env"}   warnings: 路径/覆盖告警列表
    discovered: {规范化docs路径: (显示名, 工作区根)} —— 约定根扫描的
                未登记候选, 不进检索池
    """
    reg = _load_registry()
    cand = {}                       # alias -> (path, source)
    env = os.environ.get("KB_LIBRARY", "").strip()
    if env:                         # L1 env, 先装
        for item in env.split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                alias, path = (s.strip() for s in item.split("=", 1))
            else:
                alias = os.path.basename(os.path.normpath(item))
                path = item
            if path:
                cand[alias] = (path, "env")
    overrides = []
    for alias, spec in (reg.get("libraries") or {}).items():   # L2 registry 后装, 同名覆盖
        path = spec.get("path") if isinstance(spec, dict) else spec
        if alias in cand and cand[alias][0] != str(path):
            overrides.append(f"[{alias}] registry 覆盖 env")
        if path:
            cand[str(alias)] = (str(path), "registry")

    libs, sources, warnings = {}, {}, list(overrides)
    seen_paths = {}
    # 同一路径仅保留一个别名, registry 优先于 env（别名规则见 command 契约）
    ordered = sorted(cand.items(),
                     key=lambda kv: 0 if kv[1][1] == "registry" else 1)
    for alias, (path, src) in ordered:
        docs, warn = _resolve_docs_path(path)
        if docs is None:
            warnings.append(f"[{alias}] {warn}")
            continue
        if warn:
            warnings.append(f"[{alias}] {warn}")
        norm = os.path.normcase(os.path.normpath(docs))
        if norm in seen_paths:
            warnings.append(f"[{alias}] 与 [{seen_paths[norm]}] 指向同一目录, "
                            "重复登记跳过（同一路径仅保留一个别名）")
            continue
        seen_paths[norm] = alias
        libs[alias] = docs
        sources[alias] = src

    discovered = {}             # 规范化 docs 路径 -> (显示名, 工作区根路径)
    registered = {os.path.normcase(os.path.normpath(d))
                  for d in libs.values()}
    exclude = set(reg.get("exclude", []))
    for root in _scan_roots():
        try:
            entries = os.scandir(root)
        except OSError:
            continue
        for e in entries:
            if e.name in exclude or not e.is_dir():
                continue
            docs = os.path.join(e.path, "docs")
            if os.path.isdir(docs):
                norm = os.path.normcase(os.path.normpath(docs))
                if norm not in registered:
                    discovered[norm] = (e.name, e.path)
    return libs, sources, warnings, discovered


def _resolve_project(project: str):
    """解析 project 参数 -> (名称, libs子集)。支持 'all' / 别名模糊匹配。"""
    libs, _, _, _ = _kb_state()
    p = (project or "").strip()
    if p.lower() == "all":
        return "all", libs
    if p in libs:
        return p, {p: libs[p]}
    low = p.lower()
    hits = {k: v for k, v in libs.items() if low in k.lower()}
    if len(hits) == 1:
        k, v = next(iter(hits.items()))
        return k, {k: v}
    if len(hits) > 1:
        return f"ambiguous:{p}", {k: v for k, v in hits.items()}
    return None, libs


# ---------- 切块索引（heading 边界即 chunk, 进程内 mtime 缓存） ----------

class Chunk:
    __slots__ = ("rel", "heading_path", "title", "line_start", "line_end",
                 "status_block", "status_src", "status_from", "level")

    def __init__(self, rel, heading_path, title, line_start, line_end,
                 status_block, status_src, status_from, level):
        self.rel = rel                      # 相对 docs 的路径（posix 风格）
        self.heading_path = heading_path    # "## 8 … > ### 8.1 …"
        self.title = title                  # 最低级标题文本
        self.line_start = line_start        # 1-based, 含
        self.line_end = line_end            # 1-based, 含
        self.status_block = status_block    # 生效状态行块（list[str]）或 None
        self.status_src = status_src        # "self" 自带 / "inherited" 继承父级
        self.status_from = status_from      # inherited 时的来源节标题
        self.level = level


class FileIndex:
    __slots__ = ("rel", "abs", "size", "mtime", "chunks", "has_body", "file_note")

    def __init__(self, rel, abs_, size, mtime):
        self.rel = rel
        self.abs = abs_
        self.size = size
        self.mtime = mtime
        self.chunks = []
        self.has_body = False   # 正文已载入缓存（<BODY_INDEX_MAX_BYTES）
        self.file_note = None   # 文件级证据口径（头声明/覆盖说明）, 随片段返回


_FILES = {}     # abs -> FileIndex
_LINES = {}     # abs -> list[str]（仅 has_body 的文件）

# 分位名: root = docs 根现行主题文档（game-runtime/session-handoff 等,
# 正向结论的家, 对应落盘纪律"持续更新的现行主题文档留 docs/ 根"）
_SCOPES = ("root", "evidence", "history", "review", "archive")
# current = docs 根 + evidence: 现行认知层（正向现状 + 已定案证据）
_CURRENT = {"root", "evidence"}


def _scope_dirs(scope):
    """scope 字符串 -> 允许的分位集合。current/all 为预置组合。"""
    scope = (scope or "current").strip().lower()
    if scope == "current":
        return set(_CURRENT)
    if scope == "all":
        return {"root", "evidence", "history", "review"}  # archive 需显式
    chosen = {s for s in (t.strip() for t in scope.split(",")) if s}
    return chosen if chosen <= set(_SCOPES) else None


def _iter_md(docs, allowed):
    for dirpath, dirnames, filenames in os.walk(docs):
        rel_dir = os.path.relpath(dirpath, docs).replace("\\", "/")
        top = rel_dir.split("/")[0] if rel_dir != "." else ""
        if top in ("data",) or os.path.basename(dirpath).startswith("."):
            dirnames[:] = []
            continue
        if rel_dir == ".":
            skip_root_file = "root" not in allowed   # 跳过根文件, 子目录照走
        elif top not in allowed:
            dirnames[:] = []
            continue
        else:
            skip_root_file = False
        for fn in filenames:
            if skip_root_file or not fn.lower().endswith(".md"):
                continue
            yield os.path.join(dirpath, fn), (
                fn if rel_dir == "." else f"{rel_dir}/{fn}")


def _index_file(abs_path, rel):
    try:
        st = os.stat(abs_path)
    except OSError:
        _FILES.pop(abs_path, None)
        _LINES.pop(abs_path, None)
        return None
    fi = _FILES.get(abs_path)
    if fi and fi.mtime == st.st_mtime and fi.size == st.st_size:
        return fi
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    fi = FileIndex(rel, abs_path, st.st_size, st.st_mtime)
    has_body = st.st_size <= BODY_INDEX_MAX_BYTES

    # 标题栈元素 (level, title, status_block): 状态随标题层级压栈/弹出,
    # 子节只继承仍在栈中的最近祖先状态——同级/上级新节自动甩掉兄弟节状态
    stack = []
    cur = None            # 当前开放 chunk
    status_buf = None     # 当前 chunk 头部状态行的收集缓冲（仅节头生效）
    in_fence = False      # 代码围栏内部: 不解析标题/状态行
    fence_mark = ""

    def close(end_line):
        nonlocal cur, status_buf
        if cur is not None:
            cur.line_end = end_line
            fi.chunks.append(cur)
            cur = None

    def open_chunk(level, title, line_no, heading_path):
        """打开新节, 继承栈中最近的祖先状态（带来源节标题）。"""
        nonlocal cur, status_buf
        close(line_no - 1)
        inherited = None
        for _, _, blk in reversed(stack):
            if blk:
                inherited = blk
                break
        if inherited is not None:
            src_title = next(t for _, t, b in reversed(stack) if b is inherited)
            cur = Chunk(rel, heading_path, title, line_no, line_no,
                        list(inherited), "inherited", src_title, level)
        else:
            cur = Chunk(rel, heading_path, title, line_no, line_no,
                        None, None, None, level)
        status_buf = []

    for i, line in enumerate(lines, 1):
        ls = line.lstrip()
        if in_fence:
            # 闭围栏: 同字符、长度 >= 开围栏、其后仅空白
            fm = RE_FENCE.match(line)
            if fm and fm.group(1)[0] == fence_mark[0] \
                    and len(fm.group(1)) >= len(fence_mark) \
                    and not line[fm.end():].strip():
                in_fence = False
            if cur is None:         # 围栏恰好出现在文件最前
                open_chunk(0, "(前言)", i, "(前言)")
            continue
        fm = RE_FENCE.match(line)
        if fm:                      # 开围栏: 记录实际字符与长度（```` 包 ``` 不提前闭合）
            in_fence = True
            fence_mark = fm.group(1)
            if cur is None:
                open_chunk(0, "(前言)", i, "(前言)")
            continue
        m = RE_HEADING.match(line)
        if m:
            level = len(m.group("hashes"))
            title = m.group("title").strip()
            stack[:] = [s for s in stack if s[0] < level]   # 弹出已结束章节
            stack.append((level, title, None))
            hp = " > ".join(t for _, t, _ in stack)
            open_chunk(level, title, i, hp)
            continue
        if cur is None:                 # 第一个标题之前的正文 -> 前言块
            open_chunk(0, "(前言)", i, "(前言)")
        sm = RE_STATUS.match(line)
        if sm and status_buf is not None \
                and (i - cur.line_start) == len(status_buf) + 1:
            status_buf.append(line.strip().lstrip("> ").strip())
            cur.status_block = list(v for v in status_buf if v)
            cur.status_src = "self"
            cur.status_from = None
            stack[-1] = (stack[-1][0], stack[-1][1], cur.status_block)
        elif status_buf is not None and not line.strip():
            status_buf.append("")       # 状态块内允许空行, 后随正文即断开
        elif status_buf is not None:
            status_buf = None           # 正文开始, 本节状态块结束
    close(len(lines))

    # 文件级证据口径: 文件头部元信息区的"- 认识状态…"行与覆盖说明
    # （通常位于 h1 标题之后、第一个正文小节之前）。
    # 按需读节不能把适用于整份文件的限制切掉——kb_search/kb_read 附带返回。
    notes = []
    for ln in lines[:60]:
        m = RE_HEADING.match(ln)
        if m and len(m.group("hashes")) >= 2:
            break                       # 进入正文小节, 头部结束
        if ln.strip().startswith(("- 认识状态", "- 认识状态说明")):
            notes.append(ln.strip().lstrip("- ").strip())
    if notes:
        fi.file_note = " / ".join(notes if len(notes) <= 2 else notes[-2:])

    if has_body:
        _LINES[abs_path] = lines
        fi.has_body = True
    _FILES[abs_path] = fi
    return fi


def _collect(docs, allowed):
    out = []
    for abs_path, rel in _iter_md(docs, allowed):
        fi = _index_file(abs_path, rel)
        if fi:
            out.append(fi)
    return out


def _md_census(docs):
    """docs 下 md 计数按一级目录分桶（'.' = 根）。空库展示用。"""
    from collections import Counter
    c = Counter()
    for dp, dn, fn in os.walk(docs):
        rel = os.path.relpath(dp, docs)
        top = rel.split(os.sep)[0] if rel != "." else "."
        if top == "data" or os.path.basename(dp).startswith("."):
            dn[:] = []
            continue
        c[top] += sum(1 for f in fn if f.lower().endswith(".md"))
    return c


def _pool(project_key, libs, scope):
    """解析后的库 -> [(lib名, fileIndex)]；scope 非法返回 None。"""
    allowed = _scope_dirs(scope)
    if allowed is None:
        return None
    pool = []
    for name, docs in libs.items():
        for fi in _collect(docs, allowed):
            pool.append((name, fi))
    return pool


# ---------- 检索打分 ----------

def _bigrams(term):
    grams = []
    for seg in RE_HAN.findall(term):
        if len(seg) >= 2:
            grams += [seg[i:i + 2] for i in range(len(seg) - 1)]
    return grams


def _terms(query):
    return [t for t in RE_SPLIT_Q.split(query.strip()) if t]


def _hits(term, text_low):
    """(强命中数, 弱命中数): 直接子串为强, 中文 2-gram 为弱(0.3 权重)。"""
    n = text_low.count(term.lower())
    if n:
        return n, 0
    weak = sum(text_low.count(g.lower()) for g in _bigrams(term))
    return 0, weak


def _score_chunk(terms, chunk, text_low):
    """返回 (score, detail)。覆盖率优先, 标题命中加权。"""
    strong = weak = 0
    t_hits, b_hits = [], []
    title_low = chunk.title.lower()
    for t in terms:
        ts, tw = _hits(t, title_low)
        bs, bw = _hits(t, text_low)
        t_hits.append(ts + tw)
        b_hits.append(bs + bw)
        strong += ts + bs
        weak += tw + bw
    covered = sum(1 for h, b in zip(t_hits, b_hits) if h or b)
    cov = covered / len(terms)
    title_score = sum(t_hits) * 3
    body_score = strong + 0.3 * weak
    score = cov * 1000 + title_score + body_score
    return score, {"cov": covered, "title": sum(t_hits), "body": strong + weak}


def _excerpt(fi, chunk, terms):
    """命中行 ±2 行摘录; chunk 带状态行时置顶。单行截 160 字符。"""
    lines = _LINES.get(fi.abs)
    head = []
    if chunk.status_block:
        head = [s for s in chunk.status_block if s]
    body_part = []
    if lines and fi.has_body:
        lo = max(chunk.line_start, 1)
        hi = min(chunk.line_end, len(lines))
        seg = lines[lo - 1:hi]
        hit_i = 0
        for idx, ln in enumerate(seg):
            low = ln.lower()
            if any(_hits(t, low)[0] or _hits(t, low)[1] for t in terms):
                hit_i = idx
                break
        s, e = max(0, hit_i - 2), min(len(seg), hit_i + 3)
        body_part = [ln.strip()[:160] for ln in seg[s:e] if ln.strip()]
        body_part = body_part[:6]
    parts = []
    if head:
        if chunk.status_src == "inherited":
            parts.append(f"> （状态继承自父节「{chunk.status_from}」）")
        parts += ["> " + s for s in head]
    parts += body_part
    return "\n   ".join(parts) if parts else "(无正文摘录)"


def _fmt_ref(lib, fi, chunk):
    return (f"[{lib}] {fi.rel} §{chunk.heading_path.split(' > ')[-1]} "
            f"L{chunk.line_start}-{chunk.line_end}")


# ---------- MCP 工具 ----------

@mcp.tool()
def kb_list(project: str = "all", scope: str = "current", depth: int = 2) -> str:
    """列出知识库项目与各文件的章节标题树（轻量目录, 供自我路由）。

    先用本工具看"库里有什么", 再用 kb_search 定位、kb_read 取节。
    project: 项目名/别名, 模糊匹配; "all" 列全部库。
    scope: current(默认)=docs 根现行文档+evidence; all=另加 history,review
    （archive 永远需显式）; 也可逗号组合 root,evidence,history,review,archive。
    depth: 标题树层级, 默认 2（## 级）, 0 只列文件名。

    Args:
        project: 项目名、别名或 "all"
        scope: 分位过滤, 默认 current
        depth: 标题树深度, 默认 2, 0 = 只列文件
    """
    t0 = time.perf_counter()
    libs, sources, warnings, discovered = _kb_state()
    p = (project or "all").strip()
    key = "all"
    if p.lower() != "all":
        key, libs = _resolve_project(p)
        if key is None:
            avail = ", ".join(sorted(libs)) or "(空)"
            return f"错误: 找不到项目 {p!r}。可用: {avail}"
        if key.startswith("ambiguous:"):
            return (f"错误: {p!r} 匹配到多个项目: "
                    + ", ".join(sorted(libs)) + "；请用更精确的名称。")
        sources = {k: v for k, v in sources.items() if k in libs}
        discovered = {}
    pool = _pool(key, libs, scope)
    if pool is None:
        return ("错误: scope 仅支持 current/all 或分位组合 "
                "root,evidence,history,review,archive。")
    depth = max(0, min(int(depth), 6))
    out = [f"== kb_list: {key} scope={scope} ({len(libs)} 库, {len(pool)} md, "
           f"{(time.perf_counter() - t0) * 1000:.0f}ms) =="]
    by_lib = {}
    for lib, fi in pool:
        by_lib.setdefault(lib, []).append(fi)
    for lib in sorted(libs):                    # 遍历全部登记库, 空库也显示
        out.append(f"[{lib}] {libs[lib]} （来源: {sources.get(lib, '?')}）")
        fis = by_lib.get(lib, [])
        if not fis:
            census = _md_census(libs[lib])
            total = sum(census.values())
            if not total:
                out.append("      暂无 Markdown 文档")
            else:
                detail = ", ".join(f"{k}:{v}" for k, v in sorted(census.items())
                                   if v and k != "." and k in _scope_dirs("all") | {"root"})
                out.append(f"      暂无 {scope} 范围内的 Markdown"
                           + (f"（其它分位有: {detail}）" if detail else
                              f"（共 {total} 篇在其它目录）"))
            continue
        for fi in sorted(fis, key=lambda x: x.rel):
            tag = " *" if not fi.has_body and fi.size > BODY_INDEX_MAX_BYTES else ""
            out.append(f"  - {fi.rel} ({fi.size // 1024}KB){tag}")
            if depth:
                for c in fi.chunks:
                    if c.level <= depth + 1:
                        out.append("      " + "  " * (c.level - 1)
                                   + c.heading_path.split(" > ")[-1])
    for w in warnings:
        out.append(f"!! {w}")
    if p.lower() == "all" and discovered:
        out.append(f"== 未登记发现 ({len(discovered)}) —— 登记后才会进入检索池,"
                   " 可用 /kb-register ==")
        for name, wroot in sorted(discovered.values()):
            out.append(f"  - {name}  {wroot}")
    out.append("== 提示: kb_search 定位内容, kb_read 取整节; 节头[状态：…] 行"
               "声明结论现行状态, 按状态内容判断是否可用 ==")
    return "\n".join(out)


@mcp.tool()
def kb_search(project: str, query: str, scope: str = "current",
              limit: int = 8) -> str:
    """章节级关键词检索：返回 文件+节+行号+摘录, 不回大段原文。

    查询词给 3-5 个变体（逗号分隔, OR 语义, 按词报命中）, 例如搜 UI 图标
    刷新问题: "图标不刷新,不主动刷新,bossicon,frame"。标题命中加权, 中文
    2-gram 部分匹配兜底; 多词全中的节排前。命中被推翻节时状态行置顶返回。
    定位后用 kb_read 取整节; 若查"哪里会出问题", 也搜否定词（如 崩溃,失效）。

    Args:
        project: 项目名、别名或 "all"（跨库）
        query: 关键词, 逗号分隔多个变体
        scope: 默认 current(根现行文档+evidence); all 另加 history,review;
            archive 需显式传入
        limit: 返回条数, 默认 8
    """
    t0 = time.perf_counter()
    if not query.strip():
        return "错误: query 为空。"
    terms = _terms(query)
    if not terms:
        return "错误: query 未含有效词（只有分隔符）。"
    key, libs = _resolve_project(project)
    if key is None:
        avail = ", ".join(sorted(libs)) or "(空)"
        return f"错误: 找不到项目 {project!r}。可用: {avail}"
    if key.startswith("ambiguous:"):
        return (f"错误: {project!r} 匹配到多个项目, 请更精确。"
                + "候选: " + ", ".join(sorted(libs)))
    pool = _pool(key, libs, scope)
    if pool is None:
        return ("错误: scope 仅支持 current/all 或分位组合 "
                "root,evidence,history,review,archive。")
    limit = max(1, min(int(limit), 25))
    scored = []
    for lib, fi in pool:
        for c in fi.chunks:
            text_low = ""
            if fi.has_body:
                lines = _LINES[fi.abs]
                text_low = "\n".join(lines[c.line_start - 1:c.line_end]).lower()
            if not text_low:
                text_low = c.heading_path.lower()
            s, detail = _score_chunk(terms, c, text_low)
            if s > 0:
                scored.append((s, lib, fi, c, detail))
    scored.sort(key=lambda x: (-x[0], x[2].rel, x[3].line_start))
    ms = (time.perf_counter() - t0) * 1000
    if not scored:
        return (f"== kb_search: 无命中 (query={query!r}, {len(pool)} md, {ms:.0f}ms) ==\n"
                "建议: 换查询词变体（同义词/缩写/英文名）; kb_list 先看标题树;")
    out = [f"== kb_search: {key} query={query!r} scope={scope} "
           f"({len(pool)} md, {ms:.0f}ms) =="]
    for i, (s, lib, fi, c, d) in enumerate(scored[:limit], 1):
        out.append(f"{i}. [score {s:.0f} 覆盖{d['cov']}/{len(terms)} "
                   f"标题{d['title']} 正文{d['body']}] {_fmt_ref(lib, fi, c)}")
        ex = _excerpt(fi, c, terms)
        out.append(f"   {ex}")
    seen_notes = []
    seen_keys = set()
    for _, lib0, fi0, _, _ in scored[:limit]:
        if fi0.file_note and (lib0, fi0.rel) not in seen_keys:
            seen_keys.add((lib0, fi0.rel))
            seen_notes.append((lib0, fi0.rel, fi0.file_note))
    if seen_notes:
        out.append("== 文件级证据口径（适用于该文件全部片段）==")
        for lib0, rel, note in seen_notes:
            out.append(f"  [{lib0}] {rel}：{note}")
    out.append("== 提示: kb_read(project, file, heading=\"节号\") 取整节;"
               " 节头[状态：…] 行声明结论现行状态（已推翻/部分有效/实测通过/"
               "待验证等）, 按状态内容判断是否可用, 被推翻结论以其指针为准 ==")
    return "\n".join(out)


@mcp.tool()
def kb_read(project: str, file: str, heading: str = "",
            scope: str = "current") -> str:
    """按 heading 定向读取一节的原文（86KB 调查文件只取需要的节）。

    file 用 kb_search/kb_list 返回的相对路径; heading 用节号或标题子串
    （如 "8.1" 或 "F5 实测结论"）, 多个匹配时列出候选。不指定 heading 时:
    小文件(<30KB)整读返回; 大文件返回标题树并提示用 heading 取节。
    若节头有 [状态：…] 行, 原样返回在最前——被推翻的结论以其指针为准。

    Args:
        project: 项目名或别名
        file: 相对 docs 的文件路径（kb_search/kb_list 返回的）
        heading: 节号或标题子串, 可选
        scope: 默认 current; 超出 current/history 的分位需显式组合
    """
    key, libs = _resolve_project(project)
    if key is None or key.startswith("ambiguous:"):
        return f"错误: 项目 {project!r} 无法唯一解析。可用: " + ", ".join(sorted(libs))
    pool = _pool(key, libs, scope)
    if pool is None:
        return "错误: scope 仅支持 evidence/history/review/archive 组合或 all。"
    fname = file.replace("\\", "/").strip().lower()
    target = [(lib, fi) for lib, fi in pool
              if fi.rel.lower() == fname or fi.rel.lower().endswith("/" + fname)]
    if not target:
        cands = sorted({fi.rel for _, fi in pool})
        hit = [c for c in cands if fname.split("/")[-1] in c.lower()][:10]
        return ("错误: 找不到文件 " + file +
                ("。近似: " + "; ".join(hit) if hit else
                 "。用 kb_list 查看可用文件。"))
    if len(target) > 1:
        return ("错误: 文件名在多库中重名, 请换更精确 project。候选: "
                + "; ".join(f"[{l}] {f.rel}" for l, f in target[:10]))
    lib, fi = target[0]
    lines = _LINES.get(fi.abs)
    if lines is None:
        try:
            with open(fi.abs, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError as e:
            return f"错误: 读取失败: {e}"

    def chunk_text(c):
        return "\n".join(lines[c.line_start - 1:min(c.line_end,
                                                    c.line_start + 400)])

    if not heading.strip():
        if fi.size <= WHOLE_READ_MAX_BYTES:
            return f"== kb_read: [{lib}] {fi.rel} (整文件 {fi.size // 1024}KB) ==\n" \
                   + "\n".join(lines)
        tree = [f"== kb_read: [{lib}] {fi.rel} ({fi.size // 1024}KB, "
                "超整读上限) 章节树: =="]
        for c in fi.chunks:
            tree.append("  " + "  " * (c.level - 1)
                        + c.heading_path.split(" > ")[-1] + f" L{c.line_start}")
        tree.append("== 用 heading 参数取节, 如 heading=\"8.1\" ==")
        return "\n".join(tree)

    h = heading.strip()
    if RE_SECNO_QUERY.match(h):
        # 纯节号查询: 精确比较编号, 不退化为子串（"2." 不得误中 "12." 或 "2.1"）
        target = h.rstrip(".")
        def _secno(t):
            m = RE_TITLE_SECNO.match(t)
            return m.group(1) if m else None
        matches = [c for c in fi.chunks if _secno(c.title) == target]
    else:
        # 标题文字查询: 完整匹配 -> 前缀 -> 子串
        low = h.lower()
        matches = [c for c in fi.chunks if c.title.lower() == low]
        if not matches:
            matches = [c for c in fi.chunks
                       if c.heading_path.split(" > ")[-1].lower().startswith(low)
                       or c.title.lower().startswith(low)]
        if not matches:
            matches = [c for c in fi.chunks
                       if low in c.heading_path.split(" > ")[-1].lower()
                       or low in c.title.lower()]
    if not matches:
        return ("错误: 未找到节 " + heading +
                "。可用节: " + "; ".join(
                    c.heading_path.split(" > ")[-1] for c in fi.chunks[:40]))
    if len(matches) > 1:
        return ("多节匹配 " + heading + ", 请更精确: "
                + "; ".join(c.heading_path.split(" > ")[-1]
                            for c in matches[:10]))
    c = matches[0]
    body = chunk_text(c)
    head = f"== kb_read: [{lib}] {fi.rel} §{c.heading_path.split(' > ')[-1]} " \
           f"L{c.line_start}-{c.line_end} =="
    if fi.file_note:
        head += "\n[文件级证据口径] " + fi.file_note
    if c.status_block:
        head += "\n" + "\n".join("> " + s for s in c.status_block if s)
        if c.status_src == "inherited":
            head += f"\n> （状态继承自父节「{c.status_from}」）"
    if c.line_end - c.line_start > 400:
        head += f"\n(节过长, 已截断至 400 行; 全节 L{c.line_start}-{c.line_end})"
    return head + "\n" + body


# ---------- 自检（不进 MCP 模式, 供本地回归） ----------

def _selftest(argv):
    docs = argv[2] if len(argv) > 2 else DEFAULT_SCAN_ROOT
    if os.path.isdir(docs) and os.path.basename(docs) != "docs":
        cand = os.path.join(docs, "docs")
        docs = cand if os.path.isdir(cand) else docs
    print(f"selftest docs = {docs}")
    t0 = time.perf_counter()
    pool = _collect(docs, {"root", "evidence"})
    print(f"索引: {len(pool)} md, {(time.perf_counter() - t0) * 1000:.0f}ms")
    nchunks = sum(len(f.chunks) for f in pool)
    nstatus = sum(1 for f in pool for c in f.chunks if c.status_block)
    print(f"chunks: {nchunks}, 带状态行: {nstatus}")
    cases = [q for q in argv[3:]] or [
        "F5 实测", "帧 47 雷神龙", "不主动刷新", "崩溃 引用", "生命周期 gate",
        "bossicon 机制定案", "显隐 同步", "profiler 口径", "HookUI",
        "reset 线",
    ]
    allowed = {"root", "evidence"}   # 与默认 scope=current 一致
    for q in cases:
        t0 = time.perf_counter()
        scored = []
        terms = _terms(q)
        for fi in pool:
            for c in fi.chunks:
                text_low = ""
                if fi.has_body:
                    ls = _LINES[fi.abs]
                    text_low = "\n".join(
                        ls[c.line_start - 1:c.line_end]).lower()
                if not text_low:
                    text_low = c.heading_path.lower()
                s, d = _score_chunk(terms, c, text_low)
                if s > 0:
                    scored.append((s, fi, c, d))
        scored.sort(key=lambda x: (-x[0], x[1].rel, x[2].line_start))
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n>> query={q!r} ({ms:.0f}ms)")
        for s, fi, c, d in scored[:3]:
            print(f"   [{s:.0f} 覆盖{d['cov']}/{len(terms)} 标题{d['title']}] "
                  f"{fi.rel} §{c.heading_path.split(' > ')[-1]} "
                  f"L{c.line_start}" + ("  [有状态行]" if c.status_block else ""))
        if not scored:
            print("   (无命中)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest(sys.argv)
    else:
        mcp.run(transport="stdio")
