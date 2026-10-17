#!/usr/bin/env python3
"""check_refs.py v2 — verify scholarly references against Crossref / arXiv.

Usage / 用法:
    python check_refs.py extracted_text.txt [--start "[1] "] [--end "Appendices"]

Input / 输入:
    A text file containing the full text of a manuscript, extracted with PyMuPDF
    (page-wise get_text(), pages joined by a form-feed character). Page-margin
    line numbers may be present; they are ignored.

Output / 输出:
    One line per reference:
        No | DOI | score | claimed title | official title | years | venue | status
    Status is one of OK / REVIEW / MISMATCH / FAIL / ARXIV / NODOI, plus a verdict.

v2 scoring (replaces the old diluted "entry[:80] vs title, ratio > 0.6" rule):
  - Compare the FULL entry (whitespace-collapsed) against the official title using
    best-window partial ratio: slide a window of len(official) over the entry and
    take the max SequenceMatcher ratio. Exact normalized substring -> score 1.0.
  - Rationale: author names dilute plain ratio until genuine citations score
    0.3-0.6 (overlapping with fabricated ones). Best-window alignment separates
    them cleanly: real ~0.86-1.00, fabricated ~0.3-0.4.
  - Three bands: >= --ok-threshold (0.85) OK; >= --review-floor (0.60) REVIEW;
    below MISMATCH. Year mismatch vs Crossref forces at least REVIEW.
  - REVIEW band absorbs official-metadata truncation (Crossref stores short
    versions of ACM/IMWUT titles) — these still need human eyes, as SKILL.md says.

Requires: Python 3.8+ (stdlib only).
"""
import argparse
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "ref-check/2.0 (mailto:you@example.com)"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def best_window_ratio(needle_norm: str, haystack_norm: str) -> float:
    """Best partial alignment of the official title inside the entry text."""
    if not needle_norm:
        return 0.0
    if needle_norm in haystack_norm:
        return 1.0
    if len(needle_norm) >= len(haystack_norm):
        return difflib.SequenceMatcher(None, needle_norm, haystack_norm).ratio()
    best = 0.0
    span = len(needle_norm)
    for i in range(len(haystack_norm) - span + 1):
        r = difflib.SequenceMatcher(None, needle_norm, haystack_norm[i:i + span]).ratio()
        if r > best:
            best = r
            if best > 0.97:
                break
    return best


def repair_doi(entry: str, doi: str, force: bool = False) -> str:
    """Stitch line-wrapped DOIs back together.

    PDF extraction inserts a newline inside long DOIs ("10.1016/j.\\ncopsyc.2023.101736");
    after whitespace collapsing the regex stops at the space, leaving a truncated prefix
    like "10.1016/j." — which then 404s. A captured DOI ending in [-./] is a wrap signal
    (SKILL.md: "DOI 看似残缺"是续行信号), so join the whitespace-stripped continuation.
    force=True additionally joins when the prefix ends in a word character (used as a
    404 fallback, e.g. "10.1093/pnasnexus nfad030").
    """
    if not (force or doi.endswith((".", "/", "-"))):
        return doi
    i = entry.find(doi)
    if i < 0:
        return doi
    tail = re.sub(r"\s+", "", entry[i + len(doi): i + len(doi) + 80])
    cont = re.match(r"[\w./\-()]*", tail)
    joined = doi + (cont.group(0) or "")
    return joined if len(joined) > len(doi) else doi


def datacite(doi: str):
    """DataCite lookup (10.48550/... and other DataCite-registered prefixes)."""
    url = "https://api.datacite.org/dois/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)["data"]["attributes"]
    titles = d.get("titles") or []
    title = titles[0].get("title", "") if titles else ""
    year = d.get("publicationYear")
    cont = d.get("publisher") or ""
    return title, year, cont


def crossref(doi: str, retries: int = 3):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers=UA)
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)["message"]
            break
        except urllib.error.HTTPError:
            raise                                   # 404 etc. is a real answer, don't retry
        except Exception as ex:                     # SSL hiccups / dropped connections
            last = ex
            time.sleep(1.0 + 3.0 * attempt)         # backoff: 1s, 4s
    else:
        raise last
    title = (d.get("title") or [""])[0]
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        if d.get(k) and d[k].get("date-parts"):
            year = d[k]["date-parts"][0][0]
            break
    cont = d.get("container-title") or [""]
    return title, year, cont[0]


def arxiv(arxiv_id: str, retries: int = 2) -> str:
    url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id)
    xml = None
    for attempt in range(retries):
        try:
            xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode()
            break
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.0)
    entry = xml[xml.find("<entry>"):]
    m = re.search(r"<title>(.*?)</title>", entry)
    return m.group(1).strip().replace("\n", " ") if m else ""


