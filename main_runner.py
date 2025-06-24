"""
Sistema de Monitoreo de PC - Módulo 14: Ejecutor Principal y Punto de Entrada
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Punto de entrada principal del sistema con manejo de configuración y logs
"""

import sys
import os
import logging
import argparse
import traceback
import signal
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import multiprocessing

# Agregar el directorio raíz al path para importaciones
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Importar módulos del sistema
# Se priorizan los imports absolutos asumiendo que el script se ejecuta desde el directorio raíz
# o que el directorio raíz está en PYTHONPATH.
from config_and_imports import SystemConfig, SystemConstants
from utilities import SystemUtilities, FileUtilities, SecurityUtilities
from main_interface import SystemMonitorInterface, create_system_monitor
from gui_interface import SystemMonitorGUI
from cli_interface import SystemMonitorCLI, Colors
# Nota: El bloque try-except ImportError anidado se eliminó para simplificar,
# ya que la causa más probable del error "attempted relative import with no known parent package"
# es que Python no considera el directorio actual como un paquete al ejecutar un script directamente,
# y los imports relativos explícitos (from .module) fallarían en ese caso.
# Si se ejecuta como paquete (python -m package_name.main_runner), los imports
# relativos explícitos funcionarían, pero los imports absolutos directos (como están ahora)
# también deberían funcionar si el paquete está correctamente instalado o PYTHONPATH está configurado.

