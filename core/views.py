"""
Este módulo concentra toda la lógica de presentación del prototipo.
Se usan datos en memoria (diccionarios/listas) para fines de demo pedagógica,
sin depender de modelos ni base de datos para autenticación académica.

Guía de lectura (tipo profesor):
1) Primero revisa los bloques de datos (USUARIOS, HISTORIAL_ALUMNO, MATERIAS_ACTUALES, GRUPOS).
2) Luego estudia los helpers (_compute_stats, _usuario_sesion, _require_login).
3) Finalmente sigue el flujo de vistas: login -> dashboard/docente o perfil/alumno.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404
from django.contrib.auth.hashers import check_password, make_password
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
import copy
import json
from collections import defaultdict

from .cap_estructurado import procesar_pdf_cap_estructurado
from .cap_lectura import extraer_texto_cap
from .models import (
    BloqueEvaluacion,
    CapLectura,
    CuentaAlumno,
    EsquemaEvaluacionMateria,
    RubroEvaluacion,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Usuarios demo (sin modelos, autenticación por sesión)
# ---------------------------------------------------------------------------

# Profesor: este diccionario reemplaza temporalmente una tabla de usuarios real.
# Idea clave: aquí definimos "quién entra" y "qué rol tiene", lo cual determina
# qué pantalla verá después del login (docente o alumno).
USUARIOS = {
    '90000001': {
        'password': 'demo123',
        'rol': 'docente',
        'nombre': 'Dr. Gilberto Morales',
        'cargo': 'Coordinador de Actuaría',
    },
    '90000002': {
        'password': 'demo123',
        'rol': 'alumno',
        'nombre': 'Juan Pablo Penedo',
        'matricula': 'AU210034',
        'semestre_actual': 10,
        'creditos_totales': 360,
        'creditos_acreditados': 273,
    },
    '26000000': {
        'password': 'ADMINISTRACION26',
        'rol': 'director',
        'nombre': 'Dirección Académica',
        'cargo': 'Administración — registros, CAP y visión global',
    },
    '90000003': {
        'password': 'demo123',
        'rol': 'coordinacion',
        'nombre': 'Mtra. Andrea Paredes',
        'cargo': 'Coordinación Académica',
    },
}

# ---------------------------------------------------------------------------
# Datos del alumno demo: historial + materias actuales
# ---------------------------------------------------------------------------

# Profesor: este bloque es la "fuente maestra" del historial del alumno demo.
# Todo lo que ves en tablas y gráficas del perfil sale de aquí.
# Si cambias calificaciones o créditos aquí, cambiarán los indicadores mostrados.
HISTORIAL_ALUMNO = [
    {
        'semestre': '1° Semestre',
        'periodo': 'Ago–Dic 2021',
        'materias': [
            {'nombre': 'Cálculo Diferencial e Integral I', 'creditos': 8, 'calificacion': 9.1, 'estatus': 'Acreditada'},
            {'nombre': 'Álgebra Lineal I',                 'creditos': 6, 'calificacion': 8.5, 'estatus': 'Acreditada'},
            {'nombre': 'Introducción a la Actuaría',       'creditos': 4, 'calificacion': 9.8, 'estatus': 'Acreditada'},
            {'nombre': 'Microeconomía',                    'creditos': 5, 'calificacion': 8.0, 'estatus': 'Acreditada'},
            {'nombre': 'Fundamentos de Contabilidad',      'creditos': 4, 'calificacion': 8.7, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '2° Semestre',
        'periodo': 'Ene–May 2022',
        'materias': [
            {'nombre': 'Cálculo Diferencial e Integral II','creditos': 8, 'calificacion': 8.8, 'estatus': 'Acreditada'},
            {'nombre': 'Álgebra Lineal II',                'creditos': 6, 'calificacion': 9.0, 'estatus': 'Acreditada'},
            {'nombre': 'Probabilidad I',                   'creditos': 6, 'calificacion': 9.3, 'estatus': 'Acreditada'},
            {'nombre': 'Macroeconomía',                    'creditos': 5, 'calificacion': 7.6, 'estatus': 'Acreditada'},
            {'nombre': 'Estadística Descriptiva',          'creditos': 5, 'calificacion': 9.1, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '3° Semestre',
        'periodo': 'Ago–Dic 2022',
        'materias': [
            {'nombre': 'Ecuaciones Diferenciales',         'creditos': 7, 'calificacion': 8.2, 'estatus': 'Acreditada'},
            {'nombre': 'Probabilidad II',                  'creditos': 6, 'calificacion': 8.9, 'estatus': 'Acreditada'},
            {'nombre': 'Matemáticas Financieras',          'creditos': 7, 'calificacion': 8.5, 'estatus': 'Acreditada'},
            {'nombre': 'Estadística Inferencial',          'creditos': 5, 'calificacion': 8.7, 'estatus': 'Acreditada'},
            {'nombre': 'Demografía I',                     'creditos': 4, 'calificacion': 9.2, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '4° Semestre',
        'periodo': 'Ene–May 2023',
        'materias': [
            {'nombre': 'Variable Compleja',                'creditos': 6, 'calificacion': 7.8, 'estatus': 'Acreditada'},
            {'nombre': 'Teoría del Interés',               'creditos': 7, 'calificacion': 9.0, 'estatus': 'Acreditada'},
            {'nombre': 'Modelos de Regresión Lineal',      'creditos': 6, 'calificacion': 8.6, 'estatus': 'Acreditada'},
            {'nombre': 'Estadística Actuarial I',          'creditos': 6, 'calificacion': 8.3, 'estatus': 'Acreditada'},
            {'nombre': 'Demografía II',                    'creditos': 4, 'calificacion': 9.1, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '5° Semestre',
        'periodo': 'Ago–Dic 2023',
        'materias': [
            {'nombre': 'Procesos Estocásticos I',          'creditos': 7, 'calificacion': 8.0, 'estatus': 'Acreditada'},
            {'nombre': 'Cálculo Actuarial I',              'creditos': 8, 'calificacion': 8.5, 'estatus': 'Acreditada'},
            {'nombre': 'Estadística Actuarial II',         'creditos': 6, 'calificacion': 8.8, 'estatus': 'Acreditada'},
            {'nombre': 'Modelos Lineales Generalizados',   'creditos': 5, 'calificacion': 7.9, 'estatus': 'Acreditada'},
            {'nombre': 'Análisis de Inversiones',          'creditos': 5, 'calificacion': 9.4, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '6° Semestre',
        'periodo': 'Ene–May 2024',
        'materias': [
            {'nombre': 'Procesos Estocásticos II',         'creditos': 7, 'calificacion': 7.5, 'estatus': 'Acreditada'},
            {'nombre': 'Cálculo Actuarial II',             'creditos': 8, 'calificacion': 8.2, 'estatus': 'Acreditada'},
            {'nombre': 'Teoría del Riesgo I',              'creditos': 7, 'calificacion': 8.6, 'estatus': 'Acreditada'},
            {'nombre': 'Seguros de Vida',                  'creditos': 6, 'calificacion': 9.0, 'estatus': 'Acreditada'},
            {'nombre': 'Finanzas I',                       'creditos': 5, 'calificacion': 8.1, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '7° Semestre',
        'periodo': 'Ago–Dic 2024',
        'materias': [
            {'nombre': 'Cálculo Actuarial III',            'creditos': 8, 'calificacion': 8.7, 'estatus': 'Acreditada'},
            {'nombre': 'Teoría del Riesgo II',             'creditos': 7, 'calificacion': 8.4, 'estatus': 'Acreditada'},
            {'nombre': 'Modelos de Supervivencia',         'creditos': 7, 'calificacion': 9.1, 'estatus': 'Acreditada'},
            {'nombre': 'Pensiones y Beneficios',           'creditos': 6, 'calificacion': 7.8, 'estatus': 'Acreditada'},
            {'nombre': 'Finanzas II',                      'creditos': 5, 'calificacion': 8.9, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '8° Semestre',
        'periodo': 'Ene–May 2025',
        'materias': [
            {'nombre': 'Modelos de Credibilidad',          'creditos': 7, 'calificacion': 8.5, 'estatus': 'Acreditada'},
            {'nombre': 'Reaseguro',                        'creditos': 6, 'calificacion': 8.0, 'estatus': 'Acreditada'},
            {'nombre': 'Análisis de Series de Tiempo',     'creditos': 7, 'calificacion': 9.2, 'estatus': 'Acreditada'},
            {'nombre': 'Seguros de Daños',                 'creditos': 6, 'calificacion': 8.3, 'estatus': 'Acreditada'},
            {'nombre': 'Matemáticas Actuariales de Vida',  'creditos': 7, 'calificacion': 8.7, 'estatus': 'Acreditada'},
        ],
    },
    {
        'semestre': '9° Semestre',
        'periodo': 'Ago–Dic 2025',
        'materias': [
            {'nombre': 'Modelación Actuarial',             'creditos': 7, 'calificacion': 9.0, 'estatus': 'Acreditada'},
            {'nombre': 'Análisis de Datos con R',          'creditos': 5, 'calificacion': 9.5, 'estatus': 'Acreditada'},
            {'nombre': 'Finanzas Actuariales',             'creditos': 7, 'calificacion': 8.8, 'estatus': 'Acreditada'},
            {'nombre': 'Seminario Actuarial',              'creditos': 4, 'calificacion': 9.1, 'estatus': 'Acreditada'},
            {'nombre': 'Optativa: Análisis de Riesgos ESG','creditos': 5, 'calificacion': 9.3, 'estatus': 'Acreditada'},
        ],
    },
]

# Profesor: estas materias representan el semestre actual (estado "en curso").
# Se muestran en tarjetas con avance, calificación parcial y entregas.
MATERIAS_ACTUALES = [
    {'nombre': 'Proyecto Actuarial II',           'creditos': 8, 'calificacion_parcial': 8.9, 'avance': 72, 'docente': 'Dr. Gilberto Morales',  'entregas': 9, 'total_entregas': 12},
    {'nombre': 'Ética Profesional del Actuario',  'creditos': 4, 'calificacion_parcial': 9.5, 'avance': 80, 'docente': 'Mtra. Laura Castillo',   'entregas': 8, 'total_entregas': 10},
    {'nombre': 'Optativa: Machine Learning Act.', 'creditos': 5, 'calificacion_parcial': 8.2, 'avance': 65, 'docente': 'Dr. Carlos Estrada',     'entregas': 7, 'total_entregas': 11},
    {'nombre': 'Proyecto Terminal (Titulación)',   'creditos': 6, 'calificacion_parcial': None, 'avance': 40, 'docente': 'Dr. Gilberto Morales', 'entregas': 3, 'total_entregas': 8},
]

# ---------------------------------------------------------------------------
# Grupos activos (expandido con más materias de Actuaría)
# ---------------------------------------------------------------------------

# Profesor: catálogo principal para la experiencia del docente.
# Cada grupo contiene alumnos y datos base para calcular métricas de riesgo,
# aprobación y promedio que luego se pintan en dashboard y detalle de grupo.
GRUPOS = {
    1: {
        'id': 1,
        'nombre': 'Cálculo Actuarial I',
        'nombre_corto': 'Cálculo Act. I',
        'semestre': '5° Semestre',
        'creditos': 8,
        'avance': 68,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Ana García López',      'calificacion': 9.2, 'asistencia': 95, 'riesgo': 'Bajo',  'entregas': 12, 'total_entregas': 13},
            {'nombre': 'Carlos Mendoza Ruiz',   'calificacion': 6.1, 'asistencia': 72, 'riesgo': 'Alto',  'entregas': 8,  'total_entregas': 13},
            {'nombre': 'María Torres Vega',     'calificacion': 8.5, 'asistencia': 90, 'riesgo': 'Bajo',  'entregas': 12, 'total_entregas': 13},
            {'nombre': 'Luis Hernández Cruz',   'calificacion': 7.0, 'asistencia': 80, 'riesgo': 'Medio', 'entregas': 10, 'total_entregas': 13},
            {'nombre': 'Sofía Ramírez Díaz',    'calificacion': 5.5, 'asistencia': 65, 'riesgo': 'Alto',  'entregas': 7,  'total_entregas': 13},
            {'nombre': 'Diego Flores Ortiz',    'calificacion': 8.9, 'asistencia': 93, 'riesgo': 'Bajo',  'entregas': 13, 'total_entregas': 13},
            {'nombre': 'Valentina Pérez Mora',  'calificacion': 7.4, 'asistencia': 85, 'riesgo': 'Medio', 'entregas': 11, 'total_entregas': 13},
            {'nombre': 'Andrés Castro Núñez',   'calificacion': 6.8, 'asistencia': 78, 'riesgo': 'Medio', 'entregas': 9,  'total_entregas': 13},
        ],
    },
    2: {
        'id': 2,
        'nombre': 'Estadística Actuarial II',
        'nombre_corto': 'Est. Actuarial II',
        'semestre': '5° Semestre',
        'creditos': 6,
        'avance': 82,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Fernanda López Ríos',      'calificacion': 9.6, 'asistencia': 98, 'riesgo': 'Bajo',  'entregas': 15, 'total_entregas': 15},
            {'nombre': 'Roberto Sánchez Gil',      'calificacion': 5.8, 'asistencia': 60, 'riesgo': 'Alto',  'entregas': 7,  'total_entregas': 15},
            {'nombre': 'Daniela Vargas Luna',      'calificacion': 8.2, 'asistencia': 88, 'riesgo': 'Bajo',  'entregas': 14, 'total_entregas': 15},
            {'nombre': 'Miguel Ángel Reyes',       'calificacion': 7.7, 'asistencia': 82, 'riesgo': 'Bajo',  'entregas': 13, 'total_entregas': 15},
            {'nombre': 'Isabella Moreno Paz',      'calificacion': 6.3, 'asistencia': 71, 'riesgo': 'Medio', 'entregas': 10, 'total_entregas': 15},
            {'nombre': 'Sebastián Torres Aguilar', 'calificacion': 9.1, 'asistencia': 96, 'riesgo': 'Bajo',  'entregas': 15, 'total_entregas': 15},
            {'nombre': 'Camila Jiménez Blanco',    'calificacion': 6.9, 'asistencia': 76, 'riesgo': 'Medio', 'entregas': 11, 'total_entregas': 15},
            {'nombre': 'Emilio Guerrero Ponce',    'calificacion': 5.2, 'asistencia': 58, 'riesgo': 'Alto',  'entregas': 6,  'total_entregas': 15},
        ],
    },
    3: {
        'id': 3,
        'nombre': 'Matemáticas Financieras',
        'nombre_corto': 'Mat. Financieras',
        'semestre': '3° Semestre',
        'creditos': 7,
        'avance': 55,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Lucía Delgado Serrano',  'calificacion': 8.8, 'asistencia': 91, 'riesgo': 'Bajo',  'entregas': 9,  'total_entregas': 11},
            {'nombre': 'Alejandro Vega Salinas', 'calificacion': 7.2, 'asistencia': 84, 'riesgo': 'Medio', 'entregas': 8,  'total_entregas': 11},
            {'nombre': 'Natalia Ruiz Campos',    'calificacion': 5.9, 'asistencia': 63, 'riesgo': 'Alto',  'entregas': 6,  'total_entregas': 11},
            {'nombre': 'Rodrigo Méndez Ibarra',  'calificacion': 9.0, 'asistencia': 94, 'riesgo': 'Bajo',  'entregas': 11, 'total_entregas': 11},
            {'nombre': 'Paula Olvera Castillo',  'calificacion': 6.5, 'asistencia': 70, 'riesgo': 'Medio', 'entregas': 7,  'total_entregas': 11},
            {'nombre': 'Tomás Espinoza Rivas',   'calificacion': 8.0, 'asistencia': 88, 'riesgo': 'Bajo',  'entregas': 10, 'total_entregas': 11},
            {'nombre': 'Mariana Fuentes Ojeda',  'calificacion': 5.0, 'asistencia': 55, 'riesgo': 'Alto',  'entregas': 5,  'total_entregas': 11},
            {'nombre': 'Héctor Contreras Mora',  'calificacion': 7.5, 'asistencia': 86, 'riesgo': 'Bajo',  'entregas': 9,  'total_entregas': 11},
        ],
    },
    4: {
        'id': 4,
        'nombre': 'Teoría del Riesgo I',
        'nombre_corto': 'Teoría del Riesgo I',
        'semestre': '6° Semestre',
        'creditos': 7,
        'avance': 74,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Paola Medina Soto',       'calificacion': 8.4, 'asistencia': 89, 'riesgo': 'Bajo',  'entregas': 10, 'total_entregas': 12},
            {'nombre': 'Jorge Morales Ibáñez',    'calificacion': 6.0, 'asistencia': 68, 'riesgo': 'Alto',  'entregas': 7,  'total_entregas': 12},
            {'nombre': 'Karla Fuentes Reyes',     'calificacion': 9.3, 'asistencia': 97, 'riesgo': 'Bajo',  'entregas': 12, 'total_entregas': 12},
            {'nombre': 'Iván Domínguez Pérez',    'calificacion': 7.1, 'asistencia': 79, 'riesgo': 'Medio', 'entregas': 9,  'total_entregas': 12},
            {'nombre': 'Renata Solís Carbajal',   'calificacion': 5.6, 'asistencia': 62, 'riesgo': 'Alto',  'entregas': 6,  'total_entregas': 12},
            {'nombre': 'Alberto Ríos Mondragón',  'calificacion': 8.0, 'asistencia': 87, 'riesgo': 'Bajo',  'entregas': 11, 'total_entregas': 12},
            {'nombre': 'Nadia Cervantes Cruz',    'calificacion': 7.8, 'asistencia': 83, 'riesgo': 'Bajo',  'entregas': 10, 'total_entregas': 12},
            {'nombre': 'Omar Salinas Portillo',   'calificacion': 6.4, 'asistencia': 74, 'riesgo': 'Medio', 'entregas': 8,  'total_entregas': 12},
        ],
    },
    5: {
        'id': 5,
        'nombre': 'Procesos Estocásticos I',
        'nombre_corto': 'Proc. Estocásticos',
        'semestre': '5° Semestre',
        'creditos': 7,
        'avance': 61,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Claudia Vargas Espino',   'calificacion': 7.9, 'asistencia': 86, 'riesgo': 'Bajo',  'entregas': 8,  'total_entregas': 11},
            {'nombre': 'David Leal Guzmán',       'calificacion': 5.3, 'asistencia': 59, 'riesgo': 'Alto',  'entregas': 5,  'total_entregas': 11},
            {'nombre': 'Patricia Mora Aguilera',  'calificacion': 8.7, 'asistencia': 92, 'riesgo': 'Bajo',  'entregas': 10, 'total_entregas': 11},
            {'nombre': 'Enrique Paredes Luna',    'calificacion': 6.7, 'asistencia': 75, 'riesgo': 'Medio', 'entregas': 7,  'total_entregas': 11},
            {'nombre': 'Ximena Álvarez Ruiz',     'calificacion': 9.0, 'asistencia': 96, 'riesgo': 'Bajo',  'entregas': 11, 'total_entregas': 11},
            {'nombre': 'Ramón Castro Herrera',    'calificacion': 6.2, 'asistencia': 69, 'riesgo': 'Medio', 'entregas': 6,  'total_entregas': 11},
            {'nombre': 'Sofía Núñez Barrios',     'calificacion': 7.5, 'asistencia': 84, 'riesgo': 'Bajo',  'entregas': 9,  'total_entregas': 11},
            {'nombre': 'Felipe Ortega Sánchez',   'calificacion': 5.8, 'asistencia': 63, 'riesgo': 'Alto',  'entregas': 5,  'total_entregas': 11},
        ],
    },
    6: {
        'id': 6,
        'nombre': 'Modelos de Supervivencia',
        'nombre_corto': 'Mod. Supervivencia',
        'semestre': '7° Semestre',
        'creditos': 7,
        'avance': 88,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Gabriela Torres Nieto',   'calificacion': 9.5, 'asistencia': 99, 'riesgo': 'Bajo',  'entregas': 14, 'total_entregas': 14},
            {'nombre': 'Ricardo Blanco Estrada',  'calificacion': 7.3, 'asistencia': 81, 'riesgo': 'Medio', 'entregas': 11, 'total_entregas': 14},
            {'nombre': 'Elena Ramos Gallegos',    'calificacion': 8.6, 'asistencia': 90, 'riesgo': 'Bajo',  'entregas': 13, 'total_entregas': 14},
            {'nombre': 'Arturo Velázquez Mora',   'calificacion': 6.1, 'asistencia': 70, 'riesgo': 'Alto',  'entregas': 8,  'total_entregas': 14},
            {'nombre': 'Mónica Serrano Peña',     'calificacion': 8.9, 'asistencia': 94, 'riesgo': 'Bajo',  'entregas': 14, 'total_entregas': 14},
            {'nombre': 'Fernando Chávez Ibarra',  'calificacion': 7.7, 'asistencia': 85, 'riesgo': 'Bajo',  'entregas': 12, 'total_entregas': 14},
            {'nombre': 'Liliana Acosta Bermúdez', 'calificacion': 5.7, 'asistencia': 61, 'riesgo': 'Alto',  'entregas': 7,  'total_entregas': 14},
            {'nombre': 'Gerardo Peña Zaragoza',   'calificacion': 8.2, 'asistencia': 88, 'riesgo': 'Bajo',  'entregas': 13, 'total_entregas': 14},
        ],
    },
    7: {
        'id': 7,
        'nombre': 'Análisis de Series de Tiempo',
        'nombre_corto': 'Series de Tiempo',
        'semestre': '8° Semestre',
        'creditos': 7,
        'avance': 91,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Verónica Guzmán Soto',    'calificacion': 9.1, 'asistencia': 95, 'riesgo': 'Bajo',  'entregas': 16, 'total_entregas': 16},
            {'nombre': 'Adrián Mendoza Palacios', 'calificacion': 8.3, 'asistencia': 89, 'riesgo': 'Bajo',  'entregas': 15, 'total_entregas': 16},
            {'nombre': 'Cecilia Ortiz Fuentes',   'calificacion': 6.5, 'asistencia': 73, 'riesgo': 'Medio', 'entregas': 11, 'total_entregas': 16},
            {'nombre': 'Mauricio Lara Briones',   'calificacion': 5.4, 'asistencia': 58, 'riesgo': 'Alto',  'entregas': 7,  'total_entregas': 16},
            {'nombre': 'Sandra Rojas Medina',     'calificacion': 8.8, 'asistencia': 92, 'riesgo': 'Bajo',  'entregas': 16, 'total_entregas': 16},
            {'nombre': 'César Alvarado Nava',     'calificacion': 7.4, 'asistencia': 80, 'riesgo': 'Medio', 'entregas': 12, 'total_entregas': 16},
            {'nombre': 'Aurora Pacheco Ríos',     'calificacion': 9.4, 'asistencia': 97, 'riesgo': 'Bajo',  'entregas': 16, 'total_entregas': 16},
            {'nombre': 'Hugo Téllez Campillo',    'calificacion': 6.0, 'asistencia': 66, 'riesgo': 'Alto',  'entregas': 8,  'total_entregas': 16},
        ],
    },
    8: {
        'id': 8,
        'nombre': 'Proyecto Actuarial II',
        'nombre_corto': 'Proyecto Act. II',
        'semestre': '10° Semestre',
        'creditos': 8,
        'avance': 72,
        'docente': 'Dr. Gilberto Morales',
        'alumnos': [
            {'nombre': 'Juan Pablo Penedo',       'calificacion': 8.9, 'asistencia': 94, 'riesgo': 'Bajo',  'entregas': 9,  'total_entregas': 12},
            {'nombre': 'Valeria Soto Cisneros',   'calificacion': 9.2, 'asistencia': 96, 'riesgo': 'Bajo',  'entregas': 11, 'total_entregas': 12},
            {'nombre': 'Ernesto Mejía Alcántara', 'calificacion': 7.1, 'asistencia': 78, 'riesgo': 'Medio', 'entregas': 8,  'total_entregas': 12},
            {'nombre': 'Daniela Ríos Pacheco',    'calificacion': 8.5, 'asistencia': 91, 'riesgo': 'Bajo',  'entregas': 10, 'total_entregas': 12},
            {'nombre': 'Marcos Villanueva Cruz',  'calificacion': 6.3, 'asistencia': 69, 'riesgo': 'Medio', 'entregas': 7,  'total_entregas': 12},
            {'nombre': 'Sofía Guerrero Montes',   'calificacion': 5.8, 'asistencia': 62, 'riesgo': 'Alto',  'entregas': 6,  'total_entregas': 12},
            {'nombre': 'Óscar Naranjo Ibáñez',    'calificacion': 9.0, 'asistencia': 93, 'riesgo': 'Bajo',  'entregas': 11, 'total_entregas': 12},
            {'nombre': 'Alicia Bernal Fuentes',   'calificacion': 7.6, 'asistencia': 83, 'riesgo': 'Bajo',  'entregas': 9,  'total_entregas': 12},
        ],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_stats(alumnos):
    """
    Profesor: este helper transforma datos "crudos" (lista de alumnos)
    en métricas de negocio listas para la interfaz (promedio, aprobados, riesgo, etc.).
    """
    califs = [a['calificacion'] for a in alumnos]
    promedio = round(sum(califs) / len(califs), 1)
    aprobados = sum(1 for c in califs if c >= 6.0)
    reprobados = len(califs) - aprobados
    return {
        'promedio': promedio,
        'aprobados': aprobados,
        'reprobados': reprobados,
        'pct_aprobacion': round(aprobados / len(alumnos) * 100),
        'riesgo_alto':  sum(1 for a in alumnos if a['riesgo'] == 'Alto'),
        'riesgo_medio': sum(1 for a in alumnos if a['riesgo'] == 'Medio'),
        'riesgo_bajo':  sum(1 for a in alumnos if a['riesgo'] == 'Bajo'),
        'total': len(alumnos),
    }


def _grupos_nav():
    """
    Profesor: genera una versión liviana de `GRUPOS` para navegación lateral.
    Solo toma id y nombre corto para no enviar más datos de los necesarios al menú.
    """
    return [{'id': g['id'], 'nombre_corto': g['nombre_corto']} for g in GRUPOS.values()]


def _usuario_sesion(request):
    """Profesor: lectura centralizada del usuario autenticado desde sesión."""
    return request.session.get('usuario')


def _redirect_home_for_rol(rol):
    """Tras login o cuando una vista no aplica al rol del usuario."""
    if rol == 'alumno':
        return redirect('core:perfil_alumno')
    if rol == 'director':
        return redirect('core:panel_director')
    return redirect('core:dashboard')


def _cuenta_alumno_plataforma(request):
    """Cuenta en BD vinculada a la sesión, solo si es alumno de carrera (rol alumno)."""
    usuario = _usuario_sesion(request)
    if not usuario or usuario.get('rol') != 'alumno':
        return None
    try:
        cuenta = CuentaAlumno.objects.filter(id_institucional=usuario['matricula']).first()
        if cuenta and cuenta.rol == 'alumno':
            return cuenta
    except DatabaseError:
        return None
    return None


def _require_login(request):
    """
    Profesor: guardia de acceso.
    - Si no hay sesión, redirige al login.
    - Si hay sesión, deja continuar la vista.
    """
    if not _usuario_sesion(request):
        return redirect('core:login')
    return None


# ---------------------------------------------------------------------------
# Vistas de autenticación
# ---------------------------------------------------------------------------

def login_view(request):
    """
    Profesor: esta vista hace tres cosas:
    1) Si ya hay sesión, evita re-login y redirige según rol.
    2) Si llega POST, valida ID institucional + contraseña.
    3) Si son correctos, guarda en sesión un perfil reducido para toda la app.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return _redirect_home_for_rol(u['rol'])

    error = None
    info = None
    prefill_dato = request.GET.get('dato', '').strip().lower()
    if request.GET.get('created') == '1':
        info = 'Cuenta creada correctamente. Ya puedes iniciar sesión.'
    if request.GET.get('reset') == '1':
        info = 'Contraseña actualizada correctamente. Ya puedes iniciar sesión.'
    if request.method == 'POST':
        dato_acceso = request.POST.get('dato_acceso', '').strip().lower()
        password = request.POST.get('password', '').strip()

        usuario = USUARIOS.get(dato_acceso)
        if usuario and usuario['password'] == password:
            # Profesor: aquí se "firma" la sesión de trabajo del usuario.
            # Esta estructura será usada por navbar, control de roles y vistas.
            request.session['usuario'] = {
                'correo': dato_acceso,
                'rol':    usuario['rol'],
                'nombre': usuario['nombre'],
                **({k: usuario[k] for k in ('matricula', 'semestre_actual', 'creditos_totales', 'creditos_acreditados')}
                   if usuario['rol'] == 'alumno' else {'cargo': usuario.get('cargo', '')}),
            }
            return _redirect_home_for_rol(usuario['rol'])

        try:
            cuenta = CuentaAlumno.objects.filter(id_institucional=dato_acceso).first()
        except DatabaseError:
            error = 'No se pudo consultar cuentas registradas. Verifica que las migraciones estén aplicadas en el servidor.'
            return render(
                request,
                'core/login.html',
                {
                    'error': error,
                    'info': info,
                    'prefill_dato': dato_acceso,
                },
            )

        if cuenta and check_password(password, cuenta.password_hash):
            request.session['usuario'] = {
                'correo': cuenta.id_institucional,
                'rol': cuenta.rol,
                'nombre': cuenta.nombre_completo,
                'matricula': cuenta.id_institucional,
                'semestre_actual': 1 if cuenta.rol == 'alumno' else None,
                'creditos_totales': 360 if cuenta.rol == 'alumno' else None,
                'creditos_acreditados': 0 if cuenta.rol == 'alumno' else None,
                'cargo': 'Coordinación Académica' if cuenta.rol == 'coordinacion' else ('Docente' if cuenta.rol == 'docente' else ''),
            }
            return _redirect_home_for_rol(cuenta.rol)
        else:
            error = 'ID institucional o contraseña incorrectos.'

    return render(
        request,
        'core/login.html',
        {
            'error': error,
            'info': info,
            'prefill_dato': prefill_dato,
        },
    )


