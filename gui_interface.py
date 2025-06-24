"""
Sistema de Monitoreo de PC - Módulo 12: Interfaz Gráfica de Usuario
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Interfaz gráfica moderna usando tkinter para el sistema de monitoreo
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import queue
import webbrowser
import os

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("PIL no disponible - algunas funciones de imagen serán limitadas")

# Importar módulos del sistema
from config_and_imports import SystemConfig, SystemConstants
from utilities import SystemUtilities, FileUtilities
from main_interface import (
    SystemMonitorInterface, MonitoringMode, SystemStatus,
    create_system_monitor
)

# Logger para este módulo
logger = logging.getLogger(__name__)

class ModernStyle:
    """Configuración de estilo moderno para la interfaz"""
    
    # Colores
    PRIMARY_COLOR = "#2E86AB"
    SECONDARY_COLOR = "#A23B72"
    SUCCESS_COLOR = "#28A745"
    WARNING_COLOR = "#FFC107"
    DANGER_COLOR = "#DC3545"
    INFO_COLOR = "#17A2B8"
    
    BACKGROUND_COLOR = "#F8F9FA"
    CARD_COLOR = "#FFFFFF"
    TEXT_COLOR = "#212529"
    MUTED_COLOR = "#6C757D"
    BORDER_COLOR = "#DEE2E6"
    
    # Fuentes
    FONT_FAMILY = "Segoe UI"
    FONT_SIZE_SMALL = 9
    FONT_SIZE_NORMAL = 10
    FONT_SIZE_LARGE = 12
    FONT_SIZE_TITLE = 14
    FONT_SIZE_HEADER = 16
    
    @classmethod
    def configure_style(cls, root):
        """Configura el estilo global de la aplicación"""
        style = ttk.Style(root)
        
        # Configurar tema
        style.theme_use('clam')
        
        # Configurar colores principales
        style.configure('TLabel', 
                       background=cls.BACKGROUND_COLOR,
                       foreground=cls.TEXT_COLOR,
                       font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL))
        
        style.configure('Title.TLabel',
                       font=(cls.FONT_FAMILY, cls.FONT_SIZE_TITLE, 'bold'),
                       foreground=cls.PRIMARY_COLOR)
        
        style.configure('Header.TLabel',
                       font=(cls.FONT_FAMILY, cls.FONT_SIZE_HEADER, 'bold'),
                       foreground=cls.PRIMARY_COLOR)
        
        style.configure('Card.TFrame',
                       background=cls.CARD_COLOR,
                       relief='solid',
                       borderwidth=1)
        
        style.configure('Primary.TButton',
                       background=cls.PRIMARY_COLOR,
                       foreground='white',
                       font=(cls.FONT_FAMILY, cls.FONT_SIZE_NORMAL, 'bold'))
        
        style.configure('Success.TButton',
                       background=cls.SUCCESS_COLOR,
                       foreground='white')
        
        style.configure('Warning.TButton',
                       background=cls.WARNING_COLOR,
                       foreground='white')
        
        style.configure('Danger.TButton',
                       background=cls.DANGER_COLOR,
                       foreground='white')
        
        # Configurar progressbar
        style.configure('TProgressbar',
                       background=cls.PRIMARY_COLOR,
                       troughcolor=cls.BORDER_COLOR)

class StatusIndicator(tk.Frame):
    """Widget indicador de estado con colores"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.status_canvas = tk.Canvas(self, width=16, height=16, 
                                     highlightthickness=0)
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 5))
        
        self.status_label = tk.Label(self, text="Desconocido",
                                   font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL))
        self.status_label.pack(side=tk.LEFT)
        
        self.set_status("unknown")
    
    def set_status(self, status: str, text: str = None):
        """Actualiza el estado del indicador"""
        color_map = {
            "good": ModernStyle.SUCCESS_COLOR,
            "warning": ModernStyle.WARNING_COLOR,
            "critical": ModernStyle.DANGER_COLOR,
            "info": ModernStyle.INFO_COLOR,
            "unknown": ModernStyle.MUTED_COLOR
        }
        
        color = color_map.get(status.lower(), ModernStyle.MUTED_COLOR)
        
        self.status_canvas.delete("all")
        self.status_canvas.create_oval(2, 2, 14, 14, fill=color, outline=color)
        
        if text:
            self.status_label.config(text=text)

class ProgressCard(tk.Frame):
    """Tarjeta de progreso con información detallada"""
    
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent, relief='solid', borderwidth=1, 
                        bg=ModernStyle.CARD_COLOR, **kwargs)
        
        # Título
        self.title_label = tk.Label(self, text=title,
                                  font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_LARGE, 'bold'),
                                  bg=ModernStyle.CARD_COLOR,
                                  fg=ModernStyle.PRIMARY_COLOR)
        self.title_label.pack(pady=(10, 5), padx=10, anchor='w')
        
        # Barra de progreso
        self.progress_frame = tk.Frame(self, bg=ModernStyle.CARD_COLOR)
        self.progress_frame.pack(fill='x', padx=10, pady=5)
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress_bar.pack(fill='x')
        
        # Texto de estado
        self.status_label = tk.Label(self, text="Iniciando...",
                                   font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                                   bg=ModernStyle.CARD_COLOR,
                                   fg=ModernStyle.MUTED_COLOR)
        self.status_label.pack(pady=(0, 10), padx=10, anchor='w')
    
    def update_progress(self, progress: float, message: str = ""):
        """Actualiza el progreso y mensaje"""
        self.progress_bar['value'] = progress
        if message:
            self.status_label.config(text=message)

