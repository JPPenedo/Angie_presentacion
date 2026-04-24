"""
Este módulo concentra toda la lógica de presentación del prototipo.
Se usan datos en memoria (diccionarios/listas) para fines de demo pedagógica,
sin depender de modelos ni base de datos para autenticación académica.

Guía de lectura (tipo profesor):
1) Primero revisa los bloques de datos (USUARIOS, HISTORIAL_ALUMNO, MATERIAS_ACTUALES, GRUPOS).
2) Luego estudia los helpers (_compute_stats, _usuario_sesion, _require_login).
3) Finalmente sigue el flujo de vistas: login -> dashboard/docente o perfil/alumno.
"""

from django.shortcuts import render, redirect
from django.http import Http404
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import secrets
import logging
from .models import CuentaAlumno

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Usuarios demo (sin modelos, autenticación por sesión)
# ---------------------------------------------------------------------------

# Profesor: este diccionario reemplaza temporalmente una tabla de usuarios real.
# Idea clave: aquí definimos "quién entra" y "qué rol tiene", lo cual determina
# qué pantalla verá después del login (docente o alumno).
USUARIOS = {
    'docente@anahuac.mx': {
        'password': 'demo123',
        'rol': 'docente',
        'nombre': 'Dr. Gilberto Morales',
        'cargo': 'Coordinador de Actuaría',
    },
    'alumno@anahuac.mx': {
        'password': 'demo123',
        'rol': 'alumno',
        'nombre': 'Juan Pablo Penedo',
        'matricula': 'AU210034',
        'semestre_actual': 10,
        'creditos_totales': 240,
        'creditos_acreditados': 208,
    },
    'coordinacion@anahuac.mx': {
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


def _require_login(request):
    """
    Profesor: guardia de acceso.
    - Si no hay sesión, redirige al login.
    - Si hay sesión, deja continuar la vista.
    """
    if not _usuario_sesion(request):
        return redirect('core:login')
    return None


def _build_absolute_url(request, path):
    """Construye URL absoluta para enlaces enviados por correo."""
    return request.build_absolute_uri(path)


def _send_verification_email(request, cuenta):
    """Envía un correo breve para validar la cuenta recién creada."""
    verify_url = _build_absolute_url(
        request,
        reverse('core:verificar_cuenta', args=[cuenta.verification_token]),
    )
    send_mail(
        subject='Verifica tu cuenta - Plataforma Académica',
        message=(
            f'Hola {cuenta.nombre_completo},\n\n'
            'Gracias por registrarte. Para activar tu cuenta, confirma tu correo aquí:\n'
            f'{verify_url}\n\n'
            'Si no solicitaste esta cuenta, ignora este mensaje.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[cuenta.correo_institucional],
        fail_silently=False,
    )


def _send_password_reset_email(request, cuenta):
    """Envía enlace temporal para restablecer contraseña."""
    reset_url = _build_absolute_url(
        request,
        reverse('core:reset_password', args=[cuenta.reset_token]),
    )
    send_mail(
        subject='Recuperación de contraseña - Plataforma Académica',
        message=(
            f'Hola {cuenta.nombre_completo},\n\n'
            'Recibimos una solicitud para restablecer tu contraseña.\n'
            f'Usa este enlace (vigente por 30 minutos):\n{reset_url}\n\n'
            'Si no solicitaste este cambio, puedes ignorar este correo.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[cuenta.correo_institucional],
        fail_silently=False,
    )


# ---------------------------------------------------------------------------
# Vistas de autenticación
# ---------------------------------------------------------------------------

def login_view(request):
    """
    Profesor: esta vista hace tres cosas:
    1) Si ya hay sesión, evita re-login y redirige según rol.
    2) Si llega POST, valida dato de acceso (correo o ID) + contraseña.
    3) Si son correctos, guarda en sesión un perfil reducido para toda la app.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return redirect('core:perfil_alumno' if u['rol'] == 'alumno' else 'core:dashboard')

    error = None
    info = None
    prefill_dato = request.GET.get('dato', '').strip().lower()
    if request.GET.get('created') == '1':
        info = 'Cuenta creada. Revisa tu correo y verifica tu cuenta para poder iniciar sesión.'
    if request.GET.get('verified') == '1':
        info = 'Correo verificado correctamente. Ya puedes iniciar sesión.'
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
            if usuario['rol'] == 'alumno':
                return redirect('core:perfil_alumno')
            return redirect('core:dashboard')

        try:
            cuenta = CuentaAlumno.objects.filter(
                Q(correo_institucional=dato_acceso) | Q(id_institucional=dato_acceso)
            ).first()
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
            if not cuenta.is_verified:
                error = 'Tu cuenta aún no está verificada. Revisa tu correo institucional.'
                return render(
                    request,
                    'core/login.html',
                    {
                        'error': error,
                        'info': info,
                        'prefill_dato': dato_acceso,
                    },
                )
            request.session['usuario'] = {
                'correo': cuenta.correo_institucional,
                'rol': cuenta.rol,
                'nombre': cuenta.nombre_completo,
                'matricula': cuenta.id_institucional,
                'semestre_actual': 1 if cuenta.rol == 'alumno' else None,
                'creditos_totales': 240,
                'creditos_acreditados': 0 if cuenta.rol == 'alumno' else None,
                'cargo': 'Coordinación Académica' if cuenta.rol == 'coordinacion' else ('Docente' if cuenta.rol == 'docente' else ''),
            }
            return redirect('core:perfil_alumno' if cuenta.rol == 'alumno' else 'core:dashboard')
        else:
            error = 'Dato de acceso o contraseña incorrectos.'

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
    Campos: rol, correo institucional, nombre completo, ID de 8 dígitos y contraseña.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return redirect('core:perfil_alumno' if u['rol'] == 'alumno' else 'core:dashboard')

    error = None
    form_data = {
        'rol': 'alumno',
        'correo': '',
        'nombre_completo': '',
        'id_institucional': '',
    }

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip().lower()
        nombre_completo = request.POST.get('nombre_completo', '').strip()
        id_institucional = request.POST.get('id_institucional', '').strip()
        rol = request.POST.get('rol', 'alumno').strip()
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()

        form_data = {
            'rol': rol,
            'correo': correo,
            'nombre_completo': nombre_completo,
            'id_institucional': id_institucional,
        }

        if rol not in {'alumno', 'docente', 'coordinacion'}:
            error = 'Selecciona un rol válido.'
        elif not correo.endswith('@anahuac.mx'):
            error = 'Debes usar un correo institucional que termine en @anahuac.mx.'
        elif not nombre_completo:
            error = 'El nombre completo es obligatorio.'
        elif not (id_institucional.isdigit() and len(id_institucional) == 8):
            error = 'El ID institucional debe contener exactamente 8 dígitos.'
        elif len(password) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres.'
        elif password != password_confirm:
            error = 'La confirmación de contraseña no coincide.'
        elif CuentaAlumno.objects.filter(correo_institucional=correo).exists():
            error = 'Ese correo ya tiene una cuenta registrada.'
        elif CuentaAlumno.objects.filter(id_institucional=id_institucional).exists():
            error = 'Ese ID institucional ya está registrado.'
        else:
            try:
                cuenta = CuentaAlumno.objects.create(
                    correo_institucional=correo,
                    nombre_completo=nombre_completo,
                    id_institucional=id_institucional,
                    rol=rol,
                    password_hash=make_password(password),
                    verification_token=secrets.token_urlsafe(24),
                )
            except DatabaseError:
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
            try:
                _send_verification_email(request, cuenta)
            except Exception:
                # Si falla SMTP, mantenemos cuenta creada y mostramos mensaje explicativo.
                return render(
                    request,
                    'core/signup.html',
                    {
                        'error': (
                            'La cuenta se creó, pero no se pudo enviar el correo de verificación. '
                            'Revisa la configuración de email SMTP.'
                        ),
                        'form_data': {'rol': 'alumno', 'correo': '', 'nombre_completo': '', 'id_institucional': ''},
                    },
                )
            return redirect(f"{redirect('core:login').url}?created=1&dato={correo}")

    return render(request, 'core/signup.html', {'error': error, 'form_data': form_data})


def verificar_cuenta_view(request, token):
    """Marca cuenta como verificada usando token enviado por correo."""
    cuenta = CuentaAlumno.objects.filter(verification_token=token).first()
    if not cuenta:
        return redirect(reverse('core:login'))

    cuenta.is_verified = True
    cuenta.verification_token = ''
    cuenta.save(update_fields=['is_verified', 'verification_token'])
    return redirect(f"{reverse('core:login')}?verified=1&dato={cuenta.correo_institucional}")


def recuperar_password_view(request):
    """Solicita recuperación de contraseña por correo institucional."""
    info = None
    error = None

    try:
        if request.method == 'POST':
            correo = request.POST.get('correo', '').strip().lower()
            if not correo:
                error = 'Debes ingresar un correo institucional.'
            else:
                try:
                    cuenta = CuentaAlumno.objects.filter(correo_institucional=correo).first()
                except DatabaseError:
                    error = 'No se pudo procesar la recuperación. Verifica migraciones de base de datos en el servidor.'
                    return render(request, 'core/password_recovery_request.html', {'info': info, 'error': error})
                if cuenta:
                    try:
                        cuenta.reset_token = secrets.token_urlsafe(24)
                        cuenta.reset_token_expires_at = timezone.now() + timedelta(minutes=30)
                        cuenta.save(update_fields=['reset_token', 'reset_token_expires_at'])
                        _send_password_reset_email(request, cuenta)
                    except DatabaseError:
                        error = 'No se pudo guardar el token de recuperación. Verifica migraciones de base de datos en el servidor.'
                    except Exception:
                        error = 'No se pudo enviar el correo de recuperación. Revisa la configuración SMTP.'
                if not error:
                    info = 'Si el correo existe, enviamos un enlace de recuperación.'
    except Exception:
        logger.exception('Error inesperado en recuperar_password_view')
        error = 'Ocurrió un error inesperado al procesar la recuperación.'

    return render(request, 'core/password_recovery_request.html', {'info': info, 'error': error})


def reset_password_view(request, token):
    """Permite definir una nueva contraseña usando token temporal."""
    cuenta = CuentaAlumno.objects.filter(reset_token=token).first()
    if not cuenta or not cuenta.reset_token_is_valid():
        return render(
            request,
            'core/password_recovery_reset.html',
            {'error': 'El enlace de recuperación es inválido o ya expiró.', 'token_valid': False},
        )

    error = None
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        password_confirm = request.POST.get('password_confirm', '').strip()

        if len(password) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres.'
        elif password != password_confirm:
            error = 'La confirmación de contraseña no coincide.'
        else:
            cuenta.password_hash = make_password(password)
            cuenta.reset_token = ''
            cuenta.reset_token_expires_at = None
            cuenta.save(update_fields=['password_hash', 'reset_token', 'reset_token_expires_at'])
            return redirect(f"{reverse('core:login')}?reset=1&dato={cuenta.correo_institucional}")

    return render(
        request,
        'core/password_recovery_reset.html',
        {'error': error, 'token_valid': True},
    )


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
        return redirect('core:perfil_alumno')

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
        return redirect('core:perfil_alumno')

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


# ---------------------------------------------------------------------------
# Vista alumno: perfil
# ---------------------------------------------------------------------------

def perfil_alumno(request):
    """
    Profesor: tablero personal del alumno.
    Resume avance curricular, materias en curso y desempeño histórico.
    """
    redir = _require_login(request)
    if redir:
        return redir

    usuario = _usuario_sesion(request)
    if usuario['rol'] != 'alumno':
        return redirect('core:dashboard')

    # Profesor: calcula un único promedio acumulado para la tarjeta principal del perfil.
    todas_califs = [
        m['calificacion']
        for sem in HISTORIAL_ALUMNO
        for m in sem['materias']
    ]
    promedio_global = round(sum(todas_califs) / len(todas_califs), 2)
    total_creditos_hist = sum(
        m['creditos']
        for sem in HISTORIAL_ALUMNO
        for m in sem['materias']
    )
    pct_avance = round(total_creditos_hist / usuario['creditos_totales'] * 100)

    # Profesor: enriquece cada semestre con `prom_semestre` para evitar recalcular en template.
    for sem in HISTORIAL_ALUMNO:
        califs_sem = [m['calificacion'] for m in sem['materias']]
        sem['prom_semestre'] = round(sum(califs_sem) / len(califs_sem), 2)

    # Profesor: último paso: empaquetar todo en `context` y renderizar.
    context = {
        'usuario': usuario,
        'grupos_nav': [],
        'historial': HISTORIAL_ALUMNO,
        'materias_actuales': MATERIAS_ACTUALES,
        'promedio_global': promedio_global,
        'total_creditos_hist': total_creditos_hist,
        'pct_avance': pct_avance,
    }
    return render(request, 'core/perfil_alumno.html', context)


def expo_actuaria_view(request):
    """
    Vista pública de exposición:
    - Slides sobre enfoques matemáticos actuariales implícitos en el proyecto.
    - Prototipo demo simplificado con estilo consistente.
    """
    slides = [
        {
            'titulo': 'Avance Curricular hacia los 360 Créditos',
            'idea': (
                'La plataforma muestra cuántos créditos lleva cada alumno sobre los '
                '360 que exige el plan. Observar la distribución del grupo revela '
                'dónde se concentra la masa del alumnado y dónde aparecen brechas '
                'que frenan el camino a la titulación.'
            ),
            'modelo': (
                r'\hat F(c) \;=\; \frac{1}{n}\sum_{i=1}^{n} \mathbb{1}\{C_i \le c\}'
                r'\qquad P_{50} \;=\; \inf\!\bigl\{c : \hat F(c) \ge 0.5\bigr\}'
                r'\qquad S(c) \;=\; 1 - F(c)'
            ),
            'enfoque': (
                'Función de distribución empírica y función de supervivencia S(c): '
                'el mismo instrumento con el que un actuario construye tablas de '
                'mortalidad, trasladado al "tiempo vivido" en créditos académicos.'
            ),
            'conceptos': [
                'Distribución empírica F̂ y percentiles del avance',
                'Función de supervivencia académica S(c)=P(aún en curso)',
                'Detección de rezago: colas izquierdas de la distribución',
            ],
            'demo': 'bernoulli',
        },
        {
            'titulo': 'Red de Prerrequisitos y Desbloqueo',
            'idea': (
                'El plan no es lineal: muchas materias exigen haber aprobado otras '
                'antes. Dos concatenaciones típicas del plan son '
                'Cálculo I → II → Ecs. Diferenciales y '
                'Probabilidad I → II → Procesos Estocásticos; ambas convergen '
                'en las Matemáticas Actuariales.'
            ),
            'modelo': (
                r'\text{abierto}(i) \iff \forall\, j \in \text{pre}(i): \text{aprobado}(j)'
                r'\qquad P(\text{avanza a } i) \;=\; \prod_{j \in \text{pre}(i)} P\!\bigl(\text{aprobar}\ j\bigr)'
            ),
            'enfoque': (
                'Teoría de grafos y modelos multi-estado tipo Markov — la misma '
                'estructura con la que Actuaría de vida describe transiciones '
                '(activo → inválido → fallecido), aplicada a estados curriculares.'
            ),
            'conceptos': [
                'Orden topológico y camino crítico del plan',
                'Probabilidad multiplicativa sobre la cadena de materias',
                'Cadenas de Markov sobre estados "materia aprobada"',
            ],
            'demo': 'curriculo',
        },
        {
            'titulo': 'Aprobación como Ensayo Bernoulli',
            'idea': (
                'Cada evaluación final es un ensayo Bernoulli: el alumno '
                'aprueba o no aprueba. Al agregar los n alumnos que cursan '
                'una materia obtenemos una Binomial, y con ella una '
                'estimación limpia de la tasa de aprobación y su '
                'incertidumbre.'
            ),
            'modelo': (
                r'X_i \sim \operatorname{Bernoulli}(p)'
                r'\qquad S_n = \sum_{i=1}^{n} X_i \sim \operatorname{Binomial}(n,p)'
                r'\qquad \mathbb{E}[S_n] = np,\ \ \operatorname{Var}(S_n) = np(1-p)'
            ),
            'enfoque': (
                'Misma estructura con la que un actuario mide la frecuencia '
                'siniestral en una cartera: número de éxitos sobre expuestos, '
                'con su varianza binomial — base del Exam P de la SOA.'
            ),
            'conceptos': [
                'Bernoulli/Binomial: éxito = aprobación, fracaso = reprobación',
                'Estimador p̂ = A/n y su error estándar √(p̂(1−p̂)/n)',
                'Banda de 1σ sobre p̂ por materia para priorizar revisión',
            ],
            'demo': 'binomial',
        },
        {
            'titulo': 'Z-score bajo el Modelo Normal',
            'idea': (
                'Si suponemos que las calificaciones del grupo se '
                'distribuyen aproximadamente Normal, estandarizar con Z '
                'nos dice — en desviaciones estándar — qué tan arriba o '
                'abajo del promedio está cada alumno y en qué percentil '
                'queda del grupo.'
            ),
            'modelo': (
                r'X \sim \mathcal{N}(\mu,\sigma^{2})'
                r'\qquad Z = \frac{X-\mu}{\sigma} \sim \mathcal{N}(0,1)'
                r'\qquad P(X \le x) = \Phi\!\left(\tfrac{x-\mu}{\sigma}\right)'
            ),
            'enfoque': (
                'El mismo score estandarizado con el que la actuaría '
                'clasifica riesgos — cuántos σ por encima/abajo del '
                'promedio cae el caso — sobre la distribución Normal y la '
                'FDA Φ, pilares del Exam P.'
            ),
            'conceptos': [
                'Ajuste (μ, σ) por momentos sobre calificaciones del grupo',
                'Estandarización Z y percentil vía Φ(Z)',
                'Colas: alumnos en |Z| > 1 marcados para seguimiento',
            ],
            'demo': 'zscore',
        },
        {
            'titulo': 'Tiempo hasta los 360 Créditos',
            'idea': (
                'Si los créditos se acumulan a una tasa λ por semestre, '
                'el tiempo para cubrir los créditos que faltan hasta los '
                '360 se modela como Gamma (suma de ciclos Exponenciales). '
                'De ahí sale una proyección concreta: cuántos semestres '
                'faltan para titular al ritmo actual.'
            ),
            'modelo': (
                r'T = \tfrac{360 - C}{\lambda}'
                r'\qquad \lambda = \bar r\ \text{cr/sem}'
                r'\qquad T \sim \operatorname{Gamma}\!\left(\tfrac{360-C}{45},\, \tfrac{1}{\lambda}\right)'
            ),
            'enfoque': (
                'Mismas distribuciones Exponencial y Gamma del Exam P que '
                'usa la actuaría para tiempos entre siniestros; trasladadas '
                'al "tiempo restante" hasta terminar la carrera: una '
                'esperanza de vida académica residual eₓ.'
            ),
            'conceptos': [
                'λ̂ = créditos promedio ganados por semestre',
                'E[T] = (360 − C)/λ̂ como proyección al ritmo actual',
                'Banda de incertidumbre usando √Var(T) de la Gamma',
            ],
            'demo': 'titulacion',
        },
        {
            'titulo': 'Simulador: de tu CAP a la decisión',
            'idea': (
                'Así viviría un alumno la plataforma: inicia sesión, sube su '
                'CAP — el documento oficial con su avance académico — y en '
                'segundos obtiene un diagnóstico de su situación, qué materias '
                'se le desbloquean y una proyección hacia los 360 créditos.'
            ),
            'modelo': (
                r'\text{Impacto} \;=\; \Delta\text{retención} '
                r'\;+\; \Delta\text{tiempo}_{\text{titulación}} '
                r'\;+\; \Delta\text{calidad docente}'
            ),
            'enfoque': (
                '¿Por qué importa? La información ya existe en el CAP, pero sirve '
                'poco si no se analiza. Este prototipo convierte ese documento '
                'en decisiones concretas para tres actores: el alumno (qué cursar '
                'y dónde enfocarse), coordinación (a quién apoyar primero) y la '
                'facultad (qué materias revisar o reforzar).'
            ),
            'conceptos': [
                'Alumno: diagnóstico inmediato y materias desbloqueadas',
                'Coordinación: detección temprana de rezago y cuellos de botella',
                'Facultad: evidencia para ajustar el plan y asignar recursos',
            ],
            'demo': 'simulador',
        },
    ]

    demo_alumnos = [
        {'nombre': 'A. García', 'calificacion': 8.7, 'riesgo': 'Bajo'},
        {'nombre': 'C. Mendoza', 'calificacion': 6.1, 'riesgo': 'Medio'},
        {'nombre': 'S. Ramírez', 'calificacion': 5.4, 'riesgo': 'Alto'},
        {'nombre': 'D. Flores', 'calificacion': 9.0, 'riesgo': 'Bajo'},
    ]

    context = {
        'slides': slides,
        'demo_alumnos': demo_alumnos,
        'demo_promedio': round(sum(a['calificacion'] for a in demo_alumnos) / len(demo_alumnos), 2),
        'demo_aprobacion': round(sum(1 for a in demo_alumnos if a['calificacion'] >= 6) / len(demo_alumnos) * 100),
        'demo_riesgo_alto': sum(1 for a in demo_alumnos if a['riesgo'] == 'Alto'),
    }
    return render(request, 'core/expo_actuaria.html', context)


def expo_opciones_view(request):
    """
    Vista pública pedagógica:
    - Slides que explican Bull Call Spread y Bear Put Spread.
    - Reutiliza el formato visual de `expo_actuaria`, pero con demos propias
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