def crear_cuenta_view(request):
    """
    Profesor: registro mínimo de cuentas para alumnos/docentes/coordinación.
    Campos: rol, nombre completo, ID de 8 dígitos y contraseña.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return _redirect_home_for_rol(u['rol'])

    error = None
    form_data = {
        'rol': 'alumno',
        'nombre_completo': '',
        'id_institucional': '',
    }

    if request.method == 'POST':
        nombre_completo = request.POST.get('nombre_completo', '').strip()
        id_institucional = request.POST.get('id_institucional', '').strip()
        rol = request.POST.get('rol', 'alumno').strip()
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()

        form_data = {
            'rol': rol,
            'nombre_completo': nombre_completo,
            'id_institucional': id_institucional,
        }

        if rol not in {'alumno', 'docente', 'coordinacion'}:
            error = 'Selecciona un rol válido.'
        elif not nombre_completo:
            error = 'El nombre completo es obligatorio.'
        elif not (id_institucional.isdigit() and len(id_institucional) == 8):
            error = 'El ID institucional debe contener exactamente 8 dígitos.'
        elif len(password) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres.'
        elif password != password_confirm:
            error = 'La confirmación de contraseña no coincide.'
        elif CuentaAlumno.objects.filter(id_institucional=id_institucional).exists():
            error = 'Ese ID institucional ya está registrado.'
        else:
            try:
                cuenta = CuentaAlumno.objects.create(
                    correo_institucional=f'{id_institucional}@id.local',
                    nombre_completo=nombre_completo,
                    id_institucional=id_institucional,
                    rol=rol,
                    password_hash=make_password(password),
                    is_verified=True,
                )
            except DatabaseError as exc:
                logger.exception(
                    'crear_cuenta: fallo al guardar CuentaAlumno (revisa migraciones y logs): %s',
                    exc,
                )
                return render(
                    request,
                    'core/signup.html',
                    {
                        'error': (
                            'No se pudo guardar la cuenta en base de datos. '
                            'Verifica que las migraciones estén aplicadas en el servidor.'
                        ),
                        'form_data': form_data,
                    },
                )
            return redirect(f"{redirect('core:login').url}?created=1&dato={id_institucional}")

    return render(request, 'core/signup.html', {'error': error, 'form_data': form_data})


def logout_view(request):
    """Profesor: cierre total de sesión; elimina datos y fuerza volver a login."""
    request.session.flush()
    return redirect('core:login')


# ---------------------------------------------------------------------------
# Vista docente: dashboard
# ---------------------------------------------------------------------------

def dashboard(request):
    """
    Profesor: vista principal para toma de decisiones del docente.
    Construye indicadores globales y una cola de alumnos en riesgo para seguimiento.
    """
    redir = _require_login(request)
    if redir:
        return redir

    usuario = _usuario_sesion(request)
    if usuario['rol'] == 'alumno':
        return _redirect_home_for_rol(usuario['rol'])

    grupos_con_stats = []
    total_alumnos = 0
    total_alertas = 0
    all_califs = []

    # Profesor: aquí se arma el resumen global acumulando todos los grupos.
    for grupo in GRUPOS.values():
        stats = _compute_stats(grupo['alumnos'])
        grupos_con_stats.append({**grupo, **stats})
        total_alumnos += stats['total']
        total_alertas += stats['riesgo_alto']
        all_califs.extend([a['calificacion'] for a in grupo['alumnos']])

    promedio_general = round(sum(all_califs) / len(all_califs), 1)
    pct_aprobacion_global = round(sum(1 for c in all_califs if c >= 6.0) / len(all_califs) * 100)

    # Profesor: este bloque crea la "lista de intervención" (riesgo Alto/Medio).
    alertas_globales = []
    for grupo in GRUPOS.values():
        for alumno in grupo['alumnos']:
            if alumno['riesgo'] in ('Alto', 'Medio'):
                alertas_globales.append({
                    'alumno': alumno['nombre'],
                    'grupo': grupo['nombre'],
                    'calificacion': alumno['calificacion'],
                    'asistencia': alumno['asistencia'],
                    'riesgo': alumno['riesgo'],
                })
    # Profesor: orden pedagógico de prioridad:
    # primero riesgo Alto, después riesgo Medio; en ambos casos, menor calificación primero.
    alertas_globales.sort(key=lambda x: (0 if x['riesgo'] == 'Alto' else 1, x['calificacion']))

    # Profesor: `context` es el puente entre Python (backend) y HTML (template).
    context = {
        'usuario': usuario,
        'grupos': grupos_con_stats,
        'grupos_nav': _grupos_nav(),
        'total_alumnos': total_alumnos,
        'total_alertas': total_alertas,
        'promedio_general': promedio_general,
        'pct_aprobacion_global': pct_aprobacion_global,
        'alertas': alertas_globales,
    }
    return render(request, 'core/dashboard.html', context)


def detalle_grupo(request, grupo_id):
    """
    Profesor: zoom de un grupo específico.
    Recibe `grupo_id` por URL, valida existencia y expone métricas + alumnos.
    """
    redir = _require_login(request)
    if redir:
        return redir

    usuario = _usuario_sesion(request)
    if usuario['rol'] == 'alumno':
        return _redirect_home_for_rol(usuario['rol'])

    # Profesor: validación defensiva para no renderizar IDs inválidos.
    if grupo_id not in GRUPOS:
        raise Http404("Grupo no encontrado")

    grupo = GRUPOS[grupo_id]
    stats = _compute_stats(grupo['alumnos'])

    context = {
        'usuario': usuario,
        'grupo': grupo,
        'stats': stats,
        'grupos_nav': _grupos_nav(),
    }
    return render(request, 'core/detalle_grupo.html', context)


def _kpi_cap_detail_context(
    es_demo_alumno: bool,
    historial: list,
    cap_estructurado: dict,
    meta_creditos: int,
    total_creditos_hist: int,
    pct_avance: float,
) -> dict:
    """
    Agrupa materias del CAP (o historial demo) para paneles al hacer clic en las tarjetas KPI.
    """
    cap_estructurado = cap_estructurado or {}
    courses_raw = list(cap_estructurado.get('courses') or [])
    courses_normalized = list(cap_estructurado.get('courses_normalized') or [])
    completed_courses = list(cap_estructurado.get('completed_courses') or [])
    ps = dict(cap_estructurado.get('program_summary') or {})
    areas = list(cap_estructurado.get('areas') or [])

    grupos_credito: list = []
    promedio_filas: list = []
    todas_materias: list = []
    debug_counts = {
        'total_courses_raw': len(courses_raw),
        'total_courses_normalized': len(courses_normalized),
        'total_completed_courses': len(completed_courses),
        'courses_with_numeric_credits': 0,
        'courses_with_nan_credits': 0,
        'courses_rendered_in_credit_card': 0,
    }

    def _to_str(value) -> str:
        return str(value).strip() if value is not None else ''

    def _is_nan_like(value) -> bool:
        txt = _to_str(value).lower()
        return txt in {'', 'nan', 'none', 'null', '-', 'n/a'}

    def _has_grade(course: dict) -> bool:
        g = _to_str(course.get('grade', course.get('calificacion', course.get('nota', ''))))
        return not _is_nan_like(g)

    def _has_term(course: dict) -> bool:
        term = _to_str(course.get('term', course.get('periodo', course.get('semester', ''))))
        return bool(term)

    def _has_code(course: dict) -> bool:
        code = _to_str(course.get('code', course.get('codigo', course.get('course_code', ''))))
        return bool(code)

    def _is_completed(course: dict) -> bool:
        if course.get('completed') is True:
            return True
        estado = _to_str(course.get('estado')).lower()
        if estado in {'yes', 'si', 'sí', 'completed', 'aprobada', 'cursada'}:
            return True
        return _has_grade(course)

    def _normalize_course(course: dict) -> dict:
        code = _to_str(course.get('code', course.get('codigo', course.get('course_code', ''))))
        term = _to_str(course.get('term', course.get('periodo', course.get('semester', ''))))
        name = _to_str(course.get('name', course.get('nombre', course.get('course_name', ''))))
        grade = _to_str(course.get('grade', course.get('calificacion', course.get('nota', ''))))
        credits_raw = _to_str(
            course.get('credits_raw', course.get('credits', course.get('creditos', '')))
        )
        completed = _is_completed(course)
        pending = bool(course.get('pending')) and not completed
        credits_nan = bool(course.get('credits_nan_row')) or _is_nan_like(credits_raw)
        return {
            'term': term,
            'code': code,
            'name': name,
            'credits_raw': credits_raw,
            'grade': '' if _is_nan_like(grade) else grade,
            'source': _to_str(course.get('source', '')),
            'completed': completed,
            'pending': pending,
            'credits_nan_row': credits_nan,
        }

    candidate_courses = courses_raw + courses_normalized + completed_courses

    if candidate_courses:
        normalized_courses = []
        seen = set()
        for course in candidate_courses:
            norm = _normalize_course(course)
            visible = _has_code(norm) and (
                _has_grade(norm) or norm.get('completed') is True or _has_term(norm)
            )
            if not visible:
                continue
            key = (
                norm.get('code'),
                norm.get('term'),
                norm.get('name'),
                norm.get('grade'),
                norm.get('credits_raw'),
            )
            if key in seen:
                continue
            seen.add(key)
            normalized_courses.append(norm)

        def _credit_bucket(course: dict) -> str:
            raw = _to_str(course.get('credits_raw'))
            if _is_nan_like(raw):
                return 'NaN / sin valor en fila'
            try:
                val = float(raw)
            except ValueError:
                return 'NaN / sin valor en fila'
            if abs(val) < 1e-9:
                return '0 cr.'
            return f'{val:.2f} cr.'

        by_cred = defaultdict(list)
        for c in normalized_courses:
            label = _credit_bucket(c)
            by_cred[label].append(c)
            if label == 'NaN / sin valor en fila':
                debug_counts['courses_with_nan_credits'] += 1
            else:
                debug_counts['courses_with_numeric_credits'] += 1

        def _cred_sort_key(item):
            lbl = item[0]
            if lbl == 'NaN / sin valor en fila':
                return (2, lbl)
            if lbl == '0 cr.':
                return (1, 0.0)
            try:
                num = float(lbl.replace(' cr.', '').strip())
                return (0, -num)
            except ValueError:
                return (2, lbl)

        grupos_credito = [{'label': g, 'cursos': lst} for g, lst in sorted(by_cred.items(), key=_cred_sort_key)]

        for c in normalized_courses:
            g = c.get('grade')
            if not g or _is_nan_like(g):
                continue
            try:
                float(g)
            except (TypeError, ValueError):
                continue
            promedio_filas.append(c)
        promedio_filas.sort(key=lambda x: float(x['grade']), reverse=True)

        todas_materias = normalized_courses
        debug_counts['courses_rendered_in_credit_card'] = len(normalized_courses)

    elif es_demo_alumno and historial:
        by_cred = defaultdict(list)
        for sem in historial:
            for m in sem.get('materias', []):
                cr = m.get('creditos', 0)
                label = f'{float(cr):.2f} cr.' if cr else '0 cr.'
                by_cred[label].append(
                    {
                        'term': '',
                        'code': f"DEMO-{sem.get('semestre', '')[:3]}-{len(by_cred[label]) + 1}",
                        'name': m.get('nombre', ''),
                        'credits_raw': str(cr),
                        'grade': str(m.get('calificacion', '')),
                        'source': '',
                        'completed': True,
                        'pending': False,
                        'credits_nan_row': False,
                    }
                )

        def _cred_sort_key_demo(item):
            try:
                num = float(item[0].replace(' cr.', ''))
                return (0, -num)
            except ValueError:
                return (1, item[0])

        grupos_credito = [{'label': g, 'cursos': lst} for g, lst in sorted(by_cred.items(), key=_cred_sort_key_demo)]

        for sem in historial:
            for m in sem.get('materias', []):
                promedio_filas.append(
                    {
                        'term': '',
                        'code': f"DEMO-{sem.get('semestre', '')[:3]}",
                        'name': m.get('nombre', ''),
                        'credits_raw': str(m.get('creditos', '')),
                        'grade': str(m.get('calificacion', '')),
                        'source': '',
                        'completed': True,
                        'pending': False,
                        'credits_nan_row': False,
                    }
                )
        promedio_filas.sort(key=lambda x: float(x['grade']), reverse=True)
        todas_materias = [c for g in grupos_credito for c in g['cursos']]

        if not ps.get('credits_required'):
            ps = {
                'credits_required': float(meta_creditos),
                'credits_used': float(total_creditos_hist),
                'progress_percent': float(pct_avance),
                'courses_used': len(todas_materias),
            }
        debug_counts['courses_with_numeric_credits'] = len(todas_materias)
        debug_counts['courses_rendered_in_credit_card'] = len(todas_materias)

    has_summary_or_areas = bool(ps) or bool(areas)
    enabled = bool(grupos_credito or todas_materias or has_summary_or_areas)

    return {
        'kpi_grupos_credito': grupos_credito,
        'kpi_promedio_filas': promedio_filas,
        'kpi_areas_cap': areas,
        'kpi_program_summary': ps,
        'kpi_todas_materias': todas_materias,
        'kpi_panel_enabled': enabled,
        'kpi_debug_counts': debug_counts,
        'kpi_debug_counts_json': json.dumps(debug_counts, ensure_ascii=False, indent=2),
    }


# ---------------------------------------------------------------------------
# Vista alumno: perfil
# ---------------------------------------------------------------------------


def _construir_reporte_cap_completo(cuenta_db, cap_estructurado) -> str:
    """
    Devuelve un único bloque de texto con TODA la información que se reporta y
    guarda de la lectura del CAP del alumno: metadatos del archivo, resumen
    oficial reportado por el CAP, resumen propio del parser, áreas detectadas,
    materias detectadas (créditos, calificación, estado), advertencias, texto
    literal extraído del PDF y JSON crudo de la estructura.

    Pensado para que el alumno lo copie y pegue completo en otro lugar.
    """
    if not cuenta_db:
        return ''
    cap_estructurado = cap_estructurado or {}

    lines: list = []

    def _sep(title: str) -> None:
        lines.append('')
        lines.append('=' * 72)
        lines.append(title)
        lines.append('=' * 72)

    def _fmt_dt(dt) -> str:
        if not dt:
            return '—'
        try:
            return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(dt)

    def _num(value, default='—'):
        if value is None or value == '':
            return default
        try:
            return f'{float(value):g}'
        except (TypeError, ValueError):
            return str(value)

    lines.append('REPORTE COMPLETO DE LECTURA DEL CAP')
    lines.append('Generado: ' + _fmt_dt(timezone.now()))
    lines.append('Alumno: ' + (cuenta_db.nombre_completo or '—'))
    lines.append('ID institucional: ' + (cuenta_db.id_institucional or '—'))
    lines.append('Correo: ' + (cuenta_db.correo_institucional or '—'))

    _sep('1. ARCHIVO Y EXTRACCIÓN')
    lines.append(f'Nombre del archivo: {cuenta_db.cap_nombre_archivo or "—"}')
    lines.append(f'Subido en: {_fmt_dt(cuenta_db.cap_subido_en)}')
    lines.append(f'Última lectura: {_fmt_dt(cuenta_db.cap_ultima_lectura_en)}')
    lines.append(f'Resumen de extracción: {cuenta_db.cap_extraccion_resumen or "—"}')
    lines.append(f'Error de lectura: {cuenta_db.cap_error_lectura or "—"}')
    lines.append(
        f'Caracteres en texto extraído: {len(cuenta_db.cap_texto_extraido or "")}'
    )

    program_summary = cap_estructurado.get('program_summary') or {}
    official_summary = cap_estructurado.get('official_summary') or {}
    parser_summary = cap_estructurado.get('parser_extraction_summary') or {}

    _sep('2. RESUMEN OFICIAL DEL CAP (bloque Total Required)')
    if not (program_summary or official_summary):
        lines.append(
            'Sin datos. No se detectó bloque Program Evaluation / Total Required.'
        )
    else:
        cred_req = official_summary.get('credits_required_reported') or program_summary.get(
            'credits_required'
        )
        cred_used = official_summary.get('credits_used_reported') or program_summary.get(
            'credits_used'
        )
        cursos_used = official_summary.get('courses_used_reported') or program_summary.get(
            'courses_used'
        )
        lines.append(f'Créditos requeridos reportados: {_num(cred_req)}')
        lines.append(f'Créditos usados reportados: {_num(cred_used)}')
        lines.append(f'Cursos usados reportados: {_num(cursos_used)}')
        lines.append(
            f'Avance oficial (%): {_num(program_summary.get("progress_percent"))}'
        )

    _sep('3. RESUMEN DE EXTRACCIÓN DEL PARSER')
    if not parser_summary:
        lines.append('Sin datos del parser.')
    else:
        etiquetas_parser = [
            ('courses_detected', 'Materias detectadas'),
            ('completed_courses_detected', 'Completadas detectadas'),
            ('numeric_credits_sum_detected', 'Créditos numéricos sumados'),
            ('nan_credit_courses', 'Materias con créditos NaN'),
            ('zero_credit_courses', 'Materias con 0 créditos'),
            ('missing_credit_courses', 'Materias con crédito ilegible'),
        ]
        for key, label in etiquetas_parser:
            lines.append(f'{label}: {_num(parser_summary.get(key), default="0")}')

    areas = cap_estructurado.get('areas') or []
    _sep(f'4. ÁREAS DETECTADAS ({len(areas)})')
    if not areas:
        lines.append('Sin áreas detectadas.')
    else:
        lines.append(
            f'{"#":>3}  {"Cumple":<6}  {"Req.":>7}  {"Usado":>7}  {"Cursos":>6}  Área'
        )
        for i, a in enumerate(areas, 1):
            try:
                req = float(a.get('credits_required') or 0)
            except (TypeError, ValueError):
                req = 0.0
            try:
                used = float(a.get('credits_used') or 0)
            except (TypeError, ValueError):
                used = 0.0
            try:
                cursos = int(a.get('courses_used') or 0)
            except (TypeError, ValueError):
                cursos = 0
            met = 'Sí' if a.get('met') else 'No'
            area_nombre = (a.get('area') or '').strip()
            lines.append(
                f'{i:>3}  {met:<6}  {req:>7.2f}  {used:>7.2f}  {cursos:>6}  {area_nombre}'
            )

    courses = cap_estructurado.get('courses') or []
    completed = cap_estructurado.get('completed_courses') or []
    pending = cap_estructurado.get('pending_courses') or []

    _sep(f'5. MATERIAS DETECTADAS ({len(courses)})')
    lines.append(f'Completadas: {len(completed)}  ·  Pendientes: {len(pending)}')
    if courses:
        lines.append('')
        lines.append(
            f'{"#":>3}  {"Periodo":<10}  {"Código":<10}  {"Créd":>6}  {"Calif":<7}  {"Estado":<10}  Nombre'
        )
        for i, c in enumerate(courses, 1):
            term = (c.get('term') or '').strip() or '—'
            code = (c.get('code') or '').strip() or '—'
            name = (c.get('name') or '').strip()
            credits_raw = (c.get('credits_raw') or '').strip()
            if c.get('credits_nan_row'):
                credits_disp = 'NaN'
            else:
                credits_disp = credits_raw or '—'
            grade = (c.get('grade') or '').strip() or '—'
            if c.get('completed'):
                estado = 'Hecha'
            elif c.get('pending'):
                estado = 'Pendiente'
            else:
                estado = '—'
            lines.append(
                f'{i:>3}  {term:<10}  {code:<10}  {credits_disp:>6}  {grade:<7}  {estado:<10}  {name}'
            )

    warnings = cap_estructurado.get('warnings') or []
    _sep(f'6. ADVERTENCIAS DEL PARSER ({len(warnings)})')
    if not warnings:
        lines.append('Sin advertencias.')
    else:
        for w in warnings:
            lines.append(f'- {w}')

    non_course = cap_estructurado.get('non_course_requirements') or []
    non_course_pending = cap_estructurado.get('non_course_pending') or []
    _sep(
        f'7. REQUISITOS NO-CURSO ({len(non_course)}) '
        f'· PENDIENTES NO-CURSO ({len(non_course_pending)})'
    )
    if non_course:
        for it in non_course:
            if isinstance(it, dict):
                nombre = it.get('name', '')
                met = 'cumplido' if it.get('met') else 'pendiente'
                lines.append(f'- {nombre}: {met}')
            else:
                lines.append(f'- {it}')
    else:
        lines.append('Sin requisitos no-curso registrados.')

    rejected = cap_estructurado.get('rejected_courses') or []
    not_used = cap_estructurado.get('courses_not_used') or []
    _sep(
        f'8. CURSOS RECHAZADOS / NO USADOS '
        f'(rechazados={len(rejected)} · no usados={len(not_used)})'
    )
    if rejected:
        lines.append('— Rechazados —')
        for c in rejected:
            term = c.get('term') or '—'
            code = c.get('code') or '—'
            name = c.get('name') or ''
            reason = c.get('reason') or ''
            grade = c.get('grade') or '—'
            lines.append(f'- {term} {code} | {name} | calif: {grade} | motivo: {reason}')
    if not_used:
        lines.append('— No usados —')
        for c in not_used:
            term = c.get('term') or '—'
            code = c.get('code') or '—'
            name = c.get('name') or ''
            reason = c.get('reason') or ''
            grade = c.get('grade') or '—'
            lines.append(f'- {term} {code} | {name} | calif: {grade} | motivo: {reason}')
    if not rejected and not not_used:
        lines.append('Sin registros en cursos rechazados / no usados.')

    _sep('9. TEXTO LITERAL EXTRAÍDO DEL PDF')
    texto_pdf = cuenta_db.cap_texto_extraido or ''
    if texto_pdf:
        lines.append(texto_pdf)
    else:
        lines.append('(no hay texto extraído almacenado)')

    _sep('10. JSON CRUDO COMPLETO (cap_estructurado)')
    try:
        lines.append(
            json.dumps(cap_estructurado, ensure_ascii=False, indent=2, default=str)
        )
    except Exception as exc:
        lines.append(f'(no se pudo serializar JSON: {exc})')

    return '\n'.join(lines)


def perfil_alumno(request):
    """
    Tablero personal del alumno: avance hacia 360 cr., CAP e historial académico.
    """
    redir = _require_login(request)
    if redir:
        return redir

    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return _redirect_home_for_rol(usuario['rol'])

    es_demo_alumno = usuario['correo'] == '90000002'
    cuenta_db = _cuenta_alumno_plataforma(request)

    meta_creditos = usuario.get('creditos_totales') or 360

    if es_demo_alumno:
        historial = copy.deepcopy(HISTORIAL_ALUMNO)
        materias_actuales = copy.deepcopy(MATERIAS_ACTUALES)
        todas_califs = [
            m['calificacion'] for sem in historial for m in sem['materias']
        ]
        promedio_global = round(sum(todas_califs) / len(todas_califs), 2)
        total_creditos_hist = sum(m['creditos'] for sem in historial for m in sem['materias'])
        pct_avance = min(100, round(total_creditos_hist / meta_creditos * 100))
        for sem in historial:
            califs_sem = [m['calificacion'] for m in sem['materias']]
            sem['prom_semestre'] = round(sum(califs_sem) / len(califs_sem), 2)
        cap_ok = True
        cap_message = 'Cuenta demo con historial precargado (sin flujo de subida de CAP).'
    else:
        historial = []
        materias_actuales = []
        promedio_global = None
        total_creditos_hist = 0
        pct_avance = 0
        cap_ps = {}
        if cuenta_db and isinstance(cuenta_db.cap_estructurado, dict):
            cap_ps = cuenta_db.cap_estructurado.get('program_summary') or {}
        if cuenta_db and cuenta_db.cap_subido_en and cap_ps.get('credits_required'):
            total_creditos_hist = int(round(float(cap_ps.get('credits_used', 0))))
            pct_avance = float(cap_ps.get('progress_percent') or 0)
            meta_creditos = int(round(float(cap_ps.get('credits_required'))))
            cap_ok = True
            cap_message = (
                'CAP registrado. Los créditos y el avance se toman del resumen global «Total Required» del PDF.'
            )
            cursos_ok = (cuenta_db.cap_estructurado or {}).get('completed_courses') or []
            vals = []
            for c in cursos_ok:
                g = c.get('grade')
                if g:
                    try:
                        vals.append(float(g))
                    except ValueError:
                        continue
            promedio_global = round(sum(vals) / len(vals), 2) if vals else None
        elif cuenta_db and cuenta_db.cap_subido_en:
            total_creditos_hist = 48
            pct_avance = min(100, round(total_creditos_hist / meta_creditos * 100))
            promedio_global = 8.4
            cap_ok = True
            cap_message = (
                'CAP registrado. La lectura automática aparece abajo cuando el archivo permite extraer texto '
                '(PDF con texto, CSV o XLSX).'
            )
        else:
            cap_ok = bool(cuenta_db and cuenta_db.cap_subido_en)
            cap_message = (
                'Sube tu CAP para completar tu diagnóstico académico: créditos acumulados, '
                'materias en curso y proyección hacia la meta del plan.'
            )

    # Bloques de créditos por etapa del plan (gráfico tipo portafolio)
    bloques_labels = ['1°–3° sem.', '4°–6° sem.', '7°–9° sem.', 'En curso / meta']
    if es_demo_alumno:
        chunks = [
            sum(m['creditos'] for sem in historial[0:3] for m in sem['materias']),
            sum(m['creditos'] for sem in historial[3:6] for m in sem['materias']),
            sum(m['creditos'] for sem in historial[6:9] for m in sem['materias']),
            max(0, meta_creditos - sum(m['creditos'] for sem in historial for m in sem['materias'])),
        ]
    elif cuenta_db and cuenta_db.cap_subido_en:
        areas_cap = (cuenta_db.cap_estructurado or {}).get('areas') or []
        if areas_cap and len(areas_cap) >= 1:
            chunks = []
            for a in areas_cap[:3]:
                chunks.append(max(0, int(round(float(a.get('credits_used', 0))))))
            while len(chunks) < 3:
                chunks.append(0)
            chunks.append(max(0, meta_creditos - total_creditos_hist))
            chunks = [max(0, c) for c in chunks][:4]
        else:
            chunks = [12, 14, 14, meta_creditos - total_creditos_hist]
            chunks = [max(0, c) for c in chunks]
    else:
        chunks = [0, 0, 0, meta_creditos]

    cap_struct_ctx = (cuenta_db.cap_estructurado or {}) if cuenta_db else {}
    hay_datos_cap = bool(
        cuenta_db
        and not es_demo_alumno
        and (
            cuenta_db.cap_subido_en
            or cuenta_db.cap_texto_extraido
            or cap_struct_ctx
        )
    )
    cap_reporte_completo = (
        _construir_reporte_cap_completo(cuenta_db, cap_struct_ctx)
        if hay_datos_cap
        else ''
    )
    kpi_cap = _kpi_cap_detail_context(
        es_demo_alumno,
        historial,
        cap_struct_ctx,
        meta_creditos,
        total_creditos_hist,
        float(pct_avance) if pct_avance is not None else 0.0,
    )
    kpi_interactive = kpi_cap['kpi_panel_enabled'] or es_demo_alumno or bool(
        cuenta_db and cuenta_db.cap_subido_en
    )

    context = {
        'usuario': usuario,
        'grupos_nav': [],
        'historial': historial,
        'materias_actuales': materias_actuales,
        'promedio_global': promedio_global,
        'total_creditos_hist': total_creditos_hist,
        'pct_avance': pct_avance,
        'cuenta_db': cuenta_db,
        'es_demo_alumno': es_demo_alumno,
        'meta_creditos': meta_creditos,
        'bloques_labels_json': json.dumps(bloques_labels),
        'bloques_creditos_json': json.dumps(chunks),
        'cap_ok': cap_ok,
        'cap_message': cap_message,
        'cap_extraccion_resumen': (cuenta_db.cap_extraccion_resumen or '') if cuenta_db else '',
        'cap_estructurado': cap_struct_ctx,
        'cap_reporte_completo': cap_reporte_completo,
        'cap_lectura_error': cuenta_db.cap_error_lectura if cuenta_db else '',
        'kpi_interactive': kpi_interactive,
        **kpi_cap,
    }
    return render(request, 'core/perfil_alumno.html', context)


@require_POST
def subir_cap_alumno(request):
    """Sube el CAP, intenta extraer texto (PDF/CSV/XLSX) y guarda historial de lecturas."""
    redir = _require_login(request)
    if redir:
        return redir
    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return _redirect_home_for_rol(usuario['rol'])
    cuenta = _cuenta_alumno_plataforma(request)
    if not cuenta:
        return redirect('core:perfil_alumno')

    archivo = request.FILES.get('cap_file')
    texto_extraido = ''
    error_lectura = ''
    resumen = ''
    if archivo:
        raw = archivo.read()
        nombre = (archivo.name or '')[:260]
        texto_extraido, error_lectura, resumen = extraer_texto_cap(raw, nombre)
        ext = nombre.lower().rsplit('.', 1)[-1] if '.' in nombre else ''
        if ext == 'pdf':
            cap_dict, _ = procesar_pdf_cap_estructurado(raw)
            cuenta.cap_estructurado = cap_dict
            ps = cap_dict.get('program_summary') or {}
            logger.info(
                'CAP PDF estructurado guardado: cursos=%s áreas=%s req=%s used=%s %%=%s nan_cursadas=%s',
                len(cap_dict.get('courses') or []),
                len(cap_dict.get('areas') or []),
                ps.get('credits_required'),
                ps.get('credits_used'),
                ps.get('progress_percent'),
                len(
                    [
                        c
                        for c in (cap_dict.get('courses') or [])
                        if c.get('credits_nan_row') and c.get('completed')
                    ]
                ),
            )
        else:
            cuenta.cap_estructurado = {}
    else:
        nombre = (request.POST.get('nombre_simulado') or 'CAP_simulado.pdf').strip()[:260]
        error_lectura = 'Simulación sin archivo: no se ejecutó lectura automática.'
        cuenta.cap_estructurado = {}

    now = timezone.now()
    cuenta.cap_subido_en = now
    cuenta.cap_nombre_archivo = nombre
    cuenta.cap_texto_extraido = (texto_extraido or '')[:500000]
    cuenta.cap_error_lectura = (error_lectura or '')[:500]
    cuenta.cap_extraccion_resumen = (resumen or '')[:240]
    cuenta.cap_ultima_lectura_en = now
    cuenta.save()

    CapLectura.objects.create(
        cuenta=cuenta,
        nombre_archivo=nombre,
        texto_extraido=cuenta.cap_texto_extraido[:500000],
        error_lectura=cuenta.cap_error_lectura,
        extraccion_resumen=cuenta.cap_extraccion_resumen,
    )
    return redirect('core:perfil_alumno')


def esquemas_evaluacion_lista(request):
    redir = _require_login(request)
    if redir:
        return redir
    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return _redirect_home_for_rol(usuario['rol'])

    cuenta = _cuenta_alumno_plataforma(request)
    esquemas = []
    if cuenta:
        esquemas = list(
            EsquemaEvaluacionMateria.objects.filter(cuenta=cuenta)
            .prefetch_related('bloques__rubros')
        )

    return render(
        request,
        'core/esquemas_evaluacion_lista.html',
        {
            'usuario': usuario,
            'grupos_nav': [],
            'cuenta': cuenta,
            'esquemas': esquemas,
        },
    )


@require_http_methods(['GET', 'POST'])
def esquema_evaluacion_nuevo(request):
    return _esquema_evaluacion_form(request, None)


@require_http_methods(['GET', 'POST'])
def esquema_evaluacion_editar(request, pk):
    return _esquema_evaluacion_form(request, pk)


def _esquema_evaluacion_form(request, pk):
    redir = _require_login(request)
    if redir:
        return redir
    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return _redirect_home_for_rol(usuario['rol'])

    cuenta = _cuenta_alumno_plataforma(request)
    if not cuenta:
        return redirect('core:esquemas_evaluacion_lista')

    esquema = None
    if pk is not None:
        esquema = get_object_or_404(EsquemaEvaluacionMateria, pk=pk, cuenta=cuenta)

    error_guardar = None
    if request.method == 'POST':
        try:
            payload = json.loads(request.POST.get('payload', ''))
        except json.JSONDecodeError:
            error_guardar = 'Formato de datos inválido.'
        else:
            materia = (payload.get('materia') or '').strip()[:200]
            periodo = (payload.get('periodo') or '').strip()[:120]
            bloques_data = payload.get('bloques')
            if not materia:
                error_guardar = 'Indica el nombre de la materia.'
            elif not isinstance(bloques_data, list) or not bloques_data:
                error_guardar = 'Añade al menos un bloque con criterios.'
            else:
                try:
                    with transaction.atomic():
                        if esquema is None:
                            esquema = EsquemaEvaluacionMateria.objects.create(
                                cuenta=cuenta,
                                nombre_materia=materia,
                                periodo=periodo,
                            )
                        else:
                            esquema.nombre_materia = materia
                            esquema.periodo = periodo
                            esquema.save()
                            esquema.bloques.all().delete()

                        for bi, bloque_raw in enumerate(bloques_data):
                            etiqueta = (bloque_raw.get('etiqueta') or '').strip()[:120]
                            if not etiqueta:
                                etiqueta = f'Bloque {bi + 1}'
                            bloque = BloqueEvaluacion.objects.create(
                                esquema=esquema,
                                etiqueta_grupo=etiqueta,
                                orden=bi,
                            )
                            rubros_raw = bloque_raw.get('rubros') or []
                            for ri, rubro_raw in enumerate(rubros_raw):
                                nombre_r = (rubro_raw.get('nombre') or '').strip()[:400]
                                if not nombre_r:
                                    continue
                                pct_raw = rubro_raw.get('porcentaje')
                                pct = None
                                if pct_raw is not None and str(pct_raw).strip() != '':
                                    try:
                                        pct = Decimal(str(pct_raw).replace(',', '.'))
                                    except (InvalidOperation, ValueError):
                                        pct = None
                                RubroEvaluacion.objects.create(
                                    bloque=bloque,
                                    nombre_criterio=nombre_r,
                                    porcentaje=pct,
                                    destacado=bool(rubro_raw.get('destacado')),
                                    es_fila_total=bool(rubro_raw.get('es_total')),
                                    orden=ri,
                                )
                    return redirect('core:esquemas_evaluacion_lista')
                except Exception as exc:  # noqa: BLE001
                    error_guardar = f'No se pudo guardar: {exc}'

    initial_json = None
    if esquema and request.method == 'GET':
        bloques_out = []
        for bloque in esquema.bloques.all().prefetch_related('rubros'):
            bloques_out.append({
                'etiqueta': bloque.etiqueta_grupo,
                'rubros': [
                    {
                        'nombre': r.nombre_criterio,
                        'porcentaje': '' if r.porcentaje is None else str(r.porcentaje),
                        'destacado': r.destacado,
                        'es_total': r.es_fila_total,
                    }
                    for r in bloque.rubros.all()
                ],
            })
        initial_json = json.dumps({
            'materia': esquema.nombre_materia,
            'periodo': esquema.periodo,
            'bloques': bloques_out,
        }, ensure_ascii=False)

    return render(
        request,
        'core/esquema_evaluacion_editar.html',
        {
            'usuario': usuario,
            'grupos_nav': [],
            'cuenta': cuenta,
            'esquema': esquema,
            'initial_json': initial_json,
            'error_guardar': error_guardar,
        },
    )


@require_POST
def esquema_evaluacion_eliminar(request, pk):
    redir = _require_login(request)
    if redir:
        return redir
    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return _redirect_home_for_rol(usuario['rol'])
    cuenta = _cuenta_alumno_plataforma(request)
    if not cuenta:
        return redirect('core:esquemas_evaluacion_lista')
    EsquemaEvaluacionMateria.objects.filter(pk=pk, cuenta=cuenta).delete()
    return redirect('core:esquemas_evaluacion_lista')


def panel_director(request):
    """Panel administrativo: cuentas registradas y estado de subida de CAP."""
    redir = _require_login(request)
    if redir:
        return redir
    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'director':
        return _redirect_home_for_rol(usuario['rol'])
    try:
        cuentas = list(CuentaAlumno.objects.all().order_by('-created_at'))
    except DatabaseError:
        cuentas = []
    context = {
        'usuario': usuario,
        'grupos_nav': _grupos_nav(),
        'cuentas': cuentas,
        'stat_total': len(cuentas),
        'stat_con_cap': sum(1 for c in cuentas if c.cap_subido_en),
        'stat_alumnos': sum(1 for c in cuentas if c.rol == 'alumno'),
    }
    return render(request, 'core/panel_director.html', context)


def expo_opciones_view(request):
    """
    Vista pública pedagógica:
    - Slides que explican Bull Call Spread y Bear Put Spread.
    - Formato tipo presentación con demos propias
      (diagramas de payoff al vencimiento y escenarios numéricos).
    """
    slides = [
        {
            'titulo': '¿Qué es una opción? Intuición y payoffs base',
            'idea': (
                'Una opción es un contrato que otorga el derecho —no la obligación— '
                'de comprar (call) o vender (put) un activo a un precio de ejercicio K '
                'antes o en el vencimiento T, a cambio de pagar una prima hoy. '
                'Antes de armar un spread, conviene tener presente cómo se ve el '
                'payoff al vencimiento de los bloques básicos.'
            ),
            'modelo': (
                r'\text{Call largo: } \Pi_C(S_T) \;=\; \max(S_T-K,\,0) - c'
                r'\qquad \text{Put largo: } \Pi_P(S_T) \;=\; \max(K-S_T,\,0) - p'
            ),
            'enfoque': (
                'La call larga gana cuando el subyacente sube por encima de K+c; '
                'la put larga gana cuando cae por debajo de K−p. En ambas, la '
                'pérdida máxima está acotada a la prima pagada. Es el ladrillo con '
                'el que luego construimos los spreads.'
            ),
            'conceptos': [
                'Prima (c, p) = costo del derecho; se paga hoy',
                'Strike K = precio de ejercicio fijado en el contrato',
                'Pérdida máxima acotada = prima pagada',
                'Ganancia en call es teóricamente ilimitada; en put acotada a K − p',
            ],
            'demo': 'intro',
        },
        {
            'titulo': 'Bull Call Spread · mecánica y fórmulas',
            'idea': (
                'Si esperamos una subida moderada del subyacente y queremos abaratar '
                'una call larga, vendemos simultáneamente otra call con strike más '
                'alto. El resultado es el Bull Call Spread: una posición alcista con '
                'débito neto, ganancia tope y pérdida tope ya conocidas desde el día 0.'
            ),
            'modelo': (
                r'\Pi(S_T) = \max(S_T-K_1,0) - \max(S_T-K_2,0) - (c_1 - c_2),\ \ K_1 < K_2'
                r'\qquad \text{BEP} = K_1 + (c_1 - c_2)'
                r'\qquad \Pi_{\max} = (K_2 - K_1) - (c_1 - c_2)'
                r'\qquad \Pi_{\min} = -(c_1 - c_2)'
            ),
            'enfoque': (
                'La estrategia es equivalente a "comprar un tramo [K1, K2]" del '
                'recorrido alcista: pagas un débito pequeño a cambio de capturar '
                'exactamente el movimiento entre ambos strikes. Arriba de K2 ya no '
                'ganas más; abajo de K1 sólo pierdes lo pagado.'
            ),
            'conceptos': [
                'Compras call K1 (más cara) y vendes call K2 (más barata) · mismo vencimiento',
                'Débito neto = c1 − c2  →  esto es lo máximo que puedes perder',
                'Breakeven = K1 + débito neto',
                'Ganancia tope = (K2 − K1) − débito neto, alcanzada si ST ≥ K2',
            ],
            'demo': 'bull_payoff',
        },
        {
            'titulo': 'Bull Call Spread · ejemplo numérico',
            'idea': (
                'Acción cotizando en $100. Compramos la call K1 = $100 pagando '
                'c1 = $5 y vendemos la call K2 = $110 cobrando c2 = $2. '
                'Débito neto = $3 por acción. Veamos qué pasa al vencimiento para '
                'distintos precios ST del subyacente.'
            ),
            'modelo': (
                r'c_1 - c_2 = 5 - 2 = 3'
                r'\qquad \text{BEP} = 100 + 3 = 103'
                r'\qquad \Pi_{\max} = (110-100) - 3 = 7'
                r'\qquad \Pi_{\min} = -3'
            ),
            'enfoque': (
                'Relación riesgo–beneficio 7 : 3 ≈ 2.3 a favor. Para "ganar" hay '
                'que creer que ST superará $103 al vencimiento; la estrategia '
                'funciona mejor cuando esperamos un alza controlada hasta $110, '
                'no una explosión alcista (ahí conviene más una call simple).'
            ),
            'conceptos': [
                'ST ≤ 100 → ambas calls vencen sin valor · pierdes $3 (el débito)',
                'ST = 103 → breakeven: lo ganado en la call K1 cubre exactamente el débito',
                'ST = 107 → ganas 7 − 3 = 4 por acción',
                'ST ≥ 110 → ganancia tope de 7; más subida no aporta nada adicional',
            ],
            'demo': 'bull_ejemplo',
        },
        {
            'titulo': 'Bear Put Spread · mecánica y fórmulas',
            'idea': (
                'La versión bajista del mismo razonamiento: si esperamos una caída '
                'moderada y queremos abaratar una put larga, vendemos otra put con '
                'strike más bajo. El resultado es el Bear Put Spread: débito neto, '
                'pérdida tope y ganancia tope acotadas desde el inicio.'
            ),
            'modelo': (
                r'\Pi(S_T) = \max(K_2-S_T,0) - \max(K_1-S_T,0) - (p_2 - p_1),\ \ K_1 < K_2'
                r'\qquad \text{BEP} = K_2 - (p_2 - p_1)'
                r'\qquad \Pi_{\max} = (K_2 - K_1) - (p_2 - p_1)'
                r'\qquad \Pi_{\min} = -(p_2 - p_1)'
            ),
            'enfoque': (
                'Funciona como el "espejo" del Bull Call Spread: esta vez compras '
                'la put con strike más alto (K2, más cara) y vendes la put con '
                'strike más bajo (K1, más barata). Captas exactamente el tramo '
                'bajista entre K2 y K1, con pérdida tope conocida.'
            ),
            'conceptos': [
                'Compras put K2 (más alta) y vendes put K1 (más baja) · mismo vencimiento',
                'Débito neto = p2 − p1  →  esto es lo máximo que puedes perder',
                'Breakeven = K2 − débito neto',
                'Ganancia tope = (K2 − K1) − débito neto, alcanzada si ST ≤ K1',
            ],
            'demo': 'bear_payoff',
        },
        {
            'titulo': 'Bear Put Spread · ejemplo numérico',
            'idea': (
                'Misma acción cotizando en $100. Compramos la put K2 = $100 '
                'pagando p2 = $5 y vendemos la put K1 = $90 cobrando p1 = $2. '
                'Débito neto = $3 por acción. Al vencimiento, veamos qué ocurre '
                'para distintos precios ST.'
            ),
            'modelo': (
                r'p_2 - p_1 = 5 - 2 = 3'
                r'\qquad \text{BEP} = 100 - 3 = 97'
                r'\qquad \Pi_{\max} = (100-90) - 3 = 7'
                r'\qquad \Pi_{\min} = -3'
            ),
            'enfoque': (
                'Relación riesgo–beneficio idéntica 7 : 3, pero apostando a que '
                'ST caerá por debajo de $97. La estrategia rinde al máximo si el '
                'precio cae hasta $90 o menos; si cae más, ya no capturas ganancia '
                'adicional (ahí convendría una put simple).'
            ),
            'conceptos': [
                'ST ≥ 100 → ambas puts vencen sin valor · pierdes $3 (el débito)',
                'ST = 97 → breakeven: lo ganado en la put K2 cubre exactamente el débito',
                'ST = 93 → ganas 7 − 3 = 4 por acción',
                'ST ≤ 90 → ganancia tope de 7; más caída no aporta nada adicional',
            ],
            'demo': 'bear_ejemplo',
        },
        {
            'titulo': 'Comparativa · ¿Cuándo usar cada uno?',
            'idea': (
                'Bull Call Spread y Bear Put Spread son estrategias espejo: misma '
                'estructura (debit vertical spread), mismo perfil de riesgo 7:3 en '
                'nuestro ejemplo, pero cada una apunta a una dirección del mercado. '
                'La decisión se reduce a la visión direccional y al costo relativo '
                'de las primas.'
            ),
            'modelo': (
                r'\text{Ambos: } \Pi_{\min}=-D,\ \ \Pi_{\max}=(K_2-K_1)-D'
                r'\qquad \text{Bull: BEP}=K_1+D'
                r'\qquad \text{Bear: BEP}=K_2-D'
            ),
            'enfoque': (
                'Usa Bull Call Spread cuando tu tesis es moderadamente alcista y '
                'quieres pagar menos que una call simple sacrificando la cola alta. '
                'Usa Bear Put Spread cuando tu tesis es moderadamente bajista y '
                'quieres protegerte de cabeza abajo con un costo acotado, '
                'sacrificando la cola baja.'
            ),
            'conceptos': [
                'Ambas son posiciones de débito con pérdida máxima = prima neta',
                'Ambas aprovechan paridad put-call: son equivalentes ante subyacente y strikes',
                'Bull = alcista moderado · Bear = bajista moderado',
                'Si esperas un movimiento extremo, una opción simple (call o put) domina',
            ],
            'demo': 'comparativa',
        },
    ]

    # Parámetros del ejemplo numérico usados para los payoff diagrams y tablas.
    ejemplo = {
        'spot': 100,
        'bull': {'K1': 100, 'K2': 110, 'c1': 5, 'c2': 2},
        'bear': {'K1': 90,  'K2': 100, 'p1': 2, 'p2': 5},
    }

    context = {
        'slides': slides,
        'ejemplo': ejemplo,
    }
    return render(request, 'core/expo_opciones.html', context)


def expo_sinteticos_view(request):
    """
    Vista pública pedagógica: estrategia Buy Straddle (call larga + put larga
    al mismo strike K) — apuesta a movimiento grande del subyaciente al vencimiento,
    con prima total pagada c + p y dos breakevens K ± (c + p).
    """
    slides = [
        {
            'titulo': '¿Para qué sirve?',
            'resumen_intro': (
                'Sirve cuando esperas que el precio se mueva mucho (noticia, resultados, dato macro) '
                'pero no sabes si subirá o bajará: compras call y put al mismo strike y participas en ambos lados.'
            ),
            'resumen_bullets': [
                'Pagas dos primas (el “boleto” doble); en el ejemplo, c + p = 8 con K = 100.',
                'Al vencimiento ganas si S_T queda bastante lejos de K; empatas en los breakevens (~92 y ~108 en el ejemplo).',
                'Si el precio termina pegado al strike, suele doler lo más: pagaste ambas primas y ninguna pata “despierta”.',
                'En operación real suman comisiones y bid-ask en dos contratos.',
            ],
            'nota_ampliada': (
                'La sensibilidad a la volatilidad implícita suele ser alta: antes de un evento las primas '
                'pueden estar “infladas” y, si después el mercado se calma, un crush de vol puede dañar '
                'la posición aun cuando el subyacente sí se movió.'
            ),
            'idea': (
                'Imagina que esperas que el precio del activo se mueva mucho (por una noticia, '
                'un resultado trimestral o un dato importante), pero no sabes si va a subir o a bajar. '
                'El straddle te deja participar en los dos lados: pagas un “boleto” doble (dos primas) '
                'y ganas si el precio al vencimiento queda bastante lejos del nivel acordado (el strike).'
            ),
            'dato_clave': (
                'Compras una call y una put al mismo precio de ejercicio; en el ejemplo pagas 8 dólares '
                'en total (5 + 3) y empatas si el precio termina en 92 o en 108.'
            ),
            'enfoque': (
                'Si el precio termina pegado al strike (en el ejemplo, cerca de 100), suele ser la '
                'situación más incómoda para quien compró el straddle: ahí es donde más duele haber '
                'pagado las dos primas.'
            ),
            'conceptos': [
                'Te encaja si tu historia es “habrá drama en el precio” y no “solo subirá”.',
                'Te va mal si el mercado se queda dormido y el precio no se aleja del strike.',
                'En la vida real suma comisiones y diferencia entre compra y venta en dos contratos.',
            ],
            'demo': 'straddle_para_que',
        },
        {
            'titulo': '¿Cómo se arma? · Call, put · ¿Compras o vendes?',
            'resumen_intro': (
                'En el straddle largo clásico solo hay compras: una call europea y una put europea con el '
                'mismo precio de ejercicio K y la misma fecha T. Pagas la prima de cada una.'
            ),
            'resumen_bullets': [
                '“Larga” = eres comprador; quien te vende cobra la prima y queda del otro lado del contrato.',
                'Aquí no vendes opciones: no entra el tema del margen por posiciones cortas.',
                'La call te ayuda en subidas fuertes por encima de K; la put, en bajadas fuertes por debajo de K.',
                'La tabla y los mini-gráficos repiten K = 100 con primas 5 (call) y 3 (put).',
            ],
            'nota_ampliada': (
                'En mercados reales las primas dependen de la volatilidad implícita, tasas, dividendos '
                'y del estilo de la opción (europea vs americana). La versión corta del straddle es otra '
                'historia: cobras las primas pero asumes riesgo distinto.'
            ),
            'idea': (
                'En el straddle largo clásico solo hay compras: compras una call y compras una put '
                'al mismo strike y vencimiento. Pagas la prima de la call y la prima de la put. '
                'No estás vendiendo opciones en esta versión, así que no entra el tema del margen '
                'por ventas cortas.'
            ),
            'dato_clave': (
                '“Larga” = compraste el contrato. Quien te vende cada pata cobra la prima y asume '
                'el lado opuesto del trato.'
            ),
            'enfoque': (
                'Si vendieras el straddle (versión corta), sería al revés: cobrarías las dos primas '
                'pero tu riesgo y tu sensación en el gráfico cambian por completo. Aquí nos centramos '
                'en el comprador del straddle.'
            ),
            'conceptos': [
                'Call comprada: te beneficia un suba fuerte por encima del strike (menos lo que pagaste).',
                'Put comprada: te beneficia una baja fuerte por debajo del strike (menos lo que pagaste).',
                'La tabla y los dos mini-gráficos de la derecha repiten el ejemplo con K = 100, primas 5 y 3.',
            ],
            'demo': 'straddle_forma',
        },
        {
            'titulo': '¿Quién gana y quién pierde?',
            'resumen_intro': (
                'En un modelo de libro sin comisiones, al vencimiento el resultado es suma cero: lo que '
                'gana un conjunto de posiciones lo pierde el otro, fila por fila.'
            ),
            'resumen_bullets': [
                'El comprador del straddle se enfrenta, en la práctica pedagógica, al vendedor de la call y al de la put.',
                'Con S_T = 90, 100 y 110 el cuadro muestra cómo se reparte la torta con K = 100, c = 5 y p = 3.',
                'Fila $90: comprador straddle +2; vendedor call +5; vendedor put −7; suma 0.',
                'Fila $100 (=K): el comprador pierde el premio total (−8); los vendedores se reparten +8.',
            ],
            'nota_ampliada': (
                'En la práctica hay comisiones, spreads bid-ask y posiblemente distintas contrapartes; '
                'el cuadro de la diapositiva es una foto pedagógica con tres precios finales (90, 100, 110).'
            ),
            'idea': (
                'En un ejercicio de libro, sin comisiones, el dinero que gana un lado en la fecha '
                'de vencimiento es el que pierde el otro en conjunto. Si el comprador del straddle '
                'gana en un escenario, eso sale del bolsillo combinado de quien le vendió la call '
                'y quien le vendió la put (en la misma mesa de negociación, suele simplificarse así).'
            ),
            'dato_clave': (
                'En la tabla de la derecha, la suma de las tres ganancias o pérdidas da cero en cada fila.'
            ),
            'enfoque': (
                'El gráfico de colores muestra al comprador del straddle frente al vendedor de la call '
                'y al vendedor de la put. Los números son el mismo ejemplo: precio de ejercicio 100, '
                'primas 5 y 3, y tres precios finales (90, 100 y 110).'
            ),
            'conceptos': [
                'Con precio final 90: el comprador del straddle gana 2; el de la call gana 5; el de la put pierde 7.',
                'Con precio final 100: el comprador del straddle pierde 8; los dos vendedores suman +8.',
                'Con precio final 110: el comprador gana 2; el vendedor de la call pierde 5; el de la put gana 3.',
            ],
            'demo': 'straddle_participantes',
        },
        {
            'titulo': 'Lo bueno y lo no tan bueno',
            'resumen_intro': (
                'Es una apuesta simétrica a “habrá movimiento fuerte”: ganas en colas altas y bajas del precio '
                'final, a cambio de financiar dos primas desde el día uno.'
            ),
            'resumen_bullets': [
                'Ventaja clave: no tienes que acertar la dirección; tu pérdida máxima acotada es lo pagado por c + p.',
                'Contras habituales: el tiempo y la falta de movimiento te erosionan; necesitas un salto claro para recuperar el doble costo.',
                'Tras un evento, si la volatilidad implícita cae, muchas posiciones largas sufren aunque el spot se mueva.',
                'Peor liquidez y más comisiones = breakevens “más lejos” en la práctica.',
            ],
            'nota_ampliada': (
                'El straddle largo suele compararse con apostar a la “magnitud” del movimiento; tras datos '
                'macro o resultados, una caída brusca de la volatilidad puede hacer que ambas opciones '
                'pierdan valor rápido aunque el spot no quede exactamente en K.'
            ),
            'idea': (
                'Es una forma clara de apostar a “se va a mover fuerte” sin elegir bando. '
                'A cambio, pagas dos entradas y necesitas que el movimiento sea grande para que '
                'valga la pena frente a lo que desembolsaste.'
            ),
            'dato_clave': (
                'Piensa en ello como simetría a favor tuyo en los extremos, y un “valle” incómodo '
                'justo cuando el precio termina pegado al strike.'
            ),
            'enfoque': (
                'La tarjeta verde resume lo que suele gustar del straddle largo; la rosa, lo que más '
                'duele en la práctica (costo, tiempo y sorpresas después de un evento).'
            ),
            'conceptos': [
                'Úsalo como lista de control en clase, no como consejo de inversión.',
                'Si hay un evento y la “nerviosidad” del mercado cae después, muchos straddles largos sufren.',
                'Cuanto más pagas de comisiones y peor es la liquidez, más lejos tiene que ir el precio para notar ganancia.',
            ],
            'ventajas': [
                'Ganas si el precio termina muy arriba o muy abajo del strike, no solo en una dirección.',
                'Sabes desde el inicio el máximo que puedes perder: lo que pagaste por las dos primas.',
                'Solo son dos contratos, mismo strike y misma fecha: fácil de dibujar y de explicar.',
            ],
            'desventajas': [
                'Pagas dos primas de entrada; si nada pasa, el tiempo no suele ser tu aliado.',
                'Necesitas un salto claro del precio para recuperar el boleto doble.',
                'Después de noticias, el mercado a veces “se calma” y las primas bajan; ahí duele.',
            ],
            'demo': 'straddle_pro_con',
        },
        {
            'titulo': 'Las dos patas y el resultado junto',
            'resumen_intro': (
                'El gráfico junta tres payoffs al vencimiento: call sola, put sola y la posición combinada '
                '(straddle), para que veas cómo nace la forma en V del sintético.'
            ),
            'resumen_bullets': [
                'Línea punteada violeta: payoff de la call; tono cálido: payoff de la put.',
                'Línea roja continua con relleno: straddle = call + put − (c + p) al vencer.',
                'Las guías verticales marcan los puntos de equilibrio aproximados (≈92 y ≈108 con c + p = 8).',
                'Cerca de K las dos opciones valen poco al vencer; lejos de K una pata arrastra el resultado.',
            ],
            'nota_ampliada': (
                'Antes del vencimiento el valor de la posición incluye valor temporal y volatilidad; '
                'este gráfico es el payoff teórico en la fecha T, como en los ejercicios de libro.'
            ),
            'idea': (
                'En el gráfico grande ves tres historias al vencimiento: la call sola (línea punteada '
                'violeta), la put sola (punteada en tono cálido) y la mezcla, el straddle, como '
                'línea roja sólida con relleno. Las rayitas verticales marcan dónde empatas con lo '
                'que pagaste (en el ejemplo, alrededor de 92 y 108).'
            ),
            'dato_clave': (
                'El resultado combinado no es magia: es lo que haría la call más lo que haría la put, '
                'menos las dos primas que ya pagaste.'
            ),
            'enfoque': (
                'Si el precio final queda cerca del strike, las dos patas valen poco y lo que pierdes '
                'es básicamente el costo de las primas. Si el precio se va lejos, una pata despierta '
                'y arrastra el resultado total.'
            ),
            'conceptos': [
                'Punteadas: cómo se ve cada opción por su cuenta al vencer.',
                'Línea roja continua: posición combinada (el straddle), la que ves como “sintético”.',
                'Verticales: puntos de equilibrio aproximados respecto a las primas del ejemplo.',
            ],
            'demo': 'straddle_legs_vs_result',
        },
        {
            'titulo': 'Long Straddle · costos, breakevens y perfiles',
            'resumen_intro': (
                'Misma K y mismo vencimiento para ambas patas: pagas c + p por acción y obtienes un perfil '
                'simétrico en forma de V alrededor del strike.'
            ),
            'resumen_bullets': [
                'Costo inicial (por acción): prima de la call más prima de la put.',
                'Breakevens: K ± (c + p); en el ejemplo, 92 y 108.',
                'Pérdida máxima al vencimiento: c + p cuando S_T = K.',
                'Al alza la ganancia es ilimitada en teoría; a la baja el tope teórico es K − (c + p) si S_T → 0.',
            ],
            'nota_ampliada': (
                'Las fórmulas suponen opciones europeas al vencimiento y no incluyen comisiones. '
                'En el pizarrón suele anotarse también que el delta neto cerca del ATM puede ser cercano a cero.'
            ),
            'idea': (
                'La misma call y put largas comparten un solo strike K y vencimiento: pagas c + p '
                'y obtienes un perfil simétrico al vencimiento. La tabla resume en filas el costo, '
                'qué pasa en los extremos de precio, la pérdida máxima y los dos puntos de equilibrio.'
            ),
            'dato_clave': (
                'Cada fila de la derecha aparece en orden con un pequeño “efecto de escritura” visual; '
                'si sales de la diapositiva y vuelves, la secuencia arranca de nuevo.'
            ),
            'enfoque': (
                'Úsala como cierre analítico antes del monitor simulado: conecta el dibujo en V del '
                'straddle con fórmulas compactas que puedes copiar al pizarrón.'
            ),
            'conceptos': [
                'Misma K en call y put · mismo vencimiento T',
                'Dos breakevens: K ± (c + p) — en el ejemplo, 92 y 108',
                'Pérdida máxima = c + p cuando S_T = K',
                'Ganancia al alza ilimitada; a la baja, tope teórico K − (c + p) si S_T → 0',
            ],
            'demo': 'straddle_formulas',
        },
        {
            'titulo': 'Sell Straddle · lo básico (lógica inversa)',
            'resumen_intro': (
                'Es la versión espejo del buy straddle: vendes call y put con misma K y mismo vencimiento, '
                'cobras c + p al inicio y te favorece que el precio final quede cerca del strike.'
            ),
            'resumen_bullets': [
                'Cobras las dos primas por adelantado: en el ejemplo, c + p = 8 con K = 100.',
                'El máximo beneficio ocurre si S_T termina en K: te quedas con el premio total.',
                'Empatas en los mismos breakevens K ± (c + p), aquí cerca de 92 y 108.',
                'Si el precio se aleja mucho de K, las pérdidas crecen (sobre todo al alza).',
            ],
            'nota_ampliada': (
                'En operación real suelen exigir margen porque hay riesgo de pérdidas grandes, y también '
                'pegan comisiones y spreads en ambas patas.'
            ),
            'idea': (
                'Piensa el sell straddle como la foto invertida del buy: en vez de pagar para apostar a '
                'movimiento fuerte, cobras por apostar a que el activo no se moverá demasiado al vencimiento.'
            ),
            'dato_clave': (
                'Perfil al vencimiento: una “V” invertida con pico en K; ganancia máxima = c + p y breakevens '
                'en K ± (c + p).'
            ),
            'enfoque': (
                'Sirve para introducir rápidamente la simetría inversa: mismo armado de strikes/fecha, pero '
                'resultado opuesto al comprador.'
            ),
            'conceptos': [
                'Misma estructura técnica que el long straddle, pero invertida en payoff.',
                'Mejor escenario: precio final “pegado” al strike.',
                'Escenario delicado: movimiento fuerte fuera del rango de equilibrio.',
            ],
            'demo': 'straddle_sell_basico',
        },
        {
            'titulo': 'Sell Straddle · ventajas y desventajas',
            'resumen_intro': (
                'La apuesta ahora es “mercado tranquilo”: cobras prima hoy a cambio de asumir riesgo si mañana '
                'hay un desplazamiento fuerte del precio.'
            ),
            'resumen_bullets': [
                'Ventaja principal: ingreso inicial por c + p y mejor zona cerca de K al vencimiento.',
                'Contras: riesgo grande en colas, en especial si el activo sube mucho.',
                'No necesitas adivinar dirección, pero sí estimar que no habrá salto fuerte.',
                'Suele requerir margen y una gestión de riesgo más estricta.',
            ],
            'nota_ampliada': (
                'Pedagógicamente es útil contrastarlo con el buy: uno compra convexidad, el otro la vende.'
            ),
            'idea': (
                'El sell straddle puede verse como “cobrar seguro” contra movimiento extremo: funciona cuando '
                'el precio se queda en una zona acotada, pero sufre si el mercado entra en modo sorpresa.'
            ),
            'dato_clave': (
                'Es la misma lógica de dos patas y mismo strike/vencimiento, pero con signos invertidos en casi '
                'todo el perfil de riesgo/retorno.'
            ),
            'enfoque': (
                'Úsala como checklist rápida: cuándo podría encajar, qué duele y por qué conviene remarcar el '
                'tema de margen y control de riesgo.'
            ),
            'conceptos': [
                'Gana más cuando no hay gran desplazamiento del spot al vencimiento.',
                'Pierde si el precio rompe fuerte por arriba o por abajo.',
                'En práctica real, costos y liquidez pueden achicar el colchón de primas.',
            ],
            'ventajas': [
                'Cobras primas al inicio y tu mejor zona está alrededor del strike.',
                'No exige acertar si sube o baja; te importa que no se dispare el movimiento.',
                'Misma estructura de dos contratos con K y T iguales: fácil de explicar en espejo con el long.',
                'Si el subyacente se queda en rango, el paso del tiempo suele jugar a favor del vendedor.',
            ],
            'desventajas': [
                'Riesgo alto en movimientos extremos, especialmente en subidas fuertes.',
                'Requiere margen y disciplina de gestión de riesgo.',
                'Eventos inesperados y saltos de volatilidad pueden deteriorar rápido la posición.',
                'Una mala gestión del riesgo puede borrar varias primas cobradas en poco tiempo.',
            ],
            'demo': 'straddle_sell_pro_con',
        },
        {
            'titulo': 'Escenarios al vencimiento · Buy vs Sell',
            'resumen_intro': (
                'Antes del monitor, compara escenarios discretos de precio final para ver el espejo '
                'entre buy straddle y sell straddle en una sola lámina.'
            ),
            'resumen_bullets': [
                'En S_T por debajo del break-even inferior, buy mejora y sell se deteriora.',
                'En zona media (cerca de K), buy suele perder prima y sell suele capturarla.',
                'En S_T por arriba del break-even superior, buy vuelve a mejorar y sell vuelve a sufrir.',
                'El cuadro resume ITM/ATM/OTM de call y put por escenario.',
            ],
            'nota_ampliada': (
                'Es una diapositiva puente: ayuda a pasar del payoff estático a la lectura dinámica '
                'del monitor sin perder la lógica de estados por pata.'
            ),
            'idea': (
                'En lugar de mirar solo curvas, aquí tomas algunos precios finales y lees de inmediato '
                'qué pasa con cada estrategia y con cada pata. Así conectas el dibujo con decisiones.'
            ),
            'dato_clave': (
                'El mismo S_T puede ser ITM para una pata y OTM para la otra; por eso el straddle '
                'captura movimiento en ambos sentidos.'
            ),
            'enfoque': (
                'Úsala como checklist previa al simulador: estado de call, estado de put, P/L buy y P/L sell.'
            ),
            'conceptos': [
                'Buy y sell son espejos en payoff al vencimiento.',
                'Call larga: ITM cuando S_T > K; Put larga: ITM cuando S_T < K.',
                'En S_T = K: estado ATM y máxima pérdida del buy (máxima ganancia del sell).',
            ],
            'demo': 'straddle_escenarios',
        },
        {
            'titulo': 'Monitor de juguete (simulación)',
            'resumen_intro': (
                'Es un tablero de demostración: cada 2.5 segundos se sortea un precio del activo y se recalcula '
                'el resultado del buy y del sell straddle como si ese fuera el precio al vencimiento.'
            ),
            'resumen_bullets': [
                'No son cotizaciones reales: solo sirve para ver cómo “late” el payoff cuando cambia el spot.',
                'La franja roja sigue el buy straddle y la línea verde sigue el sell straddle (inverso).',
                'Arriba verás spot simulado, prima total, P/L buy, P/L sell y distancia al breakeven más cercano.',
                'Puedes pausar el reloj para discutir con el salón qué podría pasar en el siguiente tick.',
            ],
            'nota_ampliada': (
                'El monitor ignora valor temporal, cambios de volatilidad y dividendos: solo proyecta el '
                'payoff de largo straddle como función del precio final, para fijar ideas.'
            ),
            'idea': (
                'Es un tablero de demostración: cada 2.5 segundos el programa inventa un precio del activo, '
                'recalcula cuánto ganarías o perderías al vencimiento con ese precio en buy y sell, y actualiza el '
                'gráfico. No son precios reales de bolsa. Sirve para ver cómo “late” la idea del straddle '
                'cuando el mercado se mueve.'
            ),
            'dato_clave': (
                'Puedes pausar el reloj con el botón y leer con calma; al reanudar, vuelve el tick cada 2.5 s.'
            ),
            'enfoque': (
                'Compara espejos en tiempo real: cuando buy mejora, sell empeora, y viceversa. '
                'Así se visualiza rápido la lógica inversa entre ambas posiciones.'
            ),
            'conceptos': [
                'Los números de arriba cambian con el precio simulado: spot, primas totales, resultado buy, resultado sell y distancia al equilibrio.',
                'El eje horizontal son pasos de tiempo (cada paso = 2.5 segundos de simulación).',
                'Si enseñas en vivo, pausa antes de preguntar al salón “¿qué creen que pasará en el siguiente tick?”.',
            ],
            'demo': 'straddle_live',
        },
        {
            'titulo': 'Conclusiones',
            'resumen_intro': (
                'Cierre ejecutivo de la estrategia: cuándo tiene sentido, qué vigilar y cómo evitar '
                'lecturas incompletas del payoff.'
            ),
            'resumen_bullets': [
                'Buy straddle compra convexidad: necesita desplazamiento relevante de S_T.',
                'Sell straddle monetiza calma: sufre en eventos y colas de precio.',
                'Entre K − (c + p) y K + (c + p) el comprador suele quedar detrás al vencer: pagó dos primas y hace falta que el spot salga del corredor para empatar.',
                'Long suele odiar una caída brusca de la volatilidad implícita tras la noticia; short cobra esas primas pero asume pérdidas crecientes si el precio rompe fuerte fuera de los breakevens.',
            ],
            'nota_ampliada': (
                'El marco presentado es pedagógico y al vencimiento; para operación real hay que sumar '
                'volatilidad implícita, liquidez, costos y gestión de riesgo.'
            ),
            'idea': (
                'La misma estructura técnica puede jugar a favor o en contra según el régimen del mercado. '
                'La clave no es memorizar la V, sino leer contexto, costo y distancia a equilibrio.'
            ),
            'dato_clave': (
                'Sin movimiento suficiente, el buy suele perder por prima; con sobresaltos fuertes, '
                'el sell concentra el riesgo.'
            ),
            'enfoque': (
                'Como cierre docente, resume: tesis de mercado, corredor K ± (c + p) y contraste long/short '
                'entre volatilidad implícita y riesgo en colas.'
            ),
            'conceptos': [
                'Define primero el escenario esperado (calma vs movimiento).',
                'Cuantifica siempre breakevens y costo total.',
                'Recuerda que el straddle largo gana por magnitud del movimiento respecto a K, no por acertar la dirección.',
            ],
            'demo': 'straddle_conclusiones',
        },
    ]

    ejemplo = {
        'spot': 100,
        'K': 100,
        'c': 5,
        'p': 3,
        'premio_total': 8,
        'bep_sup': 108,
        'bep_inf': 92,
        'subyacente': 'Activo subyacente (spot simulado)',
    }

    context = {
        'slides': slides,
        'ejemplo': ejemplo,
    }
    return render(request, 'core/expo_sinteticos.html', context)


def expo_cierre_view(request):
    """
    Presentación de cierre del proyecto. Acceso solo por URL directa; no se
    enlaza desde el resto de la plataforma. Pensada para una exposición de
    ~7 minutos (≈45-50 s por slide).
    """
    proyecto = {
        'nombre': 'Plataforma estratégica de visualización académica',
        'subtitulo': 'Cierre del proyecto',
        'autor': 'Juan Pablo Penedo Antúnez',
        'matricula': '00444052',
        'materia': 'Proyecto Actuarial Aplicado II',
        'institucion': 'Universidad Anáhuac Puebla · Licenciatura en Actuaría',
    }

    slides = [
        {
            # Slide 1: portada con donut de avance + hero metrics
            'demo': 'cierre_portada',
            'layout': 'hero_chart',
            'titulo': 'De datos dispersos a decisiones académicas',
            'subtitulo_slide': 'Síntesis del proyecto',
            'lead': (
                'Una capa visual de interpretación sobre datos curriculares: '
                'avance, requisitos y alertas en una sola lectura.'
            ),
            'bullets': [
                'No modifica los sistemas oficiales.',
                'Diseñado para Actuaría · Anáhuac Puebla.',
                'Lean: valor con recursos disponibles.',
            ],
            'side_kind': 'avance_donut',
            'chart': {
                'kind': 'donut_avance',
                'usados': 330,
                'requeridos': 366,
            },
            'hero_metrics': [
                {'label': 'Plan', 'value': '366 cr.'},
                {'label': 'Módulos', 'value': '5'},
                {'label': 'Cronograma', 'value': 'Feb–May'},
            ],
        },
        {
            # Slide 2: fenómeno con vista docente — distribución de calificaciones
            # Cálculo Actuarial (lo que un profesor vería en su dashboard).
            'demo': 'cierre_fenomeno',
            'layout': 'split_chart',
            'titulo': 'Información sin lectura',
            'subtitulo_slide': 'El fenómeno',
            'lead': (
                'Hoy la información académica vive dispersa entre planes, '
                'sistemas escolares y normativas. Existe, pero pocas veces '
                'se convierte en lectura útil para decidir a tiempo.'
            ),
            'bullets': [
                'Coordinación arma los reportes por generación con datos dispersos y a mano.',
                'Cada área toma decisiones con criterios distintos: no hay un tablero común.',
                'El rezago se detecta al cierre del ciclo, no durante el periodo activo.',
                'En paralelo, el estudiante tarda en identificar qué bloquea su trayectoria.',
            ],
            'side_kind': 'docente_calculo',
            'chart': {
                'kind': 'stacked_calificaciones',
                'labels': ['Parcial 1', 'Parcial 2', 'Parcial 3', 'Final'],
                'series': [
                    {'name': 'Sobresaliente (9-10)', 'data': [3, 5, 7, 9]},
                    {'name': 'Bueno (8-9)', 'data': [8, 11, 13, 13]},
                    {'name': 'Aceptable (7-8)', 'data': [8, 8, 6, 5]},
                    {'name': 'Riesgo (6-7)', 'data': [5, 3, 2, 1]},
                    {'name': 'No aprobado (<6)', 'data': [4, 1, 0, 0]},
                ],
                'titulo': 'Cálculo Actuarial · Distribución de calificaciones',
                'subtitulo': 'Vista del docente · 28 alumnos · 5to semestre',
            },
        },
        {
            # Slide 3: utilidad - sólo módulo cards en grid amplio (sin chart)
            'demo': 'cierre_utilidad',
            'layout': 'full_cards',
            'titulo': 'Cinco módulos, una sola lectura',
            'subtitulo_slide': 'Qué hace la plataforma',
            'lead': 'Centraliza, organiza y visualiza datos curriculares sin alterar las fuentes oficiales.',
            'bullets': [],
            'side_kind': 'module_cards',
            'modules': [
                {'icon': 'graph-up', 'titulo': 'Avance curricular', 'desc': 'Materias aprobadas, en curso y pendientes.'},
                {'icon': 'list-check', 'titulo': 'Requisitos académicos', 'desc': 'Titulación, seriaciones, atributos.'},
                {'icon': 'people', 'titulo': 'Dashboard docente', 'desc': 'Indicadores agregados por grupo.'},
                {'icon': 'exclamation-triangle', 'titulo': 'Alertas académicas', 'desc': 'Señales tempranas de rezago.'},
                {'icon': 'clipboard-data', 'titulo': 'Reportes estratégicos', 'desc': 'Patrones de avance y permanencia.'},
            ],
        },
        {
            # Slide 4: tres casos de uso reales con la misma estructura visual.
            'demo': 'cierre_usuarios',
            'layout': 'persona_full',
            'titulo': 'Tres momentos donde cambia la decisión',
            'subtitulo_slide': 'Casos de uso reales',
            'lead': (
                'Escenarios concretos donde una lectura integrada de '
                'los datos curriculares transforma una decisión académica '
                'cotidiana.'
            ),
            'bullets': [],
            'side_kind': 'persona_cards',
            'personas': [
                {
                    'rol': 'Planeación de inscripción',
                    'icon': 'calendar-check',
                    'kpi': 'Planear',
                    'kpi_label': 'Antes del semestre',
                    'puntos': [
                        'Trayectoria del alumno en una sola pantalla.',
                        'Seriaciones y requisitos visibles al instante.',
                        'Carga semestral planeada con evidencia.',
                    ],
                },
                {
                    'rol': 'Tutoría semanal',
                    'icon': 'chat-square-text',
                    'kpi': 'Acompañar',
                    'kpi_label': 'Durante el ciclo',
                    'puntos': [
                        'El docente revisa al grupo en segundos.',
                        'Identifica riesgos para enfocar la sesión.',
                        'Bitácora de seguimiento basada en datos.',
                    ],
                },
                {
                    'rol': 'Comité académico',
                    'icon': 'graph-up-arrow',
                    'kpi': 'Diagnosticar',
                    'kpi_label': 'Cierre del periodo',
                    'puntos': [
                        'Patrones de avance por generación.',
                        'Comparativas entre cohortes y áreas.',
                        'Decisiones de acompañamiento institucional.',
                    ],
                },
            ],
        },
        {
            # Slide 5: fundamento con vista coordinación — distribución por
            # generación (gráfico que sí podría ver el administrativo).
            'demo': 'cierre_fundamento',
            'layout': 'chart_full_top',
            'titulo': 'Cinco ejes que sostienen el proyecto',
            'subtitulo_slide': 'Fundamento teórico · vista coordinación',
            'lead': (
                'Cinco principios que conectan la necesidad institucional '
                'con literatura de analítica educativa, ilustrados con '
                'una vista típica del panel de coordinación.'
            ),
            'bullets': [],
            'side_kind': 'fundamento_coord',
            'chart': {
                'kind': 'stacked_generaciones',
                'labels': ['Generación 2022', 'Generación 2023', 'Generación 2024', 'Generación 2025'],
                'series': [
                    {'name': 'Al corriente', 'data': [78, 71, 65, 58]},
                    {'name': 'Rezago leve', 'data': [15, 19, 22, 26]},
                    {'name': 'Rezago alto', 'data': [5, 7, 9, 11]},
                    {'name': 'Irregular', 'data': [2, 3, 4, 5]},
                ],
                'titulo': 'Estado académico por generación',
                'subtitulo': 'Vista de coordinación · % de alumnos por cohorte',
            },
            'pillars': [
                {'n': '01', 'titulo': 'Trayectoria académica', 'desc': 'El avance como ruta curricular completa, no como suma aislada de materias.'},
                {'n': '02', 'titulo': 'Analítica del aprendizaje', 'desc': 'Lectura descriptiva-diagnóstica para comprender, no para predecir invasivamente.'},
                {'n': '03', 'titulo': 'Dashboard accionable', 'desc': 'Mostrar lleva a decidir; visualizar es solo el primer paso.'},
                {'n': '04', 'titulo': 'Autorregulación', 'desc': 'Información clara mejora la planeación del propio estudiante.'},
                {'n': '05', 'titulo': 'Uso responsable', 'desc': 'Datos académicos sensibles requieren reglas claras de acceso y propósito.'},
            ],
        },
        {
            # Slide 6: mejoras - tabla compacta (texto importante, sin chart)
            'demo': 'cierre_mejoras',
            'layout': 'split_table',
            'titulo': 'Dónde puede crecer',
            'subtitulo_slide': 'Limitaciones y áreas de mejora',
            'lead': 'La hoja de ruta del prototipo antes de un despliegue institucional.',
            'bullets': [
                'Calidad de datos como base.',
                'Modelos explicables, no cajas negras.',
                'Adopción progresiva, no impositiva.',
            ],
            'side_kind': 'improve_table',
            'mejoras': [
                {'reto': 'Extracción de CAP', 'estado': 'PDF con NaN', 'siguiente': 'Lectura jerárquica + validación con totales oficiales.'},
                {'reto': 'Integración', 'estado': 'Carga manual', 'siguiente': 'Conector institucional en modo lectura.'},
                {'reto': 'Alertas', 'estado': 'Reglas básicas', 'siguiente': 'Modelos diagnósticos explicables.'},
                {'reto': 'Adopción', 'estado': 'Prototipo', 'siguiente': 'Piloto con docentes y coordinación.'},
                {'reto': 'Privacidad', 'estado': 'Acceso por rol', 'siguiente': 'Auditoría y anonimización en agregados.'},
            ],
        },
        {
            # Slide 7: conclusiones con combo dashboard (barras + línea).
            'demo': 'cierre_conclusiones',
            'layout': 'chart_full_top',
            'titulo': 'A qué se concluye',
            'subtitulo_slide': 'Conclusiones del proyecto',
            'lead': (
                'Las conclusiones se ven mejor en un mini-dashboard: '
                'consultas mensuales por rol y porcentaje global de '
                'adopción de la plataforma.'
            ),
            'bullets': [],
            'side_kind': 'dashboard_combo',
            'chart': {
                'kind': 'combo_adopcion',
                'labels': ['Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul'],
                'series': [
                    {'name': 'Estudiantes', 'data': [120, 180, 240, 300, 340, 380]},
                    {'name': 'Docentes', 'data': [40, 65, 90, 110, 130, 145]},
                    {'name': 'Coordinación', 'data': [10, 18, 28, 35, 42, 48]},
                ],
                'line': {'name': 'Adopción global (%)', 'data': [22, 38, 55, 68, 78, 86]},
                'titulo': 'Consultas mensuales y adopción global',
                'subtitulo': 'Proyección estimada del piloto · Feb–Jul',
            },
            'conclusiones': [
                {'n': '1', 'titulo': 'Tesis', 'desc': 'Datos sí; lo que faltaba era una lectura integrada.'},
                {'n': '2', 'titulo': 'Capa', 'desc': 'Organiza sin sustituir a los sistemas oficiales.'},
                {'n': '3', 'titulo': 'Impacto', 'desc': 'Menos tiempo de consulta y más claridad para decidir.'},
                {'n': '4', 'titulo': 'Alcance', 'desc': 'Prototipo viable, iterable y listo para piloto.'},
            ],
        },
        {
            # Slide 8: roadmap timeline horizontal con barra de carga animada
            # (avanza una sola vez, los hitos quedan iluminados de forma persistente).
            'demo': 'cierre_siguiente',
            'layout': 'timeline_full',
            'titulo': 'Del prototipo al despliegue institucional',
            'subtitulo_slide': 'Plan de iteraciones',
            'lead': (
                'Cuatro fases para llevar el prototipo a una herramienta '
                'institucional adoptada, con métricas claras en cada paso.'
            ),
            'bullets': [],
            'side_kind': 'roadmap_timeline',
            'roadmap': [
                {'fase': 'Fase 1', 'titulo': 'Validación', 'desc': 'Sesiones con docentes y coordinación.', 'icon': 'people'},
                {'fase': 'Fase 2', 'titulo': 'Integración', 'desc': 'Conector institucional no destructivo.', 'icon': 'plug'},
                {'fase': 'Fase 3', 'titulo': 'Alertas', 'desc': 'Modelos explicables de rezago temprano.', 'icon': 'bell'},
                {'fase': 'Fase 4', 'titulo': 'Adopción', 'desc': 'Indicadores de uso y utilidad real.', 'icon': 'graph-up-arrow'},
            ],
        },
        {
            # Slide 9: cierre — mini visualización de la plataforma que se
            # auto-conduce + 4 ideas a llevarse, con textos más explicativos.
            'demo': 'cierre_final',
            'layout': 'closing_chart',
            'titulo': 'Una versión inicial, no un punto final',
            'subtitulo_slide': 'Cierre',
            'lead': (
                'Lo que queda al final: una capa visual sobre datos que '
                'ya existían, decisiones académicas mejor informadas y un '
                'punto de partida abierto a iteración.'
            ),
            'bullets': [],
            'side_kind': 'closing_mock',
            'closing_items': [
                {
                    'n': '1',
                    'titulo': 'Tesis verificada',
                    'desc': 'La información académica ya existía: el aporte está en convertirla en una lectura útil para decidir.',
                },
                {
                    'n': '2',
                    'titulo': 'Plataforma como capa',
                    'desc': 'No sustituye sistemas oficiales: los organiza, los conecta y los presenta con sentido.',
                },
                {
                    'n': '3',
                    'titulo': 'Impacto medible',
                    'desc': 'Menos tiempo de consulta, más claridad del avance y decisiones académicas con evidencia.',
                },
                {
                    'n': '4',
                    'titulo': 'Camino abierto',
                    'desc': 'Próximo paso: iterar con quienes la usan y medir su adopción real en piloto institucional.',
                },
            ],
        },
    ]

    # IMPORTANT: serializar el payload del chart a JSON aquí evita que Django
    # imprima la repr de Python (con comillas simples) dentro del atributo HTML
    # `data-payload`, lo que rompía el parse en JavaScript y dejaba los charts
    # con ejes pero sin datos.
    for slide in slides:
        chart_data = slide.get('chart')
        if chart_data:
            slide['chart_json'] = json.dumps(chart_data, ensure_ascii=False)

    context = {
        'proyecto': proyecto,
        'slides': slides,
    }
    return render(request, 'core/expo_cierre.html', context)


def proyecto_ods16_view(request):
    """
    Plataforma funcional 'Denuncia Verde' (ODS 16 · Paz, justicia e instituciones
    sólidas). Implementa literalmente lo que describen las actividades 1b, 2a, 3a
    y 3b: canal seguro de denuncia ciudadana sobre corrupción ambiental,
    contenidos educativos socioambientales y difusión de derechos.

    Sin base de datos: las denuncias de usuarios se persisten en localStorage.
    La vista sólo provee los datos de apoyo (módulos, denuncias de ejemplo,
    marco conceptual) al template.
    """
    equipo = [
        {'nombre': 'Juan Pablo Penedo Antúnez',      'correo': 'juan.penedo@anahuac.mx'},
        {'nombre': 'David Manuel Ruiz Pérez',        'correo': 'david.ruiz11@anahuac.mx'},
        {'nombre': 'Leonardo Mayoral García',        'correo': 'leonardo.mayoral@anahuac.mx'},
        {'nombre': 'Pablo Andrés Pacheco Colmenares','correo': 'pablo.pacheco@anahuac.mx'},
    ]

    # ODS que atiende el proyecto (principal + secundarios).
    ods = [
        {
            'num': 16, 'color': '#00689D',
            'nombre': 'Paz, justicia e instituciones sólidas',
            'meta': 'Meta 16.5 · Reducir considerablemente la corrupción y el soborno en todas sus formas',
            'icono': 'bi-shield-check',
            'aporte': (
                'Creamos un canal seguro de denuncia ciudadana de prácticas corruptas '
                'que afectan el medio ambiente, fortaleciendo la transparencia y la '
                'rendición de cuentas en la gestión de recursos naturales.'
            ),
            'principal': True,
        },
        {
            'num': 13, 'color': '#48773C',
            'nombre': 'Acción por el clima',
            'meta': 'Meta 13.3 · Educación, sensibilización y capacidad humana frente al cambio climático',
            'icono': 'bi-globe-americas',
            'aporte': (
                'Talleres de educación socioambiental y contenidos en la plataforma '
                'que ayudan a la comunidad a entender el impacto de prácticas '
                'irresponsables sobre el clima y los ecosistemas.'
            ),
            'principal': False,
        },
        {
            'num': 15, 'color': '#56C02B',
            'nombre': 'Vida de ecosistemas terrestres',
            'meta': 'Meta 15.1 · Conservación y uso sostenible de los ecosistemas terrestres',
            'icono': 'bi-tree',
            'aporte': (
                'Denuncias específicas de tala ilegal, uso indebido del agua o del '
                'suelo; vigilancia ciudadana sobre los ecosistemas locales de Querétaro.'
            ),
            'principal': False,
        },
    ]

    # 3 dimensiones de la responsabilidad social.
    dimensiones = [
        {
            'nombre': 'Social', 'icono': 'bi-people-fill', 'color': 'blue',
            'texto': (
                'Participación activa de la comunidad vía plataforma de denuncias '
                'seguras y talleres formativos. Fortalecer la cultura de legalidad '
                'y recuperar la confianza en las instituciones públicas.'
            ),
        },
        {
            'nombre': 'Ambiental', 'icono': 'bi-tree-fill', 'color': 'green',
            'texto': (
                'Reducción de la impunidad ambiental: supervisión social sobre '
                'tala ilegal, uso indebido del agua y sobreexplotación de recursos. '
                'Aumentar la vigilancia y reducir la discrecionalidad (Klitgaard).'
            ),
        },
        {
            'nombre': 'Económica', 'icono': 'bi-cash-coin', 'color': 'gold',
            'texto': (
                'Condiciones más equitativas en la gestión de recursos naturales, '
                'menos costos por deterioro ambiental y un desarrollo local más '
                'transparente y sostenible.'
            ),
        },
    ]

    # ISO 26000 · los 7 principios.
    iso_principios = [
        {'n': 1, 'nombre': 'Rendición de cuentas',         'icono': 'bi-clipboard-check'},
        {'n': 2, 'nombre': 'Transparencia',                'icono': 'bi-eye'},
        {'n': 3, 'nombre': 'Comportamiento ético',         'icono': 'bi-award'},
        {'n': 4, 'nombre': 'Respeto a partes interesadas', 'icono': 'bi-people'},
        {'n': 5, 'nombre': 'Respeto al principio de legalidad',          'icono': 'bi-journal-check'},
        {'n': 6, 'nombre': 'Respeto a la normativa internacional',        'icono': 'bi-globe2'},
        {'n': 7, 'nombre': 'Respeto a los derechos humanos','icono': 'bi-heart'},
    ]

    # ISO 26000 · las 7 materias fundamentales.
    iso_materias = [
        {'nombre': 'Gobernanza organizacional',           'icono': 'bi-building',    'activa': True},
        {'nombre': 'Derechos humanos',                    'icono': 'bi-person-heart','activa': True},
        {'nombre': 'Prácticas laborales',                 'icono': 'bi-briefcase',   'activa': False},
        {'nombre': 'Medio ambiente',                      'icono': 'bi-tree',        'activa': True},
        {'nombre': 'Prácticas justas de operación',       'icono': 'bi-scale',       'activa': True},
        {'nombre': 'Asuntos de consumidores',             'icono': 'bi-shield-lock', 'activa': False},
        {'nombre': 'Participación activa y desarrollo de la comunidad',
         'icono': 'bi-hand-thumbs-up','activa': True},
    ]

    # Doctrina Social de la Iglesia · 2 principios aplicados.
    dsi = [
        {
            'principio': 'Bien común',
            'idea': (
                'La sociedad debe orientarse a crear condiciones que permitan a '
                'todas las personas desarrollarse con dignidad. El agua, los '
                'ecosistemas y los espacios naturales son bienes que pertenecen a '
                'toda la sociedad.'
            ),
            'aplicacion': (
                'La plataforma permite que los ciudadanos vigilen activamente el '
                'uso de esos bienes compartidos, promoviendo transparencia y '
                'corresponsabilidad colectiva en el cuidado del entorno.'
            ),
            'icono': 'bi-people-fill',
        },
        {
            'principio': 'Subsidiariedad',
            'idea': (
                'Las decisiones deben tomarse en el nivel más cercano posible a '
                'las personas afectadas. Las comunidades locales tienen un papel '
                'fundamental en la solución de sus propios problemas.'
            ),
            'aplicacion': (
                'La comunidad se convierte en actor central: denuncia, recibe '
                'educación cívica ambiental y se organiza. Las instituciones '
                'apoyan sin sustituir la iniciativa ciudadana.'
            ),
            'icono': 'bi-diagram-3-fill',
        },
    ]

    # Derechos humanos relacionados.
    derechos = [
        {
            'nombre': 'A un medio ambiente sano',
            'fuente': 'ONU, 2022',
            'icono': 'bi-tree-fill',
            'como': (
                'Denuncia de tala ilegal, uso indebido del agua y actividades que '
                'degradan los ecosistemas. Vinculación con autoridades ambientales '
                'para dar seguimiento a los reportes.'
            ),
        },
        {
            'nombre': 'A la participación ciudadana',
            'fuente': 'DUDH, 1948',
            'icono': 'bi-megaphone-fill',
            'como': (
                'Espacio para expresar preocupaciones, denunciar irregularidades '
                'de forma anónima y segura, e involucrarse en procesos de '
                'educación cívica y ambiental.'
            ),
        },
        {
            'nombre': 'De acceso a la información',
            'fuente': 'DUDH, 1948',
            'icono': 'bi-info-circle-fill',
            'como': (
                'Difusión de información clara sobre derechos ambientales, '
                'mecanismos de denuncia y educación cívica. Materiales '
                'confiables basados en fuentes oficiales.'
            ),
        },
    ]

    # Matriz de grupos de interés.
    stakeholders = [
        {
            'nombre': 'Comunidad Local', 'icono': 'bi-people',
            'relacion': 'Beneficiarios y usuarios directos de la plataforma y los talleres.',
            'contribucion': (
                'Reportar prácticas corruptas, participar en actividades '
                'socioambientales, reforzar la vigilancia ciudadana y la cultura '
                'de legalidad.'
            ),
        },
        {
            'nombre': 'Universidades', 'icono': 'bi-mortarboard',
            'relacion': 'Colaboradores en desarrollo tecnológico y apoyo educativo.',
            'contribucion': (
                'Investigación, voluntariado, asistencia técnica en talleres y '
                'desarrollo de la plataforma.'
            ),
        },
        {
            'nombre': 'Gobierno y autoridades', 'icono': 'bi-bank',
            'relacion': 'Receptores de denuncias; responsables del seguimiento.',
            'contribucion': (
                'Que las denuncias tengan efecto real: transparencia, rendición '
                'de cuentas y protección efectiva de los recursos naturales.'
            ),
        },
        {
            'nombre': 'Organizaciones medioambientales', 'icono': 'bi-globe-americas',
            'relacion': 'Aliados estratégicos en capacitación, asesoría y difusión.',
            'contribucion': (
                'Experiencia en participación ciudadana, transparencia y '
                'protección del medio ambiente que refuerza el impacto social.'
            ),
        },
        {
            'nombre': 'Empresas', 'icono': 'bi-buildings',
            'relacion': 'Actores que dependen o utilizan recursos naturales.',
            'contribucion': (
                'Adoptar prácticas sostenibles y transparentes; participar en '
                'un desarrollo económico responsable.'
            ),
        },
    ]

    # Fases del proyecto piloto (6 meses).
    fases = [
        {
            'numero': 1, 'titulo': 'Diseño de la plataforma', 'duracion': '2 meses',
            'actividades': [
                'Desarrollo de la plataforma web y el sistema de denuncia segura',
                'Creación de contenidos educativos (talleres, videos y clases)',
                'Vinculación con instituciones (preparatorias, secundarias, etc.)',
            ],
            'recursos': '1 coordinador · 1 programador · 1 asesor jurídico ambiental · 1 especialista educativo',
        },
        {
            'numero': 2, 'titulo': 'Implementación del piloto', 'duracion': '3 meses',
            'actividades': [
                'Lanzamiento de la plataforma en una comunidad o institución educativa',
                'Talleres formativos con alumnos, vecinos y organizaciones',
                'Activación del sistema de denuncia anónima + vínculo con autoridades',
            ],
            'recursos': '2 facilitadores + voluntarios',
        },
        {
            'numero': 3, 'titulo': 'Evaluación y ajustes', 'duracion': '1 mes',
            'actividades': [
                'Medición de indicadores (denuncias recibidas, asistencia, usuarios)',
                'Ajustes tecnológicos en la plataforma con base en retroalimentación',
                'Cierre del piloto y documentación del caso para escalamiento',
            ],
            'recursos': 'Equipo completo + voluntarios · presupuesto piloto $40K–$45K MXN',
        },
    ]

    # Tipos de irregularidades que la plataforma permite reportar.
    # `icon` referencia una clave del catálogo de iconos SVG en el template.
    tipos_denuncia = [
        {'valor': 'tala_ilegal',       'etiqueta': 'Tala ilegal',                   'icon': 'tree'},
        {'valor': 'uso_agua',          'etiqueta': 'Uso indebido del agua',         'icon': 'drop'},
        {'valor': 'uso_suelo',         'etiqueta': 'Uso indebido del suelo',        'icon': 'soil'},
        {'valor': 'contaminacion',     'etiqueta': 'Contaminación o residuos',      'icon': 'factory'},
        {'valor': 'fauna',             'etiqueta': 'Daño a fauna o flora',          'icon': 'leaf'},
        {'valor': 'otro',              'etiqueta': 'Otra irregularidad ambiental',  'icon': 'warning'},
    ]

    # Denuncias "semilla" visibles desde el primer momento para que la plataforma
    # no se vea vacía. No son reales: son ejemplos representativos.
    denuncias_demo = [
        {
            'id': 'demo-1', 'tipo': 'Tala ilegal', 'tipo_valor': 'tala_ilegal',
            'lugar': 'Sierra de El Zamorano, Colón', 'fecha': '2026-03-18',
            'descripcion': (
                'Se observan cortes recientes de encino en una ladera protegida. '
                'Presencia de camionetas sin identificación cargando madera al '
                'anochecer.'
            ),
            'estado': 'En seguimiento',
        },
        {
            'id': 'demo-2', 'tipo': 'Uso indebido del agua', 'tipo_valor': 'uso_agua',
            'lugar': 'Huimilpan', 'fecha': '2026-03-22',
            'descripcion': (
                'Extracción aparentemente no autorizada desde un pozo hacia pipas '
                'particulares en horario nocturno. Vecinos reportan baja presión '
                'en la red comunitaria.'
            ),
            'estado': 'Recibida',
        },
        {
            'id': 'demo-3', 'tipo': 'Contaminación / residuos', 'tipo_valor': 'contaminacion',
            'lugar': 'Arroyo de San Pedrito, Querétaro', 'fecha': '2026-04-04',
            'descripcion': (
                'Descarga de líquidos con coloración oscura y olor fuerte desde '
                'una nave industrial. Mancha visible en el cauce durante 200 m.'
            ),
            'estado': 'Enviada a autoridad',
        },
    ]

    # Módulos educativos de la plataforma (Meta ODS 13.3).
    # Cada módulo contiene: resumen, contenido estructurado por secciones
    # (cada sección con párrafos + bullets opcionales), un video de YouTube
    # embebido (cuando está disponible) y enlaces externos verificados.
    # `icon` hace referencia a un catálogo de iconos SVG en el template.
    modulos = [
        {
            'id': 'mod-corrupcion',
            'titulo': 'Qué es la corrupción ambiental',
            'duracion': '12 min',
            'nivel': 'Básico',
            'icon': 'book',
            'resumen': (
                'Cómo el abuso del poder se traduce en daño directo a los '
                'ecosistemas que compartimos. Marco de Klitgaard, tipologías '
                'y panorama mexicano.'
            ),
            'video_id': 'TPdBE_zPt-s',
            'video_title': 'La corrupción: análisis desde el poder político',
            'video_credit': 'Contexto sobre cómo la corrupción estructural habilita delitos ambientales.',
            'objetivos': [
                'Distinguir corrupción administrativa, política y ambiental.',
                'Aplicar la ecuación de Klitgaard a casos locales.',
                'Reconocer señales de corrupción ambiental en tu entorno.',
            ],
            'contenido': [
                {
                    'titulo': 'Definición operativa',
                    'parrafos': [
                        'Hablamos de corrupción ambiental cuando una persona '
                        'con poder público o privado desvía decisiones, '
                        'permisos o recursos que debían proteger el medio '
                        'ambiente para obtener un beneficio particular. No es '
                        'sólo un soborno aislado: es el sistema el que se '
                        'descompone.',
                        'Transparencia Internacional documentó en 2024 que la '
                        'debilidad institucional en América Latina facilita '
                        'tala ilegal, minería clandestina y tráfico de fauna '
                        'silvestre, y que cerca del 80 % de los asesinatos de '
                        'defensores ambientales en el mundo ocurren en esta '
                        'región.',
                    ],
                },
                {
                    'titulo': 'La ecuación de Klitgaard',
                    'parrafos': [
                        'Robert Klitgaard resume cuarenta años de '
                        'investigación en una fórmula sencilla: '
                        'C = M + D − A. La corrupción aumenta con el monopolio '
                        'de decisión (M) y la discrecionalidad (D), y '
                        'disminuye con la rendición de cuentas (A).',
                        'Esta plataforma actúa justamente sobre A: '
                        'distribuye la vigilancia entre toda la comunidad, '
                        'reduce la discrecionalidad al documentar los casos y '
                        'rompe monopolios informativos.',
                    ],
                    'bullets': [
                        'Monopolio: una sola persona u oficina decide sobre un recurso natural.',
                        'Discrecionalidad: no hay criterios claros, públicos y verificables.',
                        'Rendición de cuentas: nadie supervisa de forma independiente.',
                    ],
                },
                {
                    'titulo': 'Tipologías más frecuentes en México',
                    'parrafos': [
                        'Conocer la tipología ayuda a identificar la '
                        'irregularidad cuando la encuentras:'
                    ],
                    'bullets': [
                        'Permisos irregulares de cambio de uso de suelo forestal.',
                        'Concesiones de agua que benefician a unas pocas manos.',
                        'Tolerancia pactada a descargas industriales y residuos peligrosos.',
                        'Contratos de obra pública en áreas naturales protegidas.',
                        'Tráfico de flora y fauna silvestre listadas en la NOM-059.',
                    ],
                },
                {
                    'titulo': 'Señales locales de alerta en Querétaro',
                    'parrafos': [
                        'Observar sin juzgar es el primer paso. Estos patrones '
                        'repetidos en una misma zona suelen coincidir con '
                        'corrupción ambiental activa:'
                    ],
                    'bullets': [
                        'Camiones cargando madera o tierra en horarios nocturnos.',
                        'Pipas de agua extrayendo de pozos sin rotulación.',
                        'Obras que avanzan sin mostrar manifestación de impacto ambiental.',
                        'Descargas visibles en ríos o arroyos sin señalamientos oficiales.',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'Índice de Percepción de la Corrupción · Transparency International', 'url': 'https://www.transparency.org/en/cpi'},
                {'label': 'UNODC: Delitos contra el medio ambiente', 'url': 'https://www.unodc.org/unodc/es/wildlife-and-forest-crime/index.html'},
                {'label': 'Instituto Nacional de Transparencia (INAI)', 'url': 'https://home.inai.org.mx/'},
            ],
        },
        {
            'id': 'mod-derechos',
            'titulo': 'Tus derechos ambientales',
            'duracion': '10 min',
            'nivel': 'Básico',
            'icon': 'leaf',
            'resumen': (
                'Toda persona en México tiene derecho a un medio ambiente '
                'sano, a participar y a informarse. Aquí se explica cada '
                'derecho con su fundamento legal.'
            ),
            'video_id': 'oykGxLQaNXs',
            'video_title': 'ONU · El medio ambiente saludable como derecho humano',
            'video_credit': 'Programa de las Naciones Unidas para el Medio Ambiente (PNUMA), 2022.',
            'objetivos': [
                'Identificar los derechos ambientales reconocidos en México.',
                'Saber dónde encontrar el fundamento legal de cada uno.',
                'Entender cómo se traducen en herramientas concretas de defensa.',
            ],
            'contenido': [
                {
                    'titulo': 'Derecho a un medio ambiente sano',
                    'parrafos': [
                        'Reconocido por la Asamblea General de la ONU en su '
                        'resolución del 28 de julio de 2022 (161 votos a favor, '
                        'ninguno en contra). Este derecho obliga al Estado a '
                        'prevenir la degradación y a proteger la salud '
                        'ecológica de las personas.',
                        'En México está consagrado en el artículo 4º de la '
                        'Constitución: «Toda persona tiene derecho a un medio '
                        'ambiente sano para su desarrollo y bienestar».',
                    ],
                },
                {
                    'titulo': 'Derecho a la participación ciudadana',
                    'parrafos': [
                        'La Declaración Universal de Derechos Humanos (1948) y '
                        'el Principio 10 de la Declaración de Río (1992) '
                        'garantizan tu derecho a intervenir en las decisiones '
                        'ambientales que te afectan.',
                        'La Ley General del Equilibrio Ecológico y la '
                        'Protección al Ambiente (LGEEPA) reconoce la denuncia '
                        'popular como mecanismo para ejercer este derecho, '
                        'incluso de forma anónima.',
                    ],
                },
                {
                    'titulo': 'Derecho de acceso a la información',
                    'parrafos': [
                        'Puedes solicitar a cualquier autoridad información '
                        'sobre permisos, manifestaciones de impacto ambiental, '
                        'concesiones de agua, sanciones y procesos '
                        'administrativos.',
                    ],
                    'bullets': [
                        'Plataforma Nacional de Transparencia: solicitudes en línea y gratuitas.',
                        'Sistema Nacional de Información Ambiental (SNIARN) — SEMARNAT.',
                        'Registro Público de Derechos de Agua (REPDA) — CONAGUA.',
                    ],
                },
                {
                    'titulo': 'Acuerdo de Escazú',
                    'parrafos': [
                        'México ratificó en 2021 este acuerdo regional que '
                        'refuerza los derechos de acceso a la información, '
                        'participación y justicia en asuntos ambientales, y '
                        'protege especialmente a quienes defienden el '
                        'territorio.',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'Resolución ONU A/RES/76/300 (medio ambiente sano)', 'url': 'https://documents.un.org/doc/undoc/gen/n22/442/77/pdf/n2244277.pdf'},
                {'label': 'LGEEPA · Cámara de Diputados', 'url': 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LGEEPA.pdf'},
                {'label': 'Acuerdo de Escazú · CEPAL', 'url': 'https://www.cepal.org/es/acuerdodeescazu'},
                {'label': 'Constitución Política de los Estados Unidos Mexicanos', 'url': 'https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf'},
            ],
        },
        {
            'id': 'mod-como-denunciar',
            'titulo': 'Cómo denunciar sin riesgo',
            'duracion': '15 min',
            'nivel': 'Intermedio',
            'icon': 'shield',
            'resumen': (
                'Guía paso a paso para hacer una denuncia efectiva, segura, '
                'anónima si así lo decides, y con evidencia que deje huella '
                'verificable.'
            ),
            'video_id': '',
            'video_title': '',
            'video_credit': '',
            'objetivos': [
                'Documentar correctamente una irregularidad ambiental.',
                'Elegir el canal adecuado (local, federal o internacional).',
                'Proteger tu identidad y tu integridad mientras denuncias.',
            ],
            'contenido': [
                {
                    'titulo': '1. Observa y documenta desde un lugar seguro',
                    'parrafos': [
                        'Registra fecha, hora y lugar exacto (una referencia '
                        'reconocible o, mejor, coordenadas de tu mapa). '
                        'Fotografía o graba video desde distancia; no '
                        'confrontes ni persigas a los responsables.',
                    ],
                    'bullets': [
                        'Anota matrículas de vehículos si son visibles.',
                        'Registra varias tomas del mismo evento: plano general y detalle.',
                        'Guarda los archivos originales (no los edites ni recortes).',
                    ],
                },
                {
                    'titulo': '2. Describe hechos verificables, no suposiciones',
                    'parrafos': [
                        'Tu relato pesa más cuando separa claramente qué viste, '
                        'qué inferiste y qué te dijeron. Escribe: «observé X», '
                        '«escuché Y», «no sé Z».',
                    ],
                    'bullets': [
                        'Qué sucedió (descripción sobria, sin calificativos).',
                        'Dónde sucedió (referencia y, si puedes, coordenadas).',
                        'Cuándo (fecha, hora aproximada, duración).',
                        'Quiénes (personas, empresas, vehículos identificables).',
                        'Qué daño observable se provocó.',
                    ],
                },
                {
                    'titulo': '3. Elige el canal adecuado',
                    'parrafos': [
                        'Cada autoridad cubre materias distintas. Usa el canal '
                        'que mejor encaje con tu caso; si lo autorizas, esta '
                        'plataforma canalizará tu reporte por ti.',
                    ],
                    'bullets': [
                        'Esta plataforma (comunitaria, anónima, con expediente abierto).',
                        'PROFEPA · 800 770 3372, denuncias@profepa.gob.mx (forestal, impacto, fauna).',
                        'CONAGUA · 55 5174 4000 (agua y cuerpos de agua nacionales).',
                        'SEDESU Querétaro · 442 238 7700 (impacto ambiental estatal).',
                        'CEDH Querétaro · 442 214 0837 (cuando se vulnera un derecho humano).',
                    ],
                },
                {
                    'titulo': '4. Protégete al denunciar',
                    'parrafos': [
                        'Puedes denunciar 100 % en anonimato. En temas de alto '
                        'riesgo conviene además una rutina de seguridad '
                        'digital y personal.',
                    ],
                    'bullets': [
                        'No publiques la denuncia en redes antes del seguimiento formal.',
                        'Guarda copia cifrada de tus evidencias en otro dispositivo.',
                        'Si recibes amenazas, reporta inmediatamente a la CEDH o a la FEMDO.',
                        'Acude a una organización de defensa de defensores ambientales (Serapaz, CEMDA).',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'PROFEPA · Cómo puedes denunciar', 'url': 'https://www.profepa.gob.mx/innovaportal/v/4991/1/mx/31_como_puedes_denunciar.html'},
                {'label': 'PROFEPA · Haz tu denuncia (formulario en línea)', 'url': 'https://www.profepa.gob.mx/innovaportal/v/1156/1/mx/haz_tu_denuncia.html'},
                {'label': 'CONAGUA · Denuncias en materia de agua', 'url': 'https://www.gob.mx/conagua/acciones-y-programas/denuncias'},
                {'label': 'CEMDA · Defensa ambiental', 'url': 'https://www.cemda.org.mx/'},
            ],
        },
        {
            'id': 'mod-queretaro',
            'titulo': 'Recursos naturales de Querétaro',
            'duracion': '11 min',
            'nivel': 'Básico',
            'icon': 'tree',
            'resumen': (
                'Conoce qué estás protegiendo cuando denuncias: ecosistemas, '
                'fauna y acuíferos locales de gran valor y en situación '
                'delicada.'
            ),
            'video_id': '',
            'video_title': '',
            'video_credit': '',
            'objetivos': [
                'Ubicar los principales ecosistemas del estado.',
                'Conocer las presiones ambientales específicas de cada zona.',
                'Relacionar cada recurso con el tipo de denuncia que lo protege.',
            ],
            'contenido': [
                {
                    'titulo': 'Reserva de la Biosfera Sierra Gorda',
                    'parrafos': [
                        'Decretada en 1997, cubre 383 567 hectáreas (un tercio '
                        'del estado). Es la reserva más diversa en ecosistemas '
                        'de México: bosques de niebla, selvas, matorrales y '
                        'pinares en un mismo territorio. Alberga jaguar, '
                        'guacamaya verde y el ajolote serrano.',
                        'Nació por iniciativa ciudadana —caso único en México— '
                        'impulsada por el Grupo Ecológico Sierra Gorda. Hoy '
                        'enfrenta presión por tala ilegal, cambio de uso de '
                        'suelo y desarrollo inmobiliario irregular.',
                    ],
                },
                {
                    'titulo': 'Acuífero Valle de Querétaro',
                    'parrafos': [
                        'Es la fuente principal de agua de la zona '
                        'metropolitana. Desde hace más de una década está '
                        'clasificado por CONAGUA como «sobreexplotado»: se '
                        'extrae más de lo que recarga la lluvia cada año.',
                        'Vigilar pozos sin concesión, descargas industriales y '
                        'uso de pipas no autorizadas es crítico para la '
                        'sostenibilidad del crecimiento urbano del estado.',
                    ],
                },
                {
                    'titulo': 'Semidesierto queretano',
                    'parrafos': [
                        'Cadereyta, Peñamiller y Tolimán conservan vegetación '
                        'xerófila única —cactáceas endémicas, biznagas '
                        'milenarias— muy vulnerable al saqueo ilegal y al '
                        'cambio climático.',
                    ],
                },
                {
                    'titulo': 'Peña de Bernal y El Zamorano',
                    'parrafos': [
                        'Parte del Área Natural Protegida Cerro El Zamorano, '
                        'con especies de fauna como águila real y puma. '
                        'Presionadas por tala, incendios provocados y '
                        'desarrollo inmobiliario irregular.',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'CONANP · Reserva de la Biosfera Sierra Gorda', 'url': 'https://conanp.gob.mx/conanp/dominios/sierragorda/index.php'},
                {'label': 'Grupo Ecológico Sierra Gorda (ONG)', 'url': 'https://sierragorda.net/'},
                {'label': 'SEDESU Querétaro · Medio Ambiente', 'url': 'https://www.queretaro.gob.mx/sedesu/'},
                {'label': 'CONAGUA · Acuíferos del país', 'url': 'https://www.gob.mx/conagua/acciones-y-programas/disponibilidad-de-acuiferos'},
            ],
        },
        {
            'id': 'mod-participacion',
            'titulo': 'Participación ciudadana y subsidiariedad',
            'duracion': '13 min',
            'nivel': 'Intermedio',
            'icon': 'people',
            'resumen': (
                'Más allá de denunciar: cómo organizarte con tu comunidad '
                'para dar seguimiento y proponer soluciones. Fundamento '
                'ético en la Doctrina Social de la Iglesia.'
            ),
            'video_id': 'Ts4a9ARPunU',
            'video_title': 'DSI · El principio de subsidiariedad',
            'video_credit': 'Colección 5Panes: Doctrina Social de la Iglesia explicada.',
            'objetivos': [
                'Entender qué es el principio de subsidiariedad y cómo aplicarlo.',
                'Formar un comité comunitario efectivo.',
                'Usar herramientas públicas para vigilar decisiones ambientales.',
            ],
            'contenido': [
                {
                    'titulo': 'Bien común y subsidiariedad',
                    'parrafos': [
                        'La Doctrina Social de la Iglesia aporta dos '
                        'principios clave para entender la participación '
                        'ciudadana ambiental: bien común (los ecosistemas '
                        'son de todos) y subsidiariedad (las decisiones deben '
                        'tomarse en el nivel más cercano a las personas '
                        'afectadas).',
                        'Esto significa que la comunidad local no es un '
                        'espectador: es protagonista. El Estado interviene '
                        'para apoyar, no para sustituir su iniciativa.',
                    ],
                },
                {
                    'titulo': 'Comités comunitarios de vigilancia',
                    'parrafos': [
                        'Son grupos vecinales que dan seguimiento continuo a '
                        'problemas ambientales locales. Funcionan mejor '
                        'cuando tienen estructura mínima y un enlace con '
                        'autoridades y ONG.',
                    ],
                    'bullets': [
                        'Entre 5 y 12 personas, con roles claros (enlace, documentación, comunicación).',
                        'Reunión mensual fija, aunque sea breve.',
                        'Bitácora simple de hechos observados y denuncias hechas.',
                        'Un aliado jurídico que oriente sobre procedimientos.',
                    ],
                },
                {
                    'titulo': 'Herramientas públicas de vigilancia',
                    'parrafos': [
                        'Existen sistemas gratuitos para pedir información '
                        'pública y rastrear lo que hacen las autoridades:'
                    ],
                    'bullets': [
                        'Plataforma Nacional de Transparencia (solicitudes de información).',
                        'INFOMEX Querétaro (información pública estatal).',
                        'Sistema de Manifestaciones de Impacto Ambiental (SEMARNAT).',
                        'Registro Público de Derechos de Agua (CONAGUA).',
                    ],
                },
                {
                    'titulo': 'Alianzas que multiplican impacto',
                    'parrafos': [
                        'Ningún ciudadano aislado puede sostener una lucha '
                        'ambiental prolongada. Estas alianzas aportan soporte '
                        'técnico, legal y de comunicación:'
                    ],
                    'bullets': [
                        'Universidades (investigación y asesoría técnica).',
                        'ONG ambientales (CEMDA, Serapaz, Grupo Ecológico Sierra Gorda).',
                        'Medios locales independientes para dar visibilidad.',
                        'Redes de defensores del Acuerdo de Escazú.',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'Plataforma Nacional de Transparencia', 'url': 'https://www.plataformadetransparencia.org.mx/'},
                {'label': 'Compendio de la Doctrina Social de la Iglesia', 'url': 'https://www.vatican.va/roman_curia/pontifical_councils/justpeace/documents/rc_pc_justpeace_doc_20060526_compendio-dott-soc_sp.html'},
                {'label': 'CEMDA · Guía del defensor ambiental', 'url': 'https://www.cemda.org.mx/'},
                {'label': 'Escazú · Guía para personas defensoras', 'url': 'https://www.cepal.org/es/acuerdodeescazu'},
            ],
        },
        {
            'id': 'mod-iso',
            'titulo': 'Responsabilidad Social · ISO 26000',
            'duracion': '16 min',
            'nivel': 'Avanzado',
            'icon': 'compass',
            'resumen': (
                'Marco internacional que guía la ética, transparencia y '
                'sostenibilidad de organizaciones. Es la norma que da '
                'sustento al diseño de esta plataforma.'
            ),
            'video_id': 'Gd_3gB_PgiM',
            'video_title': 'Norma ISO 26000 · Responsabilidad Social',
            'video_credit': 'Explicación de los principios y materias fundamentales de la norma.',
            'objetivos': [
                'Conocer los 7 principios y las 7 materias fundamentales.',
                'Diferenciar responsabilidad social de filantropía.',
                'Aplicar la norma al diseño de un proyecto comunitario.',
            ],
            'contenido': [
                {
                    'titulo': 'Qué es y qué no es ISO 26000',
                    'parrafos': [
                        'Publicada el 1 de noviembre de 2010 tras un proceso '
                        'participativo que involucró a 450 expertos de 99 '
                        'países, ISO 26000 es una guía internacional para '
                        'integrar la responsabilidad social en organizaciones '
                        'de todo tamaño y sector.',
                        'No es una norma certificable ni un sistema de '
                        'gestión. Es una orientación para contribuir al '
                        'desarrollo sostenible mediante comportamiento ético '
                        'y transparente.',
                    ],
                },
                {
                    'titulo': 'Los 7 principios',
                    'parrafos': [
                        'Son la brújula ética que debe atravesar cada decisión '
                        'organizacional:'
                    ],
                    'bullets': [
                        'Rendición de cuentas sobre los impactos.',
                        'Transparencia en decisiones y actividades.',
                        'Comportamiento ético coherente con derechos humanos.',
                        'Respeto a los intereses de las partes interesadas.',
                        'Respeto al principio de legalidad.',
                        'Respeto a la normativa internacional de comportamiento.',
                        'Respeto a los derechos humanos.',
                    ],
                },
                {
                    'titulo': 'Las 7 materias fundamentales',
                    'parrafos': [
                        'Cada organización debe identificar qué materias son '
                        'pertinentes para su actividad y para sus grupos de '
                        'interés:'
                    ],
                    'bullets': [
                        'Gobernanza organizacional (eje que articula a las demás).',
                        'Derechos humanos.',
                        'Prácticas laborales.',
                        'Medio ambiente.',
                        'Prácticas justas de operación.',
                        'Asuntos de consumidores.',
                        'Participación activa y desarrollo de la comunidad.',
                    ],
                },
                {
                    'titulo': 'No confundir con filantropía',
                    'parrafos': [
                        'La responsabilidad social busca cambios '
                        'estructurales: cultura, procesos y transparencia. '
                        'La filantropía es un gesto puntual (y loable), pero '
                        'no sustituye la obligación de evitar daños en la '
                        'operación cotidiana.',
                        'Denuncia Verde aplica las materias 1, 2, 4 y 7 de '
                        'la norma y hace de la gobernanza, los derechos '
                        'humanos, el medio ambiente y la participación '
                        'comunitaria sus ejes.',
                    ],
                },
            ],
            'enlaces': [
                {'label': 'ISO 26000 · Página oficial (ISO)', 'url': 'https://www.iso.org/iso-26000-social-responsibility.html'},
                {'label': 'Guía ISO 26000 · Descubre la norma (ISO, PDF)', 'url': 'https://www.iso.org/files/live/sites/isoorg/files/store/en/PUB100258.pdf'},
                {'label': 'ONU · Objetivos de Desarrollo Sostenible', 'url': 'https://www.un.org/sustainabledevelopment/es/'},
            ],
        },
    ]

    # Canales oficiales que complementan la plataforma.
    canales_oficiales = [
        {'nombre': 'PROFEPA',             'telefono': '800 770 3372', 'correo': 'denuncias@profepa.gob.mx'},
        {'nombre': 'CONAGUA',             'telefono': '55 5174 4000', 'correo': 'atencion.usuarios@conagua.gob.mx'},
        {'nombre': 'SEDESU Querétaro',    'telefono': '442 238 7700', 'correo': 'sedesu@queretaro.gob.mx'},
        {'nombre': 'CEDH Querétaro',      'telefono': '442 214 0837', 'correo': 'quejas@cedhqueretaro.org.mx'},
    ]

    context = {
        'proyecto': {
            'nombre': 'Denuncia Verde',
            'subtitulo': 'Plataforma comunitaria contra la corrupción ambiental',
            'ubicacion': 'Querétaro, México',
            'materia': 'Responsabilidad Social y Sustentabilidad · Universidad Anáhuac',
            'docente': 'Prof. Clemente Sánchez Uribe',
        },
        'equipo': equipo,
        'ods': ods,
        'dimensiones': dimensiones,
        'iso_principios': iso_principios,
        'iso_materias': iso_materias,
        'dsi': dsi,
        'derechos': derechos,
        'stakeholders': stakeholders,
        'fases': fases,
        'tipos_denuncia': tipos_denuncia,
        'denuncias_demo': denuncias_demo,
        'modulos': modulos,
        'canales_oficiales': canales_oficiales,
    }
    return render(request, 'core/proyecto_ods16.html', context)