class MetricCard(tk.Frame):
    """Tarjeta para mostrar métricas del sistema"""
    
    def __init__(self, parent, title: str, value: str = "0", 
                 unit: str = "", color: str = None, **kwargs):
        super().__init__(parent, relief='solid', borderwidth=1,
                        bg=ModernStyle.CARD_COLOR, **kwargs)
        
        # Título
        self.title_label = tk.Label(self, text=title,
                                  font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                                  bg=ModernStyle.CARD_COLOR,
                                  fg=ModernStyle.MUTED_COLOR)
        self.title_label.pack(pady=(10, 0), padx=10)
        
        # Valor principal
        value_color = color or ModernStyle.PRIMARY_COLOR
        self.value_label = tk.Label(self, text=value,
                                  font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_TITLE, 'bold'),
                                  bg=ModernStyle.CARD_COLOR,
                                  fg=value_color)
        self.value_label.pack(padx=10)
        
        # Unidad
        if unit:
            self.unit_label = tk.Label(self, text=unit,
                                     font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                                     bg=ModernStyle.CARD_COLOR,
                                     fg=ModernStyle.MUTED_COLOR)
            self.unit_label.pack(pady=(0, 10), padx=10)
    
    def update_value(self, value: str, color: str = None):
        """Actualiza el valor mostrado"""
        self.value_label.config(text=value)
        if color:
            self.value_label.config(fg=color)

