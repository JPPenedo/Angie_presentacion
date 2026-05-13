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
TERM_SUBJECT_COURSE_RE = re.compile(r"\b(20\d{4})\s+([A-Z]{2,6})\s+(\d{4})\b")
GRADE_TOKEN_RE = re.compile(r"\b(AC|\d{1,2}(?:\.\d+)?|NaN)\b", re.IGNORECASE)
COURSE_TAIL_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<credits>(?:\d+(?:\.\d+)?|NaN|0|-))\s+"
    r"(?P<grade>(?:AC|\d+(?:\.\d+)?|NaN))\s*(?P<source>[A-Za-z])?$",
    re.IGNORECASE,
)

SPECIAL_TAG_TOKENS = {"CING", "CLIN", "ABPE", "ABAE", "ABIE", "TBIE", "MTBA"}
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
    "https://",
    "Required",
    "Source",
]
COURSE_NAME_CORRECTIONS = {
    "HUM 1402": "Antropología fundamental",
    "HUM 1403": "Persona y trascendencia",
    "HUM 1405": "Humanismo clásico contemporáneo",
    "LDR 1401": "Liderazgo desarrollo personal",
    "LDR 2401": "Liderazgo equipos alto desempeño",
    "ACT 4401": "Matemáticas actuariales daños",
    "ACT 4402": "Simulación seguros finanzas",
    "FIN 2402": "Est financieros toma decisione",
    "MAT 3411": "Estadística matemática",
    "MAT 3410": "Ecuacione diferencia diferenci",
    "MAT 4403": "Seminario de ciencia de datos",
    "IIND 4412": "Big data para negocios",
    "SIS 1401": "Algoritmos y programación",
    "SIS 1402": "Lenguajes orientados a objetos",
    "SIS 2407": "Programación en la nube",
    "SIS 3403": "Programació dispositiv móviles",
    "ISOC 1408": "Hombre y expresión artística",
    "ESP 0401": "Hab univ para la comunicación",
    "MAT 0402": "Matemáticas básicas ACT",
    "CDA 0401": "Competencias Digitales general",
    "CDA 0402": "Python apli a la Ciencia Datos",
    "ELDR 0402": "Creación public interés perso",
    "ELDR 0411": "Empresa a través método caso",
    "ELDR 0423": "Prin fund análisis casos bioét",
    "TACL 0436": "Expresarte",
    "TDPR 0469": "Fútbol Rápido",
    "TLDR 0413": "Hab pensam toma de decisiones",
}


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
    if t == "AC":
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
    Créditos globales: preferir Total Requirements en Program Evaluation;
    si hay varios, elegir el de mayor credits_required dentro de esa sección.
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
        # Fallback: el bloque con mayor créditos requeridos en todo el documento
        all_blocks = [d for _, d in _all_total_required(full_text)]
        if not all_blocks:
            return default
        best = max(all_blocks, key=lambda d: d.get("credits_required") or 0)
        candidates = [best]

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
                "area": area_name,
                "met": blk["met"],
                "credits_required": blk["credits_required"],
                "credits_used": blk["credits_used"],
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


def _parse_course_candidate_block(block: str) -> Optional[Dict[str, Any]]:
    s = re.sub(r"\s+", " ", (block or "")).strip()
    if not s:
        return None
    if re.match(
        r"^(Area|Total Required|Program|Non Course|Detail|Courses Not|Rejected|Student|Name|ID)\b",
        s,
        re.I,
    ):
        return None

    m = TERM_SUBJECT_COURSE_RE.search(s)
    if not m:
        return None

    term, subj, cnum = m.group(1), m.group(2), m.group(3)
    tail = s[m.end():].strip()
    if not tail:
        return None
    if TERM_SUBJECT_COURSE_RE.search(tail):
        # Evitar bloques que accidentalmente juntan más de una materia.
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

    grade_raw_norm = "" if _is_nan_like(grade_raw) else grade_raw
    grade_ok = _is_valid_grade_token(grade_raw_norm)
    credits_num = _norm_num(credits_raw)
    credits_nan = credits_num is None and _is_nan_like(credits_raw)

    completed = bool(term and grade_ok)
    pending = False
    classification_reason = "term_code_grade" if completed else "course_candidate_not_completed"

    return {
        "area": "",
        "term": term,
        "code": f"{subj} {cnum}",
        "name": title,
        "credits_raw": credits_raw,
        "credits_num": credits_num,
        "grade": grade_raw_norm,
        "source": source,
        "completed": completed,
        "pending": pending,
        "credits_nan_row": credits_nan,
        "classification_reason": classification_reason,
    }


def _build_course_candidate_blocks(full_text: str) -> List[str]:
    lines = [ln.strip() for ln in re.sub(r"\r\n?", "\n", full_text).split("\n") if ln.strip()]
    candidates: List[str] = []
    seen = set()
    for i in range(len(lines)):
        if not TERM_SUBJECT_COURSE_RE.search(lines[i]):
            continue
        block = lines[i]
        if block not in seen:
            seen.add(block)
            candidates.append(block)
        for j in range(i + 1, min(i + 4, len(lines))):
            if TERM_SUBJECT_COURSE_RE.search(lines[j]):
                break
            block = f"{block} {lines[j]}".strip()
            if block in seen:
                continue
            seen.add(block)
            candidates.append(block)
    return candidates


