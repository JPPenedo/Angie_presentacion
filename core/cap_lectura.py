"""Extracción de texto legible desde CAP en PDF, CSV o XLSX (prototipo)."""
from __future__ import annotations

import csv
import io
import re
from typing import Tuple


def extraer_texto_cap(contenido: bytes, nombre_archivo: str) -> Tuple[str, str]:
    """
    Devuelve (texto_extraido, mensaje_error).
    Si todo va bien, mensaje_error es cadena vacía.
    """
    if not contenido:
        return "", "Archivo vacío."
    nombre = (nombre_archivo or "").lower()
    ext = nombre.rsplit(".", 1)[-1] if "." in nombre else ""

    try:
        if ext == "pdf":
            return _leer_pdf(contenido)
        if ext in ("csv", "txt"):
            return _leer_csv_o_texto(contenido)
        if ext in ("xlsx", "xls"):
            return _leer_excel(contenido, ext)
        return "", f"Extensión no soportada para lectura automática (.{ext})."
    except Exception as exc:  # noqa: BLE001
        return "", f"No se pudo leer el archivo: {exc}"


def _leer_pdf(data: bytes) -> Tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "Falta la dependencia pypdf en el servidor."

    reader = PdfReader(io.BytesIO(data))
    partes = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            partes.append(t)
    texto = "\n\n".join(partes).strip()
    if not texto:
        return "", "El PDF no contenía texto extraíble (¿escaneado sin OCR?)."
    return _normalizar_texto(texto), ""


def _leer_csv_o_texto(data: bytes) -> Tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            s = data.decode(enc)
            break
        except UnicodeDecodeError:
            s = None
    if s is None:
        return "", "No se pudo decodificar el archivo como texto."

    s = s.strip()
    if not s:
        return "", "Archivo de texto vacío."

    # Si parece CSV, volcar filas de forma legible
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
    partes = []
    for sheet in wb.worksheets:
        filas_txt = []
        for row in sheet.iter_rows(max_row=500, values_only=True):
            celdas = [("" if c is None else str(c)).strip() for c in row]
            if any(celdas):
                filas_txt.append(" | ".join(celdas))
        if filas_txt:
            partes.append(f"--- Hoja: {sheet.title} ---\n" + "\n".join(filas_txt))
    wb.close()
    texto = "\n\n".join(partes).strip()
    if not texto:
        return "", "La hoja de cálculo no tenía celdas con valores legibles."
    return _normalizar_texto(texto), ""


def _normalizar_texto(texto: str) -> str:
    texto = re.sub(r"\r\n?", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()