class SystemMonitorRunner:
    """Ejecutor principal del sistema de monitoreo"""
    
    def __init__(self):
        """Inicializa el ejecutor principal"""
        self.version = SystemConfig.APP_VERSION
        self.author = "SERGIORAMGO"
        self.build_date = "2025-06-22"
        self.current_user = "SERGIORAMGO"
        
        # Configuración de logging
        self.log_level = logging.INFO
        self.log_file = None
        self.console_output = True
        
        # Estado del sistema
        self.system_initialized = False
        self.running = False
        self.interface_mode = None
        
        # Interfaces disponibles
        self.cli_interface = None
        self.gui_interface = None
        self.monitor_system = None
        
        # Control de procesos
        self.main_process = None
        self.worker_processes = []
        
        # Configuración de señales
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Variables de entorno
        self.setup_environment()
    
    def setup_environment(self):
        """Configura el entorno del sistema"""
        try:
            # Configurar variables de entorno
            os.environ['SYSMONITOR_VERSION'] = self.version
            os.environ['SYSMONITOR_USER'] = self.current_user
            os.environ['SYSMONITOR_DATE'] = self.build_date
            
            # Crear directorios necesarios
            directories = [
                SystemConfig.BASE_DIR,
                SystemConfig.LOGS_DIR,
                SystemConfig.REPORTS_DIR,
                SystemConfig.TEMP_DIR,
                SystemConfig.CONFIG_DIR,
                SystemConfig.SCREENSHOTS_DIR
            ]
            
            for directory in directories:
                FileUtilities.ensure_directory(directory)
                
            # Verificar permisos
            for directory in directories:
                if not os.access(directory, os.W_OK):
                    print(f"Advertencia: Sin permisos de escritura en {directory}")
            
            print(f"Entorno configurado correctamente")
            
        except Exception as e:
            print(f"Error configurando entorno: {e}")
            raise
    
    def setup_logging(self, log_level: str = "INFO", log_file: str = None, 
                     console_output: bool = True):
        """Configura el sistema de logging"""
        try:
            # Convertir nivel de string a constante
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            
            self.log_level = level_map.get(log_level.upper(), logging.INFO)
            self.log_file = log_file
            self.console_output = console_output
            
            # Configurar logger root
            root_logger = logging.getLogger()
            root_logger.setLevel(self.log_level)
            
            # Limpiar handlers existentes
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Formato de log
            log_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # Handler para consola
            if console_output:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(self.log_level)
                console_handler.setFormatter(log_format)
                root_logger.addHandler(console_handler)
            
            # Handler para archivo
            if log_file:
                log_path = Path(log_file)
                if not log_path.is_absolute():
                    log_path = SystemConfig.LOGS_DIR / log_file
                
                file_handler = logging.FileHandler(log_path, encoding='utf-8')
                file_handler.setLevel(self.log_level)
                file_handler.setFormatter(log_format)
                root_logger.addHandler(file_handler)
            else:
                # Log file por defecto
                default_log = SystemConfig.LOGS_DIR / f"sysmonitor_{datetime.now().strftime('%Y%m%d')}.log"
                file_handler = logging.FileHandler(default_log, encoding='utf-8')
                file_handler.setLevel(self.log_level)
                file_handler.setFormatter(log_format)
                root_logger.addHandler(file_handler)
            
            # Logger específico para el runner
            self.logger = logging.getLogger(__name__) # Usar __name__
            self.logger.info(f"Sistema de logging configurado - Nivel: {log_level}")
            self.logger.info(f"Usuario: {self.current_user} | Versión: {self.version} | Fecha: {self.build_date}")
            
        except Exception as e:
            print(f"Error configurando logging: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """Maneja señales del sistema operativo"""
        try:
            signal_names = {
                signal.SIGINT: "SIGINT (Ctrl+C)",
                signal.SIGTERM: "SIGTERM"
            }
            
            signal_name = signal_names.get(signum, f"Señal {signum}")
            
            if hasattr(self, 'logger'):
                self.logger.warning(f"Señal recibida: {signal_name}")
            else:
                print(f"Señal recibida: {signal_name}")
            
            self.shutdown_system()
            
        except Exception as e:
            print(f"Error manejando señal: {e}")
            sys.exit(1)
    
    def initialize_system(self) -> bool:
        """Inicializa todos los componentes del sistema"""
        try:
            self.logger.info("Iniciando inicialización del sistema...")
            
            # Verificar dependencias críticas
            if not self._check_dependencies():
                self.logger.error("Verificación de dependencias falló")
                return False
            
            # Verificar recursos del sistema
            if not self._check_system_resources():
                self.logger.warning("Recursos del sistema limitados, continuando...")
            
            # Inicializar configuración
            if not self._initialize_configuration():
                self.logger.error("Error inicializando configuración")
                return False
            
            # Verificar permisos de seguridad
            if not SecurityUtilities.check_admin_privileges():
                self.logger.warning("Ejecutándose sin privilegios de administrador - funcionalidad limitada")
            
            # Crear sistema de monitoreo base
            self.monitor_system = create_system_monitor()
            if not self.monitor_system:
                self.logger.error("Error creando sistema de monitoreo")
                return False
            
            self.system_initialized = True
            self.logger.info("Sistema inicializado exitosamente")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error crítico inicializando sistema: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    def _check_dependencies(self) -> bool:
        """Verifica las dependencias críticas del sistema"""
        try:
            self.logger.info("Verificando dependencias del sistema...")
            
            # Dependencias de Python
            required_modules = [
                'psutil', 'wmi', 'tkinter', 'threading', 'json',
                'pathlib', 'datetime', 'logging', 'subprocess'
            ]
            
            missing_modules = []
            for module in required_modules:
                try:
                    __import__(module)
                except ImportError:
                    missing_modules.append(module)
            
            if missing_modules:
                self.logger.error(f"Módulos faltantes: {', '.join(missing_modules)}")
                return False
            
            # Verificar versión de Python
            if sys.version_info < (3, 7):
                self.logger.error(f"Python 3.7+ requerido, versión actual: {sys.version}")
                return False
            
            # Verificar sistema operativo
            if not sys.platform.startswith('win'):
                self.logger.warning("Sistema optimizado para Windows, funcionalidad puede ser limitada")
            
            # Verificar espacio en disco
            try:
                import shutil
                total, used, free = shutil.disk_usage(SystemConfig.BASE_DIR)
                free_gb = free / (1024**3)
                
                if free_gb < 1:  # Menos de 1GB libre
                    self.logger.error(f"Espacio en disco insuficiente: {free_gb:.2f}GB libres")
                    return False
                elif free_gb < 5:  # Menos de 5GB libre
                    self.logger.warning(f"Espacio en disco limitado: {free_gb:.2f}GB libres")
                    
            except Exception as e:
                self.logger.warning(f"No se pudo verificar espacio en disco: {e}")
            
            self.logger.info("Verificación de dependencias completada")
            return True
            
        except Exception as e:
            self.logger.error(f"Error verificando dependencias: {e}")
            return False
    
    def _check_system_resources(self) -> bool:
        """Verifica los recursos disponibles del sistema"""
        try:
            import psutil
            
            # Verificar memoria RAM
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            
            if available_gb < 0.5:  # Menos de 512MB
                self.logger.error(f"Memoria RAM insuficiente: {available_gb:.2f}GB disponibles")
                return False
            elif available_gb < 2:  # Menos de 2GB
                self.logger.warning(f"Memoria RAM limitada: {available_gb:.2f}GB disponibles")
            
            # Verificar CPU
            cpu_count = psutil.cpu_count()
            if cpu_count < 2:
                self.logger.warning(f"CPU con pocos núcleos: {cpu_count}")
            
            # Verificar carga del sistema
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                if cpu_percent > 90:
                    self.logger.warning(f"Sistema con alta carga de CPU: {cpu_percent:.1f}%")
            except Exception:
                pass
            
            self.logger.info(f"Recursos verificados - RAM: {available_gb:.2f}GB, CPU: {cpu_count} núcleos")
            return True
            
        except Exception as e:
            self.logger.warning(f"Error verificando recursos del sistema: {e}")
            return True  # No crítico
    
    def _initialize_configuration(self) -> bool:
        """Inicializa la configuración del sistema"""
        try:
            self.logger.info("Inicializando configuración del sistema...")
            
            # Archivo de configuración principal
            config_file = SystemConfig.CONFIG_DIR / "system_config.json"
            
            default_config = {
                "version": self.version,
                "user": self.current_user,
                "last_updated": datetime.now().isoformat(),
                "logging": {
                    "level": "INFO",
                    "console_output": True,
                    "file_output": True,
                    "max_log_size_mb": 10,
                    "max_log_files": 5
                },
                "monitoring": {
                    "default_interval": 60,
                    "max_concurrent_tasks": 4,
                    "auto_save_results": True,
                    "screenshot_on_errors": False
                },
                "interface": {
                    "default_mode": "auto",
                    "use_colors": True,
                    "auto_export_reports": True,
                    "export_format": "json"
                },
                "security": {
                    "require_admin": False,
                    "check_signatures": True,
                    "safe_mode": False
                },
                "paths": {
                    "reports_dir": str(SystemConfig.REPORTS_DIR),
                    "logs_dir": str(SystemConfig.LOGS_DIR),
                    "temp_dir": str(SystemConfig.TEMP_DIR),
                    "screenshots_dir": str(SystemConfig.SCREENSHOTS_DIR)
                }
            }
            
            # Crear configuración si no existe
            if not config_file.exists():
                FileUtilities.save_json(default_config, config_file)
                self.logger.info("Configuración por defecto creada")
            else:
                # Cargar configuración existente
                try:
                    existing_config = FileUtilities.load_json(config_file)
                    # Actualizar con nuevos valores por defecto si es necesario
                    updated_config = self._merge_configs(default_config, existing_config)
                    FileUtilities.save_json(updated_config, config_file)
                    self.logger.info("Configuración existente cargada y actualizada")
                except Exception as e:
                    self.logger.warning(f"Error cargando configuración, usando defaults: {e}")
                    FileUtilities.save_json(default_config, config_file)
            
            # Configurar límites del sistema
            SystemConfig.MAX_WORKERS = min(multiprocessing.cpu_count(), 8)
            
            self.logger.info("Configuración inicializada correctamente")
            return True
            
        except Exception as e:
            self.logger.error(f"Error inicializando configuración: {e}")
            return False
    
    def _merge_configs(self, default: Dict, existing: Dict) -> Dict:
        """Fusiona configuración por defecto con existente"""
        try:
            merged = default.copy()
            
            for key, value in existing.items():
                if key in merged:
                    if isinstance(value, dict) and isinstance(merged[key], dict):
                        merged[key] = self._merge_configs(merged[key], value)
                    else:
                        merged[key] = value
                else:
                    merged[key] = value
            
            # Actualizar timestamp
            merged["last_updated"] = datetime.now().isoformat()
            
            return merged
            
        except Exception as e:
            self.logger.warning(f"Error fusionando configuraciones: {e}")
            return default
    
    def run_cli_mode(self, args: List[str] = None) -> int:
        """Ejecuta la interfaz de línea de comandos"""
        try:
            self.logger.info("Iniciando modo CLI")
            self.interface_mode = "cli"
            
            if not self.system_initialized:
                if not self.initialize_system():
                    return 1
            
            # Crear interfaz CLI
            self.cli_interface = SystemMonitorCLI()
            
            # Ejecutar CLI
            exit_code = self.cli_interface.run(args)
            
            self.logger.info(f"Modo CLI finalizado con código: {exit_code}")
            return exit_code
            
        except Exception as e:
            self.logger.error(f"Error en modo CLI: {e}")
            self.logger.debug(traceback.format_exc())
            return 1
    
    def run_gui_mode(self) -> int:
        """Ejecuta la interfaz gráfica de usuario"""
        try:
            self.logger.info("Iniciando modo GUI")
            self.interface_mode = "gui"
            
            if not self.system_initialized:
                if not self.initialize_system():
                    return 1
            
            # Verificar disponibilidad de tkinter
            try:
                import tkinter
                tkinter.Tk().withdraw()  # Test rápido
            except Exception as e:
                self.logger.error(f"Tkinter no disponible: {e}")
                print("Error: Interfaz gráfica no disponible en este sistema")
                print("Use el modo CLI con: python -m sysmonitor --cli")
                return 1
            
            # Crear y ejecutar interfaz GUI
            self.gui_interface = SystemMonitorGUI()
            
            try:
                self.gui_interface.root.mainloop()
                self.logger.info("Interfaz GUI cerrada")
                return 0
                
            except KeyboardInterrupt:
                self.logger.info("GUI interrumpida por usuario")
                return 0
                
        except Exception as e:
            self.logger.error(f"Error en modo GUI: {e}")
            self.logger.debug(traceback.format_exc())
            return 1
    
    def run_service_mode(self) -> int:
        """Ejecuta como servicio en segundo plano"""
        try:
            self.logger.info("Iniciando modo servicio")
            self.interface_mode = "service"
            
            if not self.system_initialized:
                if not self.initialize_system():
                    return 1
            
            self.running = True
            
            # Loop principal del servicio
            while self.running:
                try:
                    # Ejecutar verificación periódica
                    self._service_health_check()
                    
                    # Esperar intervalo
                    time.sleep(300)  # 5 minutos
                    
                except KeyboardInterrupt:
                    self.logger.info("Servicio interrumpido por usuario")
                    break
                except Exception as e:
                    self.logger.error(f"Error en loop de servicio: {e}")
                    time.sleep(60)  # Esperar 1 minuto antes de reintentar
            
            self.logger.info("Modo servicio finalizado")
            return 0
            
        except Exception as e:
            self.logger.error(f"Error en modo servicio: {e}")
            return 1
    
    def _service_health_check(self):
        """Ejecuta verificación de salud en modo servicio"""
        try:
            if self.monitor_system:
                # Ejecutar verificación rápida
                result = self.monitor_system.execute_quick_check()
                
                # Log de resultados importantes
                if result:
                    status = result.get('status', 'Unknown')
                    self.logger.info(f"Verificación de salud: {status}")
                    
                    # Alertas críticas
                    alerts = result.get('alerts', [])
                    critical_alerts = [a for a in alerts if a.get('level') == 'CRITICAL']
                    
                    if critical_alerts:
                        for alert in critical_alerts:
                            self.logger.critical(f"Alerta crítica: {alert.get('message')}")
                
        except Exception as e:
            self.logger.error(f"Error en verificación de salud del servicio: {e}")
    
    def run_interactive_setup(self) -> int:
        """Ejecuta configuración interactiva inicial"""
        try:
            print(f"\n{'='*60}")
            print(f" Sistema de Monitoreo de PC v{self.version}")
            print(f" Configuración Inicial Interactiva")
            print(f" Autor: {self.author} | Fecha: {self.build_date}")
            print(f"{'='*60}\n")
            
            # Detectar modo preferido
            mode = self._detect_preferred_mode()
            print(f"Modo recomendado: {mode}")
            
            # Configurar logging
            log_level = input("\nNivel de logging (DEBUG/INFO/WARNING/ERROR) [INFO]: ").strip().upper()
            if not log_level:
                log_level = "INFO"
            
            # Configurar directorio de trabajo
            work_dir = input(f"\nDirectorio de trabajo [{SystemConfig.BASE_DIR}]: ").strip()
            if work_dir:
                SystemConfig.BASE_DIR = Path(work_dir)
                self.setup_environment()
            
            # Inicializar con configuración
            self.setup_logging(log_level, console_output=True)
            
            if not self.initialize_system():
                print("Error: No se pudo inicializar el sistema")
                return 1
            
            print("\n✓ Sistema configurado exitosamente")
            print(f"✓ Directorio de trabajo: {SystemConfig.BASE_DIR}")
            print(f"✓ Logs: {SystemConfig.LOGS_DIR}")
            print(f"✓ Reportes: {SystemConfig.REPORTS_DIR}")
            
            # Ejecutar verificación inicial
            print("\nEjecutando verificación inicial del sistema...")
            if self.monitor_system:
                result = self.monitor_system.execute_quick_check()
                if result:
                    status = result.get('status', 'Unknown')
                    print(f"Estado del sistema: {status}")
                    
                    alerts = result.get('alerts', [])
                    if alerts:
                        print(f"Alertas encontradas: {len(alerts)}")
                        for alert in alerts[:3]:  # Mostrar primeras 3
                            print(f"  - {alert.get('level')}: {alert.get('message')}")
            
            # Opciones de ejecución
            print(f"\nOpciones de ejecución:")
            print(f"  GUI:     python -m sysmonitor --gui")
            print(f"  CLI:     python -m sysmonitor --cli")
            print(f"  Servicio: python -m sysmonitor --service")
            
            return 0
            
        except KeyboardInterrupt:
            print("\nConfiguración cancelada por el usuario")
            return 130
        except Exception as e:
            print(f"Error en configuración interactiva: {e}")
            return 1
    
    def _detect_preferred_mode(self) -> str:
        """Detecta el modo preferido basado en el entorno"""
        try:
            # Verificar si hay interfaz gráfica disponible
            has_gui = False
            try:
                import tkinter
                test_root = tkinter.Tk()
                test_root.withdraw()
                test_root.destroy()
                has_gui = True
            except:
                pass
            
            # Verificar si está en terminal
            has_terminal = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
            
            # Verificar argumentos de línea de comandos
            has_args = len(sys.argv) > 1
            
            if has_gui and not has_args:
                return "GUI (Interfaz gráfica recomendada)"
            elif has_terminal:
                return "CLI (Línea de comandos)"
            else:
                return "Service (Servicio en segundo plano)"
                
        except Exception:
            return "CLI (Por defecto)"
    
    def shutdown_system(self):
        """Cierra el sistema de forma segura"""
        try:
            self.logger.info("Iniciando cierre del sistema...")
            self.running = False
            
            # Cerrar interfaces
            if self.gui_interface:
                try:
                    self.gui_interface.root.quit()
                except:
                    pass
            
            if self.cli_interface:
                try:
                    self.cli_interface.running = False
                except:
                    pass
            
            # Cerrar sistema de monitoreo
            if self.monitor_system:
                try:
                    self.monitor_system.shutdown_system()
                except Exception as e:
                    self.logger.error(f"Error cerrando sistema de monitoreo: {e}")
            
            # Terminar procesos worker
            for process in self.worker_processes:
                try:
                    process.terminate()
                    process.join(timeout=5)
                except:
                    pass
            
            self.logger.info("Sistema cerrado exitosamente")
            
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error cerrando sistema: {e}")
            else:
                print(f"Error cerrando sistema: {e}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Obtiene información del sistema y estado actual"""
        try:
            return {
                "version": self.version,
                "author": self.author,
                "build_date": self.build_date,
                "current_user": self.current_user,
                "system_initialized": self.system_initialized,
                "interface_mode": self.interface_mode,
                "running": self.running,
                "python_version": sys.version,
                "platform": sys.platform,
                "working_directory": str(SystemConfig.BASE_DIR),
                "log_level": logging.getLevelName(self.log_level),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}

def create_argument_parser() -> argparse.ArgumentParser:
    """Crea el parser de argumentos principal"""
    parser = argparse.ArgumentParser(
        prog='sysmonitor',
        description=f'Sistema de Monitoreo de PC v{SystemConfig.APP_VERSION} por SERGIORAMGO',
        epilog="""
Ejemplos de uso:
  python -m sysmonitor                    # Modo automático (GUI si disponible)
  python -m sysmonitor --gui              # Interfaz gráfica
  python -m sysmonitor --cli quick        # Verificación rápida por CLI
  python -m sysmonitor --service          # Ejecutar como servicio
  python -m sysmonitor --setup            # Configuración interactiva
  python -m sysmonitor --version          # Mostrar versión
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Grupo principal de modos
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--gui', action='store_true',
                           help='Ejecutar interfaz gráfica')
    mode_group.add_argument('--cli', action='store_true',
                           help='Ejecutar interfaz de línea de comandos')
    mode_group.add_argument('--service', action='store_true',
                           help='Ejecutar como servicio en segundo plano')
    mode_group.add_argument('--setup', action='store_true',
                           help='Configuración interactiva inicial')
    
    # Opciones de configuración
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       default='INFO', help='Nivel de logging')
    parser.add_argument('--log-file', help='Archivo de log personalizado')
    parser.add_argument('--no-console', action='store_true',
                       help='Deshabilitar salida por consola')
    parser.add_argument('--work-dir', help='Directorio de trabajo personalizado')
    parser.add_argument('--config-file', help='Archivo de configuración personalizado')
    
    # Información del sistema
    parser.add_argument('--version', action='version',
                       version=f'%(prog)s {SystemConfig.APP_VERSION}')
    parser.add_argument('--info', action='store_true',
                       help='Mostrar información del sistema')
    parser.add_argument('--check-deps', action='store_true',
                       help='Verificar dependencias del sistema')
    
    # Opciones de desarrollo y debug
    debug_group = parser.add_argument_group('opciones de desarrollo')
    debug_group.add_argument('--debug', action='store_true',
                           help='Habilitar modo debug')
    debug_group.add_argument('--profile', action='store_true',
                           help='Habilitar profiling de rendimiento')
    debug_group.add_argument('--test-mode', action='store_true',
                           help='Ejecutar en modo de prueba')
    
    return parser

def main():
    """Función principal del sistema"""
    try:
        # Crear parser de argumentos
        parser = create_argument_parser()
        
        # Si no hay argumentos, mostrar ayuda básica y usar modo automático
        if len(sys.argv) == 1:
            print(f"Sistema de Monitoreo de PC v{SystemConfig.APP_VERSION}")
            print(f"Autor: SERGIORAMGO | Fecha: 2025-06-22")
            print(f"Usuario actual: SERGIORAMGO")
            print("\nIniciando en modo automático...")
            print("Use --help para ver todas las opciones disponibles\n")
            
            # Detectar modo automático
            try:
                import tkinter
                test_root = tkinter.Tk()
                test_root.withdraw()
                test_root.destroy()
                # GUI disponible
                args = argparse.Namespace(
                    gui=True, cli=False, service=False, setup=False,
                    log_level='INFO', log_file=None, no_console=False,
                    work_dir=None, config_file=None, info=False,
                    check_deps=False, debug=False, profile=False, test_mode=False
                )
            except:
                # Solo CLI disponible
                args = argparse.Namespace(
                    gui=False, cli=True, service=False, setup=False,
                    log_level='INFO', log_file=None, no_console=False,
                    work_dir=None, config_file=None, info=False,
                    check_deps=False, debug=False, profile=False, test_mode=False
                )
                print("Interfaz gráfica no disponible, usando CLI")
        else:
            args = parser.parse_args()
        
        # Crear runner del sistema
        runner = SystemMonitorRunner()
        
        # Configurar directorio de trabajo si se especifica
        if args.work_dir:
            SystemConfig.BASE_DIR = Path(args.work_dir).resolve()
            runner.setup_environment()
        
        # Configurar logging
        console_output = not args.no_console
        if args.debug:
            log_level = 'DEBUG'
        else:
            log_level = args.log_level
        
        runner.setup_logging(log_level, args.log_file, console_output)
        
        # Ejecutar comando solicitado
        exit_code = 0
        
        if args.info:
            # Mostrar información del sistema
            info = runner.get_system_info()
            print("\nInformación del Sistema:")
            print("-" * 40)
            for key, value in info.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
            
        elif args.check_deps:
            # Verificar dependencias
            print("Verificando dependencias del sistema...")
            if runner._check_dependencies():
                print("✓ Todas las dependencias están disponibles")
                exit_code = 0
            else:
                print("✗ Faltan dependencias críticas")
                exit_code = 1
        
        elif args.setup:
            # Configuración interactiva
            exit_code = runner.run_interactive_setup()
        
        elif args.service:
            # Modo servicio
            exit_code = runner.run_service_mode()
        
        elif args.gui:
            # Modo GUI
            exit_code = runner.run_gui_mode()
        
        elif args.cli:
            # Modo CLI - pasar argumentos restantes
            cli_args = sys.argv[2:] if len(sys.argv) > 2 else []
            exit_code = runner.run_cli_mode(cli_args)
        
        else:
            # Modo por defecto
            if args.gui:
                exit_code = runner.run_gui_mode()
            else:
                exit_code = runner.run_cli_mode()
        
        # Shutdown limpio
        runner.shutdown_system()
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nOperación cancelada por el usuario")
        sys.exit(130)
    
    except Exception as e:
        print(f"Error crítico en main: {e}")
        
        # Intentar logging si está disponible
        try:
            logging.getLogger('SystemMonitor.Main').critical(f"Error crítico: {e}")
            logging.getLogger('SystemMonitor.Main').debug(traceback.format_exc())
        except:
            pass
        
        # Mostrar traceback en modo debug
        if '--debug' in sys.argv:
            traceback.print_exc()
        
        sys.exit(1)

# Punto de entrada para ejecución como módulo
if __name__ == "__main__":
    # Configurar multiprocessing para Windows
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    
    # Configurar encoding para Windows
    if sys.platform.startswith('win'):
        import locale
        try:
            locale.setlocale(locale.LC_ALL, 'es_ES.UTF-8')
        except:
            try:
                locale.setlocale(locale.LC_ALL, 'Spanish_Spain.1252')
            except:
                pass
    
    main()

# Funciones de utilidad para importación
def run_quick_check():
    """Función de utilidad para ejecutar verificación rápida"""
    try:
        runner = SystemMonitorRunner()
        runner.setup_logging('WARNING', console_output=False)
        
        if runner.initialize_system():
            result = runner.monitor_system.execute_quick_check()
            return result
        else:
            return {"error": "No se pudo inicializar el sistema"}
            
    except Exception as e:
        return {"error": str(e)}

def get_system_status():
    """Función de utilidad para obtener estado del sistema"""
    try:
        runner = SystemMonitorRunner()
        runner.setup_logging('WARNING', console_output=False)
        
        if runner.initialize_system():
            status = runner.monitor_system.get_system_status()
            return status
        else:
            return {"error": "No se pudo inicializar el sistema"}
            
    except Exception as e:
        return {"error": str(e)}

def create_gui_instance():
    """Función de utilidad para crear instancia GUI"""
    try:
        runner = SystemMonitorRunner()
        runner.setup_logging('INFO', console_output=True)
        
        if runner.initialize_system():
            return runner.run_gui_mode()
        else:
            return 1
            
    except Exception as e:
        print(f"Error creando GUI: {e}")
        return 1

# Configuración para distribución
__version__ = SystemConfig.APP_VERSION
__author__ = "SERGIORAMGO"
__date__ = "2025-06-22"
__all__ = [
    'SystemMonitorRunner',
    'main',
    'run_quick_check',
    'get_system_status',
    'create_gui_instance'
]

# Script de instalación automática
INSTALL_SCRIPT = """
@echo off
echo Sistema de Monitoreo de PC - Instalador
echo Autor: SERGIORAMGO
echo Fecha: 2025-06-22
echo.

echo Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python no está instalado o no está en el PATH
    pause
    exit /b 1
)

echo Instalando dependencias...
pip install psutil wmi pillow

echo Creando directorios...
mkdir "%USERPROFILE%\\SystemMonitor" 2>nul
mkdir "%USERPROFILE%\\SystemMonitor\\logs" 2>nul
mkdir "%USERPROFILE%\\SystemMonitor\\reports" 2>nul
mkdir "%USERPROFILE%\\SystemMonitor\\screenshots" 2>nul

echo Copiando archivos...
copy *.py "%USERPROFILE%\\SystemMonitor\\" >nul

echo Creando acceso directo...
echo python "%USERPROFILE%\\SystemMonitor\\14_main_runner.py" --gui > "%USERPROFILE%\\Desktop\\Monitor Sistema.bat"

echo.
echo Instalación completada!
echo Puede ejecutar el sistema desde el acceso directo creado en el escritorio
echo o ejecutar: python "%USERPROFILE%\\SystemMonitor\\14_main_runner.py"
echo.
pause
"""

# Guardar script de instalación si se ejecuta directamente
if __name__ == "__main__" and "--create-installer" in sys.argv:
    try:
        with open("install.bat", "w", encoding="utf-8") as f:
            f.write(INSTALL_SCRIPT)
        print("Script de instalación creado: install.bat")
    except Exception as e:
        print(f"Error creando script de instalación: {e}")