class SystemMonitorGUI:
    """Interfaz gráfica principal del sistema de monitoreo"""
    
    def __init__(self):
        """Inicializa la interfaz gráfica"""
        self.root = tk.Tk()
        self.root.title(f"Sistema de Monitoreo de PC v{SystemConfig.APP_VERSION} - {datetime.now().strftime('%Y-%m-%d')}")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        
        # Configurar icono de la aplicación
        try:
            # Crear un icono simple si no existe uno personalizado
            self.root.iconbitmap(default='')
        except:
            pass
        
        # Configurar estilo
        ModernStyle.configure_style(self.root)
        self.root.configure(bg=ModernStyle.BACKGROUND_COLOR)
        
        # Variables de estado
        self.monitor_system: Optional[SystemMonitorInterface] = None
        self.current_session_id: Optional[str] = None
        self.is_monitoring = False
        self.update_queue = queue.Queue()
        
        # Variables de interfaz
        self.status_var = tk.StringVar(value="Desconectado")
        self.session_var = tk.StringVar(value="Ninguna")
        self.progress_var = tk.StringVar(value="Listo")
        
        # Crear interfaz
        self._create_interface()
        
        # Inicializar sistema
        self._initialize_monitor_system()
        
        # Iniciar hilos de actualización
        self._start_update_threads()
        
        logger.info("Interfaz gráfica inicializada")
    
    def _create_interface(self):
        """Crea la interfaz principal"""
        # Barra de menú
        self._create_menu()
        
        # Barra de herramientas
        self._create_toolbar()
        
        # Panel principal con pestañas
        self._create_main_panel()
        
        # Barra de estado
        self._create_status_bar()
        
        # Configurar eventos de cierre
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_menu(self):
        """Crea la barra de menú"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Nueva Sesión", command=self._new_session)
        file_menu.add_command(label="Exportar Reporte...", command=self._export_report)
        file_menu.add_separator()
        file_menu.add_command(label="Configuración", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self._on_closing)
        
        # Menú Monitoreo
        monitor_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Monitoreo", menu=monitor_menu)
        monitor_menu.add_command(label="Verificación Rápida", command=self._quick_check)
        monitor_menu.add_command(label="Análisis Básico", command=self._basic_analysis)
        monitor_menu.add_command(label="Análisis Detallado", command=self._detailed_analysis)
        monitor_menu.add_separator()
        monitor_menu.add_command(label="Monitoreo Continuo", command=self._continuous_monitoring)
        monitor_menu.add_command(label="Detener Monitoreo", command=self._stop_monitoring)
        
        # Menú Herramientas
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Herramientas", menu=tools_menu)
        tools_menu.add_command(label="Captura de Pantalla", command=self._take_screenshot)
        tools_menu.add_command(label="Limpiar Datos", command=self._clear_data)
        tools_menu.add_command(label="Abrir Carpeta de Reportes", command=self._open_reports_folder)
        
        # Menú Ayuda
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ayuda", menu=help_menu)
        help_menu.add_command(label="Acerca de", command=self._show_about)
        help_menu.add_command(label="Guía de Usuario", command=self._show_help)
    
    def _create_toolbar(self):
        """Crea la barra de herramientas"""
        toolbar_frame = tk.Frame(self.root, bg=ModernStyle.BACKGROUND_COLOR, height=50)
        toolbar_frame.pack(fill='x', padx=5, pady=5)
        toolbar_frame.pack_propagate(False)
        
        # Botones principales
        ttk.Button(toolbar_frame, text="Verificación Rápida", 
                  command=self._quick_check, style='Primary.TButton').pack(side='left', padx=2)
        
        ttk.Button(toolbar_frame, text="Análisis Básico", 
                  command=self._basic_analysis).pack(side='left', padx=2)
        
        ttk.Button(toolbar_frame, text="Análisis Detallado", 
                  command=self._detailed_analysis).pack(side='left', padx=2)
        
        # Separador
        ttk.Separator(toolbar_frame, orient='vertical').pack(side='left', fill='y', padx=10)
        
        # Controles de monitoreo
        ttk.Button(toolbar_frame, text="Iniciar Monitoreo", 
                  command=self._continuous_monitoring, style='Success.TButton').pack(side='left', padx=2)
        
        ttk.Button(toolbar_frame, text="Detener", 
                  command=self._stop_monitoring, style='Danger.TButton').pack(side='left', padx=2)
        
        # Separador
        ttk.Separator(toolbar_frame, orient='vertical').pack(side='left', fill='y', padx=10)
        
        # Herramientas
        ttk.Button(toolbar_frame, text="📷 Captura", 
                  command=self._take_screenshot).pack(side='left', padx=2)
        
        ttk.Button(toolbar_frame, text="📊 Exportar", 
                  command=self._export_report).pack(side='left', padx=2)
        
        # Información del usuario
        user_frame = tk.Frame(toolbar_frame, bg=ModernStyle.BACKGROUND_COLOR)
        user_frame.pack(side='right', padx=10)
        
        tk.Label(user_frame, text=f"Usuario: SERGIORAMGO", 
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.MUTED_COLOR).pack(side='right')
        
        tk.Label(user_frame, text=f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.MUTED_COLOR).pack(side='right', padx=(0, 10))
    
    def _create_main_panel(self):
        """Crea el panel principal con pestañas"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Pestaña Dashboard
        self._create_dashboard_tab()
        
        # Pestaña Monitoreo en Tiempo Real
        self._create_realtime_tab()
        
        # Pestaña Resultados
        self._create_results_tab()
        
        # Pestaña Configuración
        self._create_config_tab()
        
        # Pestaña Logs
        self._create_logs_tab()
    
    def _create_dashboard_tab(self):
        """Crea la pestaña del dashboard"""
        dashboard_frame = tk.Frame(self.notebook, bg=ModernStyle.BACKGROUND_COLOR)
        self.notebook.add(dashboard_frame, text="Dashboard")
        
        # Panel superior - Estado del sistema
        status_frame = tk.Frame(dashboard_frame, bg=ModernStyle.BACKGROUND_COLOR)
        status_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(status_frame, text="Estado del Sistema",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(anchor='w')
        
        # Tarjetas de métricas
        metrics_frame = tk.Frame(status_frame, bg=ModernStyle.BACKGROUND_COLOR)
        metrics_frame.pack(fill='x', pady=10)
        
        # Crear métricas principales
        self.cpu_metric = MetricCard(metrics_frame, "CPU", "0", "%")
        self.cpu_metric.pack(side='left', padx=5, pady=5, fill='both', expand=True)
        
        self.memory_metric = MetricCard(metrics_frame, "Memoria", "0", "%")
        self.memory_metric.pack(side='left', padx=5, pady=5, fill='both', expand=True)
        
        self.disk_metric = MetricCard(metrics_frame, "Disco", "0", "%")
        self.disk_metric.pack(side='left', padx=5, pady=5, fill='both', expand=True)
        
        self.uptime_metric = MetricCard(metrics_frame, "Tiempo Activo", "00:00:00", "")
        self.uptime_metric.pack(side='left', padx=5, pady=5, fill='both', expand=True)
        
        # Panel de progreso actual
        progress_frame = tk.Frame(dashboard_frame, bg=ModernStyle.BACKGROUND_COLOR)
        progress_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(progress_frame, text="Progreso Actual",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(anchor='w')
        
        self.progress_card = ProgressCard(progress_frame, "Sistema Listo")
        self.progress_card.pack(fill='x', pady=10)
        
        # Panel de acciones rápidas
        actions_frame = tk.Frame(dashboard_frame, bg=ModernStyle.BACKGROUND_COLOR)
        actions_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tk.Label(actions_frame, text="Acciones Rápidas",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(anchor='w')
        
        # Botones de acciones
        actions_grid = tk.Frame(actions_frame, bg=ModernStyle.BACKGROUND_COLOR)
        actions_grid.pack(fill='both', expand=True, pady=10)
        
        # Primera fila
        row1 = tk.Frame(actions_grid, bg=ModernStyle.BACKGROUND_COLOR)
        row1.pack(fill='x', pady=5)
        
        self._create_action_button(row1, "🔍 Verificación Rápida", 
                                  "Verificación rápida del estado del sistema",
                                  self._quick_check).pack(side='left', padx=5, fill='both', expand=True)
        
        self._create_action_button(row1, "📊 Análisis Básico", 
                                  "Análisis básico de información del sistema",
                                  self._basic_analysis).pack(side='left', padx=5, fill='both', expand=True)
        
        # Segunda fila
        row2 = tk.Frame(actions_grid, bg=ModernStyle.BACKGROUND_COLOR)
        row2.pack(fill='x', pady=5)
        
        self._create_action_button(row2, "🔬 Análisis Detallado", 
                                  "Análisis completo y detallado del sistema",
                                  self._detailed_analysis).pack(side='left', padx=5, fill='both', expand=True)
        
        self._create_action_button(row2, "⚡ Monitoreo Continuo", 
                                  "Iniciar monitoreo continuo en tiempo real",
                                  self._continuous_monitoring).pack(side='left', padx=5, fill='both', expand=True)
    
    def _create_action_button(self, parent, title: str, description: str, command):
        """Crea un botón de acción con descripción"""
        button_frame = tk.Frame(parent, relief='solid', borderwidth=1,
                              bg=ModernStyle.CARD_COLOR)
        
        title_label = tk.Label(button_frame, text=title,
                             font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                             bg=ModernStyle.CARD_COLOR,
                             fg=ModernStyle.PRIMARY_COLOR)
        title_label.pack(pady=(10, 5))
        
        desc_label = tk.Label(button_frame, text=description,
                            font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                            bg=ModernStyle.CARD_COLOR,
                            fg=ModernStyle.MUTED_COLOR,
                            wraplength=200)
        desc_label.pack(pady=(0, 5))
        
        action_button = ttk.Button(button_frame, text="Ejecutar", command=command)
        action_button.pack(pady=(0, 10))
        
        return button_frame
    
    def _create_realtime_tab(self):
        """Crea la pestaña de monitoreo en tiempo real"""
        realtime_frame = tk.Frame(self.notebook, bg=ModernStyle.BACKGROUND_COLOR)
        self.notebook.add(realtime_frame, text="Tiempo Real")
        
        # Panel de control
        control_frame = tk.Frame(realtime_frame, bg=ModernStyle.BACKGROUND_COLOR)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(control_frame, text="Monitoreo en Tiempo Real",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(side='left')
        
        ttk.Button(control_frame, text="Iniciar", 
                  command=self._start_realtime_monitoring).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Pausar", 
                  command=self._pause_realtime_monitoring).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Detener", 
                  command=self._stop_realtime_monitoring).pack(side='right', padx=2)
        
        # Gráficos en tiempo real (simulados con barras de progreso)
        charts_frame = tk.Frame(realtime_frame, bg=ModernStyle.BACKGROUND_COLOR)
        charts_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # CPU Chart
        cpu_chart_frame = tk.Frame(charts_frame, relief='solid', borderwidth=1,
                                 bg=ModernStyle.CARD_COLOR)
        cpu_chart_frame.pack(fill='x', pady=5)
        
        tk.Label(cpu_chart_frame, text="Uso de CPU",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                bg=ModernStyle.CARD_COLOR).pack(pady=5)
        
        self.cpu_realtime_bar = ttk.Progressbar(cpu_chart_frame, mode='determinate')
        self.cpu_realtime_bar.pack(fill='x', padx=10, pady=5)
        
        self.cpu_realtime_label = tk.Label(cpu_chart_frame, text="0%",
                                         bg=ModernStyle.CARD_COLOR,
                                         fg=ModernStyle.MUTED_COLOR)
        self.cpu_realtime_label.pack(pady=(0, 10))
        
        # Memory Chart
        memory_chart_frame = tk.Frame(charts_frame, relief='solid', borderwidth=1,
                                    bg=ModernStyle.CARD_COLOR)
        memory_chart_frame.pack(fill='x', pady=5)
        
        tk.Label(memory_chart_frame, text="Uso de Memoria",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                bg=ModernStyle.CARD_COLOR).pack(pady=5)
        
        self.memory_realtime_bar = ttk.Progressbar(memory_chart_frame, mode='determinate')
        self.memory_realtime_bar.pack(fill='x', padx=10, pady=5)
        
        self.memory_realtime_label = tk.Label(memory_chart_frame, text="0%",
                                            bg=ModernStyle.CARD_COLOR,
                                            fg=ModernStyle.MUTED_COLOR)
        self.memory_realtime_label.pack(pady=(0, 10))
        
        # Panel de estadísticas
        stats_frame = tk.Frame(charts_frame, relief='solid', borderwidth=1,
                             bg=ModernStyle.CARD_COLOR)
        stats_frame.pack(fill='both', expand=True, pady=5)
        
        tk.Label(stats_frame, text="Estadísticas del Sistema",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                bg=ModernStyle.CARD_COLOR).pack(pady=5)
        
        self.stats_text = scrolledtext.ScrolledText(stats_frame, height=10,
                                                  font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL))
        self.stats_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))
    
    def _create_results_tab(self):
        """Crea la pestaña de resultados"""
        results_frame = tk.Frame(self.notebook, bg=ModernStyle.BACKGROUND_COLOR)
        self.notebook.add(results_frame, text="Resultados")
        
        # Panel de control
        control_frame = tk.Frame(results_frame, bg=ModernStyle.BACKGROUND_COLOR)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(control_frame, text="Resultados y Reportes",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(side='left')
        
        ttk.Button(control_frame, text="Actualizar", 
                  command=self._refresh_results).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Exportar", 
                  command=self._export_report).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Limpiar", 
                  command=self._clear_results).pack(side='right', padx=2)
        
        # Lista de resultados
        results_list_frame = tk.Frame(results_frame, bg=ModernStyle.BACKGROUND_COLOR)
        results_list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Treeview para mostrar resultados
        columns = ('Fecha', 'Tipo', 'Estado', 'Duración')
        self.results_tree = ttk.Treeview(results_list_frame, columns=columns, show='headings')
        
        for col in columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=150)
        
        # Scrollbar para la lista
        scrollbar = ttk.Scrollbar(results_list_frame, orient='vertical', 
                                command=self.results_tree.yview)
        self.results_tree.configure(yscroll=scrollbar.set)
        
        self.results_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Panel de detalles
        details_frame = tk.Frame(results_frame, relief='solid', borderwidth=1,
                               bg=ModernStyle.CARD_COLOR)
        details_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(details_frame, text="Detalles del Resultado",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                bg=ModernStyle.CARD_COLOR).pack(pady=5)
        
        self.details_text = scrolledtext.ScrolledText(details_frame, height=8,
                                                    font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL))
        self.details_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # Bind para selección
        self.results_tree.bind('<<TreeviewSelect>>', self._on_result_select)
    
    def _create_config_tab(self):
        """Crea la pestaña de configuración"""
        config_frame = tk.Frame(self.notebook, bg=ModernStyle.BACKGROUND_COLOR)
        self.notebook.add(config_frame, text="Configuración")
        
        # Canvas con scrollbar para la configuración
        canvas = tk.Canvas(config_frame, bg=ModernStyle.BACKGROUND_COLOR)
        scrollbar = ttk.Scrollbar(config_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=ModernStyle.BACKGROUND_COLOR)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Configuración General
        general_frame = tk.LabelFrame(scrollable_frame, text="Configuración General",
                                    font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                                    bg=ModernStyle.BACKGROUND_COLOR)
        general_frame.pack(fill='x', padx=10, pady=10)
        
        # Auto-guardar resultados
        self.auto_save_var = tk.BooleanVar(value=True)
        tk.Checkbutton(general_frame, text="Auto-guardar resultados",
                      variable=self.auto_save_var,
                      bg=ModernStyle.BACKGROUND_COLOR).pack(anchor='w', padx=10, pady=5)
        
        # Interval de monitoreo
        interval_frame = tk.Frame(general_frame, bg=ModernStyle.BACKGROUND_COLOR)
        interval_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(interval_frame, text="Intervalo de monitoreo (segundos):",
                bg=ModernStyle.BACKGROUND_COLOR).pack(side='left')
        
        self.interval_var = tk.StringVar(value="60")
        tk.Entry(interval_frame, textvariable=self.interval_var, width=10).pack(side='right')
        
        # Configuración de Capturas
        screenshot_frame = tk.LabelFrame(scrollable_frame, text="Capturas de Pantalla",
                                       font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                                       bg=ModernStyle.BACKGROUND_COLOR)
        screenshot_frame.pack(fill='x', padx=10, pady=10)
        
        # Captura automática
        self.auto_screenshot_var = tk.BooleanVar(value=False)
        tk.Checkbutton(screenshot_frame, text="Capturas automáticas durante monitoreo",
                      variable=self.auto_screenshot_var,
                      bg=ModernStyle.BACKGROUND_COLOR).pack(anchor='w', padx=10, pady=5)
        
        # Incluir todos los monitores
        self.all_monitors_var = tk.BooleanVar(value=True)
        tk.Checkbutton(screenshot_frame, text="Incluir todos los monitores",
                      variable=self.all_monitors_var,
                      bg=ModernStyle.BACKGROUND_COLOR).pack(anchor='w', padx=10, pady=5)
        
        # Configuración de Reportes
        reports_frame = tk.LabelFrame(scrollable_frame, text="Reportes",
                                    font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_NORMAL, 'bold'),
                                    bg=ModernStyle.BACKGROUND_COLOR)
        reports_frame.pack(fill='x', padx=10, pady=10)
        
        # Formato por defecto
        format_frame = tk.Frame(reports_frame, bg=ModernStyle.BACKGROUND_COLOR)
        format_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(format_frame, text="Formato de reporte por defecto:",
                bg=ModernStyle.BACKGROUND_COLOR).pack(side='left')
        
        self.report_format_var = tk.StringVar(value="json")
        format_combo = ttk.Combobox(format_frame, textvariable=self.report_format_var,
                                  values=["json", "html", "text"], state="readonly")
        format_combo.pack(side='right')
        
        # Botones de configuración
        buttons_frame = tk.Frame(scrollable_frame, bg=ModernStyle.BACKGROUND_COLOR)
        buttons_frame.pack(fill='x', padx=10, pady=20)
        
        ttk.Button(buttons_frame, text="Guardar Configuración", 
                  command=self._save_config).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Restaurar Defaults", 
                  command=self._restore_defaults).pack(side='left', padx=5)
        ttk.Button(buttons_frame, text="Abrir Carpeta de Configuración", 
                  command=self._open_config_folder).pack(side='left', padx=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def _create_logs_tab(self):
        """Crea la pestaña de logs"""
        logs_frame = tk.Frame(self.notebook, bg=ModernStyle.BACKGROUND_COLOR)
        self.notebook.add(logs_frame, text="Logs")
        
        # Panel de control
        control_frame = tk.Frame(logs_frame, bg=ModernStyle.BACKGROUND_COLOR)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        tk.Label(control_frame, text="Logs del Sistema",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_HEADER, 'bold'),
                bg=ModernStyle.BACKGROUND_COLOR,
                fg=ModernStyle.PRIMARY_COLOR).pack(side='left')
        
        ttk.Button(control_frame, text="Actualizar", 
                  command=self._refresh_logs).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Limpiar", 
                  command=self._clear_logs).pack(side='right', padx=2)
        ttk.Button(control_frame, text="Exportar", 
                  command=self._export_logs).pack(side='right', padx=2)
        
        # Filtros
        filter_frame = tk.Frame(logs_frame, bg=ModernStyle.BACKGROUND_COLOR)
        filter_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Label(filter_frame, text="Nivel:",
                bg=ModernStyle.BACKGROUND_COLOR).pack(side='left', padx=(0, 5))
        
        self.log_level_var = tk.StringVar(value="ALL")
        level_combo = ttk.Combobox(filter_frame, textvariable=self.log_level_var,
                                 values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                                 width=10, state="readonly")
        level_combo.pack(side='left', padx=5)
        level_combo.bind('<<ComboboxSelected>>', self._filter_logs)
        
        # Área de logs
        self.logs_text = scrolledtext.ScrolledText(logs_frame, 
                                                 font=('Courier New', ModernStyle.FONT_SIZE_SMALL),
                                                 bg='black', fg='lightgreen')
        self.logs_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Configurar colores para diferentes niveles
        self.logs_text.tag_configure("ERROR", foreground="red")
        self.logs_text.tag_configure("WARNING", foreground="orange")
        self.logs_text.tag_configure("INFO", foreground="lightblue")
        self.logs_text.tag_configure("DEBUG", foreground="gray")
        self.logs_text.tag_configure("CRITICAL", foreground="red", background="yellow")
    
    def _create_status_bar(self):
        """Crea la barra de estado"""
        self.status_bar = tk.Frame(self.root, bg=ModernStyle.BORDER_COLOR, height=25)
        self.status_bar.pack(fill='x', side='bottom')
        self.status_bar.pack_propagate(False)
        
        # Estado del sistema
        self.system_status_indicator = StatusIndicator(self.status_bar, 
                                                      bg=ModernStyle.BORDER_COLOR)
        self.system_status_indicator.pack(side='left', padx=10, pady=3)
        
        # Separador
        ttk.Separator(self.status_bar, orient='vertical').pack(side='left', fill='y', padx=5)
        
        # Sesión actual
        tk.Label(self.status_bar, text="Sesión:",
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                bg=ModernStyle.BORDER_COLOR).pack(side='left', padx=(5, 0))
        
        tk.Label(self.status_bar, textvariable=self.session_var,
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                bg=ModernStyle.BORDER_COLOR).pack(side='left', padx=(2, 10))
        
        # Progreso actual
        tk.Label(self.status_bar, textvariable=self.progress_var,
                font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                bg=ModernStyle.BORDER_COLOR).pack(side='left', padx=5)
        
        # Información del sistema
        self.system_info_label = tk.Label(self.status_bar, text="Sistema listo",
                                        font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                                        bg=ModernStyle.BORDER_COLOR)
        self.system_info_label.pack(side='right', padx=10)
    
    def _initialize_monitor_system(self):
        """Inicializa el sistema de monitoreo"""
        try:
            self.monitor_system = create_system_monitor()
            if self.monitor_system:
                # Configurar callbacks
                self.monitor_system.set_callbacks(
                    status_callback=self._on_status_change,
                    progress_callback=self._on_progress_update,
                    result_callback=self._on_result_received
                )
                
                self.system_status_indicator.set_status("good", "Conectado")
                self.system_info_label.config(text="Sistema inicializado correctamente")
                logger.info("Sistema de monitoreo inicializado desde GUI")
            else:
                self.system_status_indicator.set_status("critical", "Error")
                self.system_info_label.config(text="Error inicializando sistema")
                messagebox.showerror("Error", "No se pudo inicializar el sistema de monitoreo")
                
        except Exception as e:
            logger.error(f"Error inicializando sistema desde GUI: {e}")
            self.system_status_indicator.set_status("critical", "Error")
            messagebox.showerror("Error", f"Error crítico: {str(e)}")
    
    def _start_update_threads(self):
        """Inicia los hilos de actualización de la interfaz"""
        # Hilo para actualizar métricas en tiempo real
        self.update_thread = threading.Thread(target=self._update_metrics_loop, daemon=True)
        self.update_thread.start()
        
        # Hilo para procesar cola de actualizaciones
        self.queue_thread = threading.Thread(target=self._process_update_queue, daemon=True)
        self.queue_thread.start()
        
        logger.info("Hilos de actualización de GUI iniciados")
    
    def _update_metrics_loop(self):
        """Loop para actualizar métricas del sistema"""
        try:
            import psutil
            
            while True:
                try:
                    if self.monitor_system:
                        # Obtener métricas actuales
                        cpu_percent = psutil.cpu_percent(interval=1)
                        memory = psutil.virtual_memory()
                        
                        # Obtener uso de disco promedio
                        disk_usage = 0
                        try:
                            partitions = psutil.disk_partitions()
                            if partitions:
                                usages = []
                                for partition in partitions:
                                    try:
                                        usage = psutil.disk_usage(partition.mountpoint)
                                        usages.append((usage.used / usage.total) * 100)
                                    except PermissionError:
                                        continue
                                if usages:
                                    disk_usage = sum(usages) / len(usages)
                        except Exception:
                            pass
                        
                        # Uptime
                        try:
                            boot_time = psutil.boot_time()
                            uptime_seconds = time.time() - boot_time
                            uptime_str = SystemUtilities.format_duration(uptime_seconds)
                        except Exception:
                            uptime_str = "Unknown"
                        
                        # Actualizar interfaz via cola
                        self.update_queue.put({
                            'type': 'metrics_update',
                            'data': {
                                'cpu': cpu_percent,
                                'memory': memory.percent,
                                'disk': disk_usage,
                                'uptime': uptime_str
                            }
                        })
                        
                        # Actualizar gráficos en tiempo real si está en esa pestaña
                        current_tab = self.notebook.index(self.notebook.select())
                        if current_tab == 1:  # Pestaña de tiempo real
                            self.update_queue.put({
                                'type': 'realtime_update',
                                'data': {
                                    'cpu': cpu_percent,
                                    'memory': memory.percent,
                                    'stats': f"CPU: {cpu_percent:.1f}% | Memoria: {memory.percent:.1f}% | "
                                           f"Disponible: {SystemUtilities.format_bytes(memory.available)}"
                                }
                            })
                    
                    time.sleep(2)  # Actualizar cada 2 segundos
                    
                except Exception as e:
                    logger.error(f"Error en loop de métricas: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            logger.error(f"Error crítico en loop de métricas: {e}")
    
    def _process_update_queue(self):
        """Procesa la cola de actualizaciones de la interfaz"""
        while True:
            try:
                update = self.update_queue.get(timeout=1)
                
                if update['type'] == 'metrics_update':
                    self.root.after(0, self._update_dashboard_metrics, update['data'])
                elif update['type'] == 'realtime_update':
                    self.root.after(0, self._update_realtime_display, update['data'])
                elif update['type'] == 'progress_update':
                    self.root.after(0, self._update_progress_display, update['data'])
                elif update['type'] == 'status_update':
                    self.root.after(0, self._update_status_display, update['data'])
                elif update['type'] == 'result_update':
                    self.root.after(0, self._update_results_display, update['data'])
                elif update['type'] == 'log_update':
                    self.root.after(0, self._update_logs_display, update['data'])
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error procesando cola de actualizaciones: {e}")
    
    def _update_dashboard_metrics(self, data):
        """Actualiza las métricas del dashboard"""
        try:
            # Actualizar métricas
            cpu_color = ModernStyle.SUCCESS_COLOR if data['cpu'] < 70 else ModernStyle.WARNING_COLOR if data['cpu'] < 90 else ModernStyle.DANGER_COLOR
            self.cpu_metric.update_value(f"{data['cpu']:.1f}", cpu_color)
            
            mem_color = ModernStyle.SUCCESS_COLOR if data['memory'] < 70 else ModernStyle.WARNING_COLOR if data['memory'] < 90 else ModernStyle.DANGER_COLOR
            self.memory_metric.update_value(f"{data['memory']:.1f}", mem_color)
            
            disk_color = ModernStyle.SUCCESS_COLOR if data['disk'] < 80 else ModernStyle.WARNING_COLOR if data['disk'] < 95 else ModernStyle.DANGER_COLOR
            self.disk_metric.update_value(f"{data['disk']:.1f}", disk_color)
            
            self.uptime_metric.update_value(data['uptime'])
            
        except Exception as e:
            logger.error(f"Error actualizando métricas dashboard: {e}")
    
    def _update_realtime_display(self, data):
        """Actualiza la visualización en tiempo real"""
        try:
            self.cpu_realtime_bar['value'] = data['cpu']
            self.cpu_realtime_label.config(text=f"{data['cpu']:.1f}%")
            
            self.memory_realtime_bar['value'] = data['memory']
            self.memory_realtime_label.config(text=f"{data['memory']:.1f}%")
            
            # Agregar estadísticas al área de texto
            timestamp = datetime.now().strftime("%H:%M:%S")
            stats_line = f"[{timestamp}] {data['stats']}\n"
            
            self.stats_text.insert(tk.END, stats_line)
            self.stats_text.see(tk.END)
            
            # Limitar líneas (mantener últimas 100)
            lines = self.stats_text.get("1.0", tk.END).split('\n')
            if len(lines) > 100:
                self.stats_text.delete("1.0", f"{len(lines) - 100}.0")
            
        except Exception as e:
            logger.error(f"Error actualizando display tiempo real: {e}")
    
    def _update_progress_display(self, data):
        """Actualiza la visualización de progreso"""
        try:
            self.progress_card.update_progress(data['progress'], data['message'])
            self.progress_var.set(data['message'])
            
        except Exception as e:
            logger.error(f"Error actualizando progreso: {e}")
    
    def _update_status_display(self, data):
        """Actualiza la visualización de estado"""
        try:
            status = data['status'].lower()
            
            if status == 'idle':
                self.system_status_indicator.set_status("good", "Listo")
            elif status == 'scanning':
                self.system_status_indicator.set_status("info", "Escaneando")
            elif status == 'monitoring':
                self.system_status_indicator.set_status("info", "Monitoreando")
            elif status == 'error':
                self.system_status_indicator.set_status("critical", "Error")
            else:
                self.system_status_indicator.set_status("unknown", status.title())
            
            self.status_var.set(status.title())
            
        except Exception as e:
            logger.error(f"Error actualizando estado: {e}")
    
    def _update_results_display(self, data):
        """Actualiza la visualización de resultados"""
        try:
            # Agregar resultado a la lista
            result_id = data.get('task_id', 'Unknown')
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task_type = data.get('task_type', 'Unknown')
            status = data.get('status', 'Unknown')
            duration = data.get('execution_time', 0)
            
            self.results_tree.insert('', 0, values=(timestamp, task_type, status, f"{duration:.2f}s"))
            
        except Exception as e:
            logger.error(f"Error actualizando resultados: {e}")
    
    def _update_logs_display(self, data):
        """Actualiza la visualización de logs"""
        try:
            level = data.get('level', 'INFO')
            message = data.get('message', '')
            timestamp = data.get('timestamp', datetime.now().strftime("%H:%M:%S"))
            
            # Filtrar por nivel si es necesario
            current_filter = self.log_level_var.get()
            if current_filter != "ALL" and level != current_filter:
                return
            
            log_line = f"[{timestamp}] {level}: {message}\n"
            
            self.logs_text.insert(tk.END, log_line, level)
            self.logs_text.see(tk.END)
            
            # Limitar líneas
            lines = self.logs_text.get("1.0", tk.END).split('\n')
            if len(lines) > 500:
                self.logs_text.delete("1.0", f"{len(lines) - 500}.0")
            
        except Exception as e:
            logger.error(f"Error actualizando logs: {e}")
    
    # Eventos de la interfaz
    
    def _on_status_change(self, status):
        """Callback para cambio de estado"""
        self.update_queue.put({
            'type': 'status_update',
            'data': {'status': status.value}
        })
    
    def _on_progress_update(self, message, progress):
        """Callback para actualización de progreso"""
        self.update_queue.put({
            'type': 'progress_update',
            'data': {'message': message, 'progress': progress}
        })
    
    def _on_result_received(self, task_id, result):
        """Callback para recepción de resultado"""
        self.update_queue.put({
            'type': 'result_update',
            'data': {
                'task_id': task_id,
                'task_type': result.get('description', 'Task'),
                'status': result.get('status', 'Unknown'),
                'execution_time': result.get('execution_time', 0)
            }
        })
    
    def _on_result_select(self, event):
        """Maneja la selección de un resultado"""
        try:
            selection = self.results_tree.selection()
            if selection:
                item = self.results_tree.item(selection[0])
                values = item['values']
                
                # Mostrar detalles (simulado)
                details = f"Resultado seleccionado:\n\n"
                details += f"Fecha: {values[0]}\n"
                details += f"Tipo: {values[1]}\n"
                details += f"Estado: {values[2]}\n"
                details += f"Duración: {values[3]}\n\n"
                details += "Detalles adicionales disponibles en el archivo de reporte correspondiente."
                
                self.details_text.delete('1.0', tk.END)
                self.details_text.insert('1.0', details)
                
        except Exception as e:
            logger.error(f"Error mostrando detalles de resultado: {e}")
    
    def _on_closing(self):
        """Maneja el cierre de la aplicación"""
        try:
            if self.is_monitoring:
                response = messagebox.askyesno(
                    "Confirmación", 
                    "Hay un monitoreo en progreso. ¿Desea detenerlo y salir?"
                )
                if not response:
                    return
                
                self._stop_monitoring()
            
            if self.monitor_system:
                self.monitor_system.shutdown_system()
            
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            logger.error(f"Error cerrando aplicación: {e}")
            self.root.quit()
    
    # Acciones del menú y botones
    
    def _new_session(self):
        """Inicia una nueva sesión"""
        try:
            if self.current_session_id:
                response = messagebox.askyesno(
                    "Nueva Sesión", 
                    "¿Desea finalizar la sesión actual e iniciar una nueva?"
                )
                if not response:
                    return
                
                self._stop_monitoring()
            
            # Mostrar diálogo de configuración de sesión
            self._show_session_config_dialog()
            
        except Exception as e:
            logger.error(f"Error iniciando nueva sesión: {e}")
            messagebox.showerror("Error", f"Error iniciando nueva sesión: {str(e)}")
    
    def _show_session_config_dialog(self):
        """Muestra diálogo de configuración de sesión"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Nueva Sesión de Monitoreo")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Centrar diálogo
        dialog.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))
        
        # Modo de monitoreo
        mode_frame = tk.LabelFrame(dialog, text="Modo de Monitoreo")
        mode_frame.pack(fill='x', padx=10, pady=10)
        
        mode_var = tk.StringVar(value="basic")
        
        modes = [
            ("Básico", "basic", "Información esencial del sistema"),
            ("Detallado", "detailed", "Análisis completo del sistema"),
            ("Continuo", "continuous", "Monitoreo en tiempo real"),
            ("Seguridad", "security_focused", "Enfoque en aspectos de seguridad"),
            ("Rendimiento", "performance_focused", "Enfoque en rendimiento"),
            ("Mantenimiento", "maintenance", "Tareas de mantenimiento")
        ]
        
        for text, value, desc in modes:
            frame = tk.Frame(mode_frame)
            frame.pack(fill='x', padx=5, pady=2)
            
            tk.Radiobutton(frame, text=text, variable=mode_var, value=value).pack(side='left')
            tk.Label(frame, text=desc, font=(ModernStyle.FONT_FAMILY, ModernStyle.FONT_SIZE_SMALL),
                    fg=ModernStyle.MUTED_COLOR).pack(side='left', padx=(10, 0))
        
        # Opciones adicionales
        options_frame = tk.LabelFrame(dialog, text="Opciones")
        options_frame.pack(fill='x', padx=10, pady=10)
        
        auto_screenshot_var = tk.BooleanVar()
        tk.Checkbutton(options_frame, text="Capturas automáticas",
                      variable=auto_screenshot_var).pack(anchor='w', padx=5, pady=2)
        
        auto_export_var = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Exportar reporte automáticamente",
                      variable=auto_export_var).pack(anchor='w', padx=5, pady=2)
        
        # Botones
        buttons_frame = tk.Frame(dialog)
        buttons_frame.pack(fill='x', padx=10, pady=10)
        
        def start_session():
            try:
                mode_map = {
                    'basic': MonitoringMode.BASIC,
                    'detailed': MonitoringMode.DETAILED,
                    'continuous': MonitoringMode.CONTINUOUS,
                    'security_focused': MonitoringMode.SECURITY_FOCUSED,
                    'performance_focused': MonitoringMode.PERFORMANCE_FOCUSED,
                    'maintenance': MonitoringMode.MAINTENANCE
                }
                
                selected_mode = mode_map[mode_var.get()]
                
                if self.monitor_system:
                    self.current_session_id = self.monitor_system.start_monitoring_session(selected_mode)
                    self.session_var.set(self.current_session_id[-8:])  # Últimos 8 caracteres
                    self.is_monitoring = True
                    
                    messagebox.showinfo("Sesión Iniciada", 
                                      f"Sesión iniciada exitosamente\nID: {self.current_session_id}")
                
                dialog.destroy()
                
            except Exception as e:
                logger.error(f"Error iniciando sesión desde diálogo: {e}")
                messagebox.showerror("Error", f"Error iniciando sesión: {str(e)}")
        
        ttk.Button(buttons_frame, text="Iniciar", command=start_session).pack(side='right', padx=5)
        ttk.Button(buttons_frame, text="Cancelar", command=dialog.destroy).pack(side='right')
    
    def _quick_check(self):
        """Ejecuta verificación rápida"""
        try:
            if not self.monitor_system:
                messagebox.showerror("Error", "Sistema de monitoreo no disponible")
                return
            