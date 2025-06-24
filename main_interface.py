"""
Sistema de Monitoreo de PC - Módulo 11: Interfaz Principal y Orquestador
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Interfaz principal del sistema de monitoreo con orquestador de tareas
"""

import threading
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import asyncio
import queue
from dataclasses import dataclass, field
from enum import Enum

# Importar todos los módulos del sistema
from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    SystemUtilities, SecurityUtilities, FileUtilities,
    GlobalState, PerformanceUtilities
)
from screenshot_capture import (
    ScreenshotCapture, ScheduledCapture, initialize_screenshot_system
)
from base_classes import (
    BaseTask, TaskPriority, TaskStatus, TaskResult,
    GlobalTaskScheduler
)
from detailed_system_task import DetailedSystemInfoTask
from monitoring_tasks import (
    TemperatureMonitoringTask, CPUMonitoringTask, MemoryMonitoringTask,
    get_performance_data, clear_performance_data
)
from disk_storage_tasks import DiskAnalysisTask, TempFileCleanupTask
from security_tasks import AntivirusStatusTask, WindowsUpdateTask
from system_service_tasks import (
    SystemServicesTask, EventLogAnalysisTask, StartupProgramsTask
)
from basic_tasks import SystemInfoTask, QuickSystemCheckTask

# Logger para este módulo
logger = logging.getLogger(__name__)

class MonitoringMode(Enum):
    """Modos de monitoreo del sistema"""
    BASIC = "basic"
    DETAILED = "detailed"
    CONTINUOUS = "continuous"
    SECURITY_FOCUSED = "security_focused"
    PERFORMANCE_FOCUSED = "performance_focused"
    MAINTENANCE = "maintenance"

class SystemStatus(Enum):
    """Estados del sistema de monitoreo"""
    IDLE = "idle"
    SCANNING = "scanning"
    MONITORING = "monitoring"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    SHUTDOWN = "shutdown"

@dataclass
class MonitoringSession:
    """Información de una sesión de monitoreo"""
    session_id: str
    user: str = "SERGIORAMGO"
    start_time: datetime = field(default_factory=datetime.now)
    mode: MonitoringMode = MonitoringMode.BASIC
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_duration: float = 0.0
    results: Dict[str, Any] = field(default_factory=dict)
    active_tasks: List[str] = field(default_factory=list)
    status: SystemStatus = SystemStatus.IDLE

