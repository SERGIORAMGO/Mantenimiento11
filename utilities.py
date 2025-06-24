"""
Sistema de Monitoreo de PC - Módulo 2: Utilidades y Funciones Auxiliares
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Funciones auxiliares, decoradores, utilidades de sistema y helpers
"""

import functools
import time
import threading
import queue
import signal
import gc
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from pathlib import Path
import logging
from contextlib import contextmanager # Añadido para resolver NameError

from config_and_imports import SystemConfig, SystemConstants

# Logger para este módulo
logger = logging.getLogger(__name__)

class TimeoutError(Exception):
    """Excepción personalizada para timeouts"""
    pass

class SystemUtilities:
    """Clase con utilidades del sistema"""
    
    @staticmethod
    def format_bytes(bytes_value: Union[int, float], decimals: int = 2) -> str:
        """
        Convierte bytes a formato legible
        
        Args:
            bytes_value: Valor en bytes
            decimals: Número de decimales
            
        Returns:
            Cadena formateada (ej: "1.5 GB")
        """
        try:
            if bytes_value == 0:
                return "0 B"
            
            units = SystemConstants.UNITS['BYTES']
            size = abs(float(bytes_value))
            
            for i, unit in enumerate(units):
                if size < 1024.0 or i == len(units) - 1:
                    return f"{size:.{decimals}f} {unit}"
                size /= 1024.0
                
        except (ValueError, TypeError):
            return "0 B"
    
    @staticmethod
    def format_frequency(hz_value: Union[int, float], decimals: int = 2) -> str:
        """
        Convierte frecuencia en Hz a formato legible
        
        Args:
            hz_value: Valor en Hz
            decimals: Número de decimales
            
        Returns:
            Cadena formateada (ej: "2.4 GHz")
        """
        try:
            if hz_value == 0:
                return "0 Hz"
            
            units = SystemConstants.UNITS['FREQUENCY']
            freq = abs(float(hz_value))
            
            for i, unit in enumerate(units):
                if freq < 1000.0 or i == len(units) - 1:
                    return f"{freq:.{decimals}f} {unit}"
                freq /= 1000.0
                
        except (ValueError, TypeError):
            return "0 Hz"
    
    @staticmethod
    def format_temperature(celsius: Union[int, float], unit: str = '°C', decimals: int = 1) -> str:
        """
        Formatea temperatura
        
        Args:
            celsius: Temperatura en Celsius
            unit: Unidad de salida ('°C', '°F', 'K')
            decimals: Número de decimales
            
        Returns:
            Cadena formateada
        """
        try:
            temp = float(celsius)
            
            if unit == '°F':
                temp = (temp * 9/5) + 32
            elif unit == 'K':
                temp = temp + 273.15
            
            return f"{temp:.{decimals}f} {unit}"
            
        except (ValueError, TypeError):
            return f"0 {unit}"
    
    @staticmethod
    def format_duration(seconds: Union[int, float]) -> str:
        """
        Convierte segundos a formato legible
        
        Args:
            seconds: Duración en segundos
            
        Returns:
            Cadena formateada (ej: "1h 23m 45s")
        """
        try:
            total_seconds = int(abs(seconds))
            
            if total_seconds < 60:
                return f"{total_seconds}s"
            elif total_seconds < 3600:
                minutes = total_seconds // 60
                secs = total_seconds % 60
                return f"{minutes}m {secs}s"
            elif total_seconds < 86400:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
            else:
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                return f"{days}d {hours}h"
                
        except (ValueError, TypeError):
            return "0s"
    
    @staticmethod
    def format_percentage(value: Union[int, float], total: Union[int, float] = 100, decimals: int = 1) -> str:
        """
        Formatea porcentaje
        
        Args:
            value: Valor actual
            total: Valor total
            decimals: Número de decimales
            
        Returns:
            Cadena formateada (ej: "75.5%")
        """
        try:
            if total == 0:
                return "0%"
            
            percentage = (float(value) / float(total)) * 100
            return f"{percentage:.{decimals}f}%"
            
        except (ValueError, TypeError, ZeroDivisionError):
            return "0%"
    
    @staticmethod
    def safe_get_attribute(obj: Any, attr_path: str, default: Any = None) -> Any:
        """
        Obtiene atributo de forma segura usando notación de punto
        
        Args:
            obj: Objeto del cual obtener el atributo
            attr_path: Ruta del atributo (ej: "disk.size")
            default: Valor por defecto
            
        Returns:
            Valor del atributo o default
        """
        try:
            attrs = attr_path.split('.')
            result = obj
            
            for attr in attrs:
                if hasattr(result, attr):
                    result = getattr(result, attr)
                else:
                    return default
            
            return result
            
        except Exception:
            return default
    
    @staticmethod
    def clean_string(text: str, max_length: int = None) -> str:
        """
        Limpia y formatea cadena de texto
        
        Args:
            text: Texto a limpiar
            max_length: Longitud máxima
            
        Returns:
            Texto limpio
        """
        try:
            if not isinstance(text, str):
                text = str(text)
            
            # Limpiar caracteres especiales
            text = text.strip()
            text = ' '.join(text.split())  # Normalizar espacios
            
            # Truncar si es necesario
            if max_length and len(text) > max_length:
                text = text[:max_length-3] + "..."
            
            return text
            
        except Exception:
            return ""
    
    @staticmethod
    def get_system_uptime() -> Dict[str, Any]:
        """
        Obtiene tiempo de actividad del sistema
        
        Returns:
            Diccionario con información de uptime
        """
        try:
            import psutil
            boot_time = psutil.boot_time()
            current_time = time.time()
            uptime_seconds = current_time - boot_time
            
            boot_datetime = datetime.fromtimestamp(boot_time)
            
            return {
                'boot_time': boot_datetime,
                'uptime_seconds': uptime_seconds,
                'uptime_formatted': SystemUtilities.format_duration(uptime_seconds),
                'boot_time_formatted': boot_datetime.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo uptime: {e}")
            return {
                'boot_time': None,
                'uptime_seconds': 0,
                'uptime_formatted': "Desconocido",
                'boot_time_formatted': "Desconocido"
            }

class SecurityUtilities:
    """Utilidades de seguridad"""
    
    @staticmethod
    def hash_string(text: str, algorithm: str = 'sha256') -> str:
        """
        Genera hash de una cadena
        
        Args:
            text: Texto a hashear
            algorithm: Algoritmo de hash
            
        Returns:
            Hash en hexadecimal
        """
        try:
            if algorithm == 'md5':
                hasher = hashlib.md5()
            elif algorithm == 'sha1':
                hasher = hashlib.sha1()
            elif algorithm == 'sha256':
                hasher = hashlib.sha256()
            else:
                raise ValueError(f"Algoritmo no soportado: {algorithm}")
            
            hasher.update(text.encode('utf-8'))
            return hasher.hexdigest()
            
        except Exception as e:
            logger.error(f"Error generando hash: {e}")
            return ""
    
    @staticmethod
    def encode_base64(text: str) -> str:
        """Codifica texto en base64"""
        try:
            return base64.b64encode(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Error codificando base64: {e}")
            return ""
    
    @staticmethod
    def decode_base64(encoded_text: str) -> str:
        """Decodifica texto de base64"""
        try:
            return base64.b64decode(encoded_text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Error decodificando base64: {e}")
            return ""
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitiza nombre de archivo
        
        Args:
            filename: Nombre de archivo
            
        Returns:
            Nombre sanitizado
        """
        try:
            import re
            # Remover caracteres no válidos
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            # Remover espacios múltiples
            filename = re.sub(r'\s+', ' ', filename)
            # Truncar si es muy largo
            if len(filename) > 255:
                name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
                max_name_len = 255 - len(ext) - 1
                filename = name[:max_name_len] + ('.' + ext if ext else '')
            
            return filename.strip()
            
        except Exception:
            return f"file_{int(time.time())}"

class FileUtilities:
    """Utilidades para manejo de archivos"""
    
    @staticmethod
    def ensure_directory(path: Union[str, Path]) -> bool:
        """
        Asegura que un directorio exista
        
        Args:
            path: Ruta del directorio
            
        Returns:
            True si el directorio existe o se creó exitosamente
        """
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Error creando directorio {path}: {e}")
            return False
    
    @staticmethod
    def get_file_size(file_path: Union[str, Path]) -> int:
        """
        Obtiene el tamaño de un archivo
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            Tamaño en bytes
        """
        try:
            return Path(file_path).stat().st_size
        except Exception:
            return 0
    
    @staticmethod
    def get_available_filename(base_path: Union[str, Path], extension: str = "") -> Path:
        """
        Obtiene un nombre de archivo disponible
        
        Args:
            base_path: Ruta base
            extension: Extensión del archivo
            
        Returns:
            Ruta del archivo disponible
        """
        try:
            base_path = Path(base_path)
            if extension and not extension.startswith('.'):
                extension = '.' + extension
            
            if extension:
                full_path = base_path.with_suffix(extension)
            else:
                full_path = base_path
            
            if not full_path.exists():
                return full_path
            
            counter = 1
            while True:
                if extension:
                    new_path = base_path.with_suffix(f"_{counter}{extension}")
                else:
                    new_path = base_path.parent / f"{base_path.name}_{counter}"
                
                if not new_path.exists():
                    return new_path
                
                counter += 1
                
        except Exception as e:
            logger.error(f"Error obteniendo nombre de archivo disponible: {e}")
            return Path(f"file_{int(time.time())}")
    
    @staticmethod
    def safe_delete_file(file_path: Union[str, Path]) -> bool:
        """
        Elimina un archivo de forma segura
        
        Args:
            file_path: Ruta del archivo
            
        Returns:
            True si se eliminó exitosamente
        """
        try:
            file_path = Path(file_path)
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando archivo {file_path}: {e}")
            return False

class PerformanceUtilities:
    """Utilidades de rendimiento"""
    
    @staticmethod
    def get_memory_usage() -> Dict[str, Any]:
        """
        Obtiene uso de memoria del proceso actual
        
        Returns:
            Diccionario con información de memoria
        """
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'rss': memory_info.rss,
                'vms': memory_info.vms,
                'rss_formatted': SystemUtilities.format_bytes(memory_info.rss),
                'vms_formatted': SystemUtilities.format_bytes(memory_info.vms),
                'percent': process.memory_percent()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo uso de memoria: {e}")
            return {
                'rss': 0,
                'vms': 0,
                'rss_formatted': "0 B",
                'vms_formatted': "0 B",
                'percent': 0.0
            }
    
    @staticmethod
    def trigger_garbage_collection() -> Dict[str, int]:
        """
        Ejecuta recolección de basura
        
        Returns:
            Estadísticas de recolección
        """
        try:
            collected = gc.collect()
            stats = {
                'collected': collected,
                'generation_0': len(gc.get_objects(0)),
                'generation_1': len(gc.get_objects(1)),
                'generation_2': len(gc.get_objects(2))
            }
            
            logger.debug(f"Recolección de basura: {collected} objetos liberados")
            return stats
            
        except Exception as e:
            logger.error(f"Error en recolección de basura: {e}")
            return {'collected': 0, 'generation_0': 0, 'generation_1': 0, 'generation_2': 0}

# Decoradores útiles
def timeout_decorator(timeout_seconds: int = SystemConfig.TASK_TIMEOUT):
    """
    Decorador para aplicar timeout a funciones
    
    Args:
        timeout_seconds: Timeout en segundos
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def target():
                try:
                    result = func(*args, **kwargs)
                    result_queue.put(result)
                except Exception as e:
                    exception_queue.put(e)
            
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout_seconds)
            
            if thread.is_alive():
                logger.warning(f"Timeout en función {func.__name__} después de {timeout_seconds}s")
                raise TimeoutError(f"Función {func.__name__} excedió el timeout de {timeout_seconds}s")
            
            if not exception_queue.empty():
                raise exception_queue.get()
            
            if not result_queue.empty():
                return result_queue.get()
            
            return None
        
        return wrapper
    return decorator

def retry_decorator(max_retries: int = 3, delay: float = 1.0, exceptions: Tuple = (Exception,)):
    """
    Decorador para reintentar funciones que fallan
    
    Args:
        max_retries: Número máximo de reintentos
        delay: Delay entre reintentos
        exceptions: Excepciones a capturar
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Intento {attempt + 1}/{max_retries + 1} falló para {func.__name__}: {e}")
                        time.sleep(delay * (2 ** attempt))  # Backoff exponencial
                    else:
                        logger.error(f"Todos los intentos fallaron para {func.__name__}: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator

def log_execution_time(func: Callable) -> Callable:
    """Decorador para medir tiempo de ejecución"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} ejecutado en {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} falló después de {execution_time:.3f}s: {e}")
            raise
    
    return wrapper

def cache_result(expiry_seconds: int = 300):
    """
    Decorador para cachear resultados de funciones
    
    Args:
        expiry_seconds: Tiempo de expiración del cache
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Crear clave del cache
            cache_key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()
            
            # Verificar si existe en cache y no ha expirado
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if current_time - timestamp < expiry_seconds:
                    logger.debug(f"Resultado de {func.__name__} obtenido del cache")
                    return result
            
            # Ejecutar función y cachear resultado
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            
            # Limpiar cache expirado
            expired_keys = [
                key for key, (_, timestamp) in cache.items()
                if current_time - timestamp >= expiry_seconds
            ]
            for key in expired_keys:
                del cache[key]
            
            return result
        
        return wrapper
    return decorator

def thread_safe(lock: threading.Lock = None):
    """
    Decorador para hacer funciones thread-safe
    
    Args:
        lock: Lock a usar (si no se provee, se crea uno nuevo)
    """
    if lock is None:
        lock = threading.Lock()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper
    return decorator

# Context managers útiles
@contextmanager
def timer_context(name: str = "Operation"):
    """Context manager para medir tiempo de ejecución"""
    start_time = time.time()
    try:
        yield
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"{name} completado en {elapsed_time:.3f}s")

@contextmanager
def suppress_errors(*exceptions):
    """Context manager para suprimir errores específicos"""
    try:
        yield
    except exceptions as e:
        logger.debug(f"Error suprimido: {e}")

# Validadores
class Validators:
    """Clase con validadores comunes"""
    
    @staticmethod
    def is_valid_percentage(value: Any) -> bool:
        """Valida si un valor es un porcentaje válido (0-100)"""
        try:
            num_value = float(value)
            return 0 <= num_value <= 100
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def is_valid_file_path(path: str) -> bool:
        """Valida si una ruta de archivo es válida"""
        try:
            Path(path)
            return True
        except (ValueError, OSError):
            return False
    
    @staticmethod
    def is_valid_ip_address(ip: str) -> bool:
        """Valida si una IP es válida"""
        try:
            import ipaddress
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def is_valid_port(port: Any) -> bool:
        """Valida si un puerto es válido"""
        try:
            port_num = int(port)
            return 1 <= port_num <= 65535
        except (ValueError, TypeError):
            return False

# Singleton para configuración global
class GlobalState:
    """Estado global de la aplicación (Singleton)"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.data = {}
            self._data_lock = threading.Lock()
            self._initialized = True
    
    def set(self, key: str, value: Any):
        """Establece un valor en el estado global"""
        with self._data_lock:
            self.data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor del estado global"""
        with self._data_lock:
            return self.data.get(key, default)
    
    def update(self, updates: Dict[str, Any]):
        """Actualiza múltiples valores"""
        with self._data_lock:
            self.data.update(updates)
    
    def clear(self):
        """Limpia el estado global"""
        with self._data_lock:
            self.data.clear()

# Funciones de inicialización del módulo
def initialize_utilities():
    """Inicializa las utilidades del sistema"""
    try:
        logger.info("Inicializando utilidades del sistema...")
        
        # Verificar disponibilidad de memoria
        memory_info = PerformanceUtilities.get_memory_usage()
        logger.debug(f"Uso de memoria inicial: {memory_info['rss_formatted']}")
        
        # Ejecutar recolección de basura inicial
        gc_stats = PerformanceUtilities.trigger_garbage_collection()
        logger.debug(f"Recolección de basura inicial: {gc_stats['collected']} objetos")
        
        # Obtener información de uptime
        uptime_info = SystemUtilities.get_system_uptime()
        logger.info(f"Sistema iniciado: {uptime_info['boot_time_formatted']}")
        logger.info(f"Uptime: {uptime_info['uptime_formatted']}")
        
        logger.info("Utilidades del sistema inicializadas correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando utilidades: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_utilities()