"""
Sistema de Monitoreo de PC - Módulo 4: Clases Base y Scheduler
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Clases base para tareas, scheduler de tareas y gestión de hilos
"""

import threading
import time
import queue
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
import logging
import traceback

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    GlobalState, PerformanceUtilities, SystemUtilities
)

# Logger para este módulo
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Estados de las tareas"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PAUSED = "paused"

class TaskPriority(Enum):
    """Prioridades de las tareas"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class TaskResult:
    """Resultado de una tarea"""
    task_id: str
    status: TaskStatus
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el resultado a diccionario"""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'data': self.data,
            'error': self.error,
            'execution_time': self.execution_time,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'progress': self.progress,
            'metadata': self.metadata
        }

class BaseTask(ABC):
    """Clase base abstracta para todas las tareas del sistema"""
    
    def __init__(self, 
                 name: str,
                 description: str = "",
                 priority: TaskPriority = TaskPriority.NORMAL,
                 timeout: int = SystemConfig.TASK_TIMEOUT,
                 retry_count: int = 0,
                 dependencies: List[str] = None):
        """
        Inicializa una tarea base
        
        Args:
            name: Nombre de la tarea
            description: Descripción de la tarea
            priority: Prioridad de la tarea
            timeout: Timeout en segundos
            retry_count: Número de reintentos
            dependencies: Lista de IDs de tareas dependientes
        """
        self.task_id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.priority = priority
        self.timeout = timeout
        self.retry_count = retry_count
        self.dependencies = dependencies or []
        
        # Estado de la tarea
        self.status = TaskStatus.PENDING
        self.progress = 0.0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.execution_time = 0.0
        self.error: Optional[str] = None
        self.result_data: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        
        # Control de ejecución
        self._cancelled = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()
        
        # Callbacks
        self.on_progress: Optional[Callable[[float], None]] = None
        self.on_status_change: Optional[Callable[[TaskStatus], None]] = None
        self.on_complete: Optional[Callable[[TaskResult], None]] = None
        
        logger.debug(f"Tarea creada: {self.name} (ID: {self.task_id})")
    
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """
        Método abstracto que debe implementar cada tarea
        
        Returns:
            Diccionario con los resultados de la tarea
        """
        pass
    
    def run(self) -> TaskResult:
        """
        Ejecuta la tarea con control de estado y manejo de errores
        
        Returns:
            Resultado de la tarea
        """
        with self._lock:
            if self.status != TaskStatus.PENDING:
                logger.warning(f"Intento de ejecutar tarea {self.name} en estado {self.status.value}")
                return self._create_result()
            
            self.status = TaskStatus.RUNNING
            self.start_time = datetime.now()
            self.progress = 0.0
            
        self._notify_status_change(self.status)
        
        try:
            logger.info(f"Iniciando ejecución de tarea: {self.name}")
            
            # Verificar si la tarea fue cancelada antes de comenzar
            if self._cancelled.is_set():
                self._set_status(TaskStatus.CANCELLED)
                return self._create_result()
            
            # Ejecutar la tarea con timeout
            result_data = self._execute_with_timeout()
            
            # Verificar cancelación después de ejecución
            if self._cancelled.is_set():
                self._set_status(TaskStatus.CANCELLED)
                return self._create_result()
            
            # Tarea completada exitosamente
            with self._lock:
                self.result_data = result_data or {}
                self.progress = 100.0
                self._set_status(TaskStatus.COMPLETED)
            
            logger.info(f"Tarea completada: {self.name} en {self.execution_time:.3f}s")
            
        except TimeoutError:
            logger.error(f"Timeout en tarea {self.name} después de {self.timeout}s")
            self._set_status(TaskStatus.TIMEOUT, "Tiempo de ejecución excedido")
            
        except Exception as e:
            error_msg = f"Error en tarea {self.name}: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self._set_status(TaskStatus.FAILED, error_msg)
        
        finally:
            with self._lock:
                self.end_time = datetime.now()
                if self.start_time:
                    self.execution_time = (self.end_time - self.start_time).total_seconds()
        
        result = self._create_result()
        
        # Notificar finalización
        if self.on_complete:
            try:
                self.on_complete(result)
            except Exception as e:
                logger.error(f"Error en callback de finalización: {e}")
        
        return result
    
    def _execute_with_timeout(self) -> Dict[str, Any]:
        """Ejecuta la tarea con control de timeout"""
        result_queue = queue.Queue()
        exception_queue = queue.Queue()
        
        def target():
            try:
                result = self.execute()
                result_queue.put(result)
            except Exception as e:
                exception_queue.put(e)
        
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        
        # Esperar con verificación periódica de cancelación
        elapsed_time = 0
        check_interval = 0.1  # Verificar cada 100ms
        
        while thread.is_alive() and elapsed_time < self.timeout:
            if self._cancelled.is_set():
                logger.info(f"Tarea {self.name} cancelada durante ejecución")
                return {}
            
            time.sleep(check_interval)
            elapsed_time += check_interval
        
        if thread.is_alive():
            # Timeout alcanzado
            raise TimeoutError(f"Tarea excedió timeout de {self.timeout}s")
        
        # Verificar si hubo excepción
        if not exception_queue.empty():
            raise exception_queue.get()
        
        # Obtener resultado
        if not result_queue.empty():
            return result_queue.get()
        
        return {}
    
    def _set_status(self, status: TaskStatus, error: str = None):
        """Establece el estado de la tarea"""
        with self._lock:
            self.status = status
            if error:
                self.error = error
        
        self._notify_status_change(status)
    
    def _notify_status_change(self, status: TaskStatus):
        """Notifica cambio de estado"""
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception as e:
                logger.error(f"Error en callback de cambio de estado: {e}")
    
    def _create_result(self) -> TaskResult:
        """Crea el resultado de la tarea"""
        return TaskResult(
            task_id=self.task_id,
            status=self.status,
            data=self.result_data.copy(),
            error=self.error,
            execution_time=self.execution_time,
            start_time=self.start_time,
            end_time=self.end_time,
            progress=self.progress,
            metadata=self.metadata.copy()
        )
    
    def cancel(self):
        """Cancela la tarea"""
        with self._lock:
            if self.status == TaskStatus.RUNNING:
                self._cancelled.set()
                logger.info(f"Solicitada cancelación de tarea: {self.name}")
            elif self.status == TaskStatus.PENDING:
                self._set_status(TaskStatus.CANCELLED)
                logger.info(f"Tarea cancelada: {self.name}")
    
    def pause(self):
        """Pausa la tarea (si está en ejecución)"""
        with self._lock:
            if self.status == TaskStatus.RUNNING:
                self._paused.set()
                self._set_status(TaskStatus.PAUSED)
                logger.info(f"Tarea pausada: {self.name}")
    
    def resume(self):
        """Reanuda la tarea pausada"""
        with self._lock:
            if self.status == TaskStatus.PAUSED:
                self._paused.clear()
                self._set_status(TaskStatus.RUNNING)
                logger.info(f"Tarea reanudada: {self.name}")
    
    def update_progress(self, progress: float, message: str = ""):
        """
        Actualiza el progreso de la tarea
        
        Args:
            progress: Progreso de 0.0 a 100.0
            message: Mensaje de progreso opcional
        """
        with self._lock:
            self.progress = max(0.0, min(100.0, progress))
            if message:
                self.metadata['progress_message'] = message
        
        if self.on_progress:
            try:
                self.on_progress(self.progress)
            except Exception as e:
                logger.error(f"Error en callback de progreso: {e}")
    
    def is_cancelled(self) -> bool:
        """Verifica si la tarea fue cancelada"""
        return self._cancelled.is_set()
    
    def is_paused(self) -> bool:
        """Verifica si la tarea está pausada"""
        return self._paused.is_set()
    
    def wait_if_paused(self):
        """Espera si la tarea está pausada"""
        if self._paused.is_set():
            logger.debug(f"Tarea {self.name} esperando reanudación...")
            self._paused.wait()
    
    def get_info(self) -> Dict[str, Any]:
        """Obtiene información completa de la tarea"""
        with self._lock:
            return {
                'task_id': self.task_id,
                'name': self.name,
                'description': self.description,
                'priority': self.priority.value,
                'status': self.status.value,
                'progress': self.progress,
                'timeout': self.timeout,
                'retry_count': self.retry_count,
                'dependencies': self.dependencies.copy(),
                'start_time': self.start_time.isoformat() if self.start_time else None,
                'end_time': self.end_time.isoformat() if self.end_time else None,
                'execution_time': self.execution_time,
                'error': self.error,
                'metadata': self.metadata.copy()
            }