class SystemMonitorInterface:
    """Interfaz principal del sistema de monitoreo"""
    
    def __init__(self):
        """Inicializa la interfaz principal"""
        self.version = SystemConfig.APP_VERSION
        self.build_date = "2025-06-22"
        self.author = "SERGIORAMGO"
        
        # Estado del sistema
        self.status = SystemStatus.IDLE
        self.current_session: Optional[MonitoringSession] = None
        self.global_state = GlobalState()
        
        # Scheduler de tareas
        self.task_scheduler = GlobalTaskScheduler.get_instance()
        
        # Sistemas especializados
        self.screenshot_system: Optional[ScreenshotCapture] = None
        self.scheduled_capture: Optional[ScheduledCapture] = None
        
        # Control de hilos
        self._stop_event = threading.Event()
        self._monitoring_thread: Optional[threading.Thread] = None
        self._status_thread: Optional[threading.Thread] = None
        
        # Colas de comunicación
        self.command_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.notification_queue = queue.Queue()
        
        # Callbacks para eventos
        self.status_callback: Optional[Callable[[SystemStatus], None]] = None
        self.progress_callback: Optional[Callable[[str, float], None]] = None
        self.result_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        
        # Configuración
        self.auto_save_results = True
        self.results_directory = SystemConfig.REPORTS_DIR
        self.max_concurrent_tasks = SystemConfig.MAX_WORKERS
        
        # Estadísticas
        self.total_sessions = 0
        self.total_tasks_executed = 0
        self.total_uptime = 0.0
        self.initialization_time = datetime.now()
        
        logger.info(f"Sistema de Monitoreo v{self.version} inicializado por {self.author}")
    
    def initialize_system(self) -> bool:
        """Inicializa todos los subsistemas"""
        try:
            logger.info("Inicializando subsistemas del monitor...")
            
            # Crear directorios necesarios
            FileUtilities.ensure_directory(self.results_directory)
            FileUtilities.ensure_directory(SystemConfig.TEMP_DIR)
            FileUtilities.ensure_directory(SystemConfig.LOGS_DIR)
            
            # Inicializar scheduler de tareas
            if not self.task_scheduler.is_running:
                self.task_scheduler.start()
                logger.info("Scheduler de tareas iniciado")
            
            # Inicializar sistema de capturas
            try:
                self.screenshot_system, self.scheduled_capture = initialize_screenshot_system()
                if self.screenshot_system:
                    logger.info("Sistema de capturas inicializado")
                else:
                    logger.warning("Sistema de capturas no disponible")
            except Exception as e:
                logger.error(f"Error inicializando capturas: {e}")
            
            # Inicializar hilos de monitoreo
            self._start_monitoring_threads()
            
            # Actualizar estado global
            self.global_state.set('system_initialized', True)
            self.global_state.set('initialization_time', self.initialization_time)
            self.global_state.set('current_user', self.author)
            
            self.status = SystemStatus.IDLE
            self._notify_status_change(self.status)
            
            logger.info("Sistema de monitoreo inicializado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error inicializando sistema: {e}")
            self.status = SystemStatus.ERROR
            return False
    
    def shutdown_system(self) -> bool:
        """Cierra el sistema de monitoreo de forma segura"""
        try:
            logger.info("Iniciando cierre del sistema de monitoreo...")
            
            self.status = SystemStatus.SHUTDOWN
            self._notify_status_change(self.status)
            
            # Detener hilos de monitoreo
            self._stop_event.set()
            
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=5)
            
            if self._status_thread and self._status_thread.is_alive():
                self._status_thread.join(timeout=5)
            
            # Finalizar sesión actual si existe
            if self.current_session:
                self._finalize_session()
            
            # Detener capturas programadas
            if self.scheduled_capture:
                self.scheduled_capture.stop_scheduled_capture()
            
            # Guardar estado final
            self._save_system_state()
            
            # Detener scheduler
            self.task_scheduler.stop(wait_for_completion=True)
            
            logger.info("Sistema de monitoreo cerrado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error cerrando sistema: {e}")
            return False
    
    def start_monitoring_session(self, mode: MonitoringMode = MonitoringMode.BASIC, 
                                custom_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Inicia una nueva sesión de monitoreo
        
        Args:
            mode: Modo de monitoreo a ejecutar
            custom_config: Configuración personalizada
            
        Returns:
            ID de la sesión creada
        """
        try:
            # Finalizar sesión anterior si existe
            if self.current_session:
                self._finalize_session()
            
            # Crear nueva sesión
            session_id = f"session_{int(time.time())}_{self.author}"
            self.current_session = MonitoringSession(
                session_id=session_id,
                user=self.author,
                mode=mode,
                start_time=datetime.now()
            )
            
            self.total_sessions += 1
            self.status = SystemStatus.SCANNING
            self._notify_status_change(self.status)
            
            logger.info(f"Iniciando sesión de monitoreo: {session_id} (modo: {mode.value})")
            
            # Programar tareas según el modo
            tasks_scheduled = self._schedule_tasks_for_mode(mode, custom_config)
            
            self.current_session.active_tasks = tasks_scheduled
            self._notify_progress("Sesión iniciada", 0)
            
            return session_id
            
        except Exception as e:
            logger.error(f"Error iniciando sesión de monitoreo: {e}")
            self.status = SystemStatus.ERROR
            raise
    
    def stop_current_session(self) -> bool:
        """Detiene la sesión de monitoreo actual"""
        try:
            if not self.current_session:
                logger.warning("No hay sesión activa para detener")
                return False
            
            logger.info(f"Deteniendo sesión: {self.current_session.session_id}")
            
            # Cancelar tareas activas
            for task_id in self.current_session.active_tasks:
                self.task_scheduler.cancel_task(task_id)
            
            # Finalizar sesión
            self._finalize_session()
            
            self.status = SystemStatus.IDLE
            self._notify_status_change(self.status)
            
            return True
            
        except Exception as e:
            logger.error(f"Error deteniendo sesión: {e}")
            return False
    
    def execute_quick_check(self) -> Dict[str, Any]:
        """Ejecuta una verificación rápida del sistema"""
        try:
            logger.info("Ejecutando verificación rápida del sistema...")
            
            # Crear y ejecutar tarea de verificación rápida
            quick_task = QuickSystemCheckTask()
            result = quick_task.run()
            
            if result.status == TaskStatus.COMPLETED:
                logger.info("Verificación rápida completada exitosamente")
                return result.data
            else:
                logger.error(f"Error en verificación rápida: {result.error}")
                return {'error': result.error, 'status': 'failed'}
                
        except Exception as e:
            logger.error(f"Error ejecutando verificación rápida: {e}")
            return {'error': str(e), 'status': 'failed'}
    
    def get_system_status(self) -> Dict[str, Any]:
        """Obtiene el estado actual del sistema"""
        try:
            status_info = {
                'system_status': self.status.value,
                'current_time': datetime.now().isoformat(),
                'uptime': (datetime.now() - self.initialization_time).total_seconds(),
                'uptime_formatted': SystemUtilities.format_duration(
                    (datetime.now() - self.initialization_time).total_seconds()
                ),
                'version': self.version,
                'build_date': self.build_date,
                'author': self.author,
                'current_user': self.author,
                'current_session': None,
                'task_scheduler_status': self.task_scheduler.get_status(),
                'performance_data_available': len(get_performance_data().get('metrics', {})) > 0,
                'screenshot_system_available': self.screenshot_system is not None,
                'total_sessions': self.total_sessions,
                'total_tasks_executed': self.total_tasks_executed,
                'system_resources': self._get_current_resources(),
                'active_monitoring': False
            }
            
            # Información de sesión actual
            if self.current_session:
                status_info['current_session'] = {
                    'session_id': self.current_session.session_id,
                    'mode': self.current_session.mode.value,
                    'start_time': self.current_session.start_time.isoformat(),
                    'duration': (datetime.now() - self.current_session.start_time).total_seconds(),
                    'tasks_completed': self.current_session.tasks_completed,
                    'tasks_failed': self.current_session.tasks_failed,
                    'active_tasks_count': len(self.current_session.active_tasks)
                }
                status_info['active_monitoring'] = True
            
            return status_info
            
        except Exception as e:
            logger.error(f"Error obteniendo estado del sistema: {e}")
            return {'error': str(e)}
    
    def get_available_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene información sobre las tareas disponibles"""
        return {
            'basic_tasks': {
                'SystemInfoTask': {
                    'name': 'Información Básica del Sistema',
                    'description': 'Recopilación rápida de información esencial',
                    'estimated_duration': '30-60 segundos',
                    'resource_usage': 'Bajo'
                },
                'QuickSystemCheckTask': {
                    'name': 'Verificación Rápida',
                    'description': 'Verificación ultra-rápida del estado del sistema',
                    'estimated_duration': '5-10 segundos',
                    'resource_usage': 'Muy Bajo'
                }
            },
            'detailed_tasks': {
                'DetailedSystemInfoTask': {
                    'name': 'Análisis Detallado del Sistema',
                    'description': 'Análisis completo del sistema con WMI',
                    'estimated_duration': '2-5 minutos',
                    'resource_usage': 'Alto'
                }
            },
            'monitoring_tasks': {
                'TemperatureMonitoringTask': {
                    'name': 'Monitoreo de Temperatura',
                    'description': 'Monitoreo continuo de temperatura del sistema',
                    'estimated_duration': 'Configurable',
                    'resource_usage': 'Medio'
                },
                'CPUMonitoringTask': {
                    'name': 'Monitoreo de CPU',
                    'description': 'Monitoreo detallado de CPU',
                    'estimated_duration': 'Configurable',
                    'resource_usage': 'Medio'
                },
                'MemoryMonitoringTask': {
                    'name': 'Monitoreo de Memoria',
                    'description': 'Monitoreo detallado de memoria',
                    'estimated_duration': 'Configurable',
                    'resource_usage': 'Medio'
                }
            },
            'maintenance_tasks': {
                'DiskAnalysisTask': {
                    'name': 'Análisis de Discos',
                    'description': 'Análisis completo de discos y almacenamiento',
                    'estimated_duration': '1-3 minutos',
                    'resource_usage': 'Medio'
                },
                'TempFileCleanupTask': {
                    'name': 'Limpieza de Archivos Temporales',
                    'description': 'Análisis y limpieza de archivos temporales',
                    'estimated_duration': '2-10 minutos',
                    'resource_usage': 'Medio'
                }
            },
            'security_tasks': {
                'AntivirusStatusTask': {
                    'name': 'Estado del Antivirus',
                    'description': 'Verificación completa del estado del antivirus',
                    'estimated_duration': '30-60 segundos',
                    'resource_usage': 'Bajo'
                },
                'WindowsUpdateTask': {
                    'name': 'Estado de Windows Update',
                    'description': 'Verificación del estado de actualizaciones',
                    'estimated_duration': '1-2 minutos',
                    'resource_usage': 'Medio'
                }
            },
            'system_tasks': {
                'SystemServicesTask': {
                    'name': 'Análisis de Servicios',
                    'description': 'Análisis completo de servicios del sistema',
                    'estimated_duration': '1-2 minutos',
                    'resource_usage': 'Medio'
                },
                'EventLogAnalysisTask': {
                    'name': 'Análisis del Event Log',
                    'description': 'Análisis de eventos del sistema',
                    'estimated_duration': '1-3 minutos',
                    'resource_usage': 'Alto'
                },
                'StartupProgramsTask': {
                    'name': 'Análisis de Programas de Inicio',
                    'description': 'Análisis de programas que se ejecutan al inicio',
                    'estimated_duration': '30-90 segundos',
                    'resource_usage': 'Medio'
                }
            }
        }
    
    def execute_custom_task(self, task_name: str, task_config: Dict[str, Any] = None) -> str:
        """
        Ejecuta una tarea personalizada
        
        Args:
            task_name: Nombre de la tarea a ejecutar
            task_config: Configuración específica de la tarea
            
        Returns:
            ID de la tarea programada
        """
        try:
            task_config = task_config or {}
            
            # Crear la tarea según el nombre
            task = self._create_task_instance(task_name, task_config)
            if not task:
                raise ValueError(f"Tarea desconocida: {task_name}")
            
            # Programar la tarea
            task_id = self.task_scheduler.add_task(task)
            self.total_tasks_executed += 1
            
            # Configurar callbacks para seguimiento
            task.on_complete = lambda result: self._handle_task_completion(task_name, result)
            
            logger.info(f"Tarea {task_name} programada con ID: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea personalizada {task_name}: {e}")
            raise
    
    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene el resultado de una tarea específica"""
        try:
            result = self.task_scheduler.get_task_result(task_id)
            if result:
                return result.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo resultado de tarea {task_id}: {e}")
            return None
    
    def take_screenshot(self, include_all_monitors: bool = True) -> Optional[Dict[str, Any]]:
        """Toma una captura de pantalla"""
        try:
            if not self.screenshot_system:
                logger.error("Sistema de capturas no disponible")
                return None
            
            monitor_index = None if include_all_monitors else 0
            result = self.screenshot_system.capture_screenshot(
                monitor_index=monitor_index,
                add_timestamp=True,
                add_watermark=True
            )
            
            if result:
                logger.info(f"Captura realizada: {result['monitors_captured']} monitores")
            
            return result
            
        except Exception as e:
            logger.error(f"Error tomando captura: {e}")
            return None
    
    def start_scheduled_screenshots(self, interval_minutes: int = 5) -> bool:
        """Inicia capturas programadas"""
        try:
            if not self.scheduled_capture:
                logger.error("Sistema de capturas programadas no disponible")
                return False
            
            interval_seconds = interval_minutes * 60
            success = self.scheduled_capture.start_scheduled_capture(interval_seconds)
            
            if success:
                logger.info(f"Capturas programadas iniciadas cada {interval_minutes} minutos")
            
            return success
            
        except Exception as e:
            logger.error(f"Error iniciando capturas programadas: {e}")
            return False
    
    def stop_scheduled_screenshots(self) -> bool:
        """Detiene las capturas programadas"""
        try:
            if not self.scheduled_capture:
                return False
            
            success = self.scheduled_capture.stop_scheduled_capture()
            
            if success:
                logger.info("Capturas programadas detenidas")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deteniendo capturas programadas: {e}")
            return False
    
    def get_performance_data(self) -> Dict[str, Any]:
        """Obtiene datos de rendimiento recopilados"""
        try:
            return get_performance_data()
        except Exception as e:
            logger.error(f"Error obteniendo datos de rendimiento: {e}")
            return {}
    
    def clear_performance_data(self) -> bool:
        """Limpia los datos de rendimiento"""
        try:
            clear_performance_data()
            logger.info("Datos de rendimiento limpiados")
            return True
        except Exception as e:
            logger.error(f"Error limpiando datos de rendimiento: {e}")
            return False
    
    def export_session_report(self, session_id: str = None, 
                            format: str = 'json') -> Optional[str]:
        """
        Exporta un reporte de sesión
        
        Args:
            session_id: ID de la sesión (None para sesión actual)
            format: Formato del reporte ('json', 'html', 'text')
            
        Returns:
            Ruta del archivo generado
        """
        try:
            if not session_id and self.current_session:
                session_id = self.current_session.session_id
            
            if not session_id:
                logger.error("No hay sesión para exportar")
                return None
            
            # Recopilar datos de la sesión
            report_data = self._compile_session_report(session_id)
            
            # Generar archivo según formato
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"monitor_report_{session_id}_{timestamp}"
            
            if format == 'json':
                filepath = self.results_directory / f"{filename}.json"
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            
            elif format == 'html':
                filepath = self.results_directory / f"{filename}.html"
                html_content = self._generate_html_report(report_data)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            elif format == 'text':
                filepath = self.results_directory / f"{filename}.txt"
                text_content = self._generate_text_report(report_data)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(text_content)
            
            else:
                raise ValueError(f"Formato no soportado: {format}")
            
            logger.info(f"Reporte exportado: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error exportando reporte: {e}")
            return None
    
    def set_callbacks(self, status_callback: Callable = None,
                     progress_callback: Callable = None,
                     result_callback: Callable = None):
        """Configura callbacks para eventos del sistema"""
        self.status_callback = status_callback
        self.progress_callback = progress_callback
        self.result_callback = result_callback
        logger.info("Callbacks configurados")
    
    # Métodos privados
    
    def _schedule_tasks_for_mode(self, mode: MonitoringMode, 
                               custom_config: Dict[str, Any] = None) -> List[str]:
        """Programa tareas según el modo de monitoreo"""
        try:
            custom_config = custom_config or {}
            task_ids = []
            
            if mode == MonitoringMode.BASIC:
                # Monitoreo básico: información del sistema
                task = SystemInfoTask()
                task_ids.append(self.task_scheduler.add_task(task))
                
            elif mode == MonitoringMode.DETAILED:
                # Monitoreo detallado: análisis completo
                tasks = [
                    DetailedSystemInfoTask(),
                    DiskAnalysisTask(),
                    SystemServicesTask()
                ]
                for task in tasks:
                    task_ids.append(self.task_scheduler.add_task(task))
                    
            elif mode == MonitoringMode.CONTINUOUS:
                # Monitoreo continuo: métricas de rendimiento
                duration = custom_config.get('duration', 300)  # 5 minutos por defecto
                tasks = [
                    CPUMonitoringTask(monitoring_duration=duration),
                    MemoryMonitoringTask(monitoring_duration=duration),
                    TemperatureMonitoringTask(monitoring_duration=duration)
                ]
                for task in tasks:
                    task_ids.append(self.task_scheduler.add_task(task))
                    
            elif mode == MonitoringMode.SECURITY_FOCUSED:
                # Enfoque en seguridad
                tasks = [
                    AntivirusStatusTask(),
                    WindowsUpdateTask(),
                    EventLogAnalysisTask(days_to_analyze=3),
                    StartupProgramsTask()
                ]
                for task in tasks:
                    task_ids.append(self.task_scheduler.add_task(task))
                    
            elif mode == MonitoringMode.PERFORMANCE_FOCUSED:
                # Enfoque en rendimiento
                tasks = [
                    SystemInfoTask(),
                    CPUMonitoringTask(monitoring_duration=120),
                    MemoryMonitoringTask(monitoring_duration=120),
                    DiskAnalysisTask(include_performance=True)
                ]
                for task in tasks:
                    task_ids.append(self.task_scheduler.add_task(task))
                    
            elif mode == MonitoringMode.MAINTENANCE:
                # Tareas de mantenimiento
                tasks = [
                    TempFileCleanupTask(),
                    DiskAnalysisTask(),
                    SystemServicesTask(),
                    StartupProgramsTask()
                ]
                for task in tasks:
                    task_ids.append(self.task_scheduler.add_task(task))
            
            # Configurar callbacks para todas las tareas
            for task_id in task_ids:
                task = self.task_scheduler.get_task(task_id)
                if task:
                    task.on_complete = lambda result, tid=task_id: self._handle_task_completion(tid, result)
            
            logger.info(f"Programadas {len(task_ids)} tareas para modo {mode.value}")
            return task_ids
            
        except Exception as e:
            logger.error(f"Error programando tareas para modo {mode.value}: {e}")
            return []
    
    def _create_task_instance(self, task_name: str, config: Dict[str, Any]) -> Optional[BaseTask]:
        """Crea una instancia de tarea según el nombre"""
        task_map = {
            'SystemInfoTask': lambda: SystemInfoTask(**config),
            'QuickSystemCheckTask': lambda: QuickSystemCheckTask(),
            'DetailedSystemInfoTask': lambda: DetailedSystemInfoTask(**config),
            'TemperatureMonitoringTask': lambda: TemperatureMonitoringTask(**config),
            'CPUMonitoringTask': lambda: CPUMonitoringTask(**config),
            'MemoryMonitoringTask': lambda: MemoryMonitoringTask(**config),
            'DiskAnalysisTask': lambda: DiskAnalysisTask(**config),
            'TempFileCleanupTask': lambda: TempFileCleanupTask(**config),
            'AntivirusStatusTask': lambda: AntivirusStatusTask(**config),
            'WindowsUpdateTask': lambda: WindowsUpdateTask(**config),
            'SystemServicesTask': lambda: SystemServicesTask(**config),
            'EventLogAnalysisTask': lambda: EventLogAnalysisTask(**config),
            'StartupProgramsTask': lambda: StartupProgramsTask(**config)
        }
        
        if task_name in task_map:
            try:
                return task_map[task_name]()
            except Exception as e:
                logger.error(f"Error creando tarea {task_name}: {e}")
                return None
        
        return None
    
    def _handle_task_completion(self, task_identifier: str, result: TaskResult):
        """Maneja la finalización de una tarea"""
        try:
            if self.current_session:
                if result.status == TaskStatus.COMPLETED:
                    self.current_session.tasks_completed += 1
                    self.current_session.results[task_identifier] = result.data
                else:
                    self.current_session.tasks_failed += 1
                
                # Remover de tareas activas
                if task_identifier in self.current_session.active_tasks:
                    self.current_session.active_tasks.remove(task_identifier)
            
            # Notificar resultado
            if self.result_callback:
                self.result_callback(task_identifier, result.to_dict())
            
            # Auto-guardar si está configurado
            if self.auto_save_results:
                self._save_task_result(task_identifier, result)
            
            logger.info(f"Tarea {task_identifier} completada: {result.status.value}")
            
        except Exception as e:
            logger.error(f"Error manejando finalización de tarea: {e}")
    
    def _start_monitoring_threads(self):
        """Inicia hilos de monitoreo en segundo plano"""
        try:
            # Hilo de monitoreo general
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="SystemMonitoringLoop"
            )
            self._monitoring_thread.start()
            
            # Hilo de actualización de estado
            self._status_thread = threading.Thread(
                target=self._status_update_loop,
                daemon=True,
                name="StatusUpdateLoop"
            )
            self._status_thread.start()
            
            logger.info("Hilos de monitoreo iniciados")
            
        except Exception as e:
            logger.error(f"Error iniciando hilos de monitoreo: {e}")
    
    def _monitoring_loop(self):
        """Loop principal de monitoreo en segundo plano"""
        try:
            while not self._stop_event.is_set():
                try:
                    # Procesar comandos en cola
                    try:
                        command = self.command_queue.get_nowait()
                        self._process_command(command)
                    except queue.Empty:
                        pass
                    
                    # Verificar estado de sesión actual
                    if self.current_session:
                        self._update_session_status()
                    
                    # Actualizar estadísticas globales
                    self._update_global_statistics()
                    
                    time.sleep(1)  # Verificar cada segundo
                    
                except Exception as e:
                    logger.error(f"Error en loop de monitoreo: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            logger.error(f"Error crítico en loop de monitoreo: {e}")
    
    def _status_update_loop(self):
        """Loop de actualización de estado"""
        try:
            while not self._stop_event.is_set():
                try:
                    # Verificar cambios de estado del scheduler
                    scheduler_status = self.task_scheduler.get_status()
                    
                    # Actualizar estado del sistema según actividad
                    if self.current_session and len(self.current_session.active_tasks) > 0:
                        if self.status != SystemStatus.SCANNING:
                            self.status = SystemStatus.SCANNING
                            self._notify_status_change(self.status)
                    elif self.status == SystemStatus.SCANNING and (not self.current_session or len(self.current_session.active_tasks) == 0):
                        self.status = SystemStatus.IDLE
                        self._notify_status_change(self.status)
                    
                    time.sleep(2)  # Actualizar cada 2 segundos
                    
                except Exception as e:
                    logger.error(f"Error en loop de estado: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            logger.error(f"Error crítico en loop de estado: {e}")
    
    def _process_command(self, command: Dict[str, Any]):
        """Procesa un comando de la cola"""
        try:
            cmd_type = command.get('type')
            cmd_data = command.get('data', {})
            
            if cmd_type == 'take_screenshot':
                result = self.take_screenshot(**cmd_data)
                self.result_queue.put({'type': 'screenshot_result', 'data': result})
                
            elif cmd_type == 'execute_task':
                task_name = cmd_data.get('task_name')
                task_config = cmd_data.get('config', {})
                task_id = self.execute_custom_task(task_name, task_config)
                self.result_queue.put({'type': 'task_scheduled', 'data': {'task_id': task_id}})
                
            elif cmd_type == 'export_report':
                filepath = self.export_session_report(**cmd_data)
                self.result_queue.put({'type': 'report_exported', 'data': {'filepath': filepath}})
                
        except Exception as e:
            logger.error(f"Error procesando comando {command}: {e}")
    
    def _update_session_status(self):
        """Actualiza el estado de la sesión actual"""
        try:
            if not self.current_session:
                return
            
            # Verificar si todas las tareas han terminado
            if len(self.current_session.active_tasks) == 0 and self.current_session.tasks_completed > 0:
                self._finalize_session()
            
            # Actualizar duración
            self.current_session.total_duration = (
                datetime.now() - self.current_session.start_time
            ).total_seconds()
            
        except Exception as e:
            logger.error(f"Error actualizando estado de sesión: {e}")
    
    def _update_global_statistics(self):
        """Actualiza estadísticas globales del sistema"""
        try:
            self.total_uptime = (datetime.now() - self.initialization_time).total_seconds()
            
            # Actualizar estado global
            self.global_state.set('total_uptime', self.total_uptime)
            self.global_state.set('total_sessions', self.total_sessions)
            self.global_state.set('total_tasks_executed', self.total_tasks_executed)
            self.global_state.set('current_status', self.status.value)
            
        except Exception as e:
            logger.error(f"Error actualizando estadísticas globales: {e}")
    
    def _finalize_session(self):
        """Finaliza la sesión actual"""
        try:
            if not self.current_session:
                return
            
            self.current_session.status = SystemStatus.IDLE
            self.current_session.total_duration = (
                datetime.now() - self.current_session.start_time
            ).total_seconds()
            
            # Guardar resumen de sesión
            if self.auto_save_results:
                self._save_session_summary()
            
            logger.info(f"Sesión finalizada: {self.current_session.session_id}")
            self.current_session = None
            
        except Exception as e:
            logger.error(f"Error finalizando sesión: {e}")
    
    def _get_current_resources(self) -> Dict[str, Any]:
        """Obtiene el uso actual de recursos del sistema"""
        try:
            import psutil
            
            return {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent if psutil.disk_partitions() else 0,
                'process_count': len(list(psutil.process_iter())),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"Error obteniendo recursos actuales: {e}")
            return {}
    
    def _save_task_result(self, task_id: str, result: TaskResult):
        """Guarda el resultado de una tarea"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"task_result_{task_id}_{timestamp}.json"
            filepath = self.results_directory / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False, default=str)
                
        except Exception as e:
            logger.error(f"Error guardando resultado de tarea: {e}")
    
    def _save_session_summary(self):
        """Guarda un resumen de la sesión"""
        try:
            if not self.current_session:
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"session_summary_{self.current_session.session_id}_{timestamp}.json"
            filepath = self.results_directory / filename
            
            summary = {
                'session_id': self.current_session.session_id,
                'user': self.current_session.user,
                'mode': self.current_session.mode.value,
                'start_time': self.current_session.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'total_duration': self.current_session.total_duration,
                'tasks_completed': self.current_session.tasks_completed,
                'tasks_failed': self.current_session.tasks_failed,
                'results_summary': {
                    task_id: len(data) if isinstance(data, dict) else str(type(data))
                    for task_id, data in self.current_session.results.items()
                }
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
                
        except Exception as e:
            logger.error(f"Error guardando resumen de sesión: {e}")
    
    def _save_system_state(self):
        """Guarda el estado actual del sistema"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"system_state_{timestamp}.json"
            filepath = self.results_directory / filename
            
            state = {
                'timestamp': timestamp,
                'system_info': {
                    'version': self.version,
                    'build_date': self.build_date,
                    'author': self.author,
                    'initialization_time': self.initialization_time.isoformat(),
                    'total_uptime': self.total_uptime,
                    'total_sessions': self.total_sessions,
                    'total_tasks_executed': self.total_tasks_executed
                },
                'global_state': dict(self.global_state._state),
                'scheduler_status': self.task_scheduler.get_status()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
                
        except Exception as e:
            logger.error(f"Error guardando estado del sistema: {e}")
    
    def _compile_session_report(self, session_id: str) -> Dict[str, Any]:
        """Compila un reporte completo de sesión"""
        try:
            report = {
                'report_info': {
                    'generated_by': f"Sistema de Monitoreo v{self.version}",
                    'author': self.author,
                    'generation_time': datetime.now().isoformat(),
                    'session_id': session_id
                },
                'system_info': self.get_system_status(),
                'session_data': {},
                'performance_data': self.get_performance_data(),
                'scheduler_status': self.task_scheduler.get_status()
            }
            
            # Datos de sesión si está activa
            if self.current_session and self.current_session.session_id == session_id:
                report['session_data'] = {
                    'session_id': self.current_session.session_id,
                    'mode': self.current_session.mode.value,
                    'start_time': self.current_session.start_time.isoformat(),
                    'duration': self.current_session.total_duration,
                    'tasks_completed': self.current_session.tasks_completed,
                    'tasks_failed': self.current_session.tasks_failed,
                    'results': self.current_session.results
                }
            
            return report
            
        except Exception as e:
            logger.error(f"Error compilando reporte: {e}")
            return {'error': str(e)}
    
    def _generate_html_report(self, report_data: Dict[str, Any]) -> str:
        """Genera un reporte en formato HTML"""
        try:
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Reporte de Monitoreo - {report_data.get('report_info', {}).get('session_id', 'Unknown')}</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                    .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                    .metric {{ margin: 5px 0; }}
                    .critical {{ color: red; font-weight: bold; }}
                    .warning {{ color: orange; font-weight: bold; }}
                    .good {{ color: green; }}
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Reporte de Monitoreo del Sistema</h1>
                    <p><strong>Generado por:</strong> {report_data.get('report_info', {}).get('generated_by', 'Unknown')}</p>
                    <p><strong>Autor:</strong> {report_data.get('report_info', {}).get('author', 'Unknown')}</p>
                    <p><strong>Fecha:</strong> {report_data.get('report_info', {}).get('generation_time', 'Unknown')}</p>
                    <p><strong>Sesión:</strong> {report_data.get('report_info', {}).get('session_id', 'Unknown')}</p>
                </div>
                
                <div class="section">
                    <h2>Estado del Sistema</h2>
                    <div class="metric"><strong>Estado:</strong> {report_data.get('system_info', {}).get('system_status', 'Unknown')}</div>
                    <div class="metric"><strong>Tiempo de actividad:</strong> {report_data.get('system_info', {}).get('uptime_formatted', 'Unknown')}</div>
                    <div class="metric"><strong>Versión:</strong> {report_data.get('system_info', {}).get('version', 'Unknown')}</div>
                </div>
                
                <div class="section">
                    <h2>Información de Sesión</h2>
                    <div class="metric"><strong>Modo:</strong> {report_data.get('session_data', {}).get('mode', 'N/A')}</div>
                    <div class="metric"><strong>Duración:</strong> {report_data.get('session_data', {}).get('duration', 0):.2f} segundos</div>
                    <div class="metric"><strong>Tareas completadas:</strong> {report_data.get('session_data', {}).get('tasks_completed', 0)}</div>
                    <div class="metric"><strong>Tareas fallidas:</strong> {report_data.get('session_data', {}).get('tasks_failed', 0)}</div>
                </div>
                
                <div class="section">
                    <h2>Estado del Scheduler</h2>
                    <div class="metric"><strong>Activo:</strong> {'Sí' if report_data.get('scheduler_status', {}).get('is_running', False) else 'No'}</div>
                    <div class="metric"><strong>Tareas pendientes:</strong> {report_data.get('scheduler_status', {}).get('pending_tasks', 0)}</div>
                    <div class="metric"><strong>Tareas en ejecución:</strong> {report_data.get('scheduler_status', {}).get('running_tasks', 0)}</div>
                    <div class="metric"><strong>Tareas completadas:</strong> {report_data.get('scheduler_status', {}).get('completed_tasks', 0)}</div>
                </div>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            logger.error(f"Error generando reporte HTML: {e}")
            return f"<html><body><h1>Error generando reporte</h1><p>{str(e)}</p></body></html>"
    
    def _generate_text_report(self, report_data: Dict[str, Any]) -> str:
        """Genera un reporte en formato texto"""
        try:
            lines = [
                "=" * 80,
                "REPORTE DE MONITOREO DEL SISTEMA",
                "=" * 80,
                f"Generado por: {report_data.get('report_info', {}).get('generated_by', 'Unknown')}",
                f"Autor: {report_data.get('report_info', {}).get('author', 'Unknown')}",
                f"Fecha: {report_data.get('report_info', {}).get('generation_time', 'Unknown')}",
                f"Sesión: {report_data.get('report_info', {}).get('session_id', 'Unknown')}",
                "",
                "ESTADO DEL SISTEMA",
                "-" * 40,
                f"Estado: {report_data.get('system_info', {}).get('system_status', 'Unknown')}",
                f"Tiempo de actividad: {report_data.get('system_info', {}).get('uptime_formatted', 'Unknown')}",
                f"Versión: {report_data.get('system_info', {}).get('version', 'Unknown')}",
                "",
                "INFORMACIÓN DE SESIÓN",
                "-" * 40,
                f"Modo: {report_data.get('session_data', {}).get('mode', 'N/A')}",
                f"Duración: {report_data.get('session_data', {}).get('duration', 0):.2f} segundos",
                f"Tareas completadas: {report_data.get('session_data', {}).get('tasks_completed', 0)}",
                f"Tareas fallidas: {report_data.get('session_data', {}).get('tasks_failed', 0)}",
                "",
                "ESTADO DEL SCHEDULER",
                "-" * 40,
                f"Activo: {'Sí' if report_data.get('scheduler_status', {}).get('is_running', False) else 'No'}",
                f"Tareas pendientes: {report_data.get('scheduler_status', {}).get('pending_tasks', 0)}",
                f"Tareas en ejecución: {report_data.get('scheduler_status', {}).get('running_tasks', 0)}",
                f"Tareas completadas: {report_data.get('scheduler_status', {}).get('completed_tasks', 0)}",
                "",
                "=" * 80
            ]
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error generando reporte de texto: {e}")
            return f"Error generando reporte: {str(e)}"
    
    def _notify_status_change(self, new_status: SystemStatus):
        """Notifica cambio de estado"""
        try:
            if self.status_callback:
                self.status_callback(new_status)
            
            self.notification_queue.put({
                'type': 'status_change',
                'data': {
                    'new_status': new_status.value,
                    'timestamp': datetime.now().isoformat()
                }
            })
            
        except Exception as e:
            logger.error(f"Error notificando cambio de estado: {e}")
    
    def _notify_progress(self, message: str, progress: float):
        """Notifica progreso"""
        try:
            if self.progress_callback:
                self.progress_callback(message, progress)
            
            self.notification_queue.put({
                'type': 'progress',
                'data': {
                    'message': message,
                    'progress': progress,
                    'timestamp': datetime.now().isoformat()
                }
            })
            
        except Exception as e:
            logger.error(f"Error notificando progreso: {e}")

# Funciones de utilidad para inicialización

def create_system_monitor() -> SystemMonitorInterface:
    """Crea una nueva instancia del monitor del sistema"""
    try:
        monitor = SystemMonitorInterface()
        if monitor.initialize_system():
            logger.info("Monitor del sistema creado e inicializado exitosamente")
            return monitor
        else:
            logger.error("Error inicializando el monitor del sistema")
            return None
            
    except Exception as e:
        logger.error(f"Error creando monitor del sistema: {e}")
        return None

def run_quick_system_scan() -> Dict[str, Any]:
    """Ejecuta un escaneo rápido del sistema de forma independiente"""
    try:
        monitor = create_system_monitor()
        if not monitor:
            return {'error': 'No se pudo inicializar el monitor'}
        
        try:
            result = monitor.execute_quick_check()
            return result
        finally:
            monitor.shutdown_system()
            
    except Exception as e:
        logger.error(f"Error en escaneo rápido: {e}")
        return {'error': str(e)}

def run_basic_system_info() -> Dict[str, Any]:
    """Ejecuta recopilación básica de información del sistema"""
    try:
        monitor = create_system_monitor()
        if not monitor:
            return {'error': 'No se pudo inicializar el monitor'}
        
        try:
            task_id = monitor.execute_custom_task('SystemInfoTask')
            
            # Esperar resultado (máximo 60 segundos)
            for _ in range(60):
                result = monitor.get_task_result(task_id)
                if result:
                    return result
                time.sleep(1)
            
            return {'error': 'Timeout esperando resultado'}
            
        finally:
            monitor.shutdown_system()
            
    except Exception as e:
        logger.error(f"Error en información básica: {e}")
        return {'error': str(e)}

# Función principal para pruebas
def main():
    """Función principal para pruebas del sistema"""
    try:
        print(f"Sistema de Monitoreo de PC v{SystemConfig.APP_VERSION}")
        print(f"Autor: SERGIORAMGO")
        print(f"Fecha: 2025-06-22")
        print("=" * 50)
        
        # Crear monitor
        print("Inicializando monitor del sistema...")
        monitor = create_system_monitor()
        
        if not monitor:
            print("Error: No se pudo inicializar el monitor")
            return
        
        try:
            # Mostrar estado inicial
            status = monitor.get_system_status()
            print(f"Estado del sistema: {status['system_status']}")
            print(f"Versión: {status['version']}")
            
            # Ejecutar verificación rápida
            print("\nEjecutando verificación rápida...")
            quick_result = monitor.execute_quick_check()
            print(f"Resultado: {quick_result.get('status', 'Unknown')}")
            
            if quick_result.get('alerts'):
                print("Alertas encontradas:")
                for alert in quick_result['alerts']:
                    print(f"  - {alert['level']}: {alert['message']}")
            
            # Iniciar sesión básica
            print("\nIniciando sesión de monitoreo básico...")
            session_id = monitor.start_monitoring_session(MonitoringMode.BASIC)
            print(f"Sesión iniciada: {session_id}")
            
            # Esperar completación
            print("Esperando completación de tareas...")
            for i in range(30):  # Máximo 30 segundos
                status = monitor.get_system_status()
                if not status.get('active_monitoring', False):
                    break
                print(f"  Progreso: {i+1}/30")
                time.sleep(1)
            
            # Exportar reporte
            print("\nExportando reporte...")
            report_path = monitor.export_session_report(format='text')
            if report_path:
                print(f"Reporte guardado en: {report_path}")
            
            print("\nPrueba completada exitosamente")
            
        finally:
            print("\nCerrando sistema...")
            monitor.shutdown_system()
            
    except Exception as e:
        print(f"Error en prueba principal: {e}")
        logger.error(f"Error en función main: {e}")

if __name__ == "__main__":
    main()