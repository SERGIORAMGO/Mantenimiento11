"""
Sistema de Monitoreo de PC - Módulo 13: Interfaz de Línea de Comandos (CLI)
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Interfaz de línea de comandos completa para el sistema de monitoreo
"""

import argparse
import sys
import os
import json
import time
import signal
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path
import textwrap
import shlex

# Colores para terminal (ANSI escape codes)
class Colors:
    """Códigos de color ANSI para terminal"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Colores de texto
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Colores de fondo
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # Colores personalizados
    HEADER = '\033[95m'
    INFO = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    
    @staticmethod
    def colored(text: str, color: str) -> str:
        """Retorna texto con color ANSI"""
        return f"{color}{text}{Colors.RESET}"
    
    @staticmethod
    def is_supported() -> bool:
        """Verifica si el terminal soporta colores ANSI"""
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

# Importar módulos del sistema
from config_and_imports import SystemConfig, SystemConstants
from utilities import SystemUtilities, FileUtilities
from main_interface import (
    SystemMonitorInterface, MonitoringMode, SystemStatus,
    create_system_monitor, run_quick_system_scan, run_basic_system_info
)

# Logger para este módulo
logger = logging.getLogger(__name__)

class ProgressBar:
    """Barra de progreso para CLI"""
    
    def __init__(self, total: int = 100, width: int = 50, 
                 prefix: str = "Progreso", suffix: str = "Completo"):
        self.total = total
        self.width = width
        self.prefix = prefix
        self.suffix = suffix
        self.current = 0
        self.start_time = time.time()
    
    def update(self, current: int, message: str = ""):
        """Actualiza la barra de progreso"""
        self.current = current
        percent = (current / self.total) * 100
        filled_length = int(self.width * current // self.total)
        bar = '█' * filled_length + '░' * (self.width - filled_length)
        
        # Calcular tiempo estimado
        elapsed = time.time() - self.start_time
        if current > 0:
            eta = (elapsed / current) * (self.total - current)
            eta_str = f"ETA: {int(eta)}s"
        else:
            eta_str = "ETA: --s"
        
        # Formatear mensaje
        if message:
            display_message = f" | {message[:30]}"
        else:
            display_message = ""
        
        # Imprimir barra
        sys.stdout.write(f'\r{self.prefix} |{bar}| {percent:.1f}% {eta_str}{display_message}')
        sys.stdout.flush()
        
        if current >= self.total:
            print()  # Nueva línea al completar
    
    def finish(self, message: str = ""):
        """Finaliza la barra de progreso"""
        self.update(self.total, message)

class TableFormatter:
    """Formateador de tablas para CLI"""
    
    @staticmethod
    def format_table(data: List[Dict], headers: List[str], 
                    max_width: int = 80) -> str:
        """Formatea datos en tabla"""
        if not data:
            return "No hay datos para mostrar"
        
        # Calcular anchos de columna
        col_widths = {}
        for header in headers:
            col_widths[header] = len(header)
        
        for row in data:
            for header in headers:
                value = str(row.get(header, ''))
                col_widths[header] = max(col_widths[header], len(value))
        
        # Ajustar anchos si exceden el máximo
        total_width = sum(col_widths.values()) + len(headers) * 3
        if total_width > max_width:
            # Reducir proporcionalmente
            factor = (max_width - len(headers) * 3) / sum(col_widths.values())
            for header in headers:
                col_widths[header] = max(8, int(col_widths[header] * factor))
        
        # Crear tabla
        lines = []
        
        # Línea de encabezado
        header_line = "| " + " | ".join(
            header.ljust(col_widths[header]) for header in headers
        ) + " |"
        lines.append(header_line)
        
        # Línea separadora
        separator = "+" + "+".join(
            "-" * (col_widths[header] + 2) for header in headers
        ) + "+"
        lines.append(separator)
        
        # Líneas de datos
        for row in data:
            row_line = "| " + " | ".join(
                str(row.get(header, '')).ljust(col_widths[header])[:col_widths[header]]
                for header in headers
            ) + " |"
            lines.append(row_line)
        
        return "\n".join(lines)

class StatusDisplay:
    """Display de estado para CLI"""
    
    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors and Colors.is_supported()
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_index = 0
    
    def print_header(self, text: str):
        """Imprime encabezado"""
        if self.use_colors:
            print(Colors.colored(f"\n{'='*60}", Colors.HEADER))
            print(Colors.colored(f" {text.center(58)} ", Colors.HEADER + Colors.BOLD))
            print(Colors.colored(f"{'='*60}", Colors.HEADER))
        else:
            print(f"\n{'='*60}")
            print(f" {text.center(58)} ")
            print(f"{'='*60}")
    
    def print_section(self, text: str):
        """Imprime sección"""
        if self.use_colors:
            print(Colors.colored(f"\n▶ {text}", Colors.INFO + Colors.BOLD))
            print(Colors.colored("-" * (len(text) + 3), Colors.INFO))
        else:
            print(f"\n▶ {text}")
            print("-" * (len(text) + 3))
    
    def print_success(self, text: str):
        """Imprime mensaje de éxito"""
        if self.use_colors:
            print(Colors.colored(f"✓ {text}", Colors.SUCCESS))
        else:
            print(f"✓ {text}")
    
    def print_error(self, text: str):
        """Imprime mensaje de error"""
        if self.use_colors:
            print(Colors.colored(f"✗ {text}", Colors.ERROR))
        else:
            print(f"✗ {text}")
    
    def print_warning(self, text: str):
        """Imprime mensaje de advertencia"""
        if self.use_colors:
            print(Colors.colored(f"⚠ {text}", Colors.WARNING))
        else:
            print(f"⚠ {text}")
    
    def print_info(self, text: str):
        """Imprime mensaje informativo"""
        if self.use_colors:
            print(Colors.colored(f"ℹ {text}", Colors.INFO))
        else:
            print(f"ℹ {text}")
    
    def print_metric(self, label: str, value: str, status: str = "normal"):
        """Imprime métrica con estado"""
        color_map = {
            "good": Colors.SUCCESS,
            "warning": Colors.WARNING,
            "critical": Colors.ERROR,
            "normal": Colors.WHITE
        }
        
        color = color_map.get(status, Colors.WHITE)
        
        if self.use_colors:
            print(f"  {label}: {Colors.colored(value, color)}")
        else:
            print(f"  {label}: {value}")
    
    def get_spinner(self) -> str:
        """Obtiene siguiente carácter del spinner"""
        char = self.spinner_chars[self.spinner_index]
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        return char

class SystemMonitorCLI:
    """Interfaz de línea de comandos para el sistema de monitoreo"""
    
    def __init__(self):
        """Inicializa la CLI"""
        self.version = SystemConfig.APP_VERSION
        self.author = "SERGIORAMGO"
        self.build_date = "2025-06-22"
        
        # Configuración
        self.use_colors = Colors.is_supported()
        self.verbose = False
        self.quiet = False
        self.output_format = 'text'
        self.output_file = None
        
        # Sistema de monitoreo
        self.monitor_system: Optional[SystemMonitorInterface] = None
        self.current_session_id: Optional[str] = None
        
        # Display
        self.display = StatusDisplay(self.use_colors)
        
        # Control de señales
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Estado
        self.running = True
        self.interactive_mode = False
    
    def _signal_handler(self, signum, frame):
        """Maneja señales del sistema"""
        if signum in [signal.SIGINT, signal.SIGTERM]:
            self.display.print_warning("\nSeñal de interrupción recibida. Cerrando...")
            self.running = False
            if self.monitor_system:
                self.monitor_system.shutdown_system()
            sys.exit(0)
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Crea el parser de argumentos"""
        parser = argparse.ArgumentParser(
            prog='sysmonitor',
            description=f'Sistema de Monitoreo de PC v{self.version} por {self.author}',
            epilog='Ejemplos de uso:\n'
                   '  sysmonitor quick                    # Verificación rápida\n'
                   '  sysmonitor scan --detailed          # Escaneo detallado\n'
                   '  sysmonitor monitor --mode continuous # Monitoreo continuo\n'
                   '  sysmonitor interactive              # Modo interactivo\n',
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        
        # Argumentos globales
        parser.add_argument('-v', '--verbose', action='store_true',
                          help='Salida detallada')
        parser.add_argument('-q', '--quiet', action='store_true',
                          help='Salida mínima')
        parser.add_argument('--no-color', action='store_true',
                          help='Deshabilitar colores')
        parser.add_argument('--format', choices=['text', 'json', 'csv'],
                          default='text', help='Formato de salida')
        parser.add_argument('-o', '--output', 
                          help='Archivo de salida')
        parser.add_argument('--version', action='version',
                          version=f'%(prog)s {self.version}')
        
        # Subcomandos
        subparsers = parser.add_subparsers(dest='command', help='Comandos disponibles')
        
        # Comando quick
        quick_parser = subparsers.add_parser('quick', 
                                           help='Verificación rápida del sistema')
        quick_parser.add_argument('--export', help='Exportar resultado a archivo')
        
        # Comando scan
        scan_parser = subparsers.add_parser('scan',
                                          help='Escaneo del sistema')
        scan_parser.add_argument('--detailed', action='store_true',
                               help='Escaneo detallado')
        scan_parser.add_argument('--hardware', action='store_true',
                               help='Incluir información de hardware')
        scan_parser.add_argument('--software', action='store_true',
                               help='Incluir información de software')
        scan_parser.add_argument('--network', action='store_true',
                               help='Incluir información de red')
        scan_parser.add_argument('--export', help='Exportar resultado a archivo')
        
        # Comando monitor
        monitor_parser = subparsers.add_parser('monitor',
                                             help='Monitoreo del sistema')
        monitor_parser.add_argument('--mode', 
                                  choices=['basic', 'detailed', 'continuous', 
                                          'security', 'performance', 'maintenance'],
                                  default='basic',
                                  help='Modo de monitoreo')
        monitor_parser.add_argument('--duration', type=int, default=60,
                                  help='Duración en segundos (para modo continuo)')
        monitor_parser.add_argument('--interval', type=int, default=5,
                                  help='Intervalo de muestreo en segundos')
        monitor_parser.add_argument('--export', help='Exportar resultado a archivo')
        
        # Comando temperature
        temp_parser = subparsers.add_parser('temperature',
                                          help='Monitoreo de temperatura')
        temp_parser.add_argument('--duration', type=int, default=60,
                               help='Duración del monitoreo en segundos')
        temp_parser.add_argument('--threshold', type=float, default=80.0,
                               help='Umbral de temperatura crítica')
        temp_parser.add_argument('--continuous', action='store_true',
                               help='Monitoreo continuo')
        
        # Comando cpu
        cpu_parser = subparsers.add_parser('cpu',
                                         help='Monitoreo de CPU')
        cpu_parser.add_argument('--duration', type=int, default=60,
                              help='Duración del monitoreo en segundos')
        cpu_parser.add_argument('--show-cores', action='store_true',
                              help='Mostrar uso por núcleo')
        
        # Comando memory
        memory_parser = subparsers.add_parser('memory',
                                            help='Monitoreo de memoria')
        memory_parser.add_argument('--duration', type=int, default=60,
                                 help='Duración del monitoreo en segundos')
        memory_parser.add_argument('--show-processes', action='store_true',
                                 help='Mostrar procesos con mayor uso')
        
        # Comando disk
        disk_parser = subparsers.add_parser('disk',
                                          help='Análisis de discos')
        disk_parser.add_argument('--health', action='store_true',
                               help='Verificar salud de discos')
        disk_parser.add_argument('--performance', action='store_true',
                               help='Análisis de rendimiento')
        disk_parser.add_argument('--cleanup', action='store_true',
                               help='Análisis de archivos temporales')
        
        # Comando security
        security_parser = subparsers.add_parser('security',
                                              help='Análisis de seguridad')
        security_parser.add_argument('--antivirus', action='store_true',
                                   help='Verificar estado del antivirus')
        security_parser.add_argument('--updates', action='store_true',
                                   help='Verificar Windows Update')
        security_parser.add_argument('--firewall', action='store_true',
                                   help='Verificar firewall')
        
        # Comando services
        services_parser = subparsers.add_parser('services',
                                              help='Análisis de servicios')
        services_parser.add_argument('--running-only', action='store_true',
                                   help='Solo servicios en ejecución')
        services_parser.add_argument('--critical-only', action='store_true',
                                   help='Solo servicios críticos')
        
        # Comando startup
        startup_parser = subparsers.add_parser('startup',
                                             help='Análisis de programas de inicio')
        startup_parser.add_argument('--registry', action='store_true',
                                  help='Incluir entradas del registro')
        startup_parser.add_argument('--folders', action='store_true',
                                  help='Incluir carpetas de inicio')
        startup_parser.add_argument('--tasks', action='store_true',
                                  help='Incluir tareas programadas')
        
        # Comando screenshot
        screenshot_parser = subparsers.add_parser('screenshot',
                                                help='Captura de pantalla')
        screenshot_parser.add_argument('--all-monitors', action='store_true',
                                     help='Capturar todos los monitores')
        screenshot_parser.add_argument('--output-dir', 
                                     help='Directorio de salida')
        
        # Comando export
        export_parser = subparsers.add_parser('export',
                                            help='Exportar reportes')
        export_parser.add_argument('--session-id', help='ID de sesión a exportar')
        export_parser.add_argument('--format', choices=['json', 'html', 'text'],
                                 default='json', help='Formato de exportación')
        export_parser.add_argument('--output-dir', help='Directorio de salida')
        
        # Comando status
        status_parser = subparsers.add_parser('status',
                                            help='Estado del sistema de monitoreo')
        status_parser.add_argument('--detailed', action='store_true',
                                 help='Estado detallado')
        
        # Comando interactive
        interactive_parser = subparsers.add_parser('interactive',
                                                 help='Modo interactivo')
        
        # Comando config
        config_parser = subparsers.add_parser('config',
                                            help='Configuración del sistema')
        config_parser.add_argument('--show', action='store_true',
                                 help='Mostrar configuración actual')
        config_parser.add_argument('--reset', action='store_true',
                                 help='Restaurar configuración por defecto')
        
        return parser
    
    def run(self, args: List[str] = None) -> int:
        """Ejecuta la CLI"""
        try:
            parser = self.create_parser()
            parsed_args = parser.parse_args(args)
            
            # Configurar opciones globales
            self.verbose = parsed_args.verbose
            self.quiet = parsed_args.quiet
            if parsed_args.no_color:
                self.use_colors = False
                self.display = StatusDisplay(False)
            self.output_format = parsed_args.format
            self.output_file = parsed_args.output
            
            # Mostrar banner
            if not self.quiet:
                self._show_banner()
            
            # Ejecutar comando
            if not parsed_args.command:
                parser.print_help()
                return 0
            
            return self._execute_command(parsed_args)
            
        except KeyboardInterrupt:
            self.display.print_warning("\nOperación cancelada por el usuario")
            return 130
        except Exception as e:
            self.display.print_error(f"Error crítico: {str(e)}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return 1
    
    def _show_banner(self):
        """Muestra el banner de la aplicación"""
        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║            Sistema de Monitoreo de PC v{self.version}                    ║
║                    Autor: {self.author}                        ║
║                   Fecha: {self.build_date}                       ║
╚══════════════════════════════════════════════════════════════╝
        """
        
        if self.use_colors:
            print(Colors.colored(banner, Colors.HEADER))
        else:
            print(banner)
    
    def _execute_command(self, args) -> int:
        """Ejecuta el comando especificado"""
        try:
            command_map = {
                'quick': self._cmd_quick,
                'scan': self._cmd_scan,
                'monitor': self._cmd_monitor,
                'temperature': self._cmd_temperature,
                'cpu': self._cmd_cpu,
                'memory': self._cmd_memory,
                'disk': self._cmd_disk,
                'security': self._cmd_security,
                'services': self._cmd_services,
                'startup': self._cmd_startup,
                'screenshot': self._cmd_screenshot,
                'export': self._cmd_export,
                'status': self._cmd_status,
                'interactive': self._cmd_interactive,
                'config': self._cmd_config
            }
            
            if args.command in command_map:
                return command_map[args.command](args)
            else:
                self.display.print_error(f"Comando desconocido: {args.command}")
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error ejecutando comando: {str(e)}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return 1
    
    def _initialize_monitor(self) -> bool:
        """Inicializa el sistema de monitoreo"""
        if self.monitor_system:
            return True
        
        if not self.quiet:
            self.display.print_info("Inicializando sistema de monitoreo...")
        
        try:
            self.monitor_system = create_system_monitor()
            if self.monitor_system:
                if not self.quiet:
                    self.display.print_success("Sistema inicializado correctamente")
                return True
            else:
                self.display.print_error("Error inicializando sistema de monitoreo")
                return False
                
        except Exception as e:
            self.display.print_error(f"Error crítico inicializando sistema: {str(e)}")
            return False
    
    def _cmd_quick(self, args) -> int:
        """Comando de verificación rápida"""
        try:
            self.display.print_header("Verificación Rápida del Sistema")
            
            if not self.quiet:
                progress = ProgressBar(100, prefix="Verificando")
                progress.update(0, "Iniciando...")
            
            # Ejecutar verificación rápida
            result = run_quick_system_scan()
            
            if not self.quiet:
                progress.update(100, "Completado")
            
            if 'error' in result:
                self.display.print_error(f"Error en verificación: {result['error']}")
                return 1
            
            # Mostrar resultados
            self._display_quick_results(result)
            
            # Exportar si se solicita
            if args.export:
                self._export_result(result, args.export)
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en verificación rápida: {str(e)}")
            return 1
    
    def _cmd_scan(self, args) -> int:
        """Comando de escaneo del sistema"""
        try:
            scan_type = "detallado" if args.detailed else "básico"
            self.display.print_header(f"Escaneo {scan_type.title()} del Sistema")
            
            if not self._initialize_monitor():
                return 1
            
            # Configurar opciones de escaneo
            task_config = {}
            if args.hardware:
                task_config['include_hardware_summary'] = True
            if args.network:
                task_config['include_network'] = True
            
            # Ejecutar escaneo
            if args.detailed:
                task_name = 'DetailedSystemInfoTask'
            else:
                task_name = 'SystemInfoTask'
            
            result = self._execute_task_with_progress(task_name, task_config)
            
            if result:
                self._display_scan_results(result, args.detailed)
                
                # Exportar si se solicita
                if args.export:
                    self._export_result(result, args.export)
                
                return 0
            else:
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en escaneo: {str(e)}")
            return 1
    
    def _cmd_monitor(self, args) -> int:
        """Comando de monitoreo del sistema"""
        try:
            mode_map = {
                'basic': MonitoringMode.BASIC,
                'detailed': MonitoringMode.DETAILED,
                'continuous': MonitoringMode.CONTINUOUS,
                'security': MonitoringMode.SECURITY_FOCUSED,
                'performance': MonitoringMode.PERFORMANCE_FOCUSED,
                'maintenance': MonitoringMode.MAINTENANCE
            }
            
            mode = mode_map[args.mode]
            self.display.print_header(f"Monitoreo del Sistema - Modo {args.mode.title()}")
            
            if not self._initialize_monitor():
                return 1
            
            # Configurar monitoreo
            custom_config = {
                'duration': args.duration,
                'interval': args.interval
            }
            
            # Iniciar sesión de monitoreo
            session_id = self.monitor_system.start_monitoring_session(mode, custom_config)
            self.current_session_id = session_id
            
            self.display.print_info(f"Sesión iniciada: {session_id}")
            
            # Monitorear progreso
            self._monitor_session_progress(args.duration if args.mode == 'continuous' else 120)
            
            # Exportar si se solicita
            if args.export:
                report_path = self.monitor_system.export_session_report(session_id, 'json')
                if report_path:
                    self.display.print_success(f"Reporte exportado: {report_path}")
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en monitoreo: {str(e)}")
            return 1
    
    def _cmd_temperature(self, args) -> int:
        """Comando de monitoreo de temperatura"""
        try:
            self.display.print_header("Monitoreo de Temperatura")
            
            if not self._initialize_monitor():
                return 1
            
            # Configurar tarea de temperatura
            task_config = {
                'monitoring_duration': args.duration,
                'warning_temp_threshold': 70,
                'critical_temp_threshold': args.threshold
            }
            
            if args.continuous:
                # Monitoreo continuo
                self._continuous_temperature_monitor(task_config)
            else:
                # Monitoreo por tiempo limitado
                result = self._execute_task_with_progress('TemperatureMonitoringTask', task_config)
                if result:
                    self._display_temperature_results(result)
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en monitoreo de temperatura: {str(e)}")
            return 1
    
    def _cmd_cpu(self, args) -> int:
        """Comando de monitoreo de CPU"""
        try:
            self.display.print_header("Monitoreo de CPU")
            
            if not self._initialize_monitor():
                return 1
            
            task_config = {
                'monitoring_duration': args.duration
            }
            
            result = self._execute_task_with_progress('CPUMonitoringTask', task_config)
            
            if result:
                self._display_cpu_results(result, args.show_cores)
                return 0
            else:
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en monitoreo de CPU: {str(e)}")
            return 1
    
    def _cmd_memory(self, args) -> int:
        """Comando de monitoreo de memoria"""
        try:
            self.display.print_header("Monitoreo de Memoria")
            
            if not self._initialize_monitor():
                return 1
            
            task_config = {
                'monitoring_duration': args.duration
            }
            
            result = self._execute_task_with_progress('MemoryMonitoringTask', task_config)
            
            if result:
                self._display_memory_results(result, args.show_processes)
                return 0
            else:
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en monitoreo de memoria: {str(e)}")
            return 1
    
    def _cmd_disk(self, args) -> int:
        """Comando de análisis de discos"""
        try:
            self.display.print_header("Análisis de Discos")
            
            if not self._initialize_monitor():
                return 1
            
            if args.cleanup:
                # Análisis de limpieza
                result = self._execute_task_with_progress('TempFileCleanupTask', {})
                if result:
                    self._display_cleanup_results(result)
            else:
                # Análisis de discos
                task_config = {
                    'include_health': args.health,
                    'include_performance': args.performance
                }
                
                result = self._execute_task_with_progress('DiskAnalysisTask', task_config)
                if result:
                    self._display_disk_results(result)
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en análisis de discos: {str(e)}")
            return 1
    
    def _cmd_security(self, args) -> int:
        """Comando de análisis de seguridad"""
        try:
            self.display.print_header("Análisis de Seguridad")
            
            if not self._initialize_monitor():
                return 1
            
            results = []
            
            if args.antivirus or not any([args.antivirus, args.updates, args.firewall]):
                self.display.print_section("Verificando Antivirus")
                result = self._execute_task_with_progress('AntivirusStatusTask', {})
                if result:
                    results.append(('antivirus', result))
            
            if args.updates or not any([args.antivirus, args.updates, args.firewall]):
                self.display.print_section("Verificando Windows Update")
                result = self._execute_task_with_progress('WindowsUpdateTask', {})
                if result:
                    results.append(('updates', result))
            
            # Mostrar resultados
            for result_type, result_data in results:
                self._display_security_results(result_type, result_data)
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en análisis de seguridad: {str(e)}")
            return 1
    
    def _cmd_services(self, args) -> int:
        """Comando de análisis de servicios"""
        try:
            self.display.print_header("Análisis de Servicios")
            
            if not self._initialize_monitor():
                return 1
            
            task_config = {
                'analyze_dependencies': True,
                'check_security_services': True,
                'check_performance_impact': True
            }
            
            result = self._execute_task_with_progress('SystemServicesTask', task_config)
            
            if result:
                self._display_services_results(result, args.running_only, args.critical_only)
                return 0
            else:
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en análisis de servicios: {str(e)}")
            return 1
    
    def _cmd_startup(self, args) -> int:
        """Comando de análisis de programas de inicio"""
        try:
            self.display.print_header("Análisis de Programas de Inicio")
            
            if not self._initialize_monitor():
                return 1
            
            task_config = {
                'check_registry_startup': args.registry if args.registry else True,
                'check_startup_folders': args.folders if args.folders else True,
                'check_scheduled_tasks': args.tasks if args.tasks else True
            }
            
            result = self._execute_task_with_progress('StartupProgramsTask', task_config)
            
            if result:
                self._display_startup_results(result)
                return 0
            else:
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en análisis de inicio: {str(e)}")
            return 1
    
    def _cmd_screenshot(self, args) -> int:
        """Comando de captura de pantalla"""
        try:
            self.display.print_header("Captura de Pantalla")
            
            if not self._initialize_monitor():
                return 1
            
            result = self.monitor_system.take_screenshot(args.all_monitors)
            
            if result:
                self.display.print_success("Captura realizada exitosamente")
                self.display.print_info(f"Monitores capturados: {result.get('monitors_captured', 0)}")
                
                if 'file_paths' in result:
                    for file_path in result['file_paths']:
                        self.display.print_info(f"Archivo: {file_path}")
                
                return 0
            else:
                self.display.print_error("Error realizando captura")
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error en captura: {str(e)}")
            return 1
    
    def _cmd_export(self, args) -> int:
        """Comando de exportación de reportes"""
        try:
            self.display.print_header("Exportación de Reportes")
            
            if not self._initialize_monitor():
                return 1
            
            file_path = self.monitor_system.export_session_report(
                args.session_id, args.format
            )
            
            if file_path:
                self.display.print_success(f"Reporte exportado: {file_path}")
                return 0
            else:
                self.display.print_error("Error exportando reporte")
                return 1
                
        except Exception as e:
            self.display.print_error(f"Error exportando: {str(e)}")
            return 1
    
    def _cmd_status(self, args) -> int:
        """Comando de estado del sistema"""
        try:
            self.display.print_header("Estado del Sistema de Monitoreo")
            
            if not self._initialize_monitor():
                return 1
            
            status = self.monitor_system.get_system_status()
            
            self._display_system_status(status, args.detailed)
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error obteniendo estado: {str(e)}")
            return 1
    
    def _cmd_interactive(self, args) -> int:
        """Comando de modo interactivo"""
        try:
            self.interactive_mode = True
            self.display.print_header("Modo Interactivo")
            
            if not self._initialize_monitor():
                return 1
            
            self.display.print_info("Escriba 'help' para ver comandos disponibles o 'exit' para salir")
            
            while self.running and self.interactive_mode:
                try:
                    user_input = input(f"\n{Colors.colored('sysmonitor>', Colors.CYAN) if self.use_colors else 'sysmonitor>'} ").strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() in ['exit', 'quit', 'q']:
                        break
                    
                    self._process_interactive_command(user_input)
                    
                except KeyboardInterrupt:
                    self.display.print_warning("\nUse 'exit' para salir del modo interactivo")
                except EOFError:
                    break
            
            self.interactive_mode = False
            self.display.print_info("Saliendo del modo interactivo")
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en modo interactivo: {str(e)}")
            return 1
    
    def _cmd_config(self, args) -> int:
        """Comando de configuración"""
        try:
            self.display.print_header("Configuración del Sistema")
            
            if args.show:
                self._show_configuration()
            elif args.reset:
                self._reset_configuration()
            else:
                self.display.print_info("Use --show para ver configuración o --reset para restaurar")
            
            return 0
            
        except Exception as e:
            self.display.print_error(f"Error en configuración: {str(e)}")
            return 1
    
    def _execute_task_with_progress(self, task_name: str, task_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ejecuta una tarea mostrando progreso"""
        try:
            if not self.quiet:
                progress = ProgressBar(100, prefix=f"Ejecutando {task_name}")
                progress.update(0, "Iniciando...")
            
            task_id = self.monitor_system.execute_custom_task(task_name, task_config)
            
            # Esperar resultado con updates de progreso
            start_time = time.time()
            last_progress = 0
            
            while True:
                result = self.monitor_system.get_task_result(task_id)
                
                if result:
                    if not self.quiet:
                        progress.finish("Completado")
                    
                    if result.get('status') == 'completed':
                        return result.get('data')
                    else:
                        self.display.print_error(f"Tarea falló: {result.get('error', 'Error desconocido')}")
                        return None
                
                # Actualizar progreso estimado
                elapsed = time.time() - start_time
                estimated_progress = min(90, (elapsed / 30) * 100)  # Estimar 30s máximo
                
                if not self.quiet and estimated_progress > last_progress + 5:
                    progress.update(int(estimated_progress), "En progreso...")
                    last_progress = estimated_progress
                
                time.sleep(1)
                
                # Timeout después de 5 minutos
                if elapsed > 300:
                    if not self.quiet:
                        progress.finish("Timeout")
                    self.display.print_error("Timeout esperando resultado de tarea")
                    return None
                    
        except Exception as e:
            self.display.print_error(f"Error ejecutando tarea: {str(e)}")
            return None
    
    def _monitor_session_progress(self, max_duration: int):
        """Monitorea el progreso de una sesión"""
        try:
            if not self.quiet:
                progress = ProgressBar(max_duration, prefix="Monitoreando")
            
            start_time = time.time()
            
            while True:
                elapsed = time.time() - start_time
                
                if elapsed >= max_duration:
                    break
                
                status = self.monitor_system.get_system_status()
                
                if not status.get('active_monitoring', False):
                    break
                
                if not self.quiet:
                    session_info = status.get('current_session', {})
                    message = f"Tareas: {session_info.get('tasks_completed', 0)} completadas"
                    progress.update(int(elapsed), message)
                
                time.sleep(2)
            
            if not self.quiet:
                progress.finish("Monitoreo completado")
                
        except Exception as e:
            self.display.print_error(f"Error monitoreando sesión: {str(e)}")
    
    def _continuous_temperature_monitor(self, task_config: Dict[str, Any]):
        """Monitoreo continuo de temperatura"""
        try:
            self.display.print_info("Iniciando monitoreo continuo de temperatura (Ctrl+C para detener)")
            
            while self.running:
                # Ejecutar monitoreo corto
                task_config['monitoring_duration'] = 10
                result = self._execute_task_with_progress('TemperatureMonitoringTask', task_config)
                
                if result and 'samples' in result:
                    # Mostrar última muestra
                    samples = result['samples']
                    if samples:
                        last_sample = samples[-1]
                        timestamp = last_sample.get('timestamp', 'Unknown')
                        
                        print(f"\r{timestamp} | ", end="")
                        
                        temps = last_sample.get('temperatures', {})
                        for source, temp_data in temps.items():
                            temp = temp_data.get('current', 0)
                            color = Colors.SUCCESS
                            if temp > task_config['critical_temp_threshold']:
                                color = Colors.ERROR
                            elif temp > 70:
                                color = Colors.WARNING
                            
                            temp_str = f"{source}: {temp:.1f}°C"
                            if self.use_colors:
                                temp_str = Colors.colored(temp_str, color)
                            
                            print(f"{temp_str} | ", end="")
                        
                        sys.stdout.flush()
                
                time.sleep(5)
                
        except KeyboardInterrupt:
            print("\nMonitoreo de temperatura detenido")
    
    def _process_interactive_command(self, command: str):
        """Procesa un comando en modo interactivo"""
        try:
            # Parsear comando
            args = shlex.split(command)
            
            if not args:
                return
            
            cmd = args[0].lower()
            
            if cmd == 'help':
                self._show_interactive_help()
            elif cmd == 'status':
                status = self.monitor_system.get_system_status()
                self._display_system_status(status, False)
            elif cmd == 'quick':
                result = run_quick_system_scan()
                self._display_quick_results(result)
            elif cmd == 'screenshot':
                result = self.monitor_system.take_screenshot(True)
                if result:
                    self.display.print_success("Captura realizada")
            elif cmd == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
            elif cmd.startswith('export'):
                if len(args) > 1:
                    format_type = args[1] if args[1] in ['json', 'html', 'text'] else 'json'
                    file_path = self.monitor_system.export_session_report(None, format_type)
                    if file_path:
                        self.display.print_success(f"Reporte exportado: {file_path}")
            else:
                # Intentar ejecutar como comando completo
                try:
                    exit_code = self.run(args)
                    if exit_code != 0:
                        self.display.print_error(f"Comando falló con código {exit_code}")
                except Exception as e:
                    self.display.print_error(f"Error ejecutando comando: {str(e)}")
                    
        except Exception as e:
            self.display.print_error(f"Error procesando comando: {str(e)}")
    
    def _show_interactive_help(self):
        """Muestra ayuda del modo interactivo"""
        help_text = """
Comandos disponibles en modo interactivo:

  help              - Mostrar esta ayuda
  status            - Estado del sistema
  quick             - Verificación rápida
  screenshot        - Captura de pantalla
  export [formato]  - Exportar reporte (json/html/text)
  clear             - Limpiar pantalla
  exit, quit, q     - Salir del modo interactivo

También puede usar cualquier comando normal:
  scan --detailed
  monitor --mode continuous
  temperature --duration 30
  etc.
        """
        print(help_text)
    
    # Métodos de visualización de resultados
    
    def _display_quick_results(self, result: Dict[str, Any]):
        """Muestra resultados de verificación rápida"""
        try:
            self.display.print_section("Resultados de Verificación Rápida")
            
            status = result.get('status', 'Unknown')
            
            if status == 'GOOD':
                self.display.print_success("Sistema funcionando correctamente")
            elif status == 'WARNING':
                self.display.print_warning("Se detectaron advertencias")
            elif status == 'CRITICAL':
                self.display.print_error("Se detectaron problemas críticos")
            else:
                self.display.print_info(f"Estado: {status}")
            
            # Métricas
            metrics = result.get('metrics', {})
            if metrics:
                print("\nMétricas del sistema:")
                for key, value in metrics.items():
                    self.display.print_metric(key.replace('_', ' ').title(), str(value))
            
            # Alertas
            alerts = result.get('alerts', [])
            if alerts:
                print(f"\nAlertas encontradas ({len(alerts)}):")
                for alert in alerts:
                    level = alert.get('level', 'INFO')
                    message = alert.get('message', 'Sin mensaje')
                    
                    if level == 'CRITICAL':
                        self.display.print_error(f"  {message}")
                    elif level == 'WARNING':
                        self.display.print_warning(f"  {message}")
                    else:
                        self.display.print_info(f"  {message}")
            
            # Recomendaciones
            recommendations = result.get('recommendations', [])
            if recommendations:
                print(f"\nRecomendaciones:")
                for rec in recommendations:
                    self.display.print_info(f"  • {rec}")
                    
        except Exception as e:
            self.display.print_error(f"Error mostrando resultados rápidos: {str(e)}")
    
    def _display_scan_results(self, result: Dict[str, Any], detailed: bool):
        """Muestra resultados de escaneo"""
        try:
            self.display.print_section("Resultados del Escaneo")
            
            # Información básica del sistema
            basic_info = result.get('basic_system', {})
            if basic_info:
                print("Información del Sistema:")
                self.display.print_metric("Nombre del equipo", basic_info.get('hostname', 'Unknown'))
                self.display.print_metric("Sistema operativo", basic_info.get('platform', 'Unknown'))
                self.display.print_metric("Arquitectura", str(basic_info.get('architecture', 'Unknown')))
                self.display.print_metric("Usuario actual", basic_info.get('current_user', 'Unknown'))
                self.display.print_metric("Tiempo activo", basic_info.get('uptime_formatted', 'Unknown'))
            
            # CPU
            cpu_info = result.get('cpu_info', {})
            if cpu_info:
                print(f"\nInformación de CPU:")
                self.display.print_metric("Núcleos físicos", str(cpu_info.get('physical_cores', 0)))
                self.display.print_metric("Núcleos lógicos", str(cpu_info.get('logical_cores', 0)))
                self.display.print_metric("Uso actual", f"{cpu_info.get('current_usage', 0):.1f}%")
                
                if 'current_frequency_formatted' in cpu_info:
                    self.display.print_metric("Frecuencia actual", cpu_info['current_frequency_formatted'])
            
            # Memoria
            memory_info = result.get('memory_info', {})
            if memory_info:
                vm = memory_info.get('virtual_memory', {})
                if vm:
                    print(f"\nInformación de Memoria:")
                    self.display.print_metric("Total", vm.get('total_formatted', 'Unknown'))
                    self.display.print_metric("Disponible", vm.get('available_formatted', 'Unknown'))
                    self.display.print_metric("Uso", f"{vm.get('percent', 0):.1f}%")
            
            # Discos
            disk_info = result.get('disk_info', {})
            if disk_info:
                print(f"\nInformación de Discos:")
                self.display.print_metric("Espacio total", disk_info.get('total_disk_space_formatted', 'Unknown'))
                self.display.print_metric("Espacio usado", disk_info.get('total_used_space_formatted', 'Unknown'))
                self.display.print_metric("Espacio libre", disk_info.get('total_free_space_formatted', 'Unknown'))
                self.display.print_metric("Uso promedio", f"{disk_info.get('overall_usage_percent', 0):.1f}%")
            
            # Hardware (solo en detallado)
            if detailed:
                hardware_info = result.get('hardware_summary', {})
                if hardware_info:
                    print(f"\nResumen de Hardware:")
                    self.display.print_metric("Procesador", hardware_info.get('processor_name', 'Unknown'))
                    self.display.print_metric("Placa madre", 
                                            f"{hardware_info.get('motherboard', {}).get('manufacturer', 'Unknown')} "
                                            f"{hardware_info.get('motherboard', {}).get('product', '')}")
                    self.display.print_metric("RAM total", hardware_info.get('total_ram_formatted', 'Unknown'))
                    
                    # Tarjetas gráficas
                    graphics = hardware_info.get('graphics_cards', [])
                    if graphics:
                        print(f"\n  Tarjetas Gráficas:")
                        for i, gpu in enumerate(graphics[:3]):  # Máximo 3
                            self.display.print_metric(f"    GPU {i+1}", gpu.get('name', 'Unknown'))
            
            # Estado de salud del sistema
            health = result.get('system_health', {})
            if health:
                print(f"\nEstado de Salud del Sistema:")
                score = health.get('overall_score', 0)
                status = health.get('overall_status', 'Unknown')
                
                color = "good" if score >= 80 else "warning" if score >= 60 else "critical"
                self.display.print_metric("Puntuación", f"{score}/100", color)
                self.display.print_metric("Estado", status, color)
                
                # Issues críticos
                critical_issues = health.get('critical_issues', [])
                if critical_issues:
                    print(f"\n  Problemas Críticos:")
                    for issue in critical_issues:
                        self.display.print_error(f"    • {issue}")
                
                # Advertencias
                warnings = health.get('warnings', [])
                if warnings:
                    print(f"\n  Advertencias:")
                    for warning in warnings:
                        self.display.print_warning(f"    • {warning}")
                        
        except Exception as e:
            self.display.print_error(f"Error mostrando resultados de escaneo: {str(e)}")
    
    def _display_temperature_results(self, result: Dict[str, Any]):
        """Muestra resultados de monitoreo de temperatura"""
        try:
            self.display.print_section("Resultados de Monitoreo de Temperatura")
            
            # Información del monitoreo
            monitoring_info = result.get('monitoring_info', {})
            if monitoring_info:
                duration = monitoring_info.get('actual_duration', 0)
                samples = monitoring_info.get('samples_collected', 0)
                alerts = monitoring_info.get('alerts_generated', 0)
                
                self.display.print_metric("Duración", f"{duration:.1f} segundos")
                self.display.print_metric("Muestras recopiladas", str(samples))
                self.display.print_metric("Alertas generadas", str(alerts))
            
            # Fuentes de temperatura detectadas
            sources = result.get('temperature_sources', [])
            if sources:
                print(f"\nFuentes de Temperatura Detectadas ({len(sources)}):")
                for source in sources:
                    name = source.get('sensor_name', 'Unknown')
                    count = source.get('sensor_count', 0)
                    self.display.print_info(f"  • {name}: {count} sensores")
            
            # Estadísticas de temperatura
            stats = result.get('statistics', {})
            if stats:
                temp_sources = stats.get('temperature_sources', {})
                if temp_sources:
                    print(f"\nEstadísticas por Fuente:")
                    for source, source_stats in temp_sources.items():
                        avg_temp = source_stats.get('average', 0)
                        max_temp = source_stats.get('max', 0)
                        min_temp = source_stats.get('min', 0)
                        
                        print(f"\n  {source}:")
                        self.display.print_metric("    Promedio", f"{avg_temp:.1f}°C")
                        self.display.print_metric("    Máxima", f"{max_temp:.1f}°C")
                        self.display.print_metric("    Mínima", f"{min_temp:.1f}°C")
            
            # Alertas de temperatura
            alerts = result.get('alerts', [])
            if alerts:
                print(f"\nAlertas de Temperatura ({len(alerts)}):")
                for alert in alerts:
                    level = alert.get('level', 'INFO')
                    message = alert.get('message', 'Sin mensaje')
                    
                    if level == 'CRITICAL':
                        self.display.print_error(f"  {message}")
                    elif level == 'WARNING':
                        self.display.print_warning(f"  {message}")
                    else:
                        self.display.print_info(f"  {message}")
                        
        except Exception as e:
            self.display.print_error(f"Error mostrando resultados de temperatura: {str(e)}")
    
    def _display_cpu_results(self, result: Dict[str, Any], show_cores: bool):
        """Muestra resultados de monitoreo de CPU"""
        try:
            self.display.print_section("Resultados de Monitoreo de CPU")
            
            # Información del CPU
            cpu_info = result.get('cpu_info', {})
            if cpu_info:
                print("Información del CPU:")
                self.display.print_metric("Núcleos físicos", str(cpu_info.get('physical_cores', 0)))
                self.display.print_metric("Núcleos lógicos", str(cpu_info.get('logical_cores', 0)))
                
                if 'max_clock_speed' in cpu_info:
                    self.display.print_metric("Velocidad máxima", f"{cpu_info['max_clock_speed']} MHz")
            
            # Estadísticas del monitoreo
            stats = result.get('statistics', {})
            if stats:
                cpu_usage = stats.get('cpu_usage', {})
                if cpu_usage:
                    print(f"\nEstadísticas de Uso:")
                    avg_usage = cpu_usage.get('average', 0)
                    max_usage = cpu_usage.get('max', 0)
                    min_usage = cpu_usage.get('min', 0)
                    
                    color = "good" if avg_usage < 70 else "warning" if avg_usage < 90 else "critical"
                    
                    self.display.print_metric("Uso promedio", f"{avg_usage:.1f}%", color)
                    self.display.print_metric("Uso máximo", f"{max_usage:.1f}%")
                    self.display.print_metric("Uso mínimo", f"{min_usage:.1f}%")
                
                # Estadísticas por núcleo
                if show_cores:
                    core_stats = stats.get('core_statistics', {})
                    if core_stats:
                        print(f"\nUso por Núcleo:")
                        for core, core_data in core_stats.items():
                            avg = core_data.get('average', 0)
                            color = "good" if avg < 70 else "warning" if avg < 90 else "critical"
                            self.display.print_metric(f"  {core}", f"{avg:.1f}%", color)
            
            # Top procesos por CPU
            top_processes = result.get('top_processes', [])
            if top_processes:
                print(f"\nTop Procesos por CPU:")
                headers = ['Proceso', 'PID', 'CPU %', 'Usuario']
                table_data = []
                
                for proc in top_processes[:10]:
                    table_data.append({
                        'Proceso': proc.get('name', 'Unknown'),
                        'PID': str(proc.get('pid', 0)),
                        'CPU %': f"{proc.get('cpu_percent', 0):.1f}",
                        'Usuario': proc.get('username', 'Unknown')
                    })
                
                print(TableFormatter.format_table(table_data, headers))
                
        except Exception as e:
            self.display.print_error(f"Error mostrando resultados de CPU: {str(e)}")
    
    def _display_memory_results(self, result: Dict[str, Any], show_processes: bool):
        """Muestra resultados de monitoreo de memoria"""
        try:
            self.display.print_section("Resultados de Monitoreo de Memoria")
            
            # Información de memoria
            memory_info = result.get('memory_info', {})
            if memory_info:
                total_ram = memory_info.get('total_physical', 0)
                if total_ram:
                    self.display.print_metric("RAM Total", 
                                            memory_info.get('total_physical_formatted', 'Unknown'))
                    
                    modules = memory_info.get('physical_modules', [])
                    if modules:
                        self.display.print_metric("Módulos de memoria", str(len(modules)))
            
            # Estadísticas del monitoreo
            stats = result.get('statistics', {})
            if stats:
                vm_stats = stats.get('virtual_memory', {})
                if vm_stats:
                    usage_stats = vm_stats.get('usage_percent', {})
                    if usage_stats:
                        print(f"\nEstadísticas de Uso de Memoria:")
                        avg_usage = usage_stats.get('average', 0)
                        max_usage = usage_stats.get('max', 0)
                        min_usage = usage_stats.get('min', 0)
                        
                        color = "good" if avg_usage < 80 else "warning" if avg_usage < 95 else "critical"
                        
                        self.display.print_metric("Uso promedio", f"{avg_usage:.1f}%", color)
                        self.display.print_metric("Uso máximo", f"{max_usage:.1f}%")
                        self.display.print_