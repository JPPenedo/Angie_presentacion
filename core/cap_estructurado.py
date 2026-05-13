"""
Parseo estructurado de CAP (DegreeWorks) leyendo el documento como una
estructura JERÁRQUICA por bloques, NO como una tabla plana.

Reglas clave:

1. ``Program Evaluation / Total Required`` es la única fuente de verdad para
   los totales globales (créditos requeridos, usados, cursos usados, avance).
2. Cada línea ``Area :`` abre un bloque de área; ese bloque termina al
   encontrar el siguiente anclaje top-level (``Area :``, ``Non Course
   Requirements``, ``Courses Not Used``, ``Rejected Courses`` o EOF).
3. Los totales por área se toman exclusivamente del ``Total Required`` que
   aparece DENTRO de cada bloque de área (no se suman créditos fila a fila).
4. Las materias cursadas se anclan en ``TERM SUBJECT COURSE`` (term de 6
   dígitos tipo ``20XXXX``); las pendientes se anclan en
   ``No [AND|OR] SUBJECT COURSE`` (sin term, sin grade, sin source).
5. Los nombres de áreas y materias se limpian quitando tokens de control
   (``Yes``, ``No``, ``AND``, ``OR``, ``Required``, ``Used``, ``Credits``,
   ``Courses``, ``Attribute``, ``Source``, ``Condition``, ``Rule``,
   ``Subject``, ``Met``, ``Total Required``…) y deduplicando palabras o
   frases consecutivas repetidas.
6. ``Non Course Requirements``, ``Courses Not Used`` y ``Rejected Courses``
   se parsean en pasos separados y nunca se mezclan con materias activas.

El output mantiene las claves existentes (``program_summary``,
``official_summary``, ``parser_extraction_summary``, ``areas``, ``courses``,
``courses_normalized``, ``completed_courses``, ``pending_courses``,
``non_course_requirements``, ``pending_requirements``, ``warnings``) y agrega
nuevas: ``rejected_courses``, ``courses_not_used``, ``non_course_pending``.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .cap_lectura import MAX_PDF_PAGES

logger = logging.getLogger(__name__)


# ============================================================================
# Constantes / regex compartidos
# ============================================================================

SECTION_HEADERS = (
    "Program Evaluation",
    "Area Requirements",
    "Detail Requirements",
    "Non Course Requirements",
    "Courses Not Used",
    "Rejected Courses",
)

# Anclas que cierran un bloque de área (cuando vienen DESPUÉS del 'Area :' actual).
AREA_BLOCK_END_KINDS = {
    "Area :",
    "Non Course Requirements",
    "Courses Not Used",
    "Rejected Courses",
}

# Tokens de control que nunca son parte del nombre legible de un área o materia.
# Comparación case-insensitive (almacenados en minúsculas).
CONTROL_TOKENS_LOWER = {
    "yes",
    "no",
    "and",
    "or",
    "required",
    "used",
    "credits",
    "courses",
    "attribute",
    "source",
    "condition",
    "rule",
    "subject",
    "met",
    "total",
}

# Frases compuestas que se borran antes de tokenizar (longest-match primero).
CONTROL_PHRASES = (
    r"\bTotal\s+Required\b",
    r"\)\s*OR\s*\(",
    r"\(\s*OR\s*\)",
    r"\bRequired\s+Used\s+Required\s+Used\b",
    r"\bRequired\s+Used\s+Credits\s+Courses\b",
)

# Atributos de plan que aparecen pegados al nombre y deben extraerse como tags,
# no como parte del título de la materia.
ATTRIBUTE_TAG_TOKENS = {
    "CING", "CLIN", "ABPE", "ABAE", "ABIE", "TBIE", "MTBA", "RING",
}

# Etiquetas estándar del bloque Non Course Requirements (alias en español).
NON_COURSE_LABELS = (
    "Prog. Competencias Digitales",
    "Programa de Competencias Digitales",
    "Competencias Digitales",
    "Prácticas profesionales",
    "Practicas profesionales",
    "Servicio Social",
    "Servicio social",
    "Inglés",
    "Ingles",
    "English",
)

# Bloque Total Required: met (Yes/No), credits_required, credits_used, courses_used.
TOTAL_REQUIRED_RE = re.compile(
    r"Total\s+Required\s*:?\s*(?P<met>Yes|No)\s+"
    r"(?P<req>\d+(?:\.\d+)?|NaN)\s+"
    r"(?P<used>\d+(?:\.\d+)?|NaN)\s+"
    r"(?P<courses>\d+)",
    re.IGNORECASE,
)

# Anclas de cursos.
TERM_RE = re.compile(r"\b(20\d{4})\b")
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s+(\d{4})\b")
TERM_CODE_RE = re.compile(r"\b(20\d{4})\s+([A-Z]{2,5})\s+(\d{4})\b")

# Credits + grade [+ source] en la cola de una fila de materia cursada.
CREDIT_GRADE_RE = re.compile(
    r"(?P<credits>NaN|\d+(?:\.\d+)?|-)\s+"
    r"(?P<grade>AC|OU|E|\d{1,2}(?:\.\d+)?|NaN)"
    r"(?:\s+(?P<source>H|E|OU|U))?",
    re.IGNORECASE,
)

# Ancla de "Area :".
AREA_ANCHOR_RE = re.compile(r"\bArea\s*:\s*", re.IGNORECASE)

# Ancla de pendiente: "No [AND|OR] SUBJECT COURSE".
PENDING_ANCHOR_RE = re.compile(
    r"\bNo\s+(?:AND\s+|OR\s+|\)\s*OR\s*\(\s*|\(\s*OR\s*\)\s*)?"
    r"(?:(?P<term>20\d{4})\s+)?"
    r"(?P<subj>[A-Z]{2,5})\s+(?P<cnum>\d{4})\b"
)

# Stops para acotar la ventana derecha de cada materia.
WINDOW_STOP_RE = re.compile(
    r"(Total\s+Required|Area\s*:|Area\s+Requirements|Detail\s+Requirements"
    r"|Non\s+Course\s+Requirements|Courses\s+Not\s+Used|Rejected\s+Courses"
    r"|https?://)",
    re.IGNORECASE,
)

# Stops específicos para acotar el nombre del área.
AREA_NAME_STOP_RE = re.compile(
    r"(\bArea\s+Requirements\b|\bDetail\s+Requirements\b|\bTotal\s+Required\b"
    r"|\bRequired\s+Used\s+Required\s+Used\b"
    r"|\bArea\s*:|\bNon\s+Course\s+Requirements\b)",
    re.IGNORECASE,
)


# ============================================================================
# Utilidades de texto
# ============================================================================


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _norm_num(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_nan_like(value: str) -> bool:
    return (value or "").strip().lower() in {"", "nan", "none", "null", "-", "n/a"}


def _is_valid_grade_token(token: str) -> bool:
    t = (token or "").strip().upper()
    if not t or t == "NAN":
        return False
    if t in {"AC", "OU", "E"}:
        return True
    return _norm_num(t) is not None


def _strip_control_tokens(text: str) -> str:
    """Quita frases (``Total Required``, ``)OR(``) y tokens de control sueltos."""
    if not text:
        return ""
    cleaned = text
    for phrase in CONTROL_PHRASES:
        cleaned = re.sub(phrase, " ", cleaned, flags=re.IGNORECASE)
    out: List[str] = []
    for tok in re.split(r"(\W+)", cleaned):
        if not tok:
            continue
        norm = tok.strip().lower().strip(".,;:")
        if norm and norm in CONTROL_TOKENS_LOWER:
            continue
        out.append(tok)
    return _flatten("".join(out))


def _strip_attribute_tags(text: str) -> Tuple[str, List[str]]:
    """Recorta etiquetas de atributo (CING/CLIN/…) al final del nombre."""
    tokens = (text or "").split()
    tags: List[str] = []
    while tokens:
        last = tokens[-1].strip(",.;:").upper()
        if last in ATTRIBUTE_TAG_TOKENS:
            tags.append(last)
            tokens.pop()
            continue
        if last in {"H", "E", "OU", "U"} and len(tokens) > 1:
            tokens.pop()
            continue
        break
    return " ".join(tokens), sorted(set(tags))


def _dedupe_consecutive_words(text: str) -> str:
    res: List[str] = []
    for w in (text or "").split():
        if res and res[-1].lower() == w.lower():
            continue
        res.append(w)
    return " ".join(res)


def _dedupe_repeated_block(text: str) -> str:
    """``X X`` (misma sub-secuencia repetida) → ``X``. Iterativo hasta estabilizar."""
    words = (text or "").split()
    changed = True
    while changed:
        changed = False
        n = len(words)
        if n < 2:
            break
        for size in range(min(n // 2, 10), 0, -1):
            if [w.lower() for w in words[:size]] == [w.lower() for w in words[size:2 * size]]:
                words = words[:size] + words[2 * size:]
                changed = True
                break
    return " ".join(words)


def _clean_name(text: str) -> Tuple[str, List[str]]:
    """Limpieza estándar de nombres (área o materia). Devuelve (nombre, tags)."""
    if not text:
        return "", []
    cleaned = _strip_control_tokens(text)
    cleaned, tags = _strip_attribute_tags(cleaned)
    cleaned = _dedupe_consecutive_words(cleaned)
    cleaned = _dedupe_repeated_block(cleaned)
    cleaned = cleaned.strip(" -:;.,/\\|")
    return cleaned, tags


# ============================================================================
# Lectura del PDF
# ============================================================================


def extraer_texto_pdf_solo_fitz(data: bytes) -> Tuple[str, int]:
    """Texto del PDF página por página, solo PyMuPDF."""
    import fitz  # type: ignore

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


# ============================================================================
# Detección de anclas top-level
# ============================================================================


def _find_anchor_positions(flat: str) -> List[Tuple[int, str]]:
    """Lista ordenada de (offset, kind) para anclas top-level del CAP."""
    spots: List[Tuple[int, str]] = []
    pat = re.compile(
        r"(?P<head>" + "|".join(re.escape(s) for s in SECTION_HEADERS) + r")",
        re.IGNORECASE,
    )
    for m in pat.finditer(flat):
        title = next((s for s in SECTION_HEADERS if s.lower() == m.group("head").lower()), m.group("head"))
        spots.append((m.start(), title))
    for m in AREA_ANCHOR_RE.finditer(flat):
        spots.append((m.start(), "Area :"))
    spots.sort(key=lambda x: x[0])
    return spots


def _section_span(
    anchors: List[Tuple[int, str]],
    flat: str,
    section_name: str,
) -> Optional[Tuple[int, int]]:
    """Devuelve (start, end) del cuerpo de la sección indicada, o None."""
    for idx, (pos, kind) in enumerate(anchors):
        if kind != section_name:
            continue
        start = pos + len(section_name)
        end = len(flat)
        for nxt_pos, nxt_kind in anchors[idx + 1:]:
            if nxt_kind == section_name:
                continue
            end = nxt_pos
            break
        return start, end
    return None


# ============================================================================
# Resumen global (fuente de verdad)
# ============================================================================


def _extract_program_summary(flat: str, anchors: List[Tuple[int, str]]) -> Dict[str, Any]:
    """Resumen global: solo desde el bloque ``Program Evaluation``."""
    default: Dict[str, Any] = {
        "credits_required": 0.0,
        "credits_used": 0.0,
        "courses_used": 0,
        "progress_percent": 0.0,
    }
    span = _section_span(anchors, flat, "Program Evaluation")
    if not span:
        return default
    body = flat[span[0]:span[1]]
    candidates: List[Dict[str, Any]] = []
    for m in TOTAL_REQUIRED_RE.finditer(body):
        candidates.append(
            {
                "met": m.group("met").lower() == "yes",
                "credits_required": _norm_num(m.group("req")) or 0.0,
                "credits_used": _norm_num(m.group("used")) or 0.0,
                "courses_used": int(m.group("courses")),
            }
        )
    if not candidates:
        return default
    best = max(candidates, key=lambda d: d["credits_required"])
    req = float(best["credits_required"])
    used = float(best["credits_used"])
    pct = round((used / req) * 100, 2) if req > 0 else 0.0
    return {
        "credits_required": req,
        "credits_used": used,
        "courses_used": int(best["courses_used"]),
        "progress_percent": pct,
    }


# ============================================================================
# Bloques de área
# ============================================================================


def _extract_area_blocks(flat: str, anchors: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
    """Cada ``Area :`` abre un bloque que termina en el siguiente anclaje top-level."""
    blocks: List[Dict[str, Any]] = []

    for idx, (start, kind) in enumerate(anchors):
        if kind != "Area :":
            continue
        end = len(flat)
        for nxt_pos, nxt_kind in anchors[idx + 1:]:
            if nxt_kind in AREA_BLOCK_END_KINDS:
                end = nxt_pos
                break

        body = flat[start:end]
        # body comienza con "Area : ..."
        after_anchor = body[len("Area :"):].lstrip() if body.lower().startswith("area :") else body

        # Nombre del área: hasta el primer stop válido.
        stop = AREA_NAME_STOP_RE.search(after_anchor)
        raw_name = after_anchor[:stop.start()] if stop else after_anchor[:180]
        name, _name_tags = _clean_name(raw_name)

        # Total Required del área (sólo el de DENTRO del bloque).
        tr = TOTAL_REQUIRED_RE.search(body)
        if tr:
            met = tr.group("met").lower() == "yes"
            req = _norm_num(tr.group("req")) or 0.0
            used = _norm_num(tr.group("used")) or 0.0
            courses_used = int(tr.group("courses"))
        else:
            met = False
            req = 0.0
            used = 0.0
            courses_used = 0

        blocks.append(
            {
                "name": name,
                "raw_name": raw_name,
                "start": start,
                "end": end,
                "body": body,
                "met": met,
                "credits_required": req,
                "credits_used": used,
                "courses_used": courses_used,
            }
        )
    return blocks


# ============================================================================
# Extracción de materias por bloque
# ============================================================================


def _extract_completed_in_block(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Materias cursadas: ancladas en TERM SUBJECT COURSE + cola CREDITS GRADE [SOURCE]."""
    body: str = block["body"]
    area_name: str = block["name"]
    courses: List[Dict[str, Any]] = []

    for m in TERM_CODE_RE.finditer(body):
        term = m.group(1)
        subj = m.group(2)
        cnum = m.group(3)
        cursor = m.end()

        # Ventana hasta el siguiente TERM CODE, stop top-level, o +250 chars.
        nm = TERM_CODE_RE.search(body, cursor)
        ws = WINDOW_STOP_RE.search(body, cursor)
        candidates = [cursor + 250]
        if nm:
            candidates.append(nm.start())
        if ws:
            candidates.append(ws.start())
        hard_end = min(candidates)
        window = body[cursor:hard_end]

        cg = CREDIT_GRADE_RE.search(window)
        if not cg:
            continue

        title_raw = window[:cg.start()].strip()
        credits_raw = (cg.group("credits") or "").strip()
        grade_raw = (cg.group("grade") or "").strip().upper()
        source = (cg.group("source") or "").strip().upper()

        name_clean, tags = _clean_name(title_raw)
        # Si no hay nombre legible, intentar con la cola post-grade.
        if len(name_clean) < 2:
            post = body[cg.end() + cursor: cg.end() + cursor + 120]
            alt, _ = _clean_name(post)
            if len(alt) >= 2:
                name_clean = alt

        grade_norm = "" if _is_nan_like(grade_raw) else grade_raw
        grade_ok = _is_valid_grade_token(grade_norm)
        credits_num = _norm_num(credits_raw)
        credits_nan = credits_num is None and _is_nan_like(credits_raw)

        courses.append(
            {
                "area": area_name,
                "area_name": area_name,
                "area_met": block["met"],
                "area_credits_required": block["credits_required"],
                "area_credits_used": block["credits_used"],
                "term": term,
                "code": f"{subj} {cnum}",
                "subject": subj,
                "course_number": cnum,
                "name": name_clean,
                "credits_raw": credits_raw,
                "credits_num": credits_num,
                "grade": grade_norm,
                "source": source,
                "completed": bool(grade_ok),
                "pending": False,
                "credits_nan_row": credits_nan,
                "classification_reason": "term+code+grade" if grade_ok else "term_code_only",
                "tags": tags,
                "parse_confidence": "high" if grade_ok else "medium",
            }
        )
    return courses


