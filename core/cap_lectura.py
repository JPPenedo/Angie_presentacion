"""Extracción de texto desde CAP: PDF (varios motores locales), CSV, XLSX."""
from __future__ import annotations

import csv
import io
import re
from typing import Callable, List, Tuple

# Máximo de páginas por PDF para tiempo de respuesta razonable en web.
MAX_PDF_PAGES = 80


def extraer_texto_cap(contenido: bytes, nombre_archivo: str) -> Tuple[str, str, str]:
    """
    Devuelve (texto_extraido, mensaje_error, resumen_extraccion).
    Si todo va bien, mensaje_error es cadena vacía y resumen describe motor y estadísticas.
    """
    if not contenido:
        return "", "Archivo vacío.", ""
    nombre = (nombre_archivo or "").lower()
    ext = nombre.rsplit(".", 1)[-1] if "." in nombre else ""

    try:
        if ext == "pdf":
            return _leer_pdf_multimotor(contenido)
        if ext in ("csv", "txt"):
            t, err = _leer_csv_o_texto(contenido)
            if err:
                return "", err, ""
            return t, "", f"Texto plano ({ext.upper()}) · {len(t):,} caracteres"
        if ext in ("xlsx", "xls"):
            t, err = _leer_excel(contenido, ext)
            if err:
                return "", err, ""
            return t, "", f"Hoja de cálculo ({ext.upper()}) · {len(t):,} caracteres"
        return "", f"Extensión no soportada para lectura automática (.{ext}).", ""
    except Exception as exc:  # noqa: BLE001
        return "", f"No se pudo leer el archivo: {exc}", ""


def _score_extraccion(texto: str) -> float:
    """Prefiere textos largos con buena densidad alfanumérica (menos basura binaria)."""
    t = texto.strip()
    n = len(t)
    if n < 20:
        return float(n)
    alnum = sum(1 for c in t if c.isalnum())
    ratio = alnum / max(n, 1)
    if ratio < 0.12:
        return n * 0.25
    return n * (0.35 + 0.65 * min(1.0, ratio / 0.85))


def _normalizar_texto(texto: str) -> str:
    texto = re.sub(r"\r\n?", "\n", texto)
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _leer_pdf_multimotor(data: bytes) -> Tuple[str, str, str]:
    intentos: List[Tuple[str, str, int]] = []

    def añadir(nombre: str, fn: Callable[[bytes], Tuple[str, int]]) -> None:
        try:
            txt, paginas = fn(data)
            txt = (txt or "").strip()
            if txt:
                intentos.append((nombre, _normalizar_texto(txt), paginas))
        except Exception:
            pass

    añadir("PyMuPDF", _pdf_pymupdf)
    añadir("pdfplumber", _pdf_pdfplumber)
    añadir("pdfminer", _pdf_pdfminer)
    añadir("pypdf", _pdf_pypdf)

    if not intentos:
        return (
            "",
            "El PDF no contenía texto extraíble con los lectores locales. Si es un escaneo (solo imagen), hace falta OCR u otro formato (XLSX/CSV).",
            "",
        )

    mejor_nombre, mejor_txt, mejor_pags = max(intentos, key=lambda x: _score_extraccion(x[1]))
    # Si el mejor es muy corto frente a otro, el score ya lo discrimina.
    resumen = (
        f"Lectura optimizada · motor {mejor_nombre} · hasta {mejor_pags} pág. · "
        f"{len(mejor_txt):,} caracteres · se probaron {len(intentos)} métodos"
    )
    return mejor_txt, "", resumen


def _pdf_pymupdf(data: bytes) -> Tuple[str, int]:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        n_doc = len(doc)
        lim = min(n_doc, MAX_PDF_PAGES)
        partes: List[str] = []
        for i in range(lim):
            page = doc[i]
            t = ""
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


def _pdf_pdfplumber(data: bytes) -> Tuple[str, int]:
    import pdfplumber

    partes: List[str] = []
    n = 0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:MAX_PDF_PAGES]:
            n += 1
            t = ""
            try:
                t = page.extract_text(layout=True) or ""
            except Exception:
                t = page.extract_text() or ""
            if not t.strip():
                t = page.extract_text() or ""
            if t.strip():
                partes.append(t)
    return "\n\n".join(partes), n


def _pdf_pdfminer(data: bytes) -> Tuple[str, int]:
    from pdfminer.high_level import extract_text

    t = extract_text(io.BytesIO(data), maxpages=MAX_PDF_PAGES) or ""
    if not t.strip():
        return "", 0
    pags = max(1, t.count("\f") + 1)
    return t, min(MAX_PDF_PAGES, pags)


def _pdf_pypdf(data: bytes) -> Tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    partes: List[str] = []
    lim = min(len(reader.pages), MAX_PDF_PAGES)
    for i in range(lim):
        t = reader.pages[i].extract_text() or ""
        if t.strip():
            partes.append(t)
    return "\n\n".join(partes), lim


def _leer_csv_o_texto(data: bytes) -> Tuple[str, str]:
    s = None
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            s = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if s is None:
        return "", "No se pudo decodificar el archivo como texto."

    s = s.strip()
    if not s:
        return "", "Archivo de texto vacío."

    try:
        sample = s[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.reader(io.StringIO(s), dialect)
        filas = list(reader)
        if len(filas) > 1 and any(len(r) > 1 for r in filas[:5]):
            lineas = [" | ".join(c.strip() for c in fila) for fila in filas if any(c.strip() for c in fila)]
            return _normalizar_texto("\n".join(lineas)), ""
    except csv.Error:
        pass

    return _normalizar_texto(s), ""


def _leer_excel(data: bytes, ext: str) -> Tuple[str, str]:
    try:
        import openpyxl
    except ImportError:
        return "", "Falta la dependencia openpyxl en el servidor."

    if ext == "xls":
        return "", "Los .xls antiguos no están soportados; guarda como .xlsx."

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    partes: List[str] = []
    try:
        for sheet in wb.worksheets:
            filas_txt: List[str] = []
            for row in sheet.iter_rows(max_row=500, values_only=True):
                celdas = [("" if c is None else str(c)).strip() for c in row]
                if any(celdas):
                    filas_txt.append(" | ".join(celdas))
            if filas_txt:
                partes.append(f"--- Hoja: {sheet.title} ---\n" + "\n".join(filas_txt))
    finally:
        wb.close()
    texto = "\n\n".join(partes).strip()
    if not texto:
        return "", "La hoja de cálculo no tenía celdas con valores legibles."
    return _normalizar_texto(texto), ""
