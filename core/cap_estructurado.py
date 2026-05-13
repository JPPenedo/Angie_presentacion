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


def extraer_texto_pdf_solo_fitz(data: bytes) -> Tuple[str, int]:
    """Texto del PDF página por página, solo PyMuPDF."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        lim = min(len(doc), MAX_PDF_PAGES)
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

    grade_num = _norm_num(grade_raw)
    grade_ok = grade_num is not None
    credits_nan = credits_raw.lower() == "nan" or credits_raw == "-"

    completed = bool(grade_ok or has_yes)
    pending = bool(has_no_token and not has_yes and not grade_ok and not term)
    if term and grade_ok:
        completed = True
        pending = False
    if grade_ok:
        completed = True
        pending = False

    return {
        "term": term or "",
        "code": f"{subj} {cnum}",
        "name": title.strip(),
        "credits_raw": credits_raw,
        "grade": "" if grade_raw.lower() == "nan" else grade_raw,
        "source": source or "",
        "completed": completed,
        "pending": pending,
        "credits_nan_row": credits_nan,
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


def _extract_courses_from_detail(sections: Dict[str, str], full_text: str) -> List[Dict[str, Any]]:
    det = sections.get("Detail Requirements", "")
    courses = _extract_courses_from_text(det)
    if not courses and full_text:
        courses = _extract_courses_from_text(full_text)
    return courses


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


def _dedupe_cursos(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for c in courses:
        key = (c.get('code'), c.get('term') or '', c.get('name') or '')
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def parsear_cap_estructurado(texto_completo: str) -> Dict[str, Any]:
    texto_completo = (texto_completo or "").strip()
    sections = _split_sections_smart(texto_completo) if texto_completo else {}

    program_summary = _pick_program_summary(sections, texto_completo)
    areas = _extract_areas(sections, texto_completo)
    courses = _dedupe_cursos(_extract_courses_from_detail(sections, texto_completo))
    student = _student_stub(sections, texto_completo)
    non_course = _non_course_lines(sections)

    completed_courses = [c for c in courses if c.get("completed")]
    pending_courses = [c for c in courses if c.get("pending")]

    nan_completed = [c for c in courses if c.get("credits_nan_row") and c.get("completed")]

    warnings: List[str] = []
    if not program_summary.get("credits_required"):
        warnings.append("No se encontró bloque Total Required global en Program Evaluation.")
    if not courses:
        warnings.append("No se detectaron filas de materias en Detail Requirements (revisar formato del PDF).")

    result: Dict[str, Any] = {
        "student": student,
        "program_summary": program_summary,
        "areas": areas,
        "courses": courses,
        "completed_courses": completed_courses,
        "pending_courses": pending_courses,
        "non_course_requirements": non_course,
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
                "completed_courses": [],
                "pending_courses": [],
                "non_course_requirements": [],
                "warnings": ["PDF sin texto embebido (páginas: %s)." % pags],
            },
            "",
        )
    parsed = parsear_cap_estructurado(texto)
    return parsed, texto