def _extract_pending_in_block(
    block: Dict[str, Any],
    completed_codes: set,
) -> List[Dict[str, Any]]:
    """Pendientes: ``No [AND|OR] SUBJECT COURSE`` sin term ni grade dentro del bloque."""
    body: str = block["body"]
    area_name: str = block["name"]
    pending: List[Dict[str, Any]] = []
    seen_codes: set = set()

    for m in PENDING_ANCHOR_RE.finditer(body):
        if m.group("term"):
            # Tiene TERM → en realidad es una fila cursada marcada con No (cubierta arriba).
            continue
        subj = m.group("subj")
        cnum = m.group("cnum")
        code = f"{subj} {cnum}"
        if code in seen_codes or code in completed_codes:
            continue
        seen_codes.add(code)

        tail_start = m.end()
        # Ventana hasta próxima ancla pendiente, próximo TERM CODE o stop.
        candidates_end = [tail_start + 200]
        nm_next_pending = PENDING_ANCHOR_RE.search(body, tail_start)
        if nm_next_pending:
            candidates_end.append(nm_next_pending.start())
        nm_next_term = TERM_CODE_RE.search(body, tail_start)
        if nm_next_term:
            candidates_end.append(nm_next_term.start())
        ws = WINDOW_STOP_RE.search(body, tail_start)
        if ws:
            candidates_end.append(ws.start())
        end = min(candidates_end)
        tail = body[tail_start:end]

        # Si la cola contiene un grade VÁLIDO, no es realmente pendiente.
        cg = CREDIT_GRADE_RE.search(tail)
        if cg:
            grade_tok = (cg.group("grade") or "").strip().upper()
            if _is_valid_grade_token(grade_tok):
                continue
            # Si hay un CREDIT_GRADE con NaN/NaN, recortar la cola en ese punto.
            tail = tail[:cg.start()]

        name_clean, tags = _clean_name(tail)
        if not name_clean or len(name_clean) < 3:
            continue
        if not re.search(r"[A-Za-zÁ-ÿ]{3,}", name_clean):
            continue

        pending.append(
            {
                "area": area_name,
                "area_name": area_name,
                "area_met": block["met"],
                "area_credits_required": block["credits_required"],
                "area_credits_used": block["credits_used"],
                "term": "",
                "code": code,
                "subject": subj,
                "course_number": cnum,
                "name": name_clean,
                "credits_raw": "",
                "credits_num": None,
                "grade": "",
                "source": "",
                "completed": False,
                "pending": True,
                "credits_nan_row": False,
                "classification_reason": "no_term_no_grade",
                "tags": tags,
                "parse_confidence": "medium",
            }
        )
    return pending