def _extract_courses_from_detail(
    sections: Dict[str, str], full_text: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    det = sections.get("Detail Requirements", "")
    candidates = _build_course_candidate_blocks(full_text)
    parsed: List[Dict[str, Any]] = []
    for cand in candidates:
        p = _parse_course_candidate_block(cand)
        if p:
            parsed.append(p)

    # fallback legacy parser over detail block for rows not captured by multiline matcher
    legacy = _extract_courses_from_text(det) if det else []
    all_courses = parsed + legacy

    debug = {
        "area_blocks_detected": len(re.findall(r"(?mi)^\s*Area Requirements\s*$", full_text)),
        "detail_blocks_detected": len(re.findall(r"(?mi)^\s*Detail Requirements\s*$", full_text)),
        "course_candidate_blocks": len(candidates),
        "course_candidates_with_period_code": len(
            [c for c in candidates if TERM_SUBJECT_COURSE_RE.search(c)]
        ),
        "course_candidates_with_grade": len([c for c in candidates if GRADE_TOKEN_RE.search(c)]),
        "debug_raw_candidates_sample": candidates[:30],
    }
    return all_courses, debug


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


def normalize_cap_courses_final(courses: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    debug_final = {
        "raw_courses": len(courses),
        "after_dedup": 0,
        "duplicates_removed": 0,
        "names_fixed_by_dictionary": 0,
        "names_trimmed_by_noise_rules": 0,
        "nan_credit_completed_courses": 0,
    }
    by_code: Dict[str, List[Dict[str, Any]]] = {}
    for c in courses:
        code = (c.get("code") or "").strip()
        if not code:
            continue
        by_code.setdefault(code, []).append(c)

    normalized: List[Dict[str, Any]] = []

    for code, rows in by_code.items():
        prepared = []
        for r in rows:
            name_clean, tags, trimmed = _clean_course_name(r.get("name", ""))
            grade = (r.get("grade") or "").strip()
            grade_valid = _has_valid_grade(grade)
            term = (r.get("term") or "").strip()
            credits_raw = (r.get("credits_raw") or "").strip()
            credits_num = r.get("credits_num")
            if credits_num is None:
                credits_num = _norm_num(credits_raw)
            is_nan_credit = credits_num is None
            noise_penalty = len(re.findall(r"(Total Credits and GPA|Area Requirements|Detail Requirements|https://|Source)", r.get("name", ""), re.I))
            score = 0
            score += 40 if not tags else 0
            score += 30 if grade_valid else 0
            score += 20 if term else 0
            score += 10 if len(name_clean) >= 8 else 0
            score -= 5 * noise_penalty
            score -= max(0, len((r.get("name") or "").split()) - len(name_clean.split()))
            prepared.append(
                {
                    "row": r,
                    "name_clean": name_clean,
                    "tags": tags,
                    "trimmed": trimmed,
                    "grade_valid": grade_valid,
                    "term": term,
                    "credits_num": credits_num,
                    "credits_raw": credits_raw,
                    "is_nan_credit": is_nan_credit,
                    "score": score,
                }
            )

        best = sorted(
            prepared,
            key=lambda x: (
                x["score"],
                -len(x["tags"]),
                len(x["name_clean"]),
            ),
            reverse=True,
        )[0]
        row = dict(best["row"])
        final_name = best["name_clean"]
        if best["trimmed"]:
            debug_final["names_trimmed_by_noise_rules"] += 1
        if code in COURSE_NAME_CORRECTIONS:
            if final_name != COURSE_NAME_CORRECTIONS[code]:
                debug_final["names_fixed_by_dictionary"] += 1
            final_name = COURSE_NAME_CORRECTIONS[code]

        completed = bool(row.get("completed")) or (
            bool((row.get("term") or "").strip()) and _has_valid_grade(row.get("grade", ""))
        )
        if completed and best["is_nan_credit"]:
            debug_final["nan_credit_completed_courses"] += 1

        normalized.append(
            {
                "area": row.get("area", ""),
                "term": row.get("term", ""),
                "code": code,
                "name": final_name,
                "credits_raw": best["credits_raw"] if best["credits_raw"] else row.get("credits_raw", ""),
                "credits_num": best["credits_num"],
                "grade": row.get("grade", ""),
                "source": row.get("source", ""),
                "completed": completed,
                "pending": bool(row.get("pending")) and not completed,
                "credits_nan_row": best["is_nan_credit"],
                "classification_reason": row.get("classification_reason", ""),
                "tags": best["tags"],
            }
        )

    normalized.sort(key=lambda c: (c.get("code") or "", c.get("term") or ""))
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

    warnings: List[str] = []
    if not program_summary.get("credits_required"):
        warnings.append("No se encontró bloque Total Required global en Program Evaluation.")
    if not courses:
        warnings.append("No se detectaron filas de materias en Detail Requirements (revisar formato del PDF).")

    debug = {
        "global_credits_source": "program_summary",
        "credits_required": int(round(float(program_summary.get("credits_required") or 0))),
        "credits_used": int(round(float(program_summary.get("credits_used") or 0))),
        "courses_detected": len(courses),
        "completed_courses_detected": len(completed_courses),
        "courses_with_nan_credits": len([c for c in courses if c.get("credits_num") is None]),
        "pending_requirements_detected": len(pending_courses),
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
        "areas": areas,
        "courses": courses,
        "courses_normalized": courses_normalized,
        "completed_courses": completed_courses,
        "pending_courses": pending_courses,
        "non_course_requirements": non_course,
        "requirements": {
            "non_course": non_course,
            "pending_courses": pending_courses,
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
                "areas": [],
                "courses": [],
                "courses_normalized": [],
                "completed_courses": [],
                "pending_courses": [],
                "non_course_requirements": [],
                "requirements": {"non_course": [], "pending_courses": []},
                "debug": {
                    "global_credits_source": "program_summary",
                    "credits_required": 0,
                    "credits_used": 0,
                    "courses_detected": 0,
                    "completed_courses_detected": 0,
                    "courses_with_nan_credits": 0,
                    "pending_requirements_detected": 0,
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
                    "names_fixed_by_dictionary": 0,
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
