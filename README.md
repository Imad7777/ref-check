# ref-check

> 学术论文参考文献真实性核验技能 / A reference-verification skill for scholarly manuscripts

## 中文

`ref-check` 是一个 Agent Skill（兼容 Codex / WorkBuddy / Claude 类技能目录），用于核验学术论文参考文献的真实性：

- 从论文全文提取文本中解析参考文献条目（编号样式 / 作者-年份样式）；
- 逐条将 DOI 送 **Crossref API**、arXiv ID 送 **arXiv API**，取回官方登记的标题、年份、venue；
- 与引文标题做模糊比对，输出 **OK / MISMATCH / FAIL / ARXIV / NODOI** 分类报告；
- 用于审稿场景检测伪造引用、或写作场景自查参考文献。


### 使用

1. 用 PyMuPDF 提取论文全文（逐页 `get_text()`，页间用 `\f` 连接）存为文本文件；
2. 运行 `python scripts/check_refs.py extracted_text.txt`（可用 `--start/--end` 指定参考文献段边界）；
3. 对 MISMATCH 条目人工复核（见 SKILL.md 中的已知假阳性清单）。

详细工作流、已知陷阱与审稿联动说明见 [`SKILL.md`](SKILL.md)（中英双语）。

---

## English

`ref-check` is an agent skill (compatible with Codex / WorkBuddy / Claude-style skill directories) that verifies the authenticity of scholarly references:

- Parses reference entries from the extracted full text of a manuscript (numbered or author-year styles);
- Verifies each DOI against the **Crossref API** and each arXiv ID against the **arXiv API**, retrieving the officially registered title, year, and venue;
- Fuzzy-compares claimed vs. official titles and produces an **OK / MISMATCH / FAIL / ARXIV / NODOI** report;
- Intended for peer review and for self-checking your own reference lists.


### Usage

1. Extract the manuscript's full text with PyMuPDF (page-wise `get_text()`, pages joined by `\f`) into a text file;
2. Run `python scripts/check_refs.py extracted_text.txt` (use `--start/--end` to mark the reference-section boundaries);
3. Manually review any MISMATCH entries (see the known-false-positive list in [`SKILL.md`](SKILL.md), bilingual).

## Related skills / 相关技能

- **paper-citation-tracer** — 横向内容溯源：给定引文段落与被引文献 PDF，高亮定位原文出处（回答“引得对不对”）。与本技能正交互补：本技能回答“存不存在”。https://github.com/Imad7777/paper-citation-tracer
- **chi-review** — CHI 审稿全流程主技能，在引用核验环节调用本技能。 https://github.com/Imad7777/CHI-Review

## License

MIT