# ============================================================================
# Non Course Requirements
# ============================================================================


def _extract_non_course_items(flat: str, anchors: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
    """Lista [{name, met}] de requisitos no-curso."""
    span = _section_span(anchors, flat, "Non Course Requirements")
    if not span:
        return []
    body = flat[span[0]:span[1]]
    items: List[Dict[str, Any]] = []
    seen: set = set()
    for label in NON_COURSE_LABELS:
        if label.lower() in seen:
            continue
        for m in re.finditer(re.escape(label) + r"\b", body, re.IGNORECASE):
            # Tomamos una ventana corta posterior y buscamos Yes/No.
            window = body[m.end(): m.end() + 60]
            yn = re.search(r"\b(Yes|No)\b", window, re.IGNORECASE)
            met = bool(yn and yn.group(1).lower() == "yes")
            items.append({"name": label, "met": met})
            seen.add(label.lower())
            break
    return items


# ============================================================================
# Courses Not Used / Rejected Courses
# ============================================================================


def _extract_simple_courses_section(
    flat: str,
    anchors: List[Tuple[int, str]],
    section_name: str,
) -> List[Dict[str, Any]]:
    """Cursos listados en ``Courses Not Used`` o ``Rejected Courses``."""
    span = _section_span(anchors, flat, section_name)
    if not span:
        return []
    body = flat[span[0]:span[1]]
    out: List[Dict[str, Any]] = []
    seen: set = set()

    for m in TERM_CODE_RE.finditer(body):
        term = m.group(1)
        subj = m.group(2)
        cnum = m.group(3)
        cursor = m.end()
        nm = TERM_CODE_RE.search(body, cursor)
        hard_end = nm.start() if nm else min(cursor + 300, len(body))
        window = body[cursor:hard_end]
        cg = CREDIT_GRADE_RE.search(window)
        if cg:
            title_raw = window[: cg.start()].strip()
            credits_raw = (cg.group("credits") or "").strip()
            grade = (cg.group("grade") or "").strip().upper()
            source = (cg.group("source") or "").strip().upper()
            reason_raw = window[cg.end():].strip()
        else:
            title_raw = window.strip()
            credits_raw = ""
            grade = ""
            source = ""
            reason_raw = ""

        name_clean, tags = _clean_name(title_raw)
        reason_clean, _ = _clean_name(reason_raw[:160])

        key = (term, subj, cnum)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "term": term,
                "code": f"{subj} {cnum}",
                "subject": subj,
                "course_number": cnum,
                "name": name_clean,
                "credits_raw": credits_raw,
                "credits_num": _norm_num(credits_raw),
                "grade": "" if _is_nan_like(grade) else grade,
                "source": source,
                "reason": reason_clean,
                "tags": tags,
            }
        )
    return out


