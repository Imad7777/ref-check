#!/usr/bin/env python3
"""check_refs.py — verify scholarly references against Crossref / arXiv.

Usage / 用法:
    python check_refs.py extracted_text.txt [--start "[1] "] [--end "Appendices"]

Input / 输入:
    A text file containing the full text of a manuscript, extracted with PyMuPDF
    (page-wise get_text(), pages joined by a form-feed character). Page-margin
    line numbers may be present; they are ignored.

Output / 输出:
    One line per reference:
        No | DOI | claimed title | official title | year | venue | score | status
    Status is one of OK / MISMATCH / FAIL / ARXIV / NODOI, plus an overall verdict.

Requires: Python 3.8+ (stdlib only).
"""
import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "ref-check/1.0 (mailto:you@example.com)"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def crossref(doi: str):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)["message"]
    title = (d.get("title") or [""])[0]
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        if d.get(k) and d[k].get("date-parts"):
            year = d[k]["date-parts"][0][0]
            break
    cont = d.get("container-title") or [""]
    return title, year, cont[0]


def arxiv(arxiv_id: str) -> str:
    url = "http://export.arxiv.org/api/query?id_list=" + arxiv_id
    xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode()
    entry = xml[xml.find("<entry>"):]
    m = re.search(r"<title>(.*?)</title>", entry)
    return m.group(1).strip().replace("\n", " ") if m else ""


def main():
    ap = argparse.ArgumentParser(description="Verify scholarly references against Crossref / arXiv.")
    ap.add_argument("textfile", help="extracted full text of the manuscript (pages joined by \\f)")
    ap.add_argument("--start", default=r"\[\d+\]\s+[A-Z]", help="regex marking the first reference entry")
    ap.add_argument("--end", default=r"^(Appendix|Appendices|A\b)", help="regex marking the end of the reference section")
    ap.add_argument("--threshold", type=float, default=0.6, help="title similarity threshold (default 0.6)")
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
        claimed = entry[:80]
        dois = re.findall(r"(10\.\d{4,5}/[\w.\-()]+)", entry)
        arx = re.findall(r"ar[Xx]iv[:\s]*(\d{4}\.\d{4,5})", entry)
        try:
            if dois:
                t, y, cont = crossref(dois[0])
                sim = difflib.SequenceMatcher(None, norm(claimed), norm(t)).ratio()
                status = "OK" if sim > args.threshold else "MISMATCH"
                results.append((n, dois[0], claimed[:60], t[:60], y, cont[:40], round(sim, 2), status))
            elif arx:
                t = arxiv(arx[0])
                sim = difflib.SequenceMatcher(None, norm(claimed), norm(t)).ratio()
                status = "OK" if sim > args.threshold else "MISMATCH"
                results.append((n, "arXiv:" + arx[0], claimed[:60], t[:60], "", "", round(sim, 2), status))
            else:
                results.append((n, "no-doi", claimed[:60], "(book chapter / monograph — verify manually)", "", "", "", "NODOI"))
        except Exception as ex:
            results.append((n, dois[0] if dois else "arXiv:" + arx[0] if arx else "?", claimed[:60], "ERROR: " + str(ex)[:50], "", "", 0, "FAIL"))
        time.sleep(0.4)

    for r in results:
        print(" | ".join(str(x) for x in r))
    n_ok = sum(1 for r in results if r[-1] in ("OK", "ARXIV", "NODOI"))
    print(f"\nverdict: {n_ok}/{len(results)} verified; review all MISMATCH/FAIL lines manually "
          "(metadata truncation can cause false positives — see SKILL.md).")


if __name__ == "__main__":
    main()
