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
from .models import CuentaAlumno

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


# ---------------------------------------------------------------------------
# Vistas de autenticación
# ---------------------------------------------------------------------------

def login_view(request):
    """
    Profesor: esta vista hace tres cosas:
    1) Si ya hay sesión, evita re-login y redirige según rol.
    2) Si llega POST, valida credenciales demo contra `USUARIOS`.
    3) Si son correctas, guarda en sesión un perfil reducido para toda la app.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return redirect('core:perfil_alumno' if u['rol'] == 'alumno' else 'core:dashboard')

    error = None
    info = None
    prefill_correo = request.GET.get('correo', '').strip().lower()
    if request.GET.get('created') == '1':
        info = 'Cuenta creada correctamente. Inicia sesión con tu correo y tu ID institucional (8 dígitos).'
    if request.method == 'POST':
        correo   = request.POST.get('correo', '').strip().lower()
        password = request.POST.get('password', '').strip()

        usuario = USUARIOS.get(correo)
        if usuario and usuario['password'] == password:
            # Profesor: aquí se "firma" la sesión de trabajo del usuario.
            # Esta estructura será usada por navbar, control de roles y vistas.
            request.session['usuario'] = {
                'correo': correo,
                'rol':    usuario['rol'],
                'nombre': usuario['nombre'],
                **({k: usuario[k] for k in ('matricula', 'semestre_actual', 'creditos_totales', 'creditos_acreditados')}
                   if usuario['rol'] == 'alumno' else {'cargo': usuario.get('cargo', '')}),
            }
            if usuario['rol'] == 'alumno':
                return redirect('core:perfil_alumno')
            return redirect('core:dashboard')
        cuenta = CuentaAlumno.objects.filter(correo_institucional=correo).first()
        if cuenta and cuenta.id_institucional == password:
            request.session['usuario'] = {
                'correo': cuenta.correo_institucional,
                'rol': 'alumno',
                'nombre': cuenta.nombre_completo,
                'matricula': cuenta.id_institucional,
                'semestre_actual': 1,
                'creditos_totales': 240,
                'creditos_acreditados': 0,
            }
            return redirect('core:perfil_alumno')
        else:
            error = 'Correo o contraseña/ID incorrectos.'

    return render(
        request,
        'core/login.html',
        {
            'error': error,
            'info': info,
            'prefill_correo': prefill_correo,
        },
    )


def crear_cuenta_view(request):
    """
    Profesor: registro mínimo de cuentas para alumnos.
    Campos solicitados: correo institucional, nombre completo e ID de 8 dígitos.
    """
    if _usuario_sesion(request):
        u = _usuario_sesion(request)
        return redirect('core:perfil_alumno' if u['rol'] == 'alumno' else 'core:dashboard')

    error = None
    form_data = {'correo': '', 'nombre_completo': '', 'id_institucional': ''}

    if request.method == 'POST':
        correo = request.POST.get('correo', '').strip().lower()
        nombre_completo = request.POST.get('nombre_completo', '').strip()
        id_institucional = request.POST.get('id_institucional', '').strip()

        form_data = {
            'correo': correo,
            'nombre_completo': nombre_completo,
            'id_institucional': id_institucional,
        }

        if not correo.endswith('@anahuac.mx'):
            error = 'Debes usar un correo institucional que termine en @anahuac.mx.'
        elif not nombre_completo:
            error = 'El nombre completo es obligatorio.'
        elif not (id_institucional.isdigit() and len(id_institucional) == 8):
            error = 'El ID institucional debe contener exactamente 8 dígitos.'
        elif CuentaAlumno.objects.filter(correo_institucional=correo).exists():
            error = 'Ese correo ya tiene una cuenta registrada.'
        elif CuentaAlumno.objects.filter(id_institucional=id_institucional).exists():
            error = 'Ese ID institucional ya está registrado.'
        else:
            CuentaAlumno.objects.create(
                correo_institucional=correo,
                nombre_completo=nombre_completo,
                id_institucional=id_institucional,
            )
            return redirect(f"{redirect('core:login').url}?created=1&correo={correo}")

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
    if usuario['rol'] == 'docente':
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
