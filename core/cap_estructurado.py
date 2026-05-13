"""
Parseo estructurado de CAP (plan tipo DegreeWorks) desde texto extraído con PyMuPDF únicamente.

- Sin OCR, sin APIs, sin pdfplumber.
- Materias / filas: regex y heurísticas sobre texto embebido.
- Créditos oficiales: bloques Total Required (programa y por área), no suma fila a fila.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .cap_lectura import MAX_PDF_PAGES

logger = logging.getLogger(__name__)

SECTION_HEADERS = (
    "Program Evaluation",
    "Non Course Requirements",
    "Area Requirements",
    "Detail Requirements",
    "Courses Not Used",
    "Rejected Courses",
)

TOTAL_REQUIRED_RE = re.compile(
    r"Total\s+Required\s*:\s*(Yes|No)\s+(\d+(?:\.\d+)?|NaN)\s+(\d+(?:\.\d+)?|NaN)\s+(\d+)\s*",
    re.IGNORECASE,
)

AREA_HEADER_RE = re.compile(r"Area\s*:\s*([^\n\r]+?)\s*$", re.MULTILINE | re.IGNORECASE)
TERM_SUBJECT_COURSE_RE = re.compile(r"\b(20\d{4})\s+([A-Z]{2,5})\s+(\d{4})\b")
COURSE_START_RE = re.compile(r"^(?:(20\d{4})\s+)?([A-Z]{2,5})\s+(\d{4})\b")
GRADE_TOKEN_RE = re.compile(r"\b(AC|OU|E|\d{1,2}(?:\.\d+)?|NaN)\b", re.IGNORECASE)
COURSE_TAIL_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<credits>(?:\d+(?:\.\d+)?|NaN|0|-))\s+"
    r"(?P<grade>(?:AC|OU|E|\d+(?:\.\d+)?|NaN))\s*(?P<source>[A-Za-z])?$",
    re.IGNORECASE,
)

SPECIAL_TAG_TOKENS = {"CING", "CLIN", "ABPE", "ABAE", "ABIE", "TBIE", "MTBA", "RING"}
NOISE_TOKENS = {
    "CING",
    "CLIN",
    "ABPE",
    "ABAE",
    "ABIE",
    "TBIE",
    "MTBA",
    "H",
    "Required",
    "Courses",
    "Credits",
    "Source",
}
NAME_CUT_MARKERS = [
    "Total Credits and GPA",
    "Area Requirements",
    "Detail Requirements",
    "Total Required",
    "https://",
]


def extraer_texto_pdf_solo_fitz(data: bytes) -> Tuple[str, int]:
    """Texto del PDF página por página, solo PyMuPDF."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        lim = min(len(doc), min(MAX_PDF_PAGES, 8))
        partes: List[str] = []
        for i in range(lim):
            page = doc[i]
            try:
                t = page.get_text(sort=True) or ""
            except TypeError:
                t = page.get_text("text", sort=True) or ""
            if not t.strip():
                t = page.get_text() or ""
            if t.strip():
                partes.append(t)
        return "\n\n".join(partes), lim
    finally:
        doc.close()