# ============================================================================
# Orquestador principal
# ============================================================================


def parsear_cap_estructurado(texto_completo: str, pages_read: int = 0) -> Dict[str, Any]:
    flat = _flatten(texto_completo)
    if not flat:
        return _empty_result(pages_read)

    anchors = _find_anchor_positions(flat)

    program_summary = _extract_program_summary(flat, anchors)
    area_blocks = _extract_area_blocks(flat, anchors)

    raw_completed: List[Dict[str, Any]] = []
    raw_pending: List[Dict[str, Any]] = []
    areas_public: List[Dict[str, Any]] = []

    for block in area_blocks:
        comp = _extract_completed_in_block(block)
        # Skip áreas sin Total Required y sin materias: probablemente ruido.
        if (
            not comp
            and block["credits_required"] == 0
            and block["credits_used"] == 0
            and block["courses_used"] == 0
            and not block["name"]
        ):
            continue

        completed_codes = {c["code"] for c in comp if c.get("completed")}
        pend = _extract_pending_in_block(block, completed_codes)
        raw_completed.extend(comp)
        raw_pending.extend(pend)
        areas_public.append(
            {
                "name": block["name"],
                "area": block["name"],
                "met": block["met"],
                "credits_required": block["credits_required"],
                "credits_used": block["credits_used"],
                "courses_required": None,
                "courses_used": block["courses_used"],
            }
        )

    # Dedup completed: una sola fila por (term, code), eligiendo la mejor
    # (con grade válido > sin grade; nombre más largo > más corto).
    completed_groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for c in raw_completed:
        completed_groups.setdefault((c.get("term", ""), c.get("code", "")), []).append(c)
    completed: List[Dict[str, Any]] = []
    for key, rows in completed_groups.items():
        best = sorted(
            rows,
            key=lambda r: (
                1 if _is_valid_grade_token(r.get("grade", "")) else 0,
                len((r.get("name") or "")),
                0 if _is_nan_like(r.get("credits_raw", "")) else 1,
            ),
            reverse=True,
        )[0]
        completed.append(best)

    # Dedup pending: por código, descartando los que ya están como completed.
    completed_codes_all = {c["code"] for c in completed if c.get("completed")}
    pending_groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in raw_pending:
        if p["code"] in completed_codes_all:
            continue
        pending_groups.setdefault(p["code"], []).append(p)
    pending: List[Dict[str, Any]] = []
    for code, rows in pending_groups.items():
        best = sorted(rows, key=lambda r: len((r.get("name") or "")), reverse=True)[0]
        pending.append(best)

    courses_all: List[Dict[str, Any]] = completed + pending
    # Orden estable: por term (vacío al final), luego por código.
    courses_all.sort(key=lambda c: ((c.get("term") or "9999"), c.get("code", "")))

    non_course_items = _extract_non_course_items(flat, anchors)
    courses_not_used = _extract_simple_courses_section(flat, anchors, "Courses Not Used")
    rejected_courses = _extract_simple_courses_section(flat, anchors, "Rejected Courses")

    completed_only = [c for c in courses_all if c.get("completed")]
    pending_only = [c for c in courses_all if c.get("pending") and not c.get("completed")]

    # Estadísticas de extracción.
    nan_credit_courses = sum(
        1 for c in courses_all if (c.get("credits_raw") or "").strip().lower() == "nan"
    )
    zero_credit_courses = sum(
        1 for c in courses_all if c.get("credits_num") == 0.0
    )
    missing_credit_courses = sum(
        1
        for c in courses_all
        if c.get("credits_num") is None
        and (c.get("credits_raw") or "").strip().lower() != "nan"
    )
    numeric_credits_sum_detected = round(
        sum(float(c["credits_num"]) for c in completed_only if c.get("credits_num") is not None),
        2,
    )

    # Validación / warnings.
    warnings: List[str] = []
    if not program_summary["credits_required"]:
        warnings.append("No se encontró bloque Total Required global en Program Evaluation.")
    if not areas_public:
        warnings.append("No se detectaron bloques 'Area :' en el documento.")
    if program_summary["credits_used"]:
        diff = abs(program_summary["credits_used"] - numeric_credits_sum_detected)
        if diff > 0.01:
            if nan_credit_courses > 0 or missing_credit_courses > 0:
                warnings.append(
                    "individual course credits incomplete due to NaN extraction "
                    f"(oficial usado={program_summary['credits_used']}, "
                    f"suma parser={numeric_credits_sum_detected})"
                )
            else:
                warnings.append(
                    f"individual course credits sum ({numeric_credits_sum_detected}) "
                    f"no coincide con el oficial usado ({program_summary['credits_used']})"
                )

    official_summary = {
        "credits_required_reported": float(program_summary["credits_required"]),
        "credits_used_reported": float(program_summary["credits_used"]),
        "courses_used_reported": int(program_summary["courses_used"]),
    }
    parser_extraction_summary = {
        "courses_detected": len(courses_all),
        "completed_courses_detected": len(completed_only),
        "pending_courses_detected": len(pending_only),
        "non_course_items_detected": len(non_course_items),
        "non_course_pending_detected": sum(1 for it in non_course_items if not it["met"]),
        "rejected_courses_detected": len(rejected_courses),
        "courses_not_used_detected": len(courses_not_used),
        "numeric_credits_sum_detected": numeric_credits_sum_detected,
        "nan_credit_courses": nan_credit_courses,
        "zero_credit_courses": zero_credit_courses,
        "missing_credit_courses": missing_credit_courses,
    }

    non_course_pending_names = [it["name"] for it in non_course_items if not it["met"]]

    courses_normalized = [
        {
            "area": c.get("area", ""),
            "area_name": c.get("area_name", c.get("area", "")),
            "area_met": bool(c.get("area_met")),
            "area_credits_required": c.get("area_credits_required"),
            "area_credits_used": c.get("area_credits_used"),
            "term": c.get("term", ""),
            "code": c.get("code", ""),
            "subject": c.get("subject", ""),
            "course_number": c.get("course_number", ""),
            "name": c.get("name", ""),
            "credits_raw": c.get("credits_raw", ""),
            "credits_num": c.get("credits_num"),
            "grade": c.get("grade", ""),
            "completed": bool(c.get("completed")),
            "pending": bool(c.get("pending")) and not c.get("completed"),
            "credits_nan_row": bool(c.get("credits_nan_row")),
            "source": c.get("source", ""),
            "classification_reason": c.get("classification_reason", ""),
            "tags": list(c.get("tags") or []),
        }
        for c in courses_all
    ]

    result: Dict[str, Any] = {
        "student": {},
        "program_summary": program_summary,
        "official_summary": official_summary,
        "parser_extraction_summary": parser_extraction_summary,
        "areas": areas_public,
        "courses": courses_all,
        "courses_normalized": courses_normalized,
        "completed_courses": completed_only,
        "pending_courses": pending_only,
        "non_course_requirements": non_course_items,
        "non_course_pending": non_course_pending_names,
        "pending_requirements": non_course_pending_names,
        "rejected_courses": rejected_courses,
        "courses_not_used": courses_not_used,
        "requirements": {
            "non_course": non_course_items,
            "non_course_pending": non_course_pending_names,
            "pending_courses": pending_only,
            "rejected_courses": rejected_courses,
            "courses_not_used": courses_not_used,
        },
        "debug": {
            "total_courses_raw": len(raw_completed) + len(raw_pending),
            "total_courses_normalized": len(courses_all),
            "duplicates_removed": max(
                0,
                (len(raw_completed) + len(raw_pending)) - len(courses_all),
            ),
            "courses_with_nan_credits": nan_credit_courses,
            "courses_with_noise_trimmed": 0,
            "area_totals_detected": len(areas_public),
            "global_summary_detected": bool(program_summary["credits_required"]),
        },
        "debug_extraction": {
            "pages_read": int(pages_read),
            "area_blocks_detected": len(area_blocks),
            "areas_detected": len(areas_public),
            "completed_courses_detected": len(completed_only),
            "pending_courses_detected": len(pending_only),
            "courses_with_area": sum(1 for c in courses_all if c.get("area")),
            "courses_without_area": sum(1 for c in courses_all if not c.get("area")),
            "non_course_items_detected": len(non_course_items),
            "rejected_courses_detected": len(rejected_courses),
            "courses_not_used_detected": len(courses_not_used),
        },
        "warnings": warnings,
    }

    logger.info(
        "CAP estructurado: areas=%s completed=%s pending=%s rejected=%s not_used=%s "
        "global_req=%s global_used=%s",
        len(areas_public),
        len(completed_only),
        len(pending_only),
        len(rejected_courses),
        len(courses_not_used),
        program_summary.get("credits_required"),
        program_summary.get("credits_used"),
    )
    for i, a in enumerate(areas_public):
        logger.info(
            "CAP área[%s]: %s req=%s used=%s courses=%s met=%s",
            i,
            (a.get("area") or "")[:80],
            a.get("credits_required"),
            a.get("credits_used"),
            a.get("courses_used"),
            a.get("met"),
        )

    return result