class TaskScheduler:
    """Scheduler para gestión de tareas"""
    
    def __init__(self, max_workers: int = SystemConfig.MAX_WORKERS):
        """
        Inicializa el scheduler
        
        Args:
            max_workers: Número máximo de workers
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="TaskWorker"
        )
        
        # Colas de tareas por prioridad
        self.task_queues = {
            TaskPriority.CRITICAL: queue.PriorityQueue(),
            TaskPriority.HIGH: queue.PriorityQueue(),
            TaskPriority.NORMAL: queue.PriorityQueue(),
            TaskPriority.LOW: queue.PriorityQueue()
        }
        
        # Control del scheduler
        self.is_running = False
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        
        # Seguimiento de tareas
        self.tasks: Dict[str, BaseTask] = {}
        self.running_tasks: Dict[str, Future] = {}
        self.completed_tasks: Dict[str, TaskResult] = {}
        
        # Estadísticas
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'cancelled_tasks': 0,
            'average_execution_time': 0.0
        }
        
        # Lock para operaciones thread-safe
        self._lock = threading.Lock()
        
        logger.info(f"TaskScheduler inicializado con {max_workers} workers")
    
    def start(self):
        """Inicia el scheduler"""
        with self._lock:
            if self.is_running:
                logger.warning("TaskScheduler ya está ejecutándose")
                return
            
            self.is_running = True
            self.stop_event.clear()
            
            self.scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="TaskScheduler"
            )
            self.scheduler_thread.start()
            
            logger.info("TaskScheduler iniciado")
    
    def stop(self, wait_for_completion: bool = True):
        """
        Detiene el scheduler
        
        Args:
            wait_for_completion: Si esperar a que terminen las tareas en ejecución
        """
        with self._lock:
            if not self.is_running:
                return
            
            self.is_running = False
            self.stop_event.set()
        
        logger.info("Deteniendo TaskScheduler...")
        
        # Esperar a que termine el scheduler
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        # Cancelar tareas en ejecución si no se espera completación
        if not wait_for_completion:
            self._cancel_running_tasks()
        
        # Cerrar executor
        self.executor.shutdown(wait=wait_for_completion)
        
        logger.info("TaskScheduler detenido")
    
    def add_task(self, task: BaseTask) -> str:
        """
        Añade una tarea al scheduler
        
        Args:
            task: Tarea a añadir
            
        Returns:
            ID de la tarea
        """
        with self._lock:
            # Verificar dependencias
            for dep_id in task.dependencies:
                if dep_id not in self.tasks and dep_id not in self.completed_tasks:
                    raise ValueError(f"Dependencia no encontrada: {dep_id}")
            
            # Añadir tarea
            self.tasks[task.task_id] = task
            self.stats['total_tasks'] += 1
            
            # Encolar tarea
            priority_value = task.priority.value
            timestamp = time.time()
            self.task_queues[task.priority].put((priority_value, timestamp, task.task_id))
            
            logger.debug(f"Tarea añadida: {task.name} (Prioridad: {task.priority.name})")
            
            return task.task_id
    
    def remove_task(self, task_id: str) -> bool:
        """
        Elimina una tarea del scheduler
        
        Args:
            task_id: ID de la tarea
            
        Returns:
            True si se eliminó exitosamente
        """
        with self._lock:
            # Verificar si está en ejecución
            if task_id in self.running_tasks:
                future = self.running_tasks[task_id]
                future.cancel()
                del self.running_tasks[task_id]
            
            # Eliminar de tareas pendientes
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.cancel()
                del self.tasks[task_id]
                logger.info(f"Tarea eliminada: {task.name}")
                return True
            
            return False
    
    def get_task(self, task_id: str) -> Optional[BaseTask]:
        """
        Obtiene una tarea por su ID
        
        Args:
            task_id: ID de la tarea
            
        Returns:
            Tarea o None si no existe
        """
        return self.tasks.get(task_id)
    
    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """
        Obtiene el resultado de una tarea completada
        
        Args:
            task_id: ID de la tarea
            
        Returns:
            Resultado de la tarea o None
        """
        return self.completed_tasks.get(task_id)
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancela una tarea específica
        
        Args:
            task_id: ID de la tarea
            
        Returns:
            True si se canceló exitosamente
        """
        with self._lock:
            # Cancelar si está en ejecución
            if task_id in self.running_tasks:
                future = self.running_tasks[task_id]
                if future.cancel():
                    del self.running_tasks[task_id]
                    return True
            
            # Cancelar si está pendiente
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.cancel()
                return True
            
            return False
    
    def pause_task(self, task_id: str) -> bool:
        """Pausa una tarea en ejecución"""
        with self._lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.pause()
                return True
            return False
    
    def resume_task(self, task_id: str) -> bool:
        """Reanuda una tarea pausada"""
        with self._lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.resume()
                return True
            return False
    
    def _scheduler_loop(self):
        """Loop principal del scheduler"""
        logger.debug("Iniciando loop del scheduler")
        
        while not self.stop_event.is_set():
            try:
                # Procesar tareas por prioridad
                for priority in [TaskPriority.CRITICAL, TaskPriority.HIGH, 
                               TaskPriority.NORMAL, TaskPriority.LOW]:
                    
                    if self.stop_event.is_set():
                        break
                    
                    self._process_priority_queue(priority)
                
                # Limpiar tareas completadas
                self._cleanup_completed_tasks()
                
                # Pequeña pausa para evitar uso excesivo de CPU
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error en loop del scheduler: {e}")
                time.sleep(1)
        
        logger.debug("Loop del scheduler terminado")
    
    def _process_priority_queue(self, priority: TaskPriority):
        """Procesa la cola de una prioridad específica"""
        queue_obj = self.task_queues[priority]
        
        while not queue_obj.empty() and len(self.running_tasks) < self.max_workers:
            try:
                _, _, task_id = queue_obj.get_nowait()
                
                if task_id not in self.tasks:
                    continue
                
                task = self.tasks[task_id]
                
                # Verificar dependencias
                if not self._dependencies_completed(task):
                    # Re-encolar para más tarde
                    queue_obj.put((priority.value, time.time(), task_id))
                    break
                
                # Ejecutar tarea
                future = self.executor.submit(self._execute_task, task)
                self.running_tasks[task_id] = future
                
                logger.debug(f"Tarea enviada a ejecución: {task.name}")
                
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error procesando cola {priority.name}: {e}")
    
    def _dependencies_completed(self, task: BaseTask) -> bool:
        """Verifica si las dependencias de una tarea están completadas"""
        for dep_id in task.dependencies:
            if dep_id in self.tasks:
                dep_task = self.tasks[dep_id]
                if dep_task.status != TaskStatus.COMPLETED:
                    return False
            elif dep_id not in self.completed_tasks:
                return False
        
        return True
    
    def _execute_task(self, task: BaseTask) -> TaskResult:
        """Ejecuta una tarea y maneja el resultado"""
        try:
            result = task.run()
            
            with self._lock:
                # Mover tarea a completadas
                if task.task_id in self.tasks:
                    del self.tasks[task.task_id]
                
                self.completed_tasks[task.task_id] = result
                
                # Actualizar estadísticas
                if result.status == TaskStatus.COMPLETED:
                    self.stats['completed_tasks'] += 1
                elif result.status == TaskStatus.FAILED:
                    self.stats['failed_tasks'] += 1
                elif result.status == TaskStatus.CANCELLED:
                    self.stats['cancelled_tasks'] += 1
                
                # Actualizar tiempo promedio de ejecución
                if self.stats['completed_tasks'] > 0:
                    total_time = (self.stats['average_execution_time'] * 
                                (self.stats['completed_tasks'] - 1) + result.execution_time)
                    self.stats['average_execution_time'] = total_time / self.stats['completed_tasks']
            
            return result
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea {task.name}: {e}")
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=str(e)
            )
        finally:
            # Limpiar de tareas en ejecución
            with self._lock:
                if task.task_id in self.running_tasks:
                    del self.running_tasks[task.task_id]
    
    def _cleanup_completed_tasks(self, max_completed: int = 1000):
        """Limpia tareas completadas antiguas"""
        with self._lock:
            if len(self.completed_tasks) > max_completed:
                # Mantener solo las más recientes
                sorted_tasks = sorted(
                    self.completed_tasks.items(),
                    key=lambda x: x[1].end_time or datetime.min,
                    reverse=True
                )
                
                # Mantener solo las más recientes
                self.completed_tasks = dict(sorted_tasks[:max_completed])
                
                logger.debug(f"Limpieza de tareas: mantenidas {len(self.completed_tasks)} de {len(sorted_tasks)}")
    
    def _cancel_running_tasks(self):
        """Cancela todas las tareas en ejecución"""
        with self._lock:
            for task_id, future in list(self.running_tasks.items()):
                try:
                    future.cancel()
                    if task_id in self.tasks:
                        self.tasks[task_id].cancel()
                except Exception as e:
                    logger.error(f"Error cancelando tarea {task_id}: {e}")
            
            self.running_tasks.clear()
    
    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado actual del scheduler"""
        with self._lock:
            pending_count = sum(queue_obj.qsize() for queue_obj in self.task_queues.values())
            
            return {
                'is_running': self.is_running,
                'max_workers': self.max_workers,
                'pending_tasks': pending_count,
                'running_tasks': len(self.running_tasks),
                'completed_tasks': len(self.completed_tasks),
                'total_tasks_processed': self.stats['total_tasks'],
                'successful_tasks': self.stats['completed_tasks'],
                'failed_tasks': self.stats['failed_tasks'],
                'cancelled_tasks': self.stats['cancelled_tasks'],
                'average_execution_time': self.stats['average_execution_time'],
                'queue_sizes': {
                    priority.name: queue_obj.qsize() 
                    for priority, queue_obj in self.task_queues.items()
                }
            }
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Obtiene información de todas las tareas"""
        with self._lock:
            all_tasks = {}
            
            # Tareas pendientes y en ejecución
            for task_id, task in self.tasks.items():
                all_tasks[task_id] = task.get_info()
            
            # Tareas completadas (últimas 100)
            sorted_completed = sorted(
                self.completed_tasks.items(),
                key=lambda x: x[1].end_time or datetime.min,
                reverse=True
            )[:100]
            
            for task_id, result in sorted_completed:
                all_tasks[task_id] = result.to_dict()
            
            return all_tasks