def _norm_num(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_nan_like(value: str) -> bool:
    v = (value or "").strip().lower()
    return v in {"", "nan", "none", "null", "-", "n/a"}


def _is_valid_grade_token(token: str) -> bool:
    t = (token or "").strip().upper()
    if not t or t == "NAN":
        return False
    if t in {"AC", "OU", "E"}:
        return True
    return _norm_num(t) is not None


def _parse_total_required_block(m: re.Match[str]) -> Dict[str, Any]:
    met = m.group(1).strip().lower() == "yes"
    req = _norm_num(m.group(2))
    used = _norm_num(m.group(3))
    courses = int(m.group(4))
    return {
        "met": met,
        "credits_required": req if req is not None else 0.0,
        "credits_used": used if used is not None else 0.0,
        "courses_used": courses,
    }


def _split_sections_smart(text: str) -> Dict[str, str]:
    """Intenta cortar por encabezados de sección; si el PDF no los dejó en línea propia, inserta saltos."""
    s = _split_sections(text)
    if len(s) >= 2:
        return s
    t2 = re.sub(r"\r\n?", "\n", text)
    for h in sorted(SECTION_HEADERS, key=len, reverse=True):
        t2 = re.sub(
            rf"(?<![\w/])({re.escape(h)})(?=[\s\n:]|$)",
            r"\n\1\n",
            t2,
            flags=re.IGNORECASE,
        )
    s2 = _split_sections(t2)
    return s2 if len(s2) >= len(s) else s


def _split_sections(text: str) -> Dict[str, str]:
    text = re.sub(r"\r\n?", "\n", text)
    esc = "|".join(re.escape(h) for h in SECTION_HEADERS)
    pat = re.compile(rf"(?mi)^\s*({esc})\s*$", re.MULTILINE)
    matches = list(pat.finditer(text))
    out: Dict[str, str] = {}
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        title_norm = next((h for h in SECTION_HEADERS if h.lower() == title.lower()), title)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[title_norm] = text[start:end].strip()
    return out


def _all_total_required(text: str) -> List[Tuple[int, Dict[str, Any]]]:
    """Lista de (posición, dict) por cada línea Total Required."""
    found: List[Tuple[int, Dict[str, Any]]] = []
    for m in TOTAL_REQUIRED_RE.finditer(text):
        found.append((m.start(), _parse_total_required_block(m)))
    return found


def _pick_program_summary(sections: Dict[str, str], full_text: str) -> Dict[str, Any]:
    """
    Créditos globales: solo desde Program Evaluation.
    Si hay varios, elegir el de mayor credits_required dentro de esa sección.
    """
    pe = sections.get("Program Evaluation", "")
    default: Dict[str, Any] = {
        "credits_required": 0.0,
        "credits_used": 0.0,
        "courses_used": 0,
        "progress_percent": 0.0,
    }

    candidates: List[Dict[str, Any]] = []
    if pe:
        for m in TOTAL_REQUIRED_RE.finditer(pe):
            candidates.append(_parse_total_required_block(m))
    if not candidates:
        return default

    best = max(candidates, key=lambda d: d.get("credits_required") or 0)
    req = float(best["credits_required"])
    used = float(best["credits_used"])
    pct = round((used / req) * 100, 2) if req > 0 else 0.0
    return {
        "credits_required": req,
        "credits_used": used,
        "courses_used": int(best["courses_used"]),
        "progress_percent": pct,
    }


def _extract_areas(sections: Dict[str, str], full_text: str) -> List[Dict[str, Any]]:
    """Áreas desde Area Requirements + Total Required por bloque."""
    ar = sections.get("Area Requirements", "")
    if not ar:
        return []

    areas: List[Dict[str, Any]] = []
    # Posiciones de "Area :" dentro de Area Requirements
    headers = [(m.start(), m.group(1).strip()) for m in AREA_HEADER_RE.finditer(ar)]
    for i, (pos, area_name) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else len(ar)
        chunk = ar[pos:end]
        tm = TOTAL_REQUIRED_RE.search(chunk)
        if not tm:
            continue
        blk = _parse_total_required_block(tm)
        areas.append(
            {
                "name": area_name,
                "area": area_name,
                "met": blk["met"],
                "credits_required": blk["credits_required"],
                "credits_used": blk["credits_used"],
                "courses_required": None,
                "courses_used": blk["courses_used"],
            }
        )
    return areas


def _parse_course_line(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line or len(line) < 8:
        return None
    if re.match(
        r"^(Area|Total Required|Program|Non Course|Detail|Courses Not|Rejected|Student|Name|ID)\b",
        line,
        re.I,
    ):
        return None

    parts = re.split(r"\s+", line)
    if len(parts) < 5:
        return None

    idx = 0
    term: Optional[str] = None
    if len(parts[0]) == 6 and parts[0].isdigit():
        term = parts[0]
        idx = 1

    if idx + 2 >= len(parts):
        return None

    subj, cnum = parts[idx], parts[idx + 1]
    if not re.match(r"^[A-Z]{2,6}$", subj):
        return None
    if not re.match(r"^\d{4}$", cnum):
        return None

    rest = parts[idx + 2 :]
    if len(rest) < 2:
        return None

    tokens_word = set(rest)
    has_yes = "Yes" in tokens_word
    has_no_token = "No" in tokens_word

    source: Optional[str] = None
    if rest and len(rest[-1]) == 1 and rest[-1].isalpha():
        source = rest[-1]
        rest = rest[:-1]
    if len(rest) < 2:
        return None

    grade_raw = rest[-1]
    credits_raw = rest[-2]
    title_tokens = rest[:-2]
    if not title_tokens:
        return None
    title = " ".join(title_tokens)

    grade_raw_norm = "" if _is_nan_like(grade_raw) else grade_raw
    grade_ok = _is_valid_grade_token(grade_raw_norm)
    credits_num = _norm_num(credits_raw)
    credits_nan = credits_num is None and _is_nan_like(credits_raw)

    has_term = bool(term)
    has_code = True  # subj + cnum ya validado arriba

    completed = bool(has_term and has_code and grade_ok)
    pending = False
    classification_reason = "invalid"

    if completed:
        classification_reason = "term+code+grade"
    elif has_yes and (grade_ok or has_term):
        completed = True
        classification_reason = "yes_or_grade_signal"
    elif has_no_token and not has_yes and not has_term and not grade_ok:
        pending = True
        classification_reason = "no_without_term_or_grade"
    elif has_no_token and (has_term or grade_ok):
        completed = True
        pending = False
        classification_reason = "no_but_with_term_code_grade"
    elif grade_ok:
        completed = True
        classification_reason = "grade_present"
    else:
        classification_reason = "unclassified_course_row"

    return {
        "area": "",
        "term": term or "",
        "code": f"{subj} {cnum}",
        "name": title.strip(),
        "credits_raw": credits_raw,
        "credits_num": credits_num,
        "grade": grade_raw_norm,
        "source": source or "",
        "completed": completed,
        "pending": pending,
        "credits_nan_row": credits_nan,
        "classification_reason": classification_reason,
    }


def _extract_courses_from_text(block: str) -> List[Dict[str, Any]]:
    courses: List[Dict[str, Any]] = []
    for raw_line in block.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        p = _parse_course_line(line)
        if p:
            courses.append(p)
    return courses


def _parse_course_candidate_block(block: str, area_name: str = "") -> Optional[Dict[str, Any]]:
    s = re.sub(r"\s+", " ", (block or "")).strip()
    if not s:
        return None
    m = TERM_SUBJECT_COURSE_RE.search(s)
    if not m:
        return None

    term, subj, cnum = m.group(1), m.group(2), m.group(3)
    tail = s[m.end():].strip()
    if not tail:
        return None

    # Corta contaminación por encabezados / links / otras filas
    for marker in NAME_CUT_MARKERS:
        pos = tail.lower().find(marker.lower())
        if pos > 0:
            tail = tail[:pos].strip()
    m2 = TERM_SUBJECT_COURSE_RE.search(tail)
    if m2:
        tail = tail[:m2.start()].strip()
    m3 = COURSE_START_RE.search(tail)
    if m3:
        tail = tail[:m3.start()].strip()
    if not tail:
        return None

    tm = COURSE_TAIL_RE.match(tail)
    if not tm:
        return None

    title = (tm.group("title") or "").strip()
    credits_raw = (tm.group("credits") or "").strip()
    grade_raw = (tm.group("grade") or "").strip()
    source = (tm.group("source") or "").strip()
    if not title:
        return None

    grade_raw_norm = "" if _is_nan_like(grade_raw) else grade_raw.upper()
    grade_ok = _is_valid_grade_token(grade_raw_norm)
    credits_num = _norm_num(credits_raw)
    credits_nan = credits_num is None and _is_nan_like(credits_raw)
    parse_confidence = "high" if grade_ok else "medium"

    return {
        "area": area_name or "",
        "term": term,
        "code": f"{subj} {cnum}",
        "subject": subj,
        "course_number": cnum,
        "name": title,
        "credits_raw": credits_raw,
        "credits_num": credits_num,
        "grade": grade_raw_norm,
        "source": source,
        "completed": bool(term and grade_ok),
        "pending": False,
        "credits_nan_row": credits_nan,
        "classification_reason": "term_code_grade" if grade_ok else "course_candidate_incomplete",
        "tags": [],
        "parse_confidence": parse_confidence,
    }


def _extract_courses_from_detail(
    sections: Dict[str, str], full_text: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    lines = [ln.strip() for ln in re.sub(r"\r\n?", "\n", full_text).split("\n") if ln.strip()]
    courses: List[Dict[str, Any]] = []
    raw_candidates: List[str] = []
    active_section = ""
    active_area = ""

    for i, line in enumerate(lines):
        low = line.lower()
        if low in {h.lower() for h in SECTION_HEADERS}:
            active_section = line
            continue

        am = re.match(r"^Area\s*:\s*(.+)$", line, re.I)
        if am:
            active_area = am.group(1).strip()
            continue

        if not TERM_SUBJECT_COURSE_RE.search(line):
            continue

        block = line
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j]
            nxt_low = nxt.lower()
            if nxt_low in {h.lower() for h in SECTION_HEADERS}:
                break
            if re.match(r"^Area\s*:\s*(.+)$", nxt, re.I):
                break
            if TERM_SUBJECT_COURSE_RE.search(nxt):
                break
            block = f"{block} {nxt}".strip()

        raw_candidates.append(block)
        parsed = _parse_course_candidate_block(block, area_name=active_area)
        if parsed:
            parsed["section"] = active_section
            courses.append(parsed)

    # fallback para casos no capturados en multiline
    det = sections.get("Detail Requirements", "")
    legacy = _extract_courses_from_text(det) if det else []
    for c in legacy:
        c.setdefault("subject", (c.get("code", " ").split(" ", 1)[0] if c.get("code") else ""))
        c.setdefault("course_number", (c.get("code", " ").split(" ", 1)[1] if " " in c.get("code", "") else ""))
        c.setdefault("parse_confidence", "low")
        c.setdefault("tags", [])
        courses.append(c)

    debug = {
        "area_blocks_detected": len(re.findall(r"(?mi)^\s*Area Requirements\s*$", full_text)),
        "detail_blocks_detected": len(re.findall(r"(?mi)^\s*Detail Requirements\s*$", full_text)),
        "course_candidate_blocks": len(raw_candidates),
        "course_candidates_with_period_code": len(
            [c for c in raw_candidates if TERM_SUBJECT_COURSE_RE.search(c)]
        ),
        "course_candidates_with_grade": len([c for c in raw_candidates if GRADE_TOKEN_RE.search(c)]),
        "debug_raw_candidates_sample": raw_candidates[:30],
    }
    return courses, debug


def _student_stub(sections: Dict[str, str], full_text: str) -> Dict[str, Any]:
    """Campos básicos si aparecen en Program Evaluation (best effort)."""
    pe = sections.get("Program Evaluation", full_text[:12000])
    out: Dict[str, Any] = {}
    for label, key in (
        (r"Student\s*ID\s*[:#]?\s*(\S+)", "student_id"),
        (r"Name\s*[:#]?\s*([^\n]+)", "name"),
        (r"Program\s*[:#]?\s*([^\n]+)", "program"),
    ):
        m = re.search(label, pe, re.I)
        if m:
            out[key] = m.group(1).strip()
    return out


def _non_course_lines(sections: Dict[str, str]) -> List[str]:
    nc = sections.get("Non Course Requirements", "")
    if not nc:
        return []
    return [ln.strip() for ln in nc.split("\n") if ln.strip() and len(ln.strip()) > 2]


def _pending_requirement_lines(sections: Dict[str, str], full_text: str) -> List[str]:
    out: List[str] = []
    for key in ("Non Course Requirements", "Area Requirements"):
        block = sections.get(key, "")
        if not block:
            continue
        for raw in block.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if TERM_SUBJECT_COURSE_RE.search(line) and GRADE_TOKEN_RE.search(line):
                continue
            if re.search(r"\bNo\b", line) and not re.search(r"\bNo\s+AND\b", line):
                out.append(line)
    # dedupe stable
    seen = set()
    cleaned = []
    for line in out:
        if line in seen:
            continue
        seen.add(line)
        cleaned.append(line)
    return cleaned


def _clean_course_name(name: str) -> Tuple[str, List[str], bool]:
    original = re.sub(r"\s+", " ", (name or "")).strip()
    cleaned = original
    trimmed = False
    tags: List[str] = []

    for marker in NAME_CUT_MARKERS:
        pos = cleaned.lower().find(marker.lower())
        if pos > 0:
            cleaned = cleaned[:pos].strip()
            trimmed = True

    cut_term = re.search(r"\b20\d{4}\b", cleaned)
    if cut_term and cut_term.start() > 0:
        cleaned = cleaned[:cut_term.start()].strip()
        trimmed = True
    cut_code = re.search(r"\b[A-Z]{2,5}\s+\d{4}\b", cleaned)
    if cut_code and cut_code.start() > 0:
        cleaned = cleaned[:cut_code.start()].strip()
        trimmed = True

    tokens = cleaned.split()
    kept: List[str] = []
    for tok in tokens:
        tok_clean = tok.strip(",.;:")
        if tok_clean.upper() in SPECIAL_TAG_TOKENS:
            tags.append(tok_clean.upper())
            trimmed = True
            continue
        if tok_clean in NOISE_TOKENS:
            trimmed = True
            continue
        kept.append(tok)
    cleaned = " ".join(kept).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or original, sorted(set(tags)), trimmed


def _has_valid_grade(grade: str) -> bool:
    return _is_valid_grade_token((grade or "").strip())


def _is_special_area(area_name: str) -> bool:
    n = (area_name or "").lower()
    return any(k in n for k in ("ingl", "linea", "línea", "online", "special", "especial"))


def _candidate_dedupe_key(course: Dict[str, Any]) -> Tuple[str, str]:
    term = (course.get("term") or "").strip()
    code = (course.get("code") or "").strip()
    if term:
        return term, code
    return "", f"{code}|{(course.get('grade') or '').strip()}"


def normalize_cap_courses_final(courses: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    debug_final = {
        "raw_courses": len(courses),
        "after_dedup": 0,
        "duplicates_removed": 0,
        "names_trimmed_by_noise_rules": 0,
        "nan_credit_completed_courses": 0,
    }
    stage_one: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in courses:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        k = _candidate_dedupe_key(row)
        stage_one.setdefault(k, []).append(row)

    dedup_one: List[Dict[str, Any]] = []
    for _, rows in stage_one.items():
        prepared = []
        for r in rows:
            name_clean, tags, trimmed = _clean_course_name(r.get("name", ""))
            grade = (r.get("grade") or "").strip().upper()
            grade_valid = _has_valid_grade(grade)
            term = (r.get("term") or "").strip()
            credits_raw = (r.get("credits_raw") or "").strip()
            credits_num = r.get("credits_num")
            if credits_num is None:
                credits_num = _norm_num(credits_raw)
            is_nan_credit = credits_num is None
            noise_hits = len(re.findall(r"(Total Credits and GPA|Total Required|Area Requirements|Detail Requirements|https://)", r.get("name", ""), re.I))
            score = 0
            score += 35 if grade_valid else 0
            score += 25 if term else 0
            score += 20 if not _is_special_area(r.get("area", "")) else 0
            score += 8 if (r.get("area") or "").strip() else 0
            score += 10 if len(name_clean) >= 8 else 0
            score -= 8 * noise_hits
            score -= len(tags)
            prepared.append(
                {
                    "row": r,
                    "name_clean": name_clean,
                    "tags": tags,
                    "trimmed": trimmed,
                    "grade_valid": grade_valid,
                    "credits_raw": credits_raw,
                    "credits_num": credits_num,
                    "is_nan_credit": is_nan_credit,
                    "score": score,
                    "noise_hits": noise_hits,
                }
            )
        best = sorted(prepared, key=lambda x: (x["score"], len(x["name_clean"])), reverse=True)[0]
        row = dict(best["row"])
        row["name"] = best["name_clean"]
        row["tags"] = sorted(set((row.get("tags") or []) + best["tags"]))
        row["credits_raw"] = best["credits_raw"]
        row["credits_num"] = best["credits_num"]
        row["credits_nan_row"] = best["is_nan_credit"]
        if best["trimmed"] or best["noise_hits"] > 0:
            debug_final["names_trimmed_by_noise_rules"] += 1
        dedup_one.append(row)

    # Segunda dedupe: code + grade para colapsar cruces área principal/especial
    stage_two: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in dedup_one:
        key = ((r.get("code") or "").strip(), (r.get("grade") or "").strip().upper())
        stage_two.setdefault(key, []).append(r)

    normalized: List[Dict[str, Any]] = []
    for _, rows in stage_two.items():
        best = sorted(
            rows,
            key=lambda r: (
                1 if _has_valid_grade(r.get("grade", "")) else 0,
                1 if (r.get("term") or "").strip() else 0,
                1 if not _is_special_area(r.get("area", "")) else 0,
                1 if (r.get("area") or "").strip() else 0,
                len((r.get("name") or "").strip()),
            ),
            reverse=True,
        )[0]
        tags_agg = set(best.get("tags") or [])
        for r in rows:
            tags_agg.update(r.get("tags") or [])
        code = (best.get("code") or "").strip()
        subject = (best.get("subject") or code.split(" ", 1)[0]).strip()
        cnum = (best.get("course_number") or (code.split(" ", 1)[1] if " " in code else "")).strip()
        grade = (best.get("grade") or "").strip().upper()
        completed = bool((best.get("term") or "").strip() and _has_valid_grade(grade))
        credits_num = best.get("credits_num")
        if credits_num is None:
            credits_num = _norm_num(best.get("credits_raw", ""))
        is_nan_credit = credits_num is None
        if completed and is_nan_credit:
            debug_final["nan_credit_completed_courses"] += 1

        confidence = "high"
        if not completed:
            confidence = "medium"
        if not (best.get("name") or "").strip():
            confidence = "low"

        normalized.append(
            {
                "area": best.get("area", ""),
                "term": best.get("term", ""),
                "code": code,
                "subject": subject,
                "course_number": cnum,
                "name": best.get("name", ""),
                "credits_raw": best.get("credits_raw", ""),
                "credits_num": credits_num,
                "grade": grade,
                "source": best.get("source", ""),
                "completed": completed,
                "pending": bool(best.get("pending")) and not completed,
                "credits_nan_row": is_nan_credit,
                "classification_reason": best.get("classification_reason", ""),
                "tags": sorted(tags_agg),
                "parse_confidence": confidence,
            }
        )

    normalized.sort(key=lambda c: ((c.get("term") or ""), (c.get("code") or "")))
    debug_final["after_dedup"] = len(normalized)
    debug_final["duplicates_removed"] = max(0, debug_final["raw_courses"] - debug_final["after_dedup"])
    return normalized, debug_final


def parsear_cap_estructurado(texto_completo: str, pages_read: int = 0) -> Dict[str, Any]:
    texto_completo = (texto_completo or "").strip()
    sections = _split_sections_smart(texto_completo) if texto_completo else {}

    program_summary = _pick_program_summary(sections, texto_completo)
    areas = _extract_areas(sections, texto_completo)
    courses_pre, extraction_debug = _extract_courses_from_detail(sections, texto_completo)
    courses, debug_normalization_final = normalize_cap_courses_final(courses_pre)
    student = _student_stub(sections, texto_completo)
    non_course = _non_course_lines(sections)
    pending_requirements = _pending_requirement_lines(sections, texto_completo)

    completed_courses = [c for c in courses if c.get("completed")]
    pending_courses = [c for c in courses if c.get("pending")]
    courses_normalized = [
        {
            "area": c.get("area", ""),
            "term": c.get("term", ""),
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "credits_raw": c.get("credits_raw", ""),
            "credits_num": c.get("credits_num"),
            "grade": c.get("grade", ""),
            "completed": bool(c.get("completed")),
            "classification_reason": c.get("classification_reason", ""),
            "pending": bool(c.get("pending")),
            "credits_nan_row": bool(c.get("credits_nan_row")),
            "source": c.get("source", ""),
        }
        for c in courses
    ]

    nan_completed = [c for c in courses if c.get("credits_nan_row") and c.get("completed")]
    numeric_credits_sum_detected = round(
        sum(float(c.get("credits_num")) for c in completed_courses if c.get("credits_num") is not None),
        2,
    )
    nan_credit_courses = 0
    zero_credit_courses = 0
    missing_credit_courses = 0
    for c in courses:
        credits_raw = (c.get("credits_raw") or "").strip()
        credits_num = c.get("credits_num")
        if credits_num is None:
            if credits_raw.lower() == "nan":
                nan_credit_courses += 1
            else:
                missing_credit_courses += 1
        elif float(credits_num) == 0.0:
            zero_credit_courses += 1

    warnings: List[str] = []
    if not program_summary.get("credits_required"):
        warnings.append("No se encontró bloque Total Required global en Program Evaluation.")
    if not courses:
        warnings.append("No se detectaron filas de materias en Detail Requirements (revisar formato del PDF).")

    official_summary = {
        "credits_required_reported": float(program_summary.get("credits_required") or 0.0),
        "credits_used_reported": float(program_summary.get("credits_used") or 0.0),
        "courses_used_reported": int(program_summary.get("courses_used") or 0),
    }
    parser_extraction_summary = {
        "courses_detected": len(courses),
        "completed_courses_detected": len(completed_courses),
        "numeric_credits_sum_detected": numeric_credits_sum_detected,
        "nan_credit_courses": nan_credit_courses,
        "zero_credit_courses": zero_credit_courses,
        "missing_credit_courses": missing_credit_courses,
    }

    debug = {
        "total_courses_raw": len(courses_pre),
        "total_courses_normalized": len(courses),
        "duplicates_removed": int(debug_normalization_final.get("duplicates_removed", 0)),
        "courses_with_nan_credits": nan_credit_courses,
        "courses_with_noise_trimmed": int(
            debug_normalization_final.get("names_trimmed_by_noise_rules", 0)
        ),
        "area_totals_detected": len(areas),
        "global_summary_detected": bool(program_summary.get("credits_required")),
    }
    debug_extraction = {
        "pages_read": int(pages_read),
        "area_blocks_detected": int(extraction_debug.get("area_blocks_detected", 0)),
        "detail_blocks_detected": int(extraction_debug.get("detail_blocks_detected", 0)),
        "course_candidate_blocks": int(extraction_debug.get("course_candidate_blocks", 0)),
        "course_candidates_with_period_code": int(
            extraction_debug.get("course_candidates_with_period_code", 0)
        ),
        "course_candidates_with_grade": int(extraction_debug.get("course_candidates_with_grade", 0)),
        "courses_raw": len(courses_pre),
        "courses_normalized": len(courses),
    }

    result: Dict[str, Any] = {
        "student": student,
        "program_summary": program_summary,
        "official_summary": official_summary,
        "parser_extraction_summary": parser_extraction_summary,
        "areas": areas,
        "courses": courses,
        "courses_normalized": courses_normalized,
        "completed_courses": completed_courses,
        "pending_courses": pending_courses,
        "pending_requirements": pending_requirements,
        "non_course_requirements": non_course,
        "requirements": {
            "non_course": non_course,
            "pending_courses": pending_courses,
            "pending_requirements": pending_requirements,
        },
        "debug": debug,
        "debug_extraction": debug_extraction,
        "debug_normalization_final": debug_normalization_final,
        "debug_raw_candidates_sample": extraction_debug.get("debug_raw_candidates_sample", []),
        "warnings": warnings,
    }

    logger.info(
        "CAP estructurado: cursos=%s áreas=%s global_req=%s global_used=%s cursos_usados_global=%s "
        "nan_cursadas=%s",
        len(courses),
        len(areas),
        program_summary.get("credits_required"),
        program_summary.get("credits_used"),
        program_summary.get("courses_used"),
        len(nan_completed),
    )
    for i, a in enumerate(areas):
        logger.info(
            "CAP área[%s]: %s req=%s used=%s courses=%s met=%s",
            i,
            (a.get("area") or "")[:80],
            a.get("credits_required"),
            a.get("credits_used"),
            a.get("courses_used"),
            a.get("met"),
        )
    if nan_completed:
        logger.info("CAP materias cursadas con créditos NaN en fila: %s", len(nan_completed))

    return result


def procesar_pdf_cap_estructurado(data: bytes) -> Tuple[Dict[str, Any], str]:
    """
    Extrae con fitz y parsea. Devuelve (dict resultado, texto_plano para depuración).
    """
    texto, pags = extraer_texto_pdf_solo_fitz(data)
    if not texto.strip():
        return (
            {
                "student": {},
                "program_summary": {
                    "credits_required": 0,
                    "credits_used": 0,
                    "courses_used": 0,
                    "progress_percent": 0,
                },
                "official_summary": {
                    "credits_required_reported": 0,
                    "credits_used_reported": 0,
                    "courses_used_reported": 0,
                },
                "parser_extraction_summary": {
                    "courses_detected": 0,
                    "completed_courses_detected": 0,
                    "numeric_credits_sum_detected": 0,
                    "nan_credit_courses": 0,
                    "zero_credit_courses": 0,
                    "missing_credit_courses": 0,
                },
                "areas": [],
                "courses": [],
                "courses_normalized": [],
                "completed_courses": [],
                "pending_courses": [],
                "pending_requirements": [],
                "non_course_requirements": [],
                "requirements": {
                    "non_course": [],
                    "pending_courses": [],
                    "pending_requirements": [],
                },
                "debug": {
                    "total_courses_raw": 0,
                    "total_courses_normalized": 0,
                    "duplicates_removed": 0,
                    "courses_with_nan_credits": 0,
                    "courses_with_noise_trimmed": 0,
                    "area_totals_detected": 0,
                    "global_summary_detected": False,
                },
                "debug_extraction": {
                    "pages_read": int(pags),
                    "area_blocks_detected": 0,
                    "detail_blocks_detected": 0,
                    "course_candidate_blocks": 0,
                    "course_candidates_with_period_code": 0,
                    "course_candidates_with_grade": 0,
                    "courses_raw": 0,
                    "courses_normalized": 0,
                },
                "debug_normalization_final": {
                    "raw_courses": 0,
                    "after_dedup": 0,
                    "duplicates_removed": 0,
                    "names_trimmed_by_noise_rules": 0,
                    "nan_credit_completed_courses": 0,
                },
                "debug_raw_candidates_sample": [],
                "warnings": ["PDF sin texto embebido (páginas: %s)." % pags],
            },
            "",
        )
    parsed = parsear_cap_estructurado(texto, pages_read=pags)
    return parsed, texto
