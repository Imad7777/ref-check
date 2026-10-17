---
name: ref-check
description: |
  [EN] Verify the authenticity of scholarly references: parse reference entries from an
  extracted manuscript text, verify each DOI against the Crossref API and each arXiv ID
  against the arXiv API, fuzzy-compare claimed vs. official titles, and produce an
  OK / MISMATCH / FAIL / ARXIV / NODOI report. Works for any venue (CHI, CSCW, NeurIPS,
  journals). Use when asked to check for fabricated citations or validate reference lists.
  [中文] 学术论文参考文献真实性核验：从论文全文提取文本解析参考文献条目，DOI 送 Crossref
  API、arXiv ID 送 arXiv API 逐条验证，标题模糊比对后输出 OK / MISMATCH / FAIL / ARXIV /
  NODOI 分类报告。适用于任何 venue；用于检测伪造引用或自查参考文献。
---

# Reference Check / 参考文献核验

Verify that every reference in a manuscript actually exists — and that the claimed title,
year, and venue match the official record. / 核验论文参考文献是否真实存在，标题、年份、
venue 是否与官方登记一致。

## 1. Workflow / 工作流

**EN**
1. **Locate the reference section** in the extracted full text (first numbered entry `[1] ...`
   or author-year entries; end boundary = next section heading).
2. **Split entries** with `re.split(r'\n\[(\d+)\]\s', ...)`. For every NODOI entry,
   re-check the original text for a line-wrapped DOI (`10.1145/\n3613904...` is common).
   - **Line-wrapped DOIs — always look at the NEXT line**: grep shows only the matched
     line, so the continuation is invisible. Real-world miss: one entry ended with
     `doi:10.1016/j.tics.` and the continuation `2021.02.007` sat on the next line —
     checking only the matched line caused a false "incomplete DOI" verdict.
     Safer: join each entry's internal newlines into spaces (or append the next line)
     before regex-matching DOIs.
   - **An "incomplete-looking" DOI is a wrap signal, not a citation error**: a captured
     DOI ending in `.` or `/` (e.g. `10.1016/j.tics.`, `10.1145/`) should be assumed
     line-wrapped — stitch the original text and verify before judging; only then FAIL.
3. **Verify each entry**:
   - DOI → `https://api.crossref.org/works/{doi}` (User-Agent with a mailto; sleep 0.3–0.5 s
     between calls); retrieve `title / container-title / issued`.
   - `10.48550/arXiv.*` DOIs are DataCite-registered → route to the arXiv API directly;
     a Crossref 404 on a repaired DOI falls back to `https://api.datacite.org/dois/{doi}`.
   - arXiv → `https://export.arxiv.org/api/query?id_list={id}`; parse `<entry><title>`.
   - Line-wrapped DOIs are stitched by `repair_doi` (see step 2); network errors retry
     with backoff — a FAIL that survives retries is worth re-running before judging.
   - Entries without a DOI (book chapters, monographs, web pages) are judged manually — never FAIL.
4. **Title comparison (v2)**: compare the FULL entry (whitespace-collapsed) against the
   official title via best-window partial ratio — slide a window of len(official) over the
   entry, take the max `SequenceMatcher.ratio()`; exact normalized substring = 1.0.
   Bands: **≥ 0.85 OK / 0.60–0.85 REVIEW / < 0.60 MISMATCH**; official-year absent from
   the entry forces at least REVIEW. Do NOT use plain ratio on `entry[:80]`: author names
   dilute it until genuine citations score 0.3–0.6, overlapping fabricated ones (measured).
5. **Report**: one line per entry — `No | DOI | score | claimed title | official title |
   years | venue | OK/REVIEW/MISMATCH/FAIL/ARXIV/NODOI` — plus an overall verdict;
   review all REVIEW/MISMATCH/FAIL lines manually.

