"""
Sistema de Monitoreo de PC - Módulo 1: Configuración e Imports
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Configuración global, constantes e imports del sistema
"""

# Imports estándar de Python
import sys
import os
import logging
import threading
import time
import datetime
import json
import tempfile
import shutil
import subprocess
import platform
import socket
import uuid
import traceback
import queue
import functools
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from contextlib import contextmanager

# Imports de terceros
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import pandas as pd
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import LineChart, Reference
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    import psutil
    import wmi
    import win32api
    import win32con
    import win32security
    import win32service
    import win32serviceutil
    import win32evtlog
    import win32gui
    import win32process
    import PIL
    from PIL import Image, ImageTk, ImageGrab
except ImportError as e:
    print(f"Error importando dependencias: {e}")
    print("Ejecute: pip install -r requirements.txt")
    sys.exit(1)

# Configuración global del sistema
class SystemConfig:
    """Configuración global del sistema de monitoreo"""
    
    # Información de la aplicación
    APP_NAME = "Mantenimiento de PC"  # Actualizado
    APP_VERSION = "3.0.0"
    APP_AUTHOR = "SERGIORAMGO"
    APP_DATE = "2025-06-22"
    
    # Configuración de paths
    BASE_DIR = Path(__file__).parent.absolute()
    # LOGS_DIR = BASE_DIR / "logs" # Opción original
    LOGS_DIR = Path.home() / "MantenimientoCPU_Logs" # Según documentación
    EXPORTS_DIR = BASE_DIR / "exports"
    SCREENSHOTS_DIR = BASE_DIR / "screenshots"
    TEMP_DIR = BASE_DIR / "temp"
    CONFIG_DIR = BASE_DIR / "config"
    
    # Configuración de archivos
    LOG_FILE = LOGS_DIR / f"mantenimiento_pc_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log" # Nombre de log actualizado y timestamp más preciso
    CONFIG_FILE = CONFIG_DIR / "settings.json"
    STATE_FILE = CONFIG_DIR / "app_state.json"
    
    # Configuración de logging
    LOG_LEVEL = logging.DEBUG
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB
    LOG_BACKUP_COUNT = 5
    
    # Configuración de timeouts (en segundos)
    WMI_TIMEOUT = 30
    TASK_TIMEOUT = 60
    SCREENSHOT_TIMEOUT = 10
    EXPORT_TIMEOUT = 300
    
    # Configuración de intervalos de actualización (en segundos)
    MONITORING_INTERVAL = 2
    UI_UPDATE_INTERVAL = 1
    AUTO_SAVE_INTERVAL = 300  # 5 minutos
    
    # Configuración de la interfaz
    WINDOW_WIDTH = 1400
    WINDOW_HEIGHT = 900
    MIN_WINDOW_WIDTH = 1200
    MIN_WINDOW_HEIGHT = 700
    
    # Configuración de colores
    COLORS = {
        'primary': '#2E86AB',
        'secondary': '#A23B72',
        'success': '#28A745',
        'warning': '#FFC107',
        'danger': '#DC3545',
        'info': '#17A2B8',
        'light': '#F8F9FA',
        'dark': '#343A40',
        'background': '#FFFFFF',
        'text': '#212529'
    }
    
    # Configuración de gráficos
    GRAPH_COLORS = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57', '#FF9FF3']
    GRAPH_STYLE = 'seaborn-v0_8'
    GRAPH_DPI = 100
    
    # Configuración de exportación
    EXCEL_SHEET_NAMES = {
        'system_info': 'Información del Sistema',
        'monitoring': 'Datos de Monitoreo',
        'performance': 'Rendimiento',
        'security': 'Seguridad',
        'services': 'Servicios',
        'events': 'Eventos del Sistema'
    }
    
    # Configuración de captura de pantalla
    SCREENSHOT_QUALITY = 95
    SCREENSHOT_FORMAT = 'PNG'
    MAX_SCREENSHOT_SIZE = (1920, 1080)
    
    # Configuración de seguridad
    ENCRYPTED_FIELDS = ['passwords', 'tokens', 'keys']
    SENSITIVE_PROCESSES = ['winlogon.exe', 'csrss.exe', 'smss.exe', 'lsass.exe']
    
    # Configuración de rendimiento
    MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)
    MEMORY_THRESHOLD = 80  # Porcentaje
    CPU_THRESHOLD = 90     # Porcentaje
    DISK_THRESHOLD = 90    # Porcentaje
    
    @classmethod
    def ensure_directories(cls):
        """Asegura que todos los directorios necesarios existan"""
        directories = [
            cls.LOGS_DIR,
            cls.EXPORTS_DIR,
            cls.SCREENSHOTS_DIR,
            cls.TEMP_DIR,
            cls.CONFIG_DIR
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Error creando directorio {directory}: {e}")
    
    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """Carga la configuración desde archivo"""
        try:
            if cls.CONFIG_FILE.exists():
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error cargando configuración: {e}")
        return {}
    
    @classmethod
    def save_config(cls, config: Dict[str, Any]):
        """Guarda la configuración en archivo"""
        try:
            cls.ensure_directories()
            with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando configuración: {e}")

# Constantes del sistema
class SystemConstants:
    """Constantes utilizadas en todo el sistema"""
    
    # Estados de tareas
    TASK_STATUS = {
        'PENDING': 'Pendiente',
        'RUNNING': 'Ejecutando',
        'COMPLETED': 'Completado',
        'FAILED': 'Fallido',
        'TIMEOUT': 'Tiempo agotado',
        'CANCELLED': 'Cancelado'
    }
    
    # Tipos de análisis
    ANALYSIS_TYPES = {
        'BASIC': 'Análisis Básico',
        'DETAILED': 'Análisis Detallado',
        'MONITORING': 'Monitoreo Continuo',
        'SECURITY': 'Análisis de Seguridad',
        'PERFORMANCE': 'Análisis de Rendimiento'
    }
    
    # Prioridades de tareas
    TASK_PRIORITIES = {
        'LOW': 1,
        'NORMAL': 2,
        'HIGH': 3,
        'CRITICAL': 4
    }
    
    # Tipos de eventos del sistema
    EVENT_TYPES = {
        'INFORMATION': 1,
        'WARNING': 2,
        'ERROR': 3,
        'SUCCESS_AUDIT': 4,
        'FAILURE_AUDIT': 5
    }
    
    # Unidades de medida
    UNITS = {
        'BYTES': ['B', 'KB', 'MB', 'GB', 'TB'],
        'FREQUENCY': ['Hz', 'KHz', 'MHz', 'GHz'],
        'TEMPERATURE': ['°C', '°F', 'K'],
        'TIME': ['ms', 's', 'm', 'h', 'd']
    }
    
    # Extensiones de archivo soportadas
    SUPPORTED_FORMATS = {
        'EXPORT': ['.xlsx', '.pdf', '.csv', '.json'],
        'IMAGE': ['.png', '.jpg', '.jpeg', '.bmp', '.gif'],
        'LOG': ['.log', '.txt']
    }

# Configuración de logging mejorada
def setup_logging():
    """Configura el sistema de logging"""
    try:
        SystemConfig.ensure_directories()
        
        # Configurar el logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(SystemConfig.LOG_LEVEL)
        
        # Limpiar handlers existentes
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Handler para archivo con rotación
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            SystemConfig.LOG_FILE,
            maxBytes=SystemConfig.MAX_LOG_SIZE,
            backupCount=SystemConfig.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            SystemConfig.LOG_FORMAT,
            datefmt=SystemConfig.LOG_DATE_FORMAT
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Handler para consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # Logger específico para la aplicación
        app_logger = logging.getLogger(__name__) # Usar __name__
        app_logger.info(f"Sistema de logging inicializado - {SystemConfig.APP_NAME} v{SystemConfig.APP_VERSION}")
        
        return app_logger
        
    except Exception as e:
        print(f"Error configurando logging: {e}")
        # Logger básico como fallback
        logging.basicConfig(
            level=logging.INFO, # Usar SystemConfig.LOG_LEVEL aquí también sería consistente
            format=SystemConfig.LOG_FORMAT,
            datefmt=SystemConfig.LOG_DATE_FORMAT
        )
        return logging.getLogger(__name__) # Usar __name__

# Inicialización del sistema
def initialize_system():
    """Inicializa el sistema completo"""
    try:
        # Crear directorios necesarios
        SystemConfig.ensure_directories()
        
        # Configurar logging
        logger = setup_logging()
        logger.info("Iniciando sistema de monitoreo...")
        
        # Verificar sistema operativo
        if platform.system() != 'Windows':
            logger.error("Este sistema solo funciona en Windows")
            return False
        
        # Verificar permisos de administrador
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if not is_admin:
                logger.warning("Se recomienda ejecutar como administrador para funcionalidad completa")
        except Exception:
            logger.warning("No se pudo verificar permisos de administrador")
        
        # Limpiar archivos temporales antiguos
        cleanup_temp_files()
        
        logger.info("Sistema inicializado correctamente")
        return True
        
    except Exception as e:
        print(f"Error inicializando sistema: {e}")
        return False

def cleanup_temp_files():
    """Limpia archivos temporales antiguos"""
    logger = logging.getLogger(__name__) # Usar __name__ y obtener logger localmente
    try:
        temp_dir = SystemConfig.TEMP_DIR
        if temp_dir.exists():
            current_time = time.time()
            for file_path in temp_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_age = current_time - file_path.stat().st_mtime
                        # Eliminar archivos más antiguos que 24 horas
                        if file_age > 24 * 3600: # 1 día
                            logger.debug(f"Eliminando archivo temporal antiguo: {file_path}")
                            file_path.unlink()
                    except Exception as ex_file:
                        logger.warning(f"No se pudo procesar/eliminar archivo temporal {file_path}: {ex_file}")
                        
        # Limpiar screenshots antiguos (más de 7 días)
        screenshots_dir = SystemConfig.SCREENSHOTS_DIR
        if screenshots_dir.exists():
            current_time = time.time()
            for file_path in screenshots_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_age = current_time - file_path.stat().st_mtime
                        if file_age > 7 * 24 * 3600: # 7 días
                            logger.debug(f"Eliminando screenshot antiguo: {file_path}")
                            file_path.unlink()
                    except Exception as ex_screenshot:
                        logger.warning(f"No se pudo procesar/eliminar screenshot {file_path}: {ex_screenshot}")
                        
    except Exception as e:
        logger.exception("Error general durante la limpieza de archivos temporales.") # Usar logger.exception

# Verificación final de imports
def verify_dependencies():
    """Verifica que todas las dependencias estén disponibles"""
    required_modules = [
        'tkinter', 'matplotlib', 'pandas', 'openpyxl', 'reportlab',
        'psutil', 'wmi', 'win32api', 'PIL'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print(f"Módulos faltantes: {', '.join(missing_modules)}")
        print("Ejecute: pip install -r requirements.txt")
        return False
    
    return True

# Información del sistema al inicio
def log_system_info():
    """Registra información básica del sistema"""
    logger = logging.getLogger(__name__) # Usar __name__
    try:
        logger.info(f"=== {SystemConfig.APP_NAME} v{SystemConfig.APP_VERSION} ===")
        logger.info(f"Autor: {SystemConfig.APP_AUTHOR}")
        logger.info(f"Fecha: {SystemConfig.APP_DATE}")
        logger.info(f"Python: {sys.version}")
        logger.info(f"Plataforma: {platform.platform()}")
        logger.info(f"Procesador: {platform.processor()}")
        logger.info(f"Arquitectura: {platform.architecture()[0]}")
        logger.info(f"Hostname: {socket.gethostname()}")
        logger.info(f"Usuario: {os.getenv('USERNAME', 'Desconocido')}")
        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Error registrando información del sistema: {e}")

# Inicialización automática al importar
if __name__ != "__main__":
    if not verify_dependencies():
        sys.exit(1)
    
    if not initialize_system():
        sys.exit(1)
    
    log_system_info()