# Singleton para el scheduler global
class GlobalTaskScheduler:
    """Scheduler global singleton"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = TaskScheduler()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> TaskScheduler:
        """Obtiene la instancia del scheduler global"""
        return cls()

# Funciones de utilidad
def create_task_chain(tasks: List[BaseTask]) -> List[str]:
    """
    Crea una cadena de tareas con dependencias secuenciales
    
    Args:
        tasks: Lista de tareas a encadenar
        
    Returns:
        Lista de IDs de tareas
    """
    if not tasks:
        return []
    
    scheduler = GlobalTaskScheduler.get_instance()
    task_ids = []
    
    for i, task in enumerate(tasks):
        if i > 0:
            # Añadir dependencia de la tarea anterior
            task.dependencies.append(task_ids[i-1])
        
        task_id = scheduler.add_task(task)
        task_ids.append(task_id)
    
    logger.info(f"Cadena de tareas creada: {len(tasks)} tareas")
    return task_ids

def wait_for_task(task_id: str, timeout: float = None) -> Optional[TaskResult]:
    """
    Espera a que una tarea específica termine
    
    Args:
        task_id: ID de la tarea
        timeout: Timeout en segundos
        
    Returns:
        Resultado de la tarea o None si timeout
    """
    scheduler = GlobalTaskScheduler.get_instance()
    start_time = time.time()
    
    while True:
        # Verificar si la tarea está completada
        result = scheduler.get_task_result(task_id)
        if result:
            return result
        
        # Verificar timeout
        if timeout and (time.time() - start_time) > timeout:
            logger.warning(f"Timeout esperando tarea {task_id}")
            return None
        
        # Verificar si la tarea aún existe
        task = scheduler.get_task(task_id)
        if not task and not result:
            logger.warning(f"Tarea {task_id} no encontrada")
            return None
        
        time.sleep(0.1)

# Inicialización del módulo
def initialize_base_classes():
    """Inicializa las clases base del sistema"""
    try:
        logger.info("Inicializando clases base del sistema...")
        
        # Inicializar scheduler global
        scheduler = GlobalTaskScheduler.get_instance()
        scheduler.start()
        
        # Registrar información del sistema
        global_state = GlobalState()
        global_state.set('scheduler_initialized', True)
        global_state.set('scheduler_start_time', datetime.now())
        
        logger.info("Clases base inicializadas correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando clases base: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_base_classes()