**中文**
1. 在提取文本中定位参考文献段（首个编号条目起，下一章节标题止）。
2. 按编号正则切分条目；每个 NO-DOI 条目回原文二次检查跨行 DOI。
   - **跨行 DOI 必须看命中行的下一行**：grep 只显示命中行，续行会漏（实例：某条目命中行
     结尾是 `doi:10.1016/j.tics.`，续行 `2021.02.007` 在下一行；只看命中行会误判"残缺
     DOI"）。更稳妥的方式：切分时把条目内部换行合并为空格（或拼接下一行）后再匹配 DOI。
   - **"DOI 看似残缺"是续行信号而非引用错误**：正则抓到以 `.` 或 `/` 结尾的 DOI
     （如 `10.1016/j.tics.`、`10.1145/`），先假定跨行折断，回原文拼接验证后再下结论。
3. 逐条核验：DOI → Crossref API（带 mailto 的 User-Agent，限速 0.3–0.5 秒）；
   `10.48550/arXiv.*` 是 DataCite 前缀 → 直接送 arXiv API；Crossref 404 且 DOI 已修复 →
   回退 DataCite API（api.datacite.org）；跨行 DOI 由 repair_doi 拼接（见第 2 步）；
   网络错误带退避重试，重试后仍 FAIL 的先重跑再下结论。arXiv → arXiv API；
   无 DOI 条目（书章/专著/网页）人工判断，列出来，不判 FAIL。
4. 标题比对（v2）：**整条条目**（合并空白）vs 官方标题，用最优滑窗 partial ratio
   （归一化后精确子串 = 1.0）。分档：**≥0.85 OK / 0.60–0.85 REVIEW / <0.60 MISMATCH**；
   官方年份在条目中找不到 → 强制至少 REVIEW。
5. 输出逐条报告（编号 | DOI | 分数 | 引文标题 | 官方标题 | 年份 | venue | 状态）+ 总体
   结论；所有 REVIEW/MISMATCH/FAIL 逐条人工复核，核验结论写入交付文档的复核/附录小节。

## 2. Known false positives / 可能的检查失误

- **Official metadata title truncation** — Crossref often stores short versions of ACM/IMWUT
  titles (real cases: Gaver 1999 → "Design: Cultural probes"; Geeng & Roesner → "Who's In
  Control?"; Sasha → "Sasha"). If the DOI resolves to the very paper cited, it is OK.
- Author names in the entry no longer distort v2 best-window scoring, but very short
  official titles (book chapters, "Implicit personalization"-style truncations) can still
  fall below the OK band — that is what REVIEW is for.
- Subtitle casing / hyphenation differences.

中文：官方元数据标题截断（DOI 解析正确即为 OK，v2 下多落入 REVIEW 灰区，人工确认）；极短官方
标题可能够不到 OK 档；副标题大小写与连字符差异。

## 3. Genuine mismatch signals / 引用错误

- DOI resolves 404; official title unrelated to the claim; year/venue mismatch; the same DOI
  reused by multiple entries; a "citation" pointing to a non-existent software release.

中文：DOI 404；官方标题与引文无关；年份/venue 对不上；同一 DOI 被多条引文共用；指向不存在的软件发布页。


## 4. Related skills / 相关技能

- **paper-citation-tracer** — orthogonal: traces a quoted passage INTO the cited paper's PDF
  and highlights the original wording (answers "is it cited correctly?"; requires the cited
  PDF). This skill answers "does the entry exist?" (requires only network access). In a review,
  run this skill first, then switch to the tracer for any suspicious entry.
- **chi-review** — the full CHI review workflow; calls this skill in its reference-verification
  step.

中文：**paper-citation-tracer** 与本技能正交互补——tracer 溯源内容（引文段落 → 被引 PDF 高亮），
本技能核验条目（参考文献列表 → 官方元数据）。审稿先跑本技能，可疑引用再切 tracer。
https://github.com/Imad7777/paper-citation-tracer