def main():
    ap = argparse.ArgumentParser(description="Verify scholarly references against Crossref / arXiv.")
    ap.add_argument("textfile", help="extracted full text of the manuscript (pages joined by \\f)")
    ap.add_argument("--start", default=r"\[\d+\]\s+[A-Z]", help="regex marking the first reference entry")
    ap.add_argument("--end", default=r"^(Appendix|Appendices|A\b)", help="regex marking the end of the reference section")
    ap.add_argument("--ok-threshold", type=float, default=0.85,
                    help="best-window score at/above which an entry is OK (default 0.85)")
    ap.add_argument("--review-floor", type=float, default=0.60,
                    help="best-window score at/above which an entry goes to REVIEW instead of MISMATCH (default 0.60)")
    args = ap.parse_args()

    raw = open(args.textfile, encoding="utf-8").read()
    m = re.search(args.start, raw)
    if not m:
        sys.exit("reference start not found; adjust --start")
    tail = raw[m.start():]
    m2 = re.search(args.end, tail[10:])
    if m2:
        tail = tail[: 10 + m2.start()]

    parts = re.split(r"\n\[(\d+)\]\s", "\n" + tail)
    entries = {}
    for k in range(1, len(parts), 2):
        entries[int(parts[k])] = re.sub(r"\s+", " ", parts[k + 1])

    results = []
    for n in sorted(entries):
        entry = entries[n]
        # full-entry comparison string; keep a short display form
        hay = norm(entry)
        display = entry[:60]
        entry_years = set(re.findall(r"(?:19|20)\d{2}", entry))
        dois = re.findall(r"(10\.\d{4,5}/[\w.\-()]+)", entry)
        arx = re.findall(r"ar[Xx]iv[:\s]*(\d{4}\.\d{4,5})", entry)
        try:
            if dois:
                doi = repair_doi(entry, dois[0])
                m_arxiv_datacite = re.match(r"(?i)10\.48550/arxiv[.:](.+)", doi)
                if m_arxiv_datacite:
                    # DataCite-registered arXiv DOI: route to the arXiv API directly
                    t = arxiv(m_arxiv_datacite.group(1))
                    y, cont = "", ""
                    score = best_window_ratio(norm(t), hay)
                    status = "OK" if score >= args.ok_threshold else ("REVIEW" if score >= args.review_floor else "MISMATCH")
                    results.append((n, doi, round(score, 2), display, t[:60], y, cont[:40], status))
                else:
                    try:
                        t, y, cont = crossref(doi)
                    except urllib.error.HTTPError:
                        # 404 on a truncated prefix: force-join the continuation once
                        doi2 = repair_doi(entry, dois[0], force=True)
                        if doi2 != doi:
                            doi = doi2
                            try:
                                t, y, cont = crossref(doi)
                            except urllib.error.HTTPError:
                                t, y, cont = datacite(doi)   # DataCite-registered?
                        else:
                            t, y, cont = datacite(doi)       # DataCite-registered?
                    score = best_window_ratio(norm(t), hay)
                    if score >= args.ok_threshold:
                        status = "OK"
                    elif score >= args.review_floor:
                        status = "REVIEW"
                    else:
                        status = "MISMATCH"
                    year_note = str(y) if y else ""
                    # year cross-check: official year must appear somewhere in the entry
                    if y and str(y) not in entry_years and status == "OK":
                        status = "REVIEW"
                        year_note += " (!)"
                    results.append((n, doi, round(score, 2), display, t[:60], year_note, cont[:40], status))
            elif arx:
                t = arxiv(arx[0])
                score = best_window_ratio(norm(t), hay)
                status = "OK" if score >= args.ok_threshold else ("REVIEW" if score >= args.review_floor else "MISMATCH")
                results.append((n, "arXiv:" + arx[0], round(score, 2), display, t[:60], "", "", status))
            else:
                results.append((n, "no-doi", "", display, "(book chapter / monograph — verify manually)", "", "", "NODOI"))
        except Exception as ex:
            results.append((n, dois[0] if dois else "arXiv:" + arx[0] if arx else "?", 0,
                            display, "ERROR: " + str(ex)[:50], "", "", "FAIL"))
        time.sleep(0.35)

    for r in results:
        print(" | ".join(str(x) for x in r))

    counts = {}
    for r in results:
        counts[r[-1]] = counts.get(r[-1], 0) + 1
    print("\nverdict: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) +
          f"; {len(results)} total.")
    print("Review all REVIEW/MISMATCH/FAIL lines manually (Crossref metadata truncation\n"
          "lands in REVIEW; a wrong entry year vs official year is flagged '!').")


if __name__ == "__main__":
    main()