def _empty_result(pages_read: int) -> Dict[str, Any]:
    return {
        "student": {},
        "program_summary": {
            "credits_required": 0.0,
            "credits_used": 0.0,
            "courses_used": 0,
            "progress_percent": 0.0,
        },
        "official_summary": {
            "credits_required_reported": 0.0,
            "credits_used_reported": 0.0,
            "courses_used_reported": 0,
        },
        "parser_extraction_summary": {
            "courses_detected": 0,
            "completed_courses_detected": 0,
            "pending_courses_detected": 0,
            "non_course_items_detected": 0,
            "non_course_pending_detected": 0,
            "rejected_courses_detected": 0,
            "courses_not_used_detected": 0,
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
        "non_course_requirements": [],
        "non_course_pending": [],
        "pending_requirements": [],
        "rejected_courses": [],
        "courses_not_used": [],
        "requirements": {
            "non_course": [],
            "non_course_pending": [],
            "pending_courses": [],
            "rejected_courses": [],
            "courses_not_used": [],
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
            "pages_read": int(pages_read),
            "area_blocks_detected": 0,
            "areas_detected": 0,
            "completed_courses_detected": 0,
            "pending_courses_detected": 0,
            "courses_with_area": 0,
            "courses_without_area": 0,
            "non_course_items_detected": 0,
            "rejected_courses_detected": 0,
            "courses_not_used_detected": 0,
        },
        "warnings": ["PDF sin texto embebido."] if pages_read else [],
    }


def procesar_pdf_cap_estructurado(data: bytes) -> Tuple[Dict[str, Any], str]:
    """Extrae con fitz y parsea. Devuelve (dict resultado, texto_plano)."""
    texto, pags = extraer_texto_pdf_solo_fitz(data)
    if not texto.strip():
        return _empty_result(pags), ""
    return parsear_cap_estructurado(texto, pages_read=pags), texto
