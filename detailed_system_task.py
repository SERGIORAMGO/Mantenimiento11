"""
Sistema de Monitoreo de PC - Módulo 5: Tarea de Análisis Detallado del Sistema
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Implementación de la tarea de análisis detallado con timeouts y WMI
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
import traceback
import socket
import platform
import subprocess
import os
import json

try:
    import psutil
    import wmi
    import win32api
    import win32con
    import win32security
    import win32net
    import win32netcon
    import win32file
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias WMI y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, SecurityUtilities, PerformanceUtilities,
    TimeoutError
)
from base_classes import BaseTask, TaskPriority, TaskStatus

# Logger para este módulo
logger = logging.getLogger(__name__)

class WMIConnectionManager:
    """Gestor de conexiones WMI con timeout y reconexión"""
    
    def __init__(self):
        self._connection = None
        self._lock = threading.Lock()
        self._last_connection_time = 0
        self._connection_timeout = SystemConfig.WMI_TIMEOUT
        
    @timeout_decorator(SystemConfig.WMI_TIMEOUT)
    def get_connection(self) -> Optional[wmi.WMI]:
        """
        Obtiene conexión WMI con timeout
        
        Returns:
            Conexión WMI o None si falla
        """
        with self._lock:
            try:
                current_time = time.time()
                
                # Verificar si necesitamos nueva conexión
                if (not self._connection or 
                    current_time - self._last_connection_time > 300):  # 5 minutos
                    
                    logger.debug("Estableciendo nueva conexión WMI...")
                    # Inicializar COM para el hilo actual si es necesario
                    try:
                        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    except pythoncom.com_error: # pylint: disable=no-member
                        # COM ya podría estar inicializado en este hilo (ej. si se llama múltiples veces)
                        logger.debug("COM ya inicializado en este hilo.")
                        pass
                    
                    self._connection = wmi.WMI()
                    self._last_connection_time = current_time
                    logger.debug("Conexión WMI establecida exitosamente")
                
                return self._connection
                
            except Exception as e:
                logger.exception("Error estableciendo conexión WMI.") # Usar logger.exception
                self._connection = None
                return None
    
    @timeout_decorator(SystemConfig.WMI_TIMEOUT)
    def query(self, wql_query: str, timeout: int = None) -> List[Any]:
        """
        Ejecuta consulta WMI con timeout
        
        Args:
            wql_query: Consulta WQL
            timeout: Timeout específico para esta consulta
            
        Returns:
            Lista de resultados
        """
        try:
            connection = self.get_connection()
            if not connection:
                raise Exception("No se pudo establecer conexión WMI")
            
            logger.debug(f"Ejecutando consulta WMI: {wql_query}")
            
            # Ejecutar consulta en hilo separado para control de timeout
            result_queue = threading.Queue()
            exception_queue = threading.Queue()
            
            def execute_query():
                try:
                    result = connection.query(wql_query)
                    result_queue.put(list(result))
                except Exception as e:
                    exception_queue.put(e)
            
            thread = threading.Thread(target=execute_query, daemon=True)
            thread.start()
            
            query_timeout = timeout or self._connection_timeout
            thread.join(query_timeout)
            
            if thread.is_alive():
                raise TimeoutError(f"Consulta WMI excedió timeout de {query_timeout}s")
            
            if not exception_queue.empty():
                raise exception_queue.get()
            
            if not result_queue.empty():
                results = result_queue.get()
                logger.debug(f"Consulta WMI completada: {len(results)} resultados")
                return results
            
            return []
            
        except Exception as e:
            logger.error(f"Error en consulta WMI '{wql_query}': {e}")
            return []
    
    def close_connection(self):
        """Cierra la conexión WMI"""
        with self._lock:
            if self._connection:
                try:
                    self._connection = None
                    logger.debug("Conexión WMI cerrada")
                except Exception as e:
                    logger.error(f"Error cerrando conexión WMI: {e}")

# Instancia global del gestor WMI
wmi_manager = WMIConnectionManager()

class DetailedSystemInfoTask(BaseTask):
    """Tarea para análisis detallado del sistema con timeouts y WMI"""
    
    def __init__(self, include_hardware: bool = True, 
                 include_software: bool = True,
                 include_network: bool = True,
                 include_security: bool = True,
                 include_performance: bool = True):
        """
        Inicializa la tarea de análisis detallado
        
        Args:
            include_hardware: Incluir información de hardware
            include_software: Incluir información de software
            include_network: Incluir información de red
            include_security: Incluir información de seguridad
            include_performance: Incluir métricas de rendimiento
        """
        super().__init__(
            name="Análisis Detallado del Sistema",
            description="Análisis completo del sistema con WMI y timeouts",
            priority=TaskPriority.HIGH,
            timeout=SystemConfig.TASK_TIMEOUT * 2  # Timeout extendido
        )
        
        self.include_hardware = include_hardware
        self.include_software = include_software
        self.include_network = include_network
        self.include_security = include_security
        self.include_performance = include_performance
        
        # Configurar secciones a procesar
        self.sections = []
        if include_hardware:
            self.sections.extend(['motherboard', 'processor', 'memory', 'storage', 'graphics'])
        if include_software:
            self.sections.extend(['operating_system', 'installed_programs', 'running_processes'])
        if include_network:
            self.sections.extend(['network_adapters', 'network_connections'])
        if include_security:
            self.sections.extend(['security_info', 'user_accounts'])
        if include_performance:
            self.sections.extend(['performance_counters'])
        
        self.total_sections = len(self.sections)
        self.current_section = 0
        
        logger.info(f"DetailedSystemInfoTask configurada con {self.total_sections} secciones")
    
    def execute(self) -> Dict[str, Any]:
        """
        Ejecuta el análisis detallado del sistema
        
        Returns:
            Diccionario con toda la información del sistema
        """
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for DetailedSystemInfoTask thread.")

            logger.info("Iniciando análisis detallado del sistema...")
            start_time = time.time()
            
            system_info = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'user': os.getenv('USERNAME', 'Unknown'),
                    'computer_name': socket.gethostname(),
                    'scan_type': 'detailed',
                    'sections_included': self.sections.copy()
                },
                'basic_info': {},
                'hardware': {},
                'software': {},
                'network': {},
                'security': {},
                'performance': {},
                'errors': []
            }
            
            # Información básica del sistema (siempre incluida)
            self._collect_basic_info(system_info)
            
            # Procesar cada sección
            for i, section in enumerate(self.sections):
                if self.is_cancelled():
                    logger.info("Análisis cancelado por el usuario")
                    break
                
                self.wait_if_paused()
                
                self.current_section = i + 1
                progress = (self.current_section / self.total_sections) * 100
                self.update_progress(progress, f"Analizando {section}...")
                
                try:
                    self._process_section(section, system_info)
                except Exception as e:
                    error_msg = f"Error procesando sección {section}: {str(e)}"
                    logger.error(error_msg)
                    system_info['errors'].append({
                        'section': section,
                        'error': error_msg,
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Finalizar información de escaneo
            end_time = time.time()
            system_info['scan_info']['end_time'] = datetime.now().isoformat()
            system_info['scan_info']['duration_seconds'] = end_time - start_time
            system_info['scan_info']['duration_formatted'] = SystemUtilities.format_duration(end_time - start_time)
            system_info['scan_info']['sections_processed'] = self.current_section
            system_info['scan_info']['errors_count'] = len(system_info['errors'])
            
            self.update_progress(100.0, "Análisis completado")
            
            logger.info(f"Análisis detallado completado en {system_info['scan_info']['duration_formatted']}")
            
            return system_info
            
        except Exception as e:
            logger.exception("Error crítico en análisis detallado.") # Usar logger.exception
            raise
        finally:
            if initialized_com:
                pythoncom.CoUninitialize()
                logger.debug("COM uninitialized for DetailedSystemInfoTask thread.")
    
    def _collect_basic_info(self, system_info: Dict[str, Any]):
        """Recopila información básica del sistema"""
        try:
            logger.debug("Recopilando información básica...")
            
            basic_info = {
                'hostname': socket.gethostname(),
                'platform': platform.platform(),
                'architecture': platform.architecture(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'user': os.getenv('USERNAME', 'Unknown'),
                'domain': os.getenv('USERDOMAIN', 'WORKGROUP'),
                'system_directory': os.getenv('SYSTEMROOT', 'C:\\Windows'),
                'temp_directory': os.getenv('TEMP', 'C:\\Temp')
            }
            
            # Información de Windows específica
            try:
                basic_info['windows_version'] = platform.win32_ver()
                basic_info['windows_edition'] = platform.win32_edition()
            except Exception as e:
                logger.debug(f"Error obteniendo versión de Windows: {e}")
            
            # Zona horaria
            try:
                import time
                basic_info['timezone'] = time.tzname
                basic_info['timezone_offset'] = time.timezone
            except Exception as e:
                logger.debug(f"Error obteniendo zona horaria: {e}")
            
            system_info['basic_info'] = basic_info
            
        except Exception as e:
            logger.error(f"Error recopilando información básica: {e}")
    
    def _process_section(self, section: str, system_info: Dict[str, Any]):
        """Procesa una sección específica del análisis"""
        try:
            if section == 'motherboard':
                self._collect_motherboard_info(system_info)
            elif section == 'processor':
                self._collect_processor_info(system_info)
            elif section == 'memory':
                self._collect_memory_info(system_info)
            elif section == 'storage':
                self._collect_storage_info(system_info)
            elif section == 'graphics':
                self._collect_graphics_info(system_info)
            elif section == 'operating_system':
                self._collect_os_info(system_info)
            elif section == 'installed_programs':
                self._collect_installed_programs(system_info)
            elif section == 'running_processes':
                self._collect_running_processes(system_info)
            elif section == 'network_adapters':
                self._collect_network_adapters(system_info)
            elif section == 'network_connections':
                self._collect_network_connections(system_info)
            elif section == 'security_info':
                self._collect_security_info(system_info)
            elif section == 'user_accounts':
                self._collect_user_accounts(system_info)
            elif section == 'performance_counters':
                self._collect_performance_counters(system_info)
            else:
                logger.warning(f"Sección desconocida: {section}")
                
        except Exception as e:
            logger.error(f"Error procesando sección {section}: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_motherboard_info(self, system_info: Dict[str, Any]):
        """Recopila información de la placa madre"""
        try:
            logger.debug("Recopilando información de placa madre...")
            
            motherboard_info = {}
            
            # Información de BIOS/UEFI
            bios_results = wmi_manager.query("SELECT * FROM Win32_BIOS")
            if bios_results:
                bios = bios_results[0]
                motherboard_info['bios'] = {
                    'manufacturer': getattr(bios, 'Manufacturer', 'Unknown'),
                    'version': getattr(bios, 'Version', 'Unknown'),
                    'release_date': getattr(bios, 'ReleaseDate', 'Unknown'),
                    'serial_number': getattr(bios, 'SerialNumber', 'Unknown'),
                    'smbios_version': getattr(bios, 'SMBIOSBIOSVersion', 'Unknown')
                }
            
            # Información de placa base
            board_results = wmi_manager.query("SELECT * FROM Win32_BaseBoard")
            if board_results:
                board = board_results[0]
                motherboard_info['motherboard'] = {
                    'manufacturer': getattr(board, 'Manufacturer', 'Unknown'),
                    'product': getattr(board, 'Product', 'Unknown'),
                    'version': getattr(board, 'Version', 'Unknown'),
                    'serial_number': getattr(board, 'SerialNumber', 'Unknown')
                }
            
            # Información del sistema
            system_results = wmi_manager.query("SELECT * FROM Win32_ComputerSystem")
            if system_results:
                system = system_results[0]
                motherboard_info['system'] = {
                    'manufacturer': getattr(system, 'Manufacturer', 'Unknown'),
                    'model': getattr(system, 'Model', 'Unknown'),
                    'system_type': getattr(system, 'SystemType', 'Unknown'),
                    'total_physical_memory': getattr(system, 'TotalPhysicalMemory', 0)
                }
            
            system_info['hardware']['motherboard'] = motherboard_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de placa madre: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_processor_info(self, system_info: Dict[str, Any]):
        """Recopila información del procesador"""
        try:
            logger.debug("Recopilando información del procesador...")
            
            processor_info = {}
            
            # Información del procesador via WMI
            cpu_results = wmi_manager.query("SELECT * FROM Win32_Processor")
            if cpu_results:
                processors = []
                for cpu in cpu_results:
                    proc_data = {
                        'name': getattr(cpu, 'Name', 'Unknown'),
                        'manufacturer': getattr(cpu, 'Manufacturer', 'Unknown'),
                        'architecture': getattr(cpu, 'Architecture', 'Unknown'),
                        'family': getattr(cpu, 'Family', 'Unknown'),
                        'model': getattr(cpu, 'Model', 'Unknown'),
                        'stepping': getattr(cpu, 'Stepping', 'Unknown'),
                        'max_clock_speed': getattr(cpu, 'MaxClockSpeed', 0),
                        'current_clock_speed': getattr(cpu, 'CurrentClockSpeed', 0),
                        'cores': getattr(cpu, 'NumberOfCores', 0),
                        'logical_processors': getattr(cpu, 'NumberOfLogicalProcessors', 0),
                        'l2_cache_size': getattr(cpu, 'L2CacheSize', 0),
                        'l3_cache_size': getattr(cpu, 'L3CacheSize', 0),
                        'voltage': getattr(cpu, 'CurrentVoltage', 0),
                        'socket_designation': getattr(cpu, 'SocketDesignation', 'Unknown')
                    }
                    
                    # Formatear frecuencias
                    if proc_data['max_clock_speed']:
                        proc_data['max_clock_speed_formatted'] = SystemUtilities.format_frequency(
                            proc_data['max_clock_speed'] * 1_000_000
                        )
                    
                    if proc_data['current_clock_speed']:
                        proc_data['current_clock_speed_formatted'] = SystemUtilities.format_frequency(
                            proc_data['current_clock_speed'] * 1_000_000
                        )
                    
                    processors.append(proc_data)
                
                processor_info['processors'] = processors
            
            # Información adicional con psutil
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                cpu_freq = psutil.cpu_freq()
                cpu_times = psutil.cpu_times()
                
                processor_info['current_usage'] = {
                    'cpu_percent': cpu_percent,
                    'frequency_current': cpu_freq.current if cpu_freq else 0,
                    'frequency_min': cpu_freq.min if cpu_freq else 0,
                    'frequency_max': cpu_freq.max if cpu_freq else 0,
                    'times': {
                        'user': cpu_times.user,
                        'system': cpu_times.system,
                        'idle': cpu_times.idle,
                        'interrupt': getattr(cpu_times, 'interrupt', 0),
                        'dpc': getattr(cpu_times, 'dpc', 0)
                    }
                }
                
            except Exception as e:
                logger.debug(f"Error obteniendo información adicional de CPU: {e}")
            
            system_info['hardware']['processor'] = processor_info
            
        except Exception as e:
            logger.error(f"Error recopilando información del procesador: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_memory_info(self, system_info: Dict[str, Any]):
        """Recopila información de memoria"""
        try:
            logger.debug("Recopilando información de memoria...")
            
            memory_info = {}
            
            # Módulos de memoria físicos
            memory_results = wmi_manager.query("SELECT * FROM Win32_PhysicalMemory")
            if memory_results:
                memory_modules = []
                total_capacity = 0
                
                for memory in memory_results:
                    capacity = getattr(memory, 'Capacity', 0)
                    if isinstance(capacity, str):
                        capacity = int(capacity) if capacity.isdigit() else 0
                    
                    module_data = {
                        'capacity': capacity,
                        'capacity_formatted': SystemUtilities.format_bytes(capacity),
                        'speed': getattr(memory, 'Speed', 0),
                        'manufacturer': getattr(memory, 'Manufacturer', 'Unknown'),
                        'part_number': getattr(memory, 'PartNumber', 'Unknown'),
                        'serial_number': getattr(memory, 'SerialNumber', 'Unknown'),
                        'memory_type': getattr(memory, 'MemoryType', 'Unknown'),
                        'form_factor': getattr(memory, 'FormFactor', 'Unknown'),
                        'device_locator': getattr(memory, 'DeviceLocator', 'Unknown'),
                        'bank_label': getattr(memory, 'BankLabel', 'Unknown')
                    }
                    
                    memory_modules.append(module_data)
                    total_capacity += capacity
                
                memory_info['physical_memory'] = {
                    'modules': memory_modules,
                    'total_capacity': total_capacity,
                    'total_capacity_formatted': SystemUtilities.format_bytes(total_capacity),
                    'module_count': len(memory_modules)
                }
            
            # Información de memoria virtual
            try:
                virtual_memory = psutil.virtual_memory()
                swap_memory = psutil.swap_memory()
                
                memory_info['current_usage'] = {
                    'virtual_memory': {
                        'total': virtual_memory.total,
                        'available': virtual_memory.available,
                        'used': virtual_memory.used,
                        'free': virtual_memory.free,
                        'percent': virtual_memory.percent,
                        'total_formatted': SystemUtilities.format_bytes(virtual_memory.total),
                        'available_formatted': SystemUtilities.format_bytes(virtual_memory.available),
                        'used_formatted': SystemUtilities.format_bytes(virtual_memory.used)
                    },
                    'swap_memory': {
                        'total': swap_memory.total,
                        'used': swap_memory.used,
                        'free': swap_memory.free,
                        'percent': swap_memory.percent,
                        'total_formatted': SystemUtilities.format_bytes(swap_memory.total),
                        'used_formatted': SystemUtilities.format_bytes(swap_memory.used)
                    }
                }
                
            except Exception as e:
                logger.debug(f"Error obteniendo uso actual de memoria: {e}")
            
            system_info['hardware']['memory'] = memory_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de memoria: {e}")
            raise
    
    @timeout_decorator(45)
    def _collect_storage_info(self, system_info: Dict[str, Any]):
        """Recopila información de almacenamiento"""
        try:
            logger.debug("Recopilando información de almacenamiento...")
            
            storage_info = {}
            
            # Discos físicos
            disk_results = wmi_manager.query("SELECT * FROM Win32_DiskDrive")
            if disk_results:
                physical_disks = []
                
                for disk in disk_results:
                    size = getattr(disk, 'Size', 0)
                    if isinstance(size, str):
                        size = int(size) if size.isdigit() else 0
                    
                    disk_data = {
                        'model': getattr(disk, 'Model', 'Unknown'),
                        'manufacturer': getattr(disk, 'Manufacturer', 'Unknown'),
                        'serial_number': getattr(disk, 'SerialNumber', 'Unknown'),
                        'size': size,
                        'size_formatted': SystemUtilities.format_bytes(size),
                        'interface_type': getattr(disk, 'InterfaceType', 'Unknown'),
                        'media_type': getattr(disk, 'MediaType', 'Unknown'),
                        'status': getattr(disk, 'Status', 'Unknown'),
                        'device_id': getattr(disk, 'DeviceID', 'Unknown')
                    }
                    
                    physical_disks.append(disk_data)
                
                storage_info['physical_disks'] = physical_disks
            
            # Particiones y volúmenes lógicos
            try:
                disk_usage = []
                disk_partitions = psutil.disk_partitions()
                
                for partition in disk_partitions:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        
                        partition_data = {
                            'device': partition.device,
                            'mountpoint': partition.mountpoint,
                            'filesystem': partition.fstype,
                            'total': usage.total,
                            'used': usage.used,
                            'free': usage.free,
                            'percent': (usage.used / usage.total) * 100 if usage.total > 0 else 0,
                            'total_formatted': SystemUtilities.format_bytes(usage.total),
                            'used_formatted': SystemUtilities.format_bytes(usage.used),
                            'free_formatted': SystemUtilities.format_bytes(usage.free)
                        }
                        
                        disk_usage.append(partition_data)
                        
                    except PermissionError:
                        # Algunos dispositivos pueden no ser accesibles
                        continue
                
                storage_info['disk_usage'] = disk_usage
                
            except Exception as e:
                logger.debug(f"Error obteniendo uso de discos: {e}")
            
            # Información de volúmenes lógicos via WMI
            volume_results = wmi_manager.query("SELECT * FROM Win32_LogicalDisk")
            if volume_results:
                logical_disks = []
                
                for volume in volume_results:
                    size = getattr(volume, 'Size', 0)
                    free_space = getattr(volume, 'FreeSpace', 0)
                    
                    if isinstance(size, str):
                        size = int(size) if size.isdigit() else 0
                    if isinstance(free_space, str):
                        free_space = int(free_space) if free_space.isdigit() else 0
                    
                    used_space = size - free_space if size > 0 else 0
                    
                    volume_data = {
                        'device_id': getattr(volume, 'DeviceID', 'Unknown'),
                        'description': getattr(volume, 'Description', 'Unknown'),
                        'file_system': getattr(volume, 'FileSystem', 'Unknown'),
                        'volume_name': getattr(volume, 'VolumeName', ''),
                        'size': size,
                        'free_space': free_space,
                        'used_space': used_space,
                        'size_formatted': SystemUtilities.format_bytes(size),
                        'free_formatted': SystemUtilities.format_bytes(free_space),
                        'used_formatted': SystemUtilities.format_bytes(used_space),
                        'percent_used': (used_space / size) * 100 if size > 0 else 0
                    }
                    
                    logical_disks.append(volume_data)
                
                storage_info['logical_disks'] = logical_disks
            
            system_info['hardware']['storage'] = storage_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de almacenamiento: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_graphics_info(self, system_info: Dict[str, Any]):
        """Recopila información de tarjetas gráficas"""
        try:
            logger.debug("Recopilando información de gráficos...")
            
            graphics_info = {}
            
            # Adaptadores de video
            video_results = wmi_manager.query("SELECT * FROM Win32_VideoController")
            if video_results:
                video_adapters = []
                
                for adapter in video_results:
                    adapter_ram = getattr(adapter, 'AdapterRAM', 0)
                    if isinstance(adapter_ram, str):
                        adapter_ram = int(adapter_ram) if adapter_ram.isdigit() else 0
                    
                    adapter_data = {
                        'name': getattr(adapter, 'Name', 'Unknown'),
                        'adapter_type': getattr(adapter, 'VideoProcessor', 'Unknown'),
                        'adapter_ram': adapter_ram,
                        'adapter_ram_formatted': SystemUtilities.format_bytes(adapter_ram),
                        'driver_version': getattr(adapter, 'DriverVersion', 'Unknown'),
                        'driver_date': getattr(adapter, 'DriverDate', 'Unknown'),
                        'video_mode_description': getattr(adapter, 'VideoModeDescription', 'Unknown'),
                        'current_horizontal_resolution': getattr(adapter, 'CurrentHorizontalResolution', 0),
                        'current_vertical_resolution': getattr(adapter, 'CurrentVerticalResolution', 0),
                        'current_refresh_rate': getattr(adapter, 'CurrentRefreshRate', 0),
                        'status': getattr(adapter, 'Status', 'Unknown'),
                        'availability': getattr(adapter, 'Availability', 'Unknown')
                    }
                    
                    video_adapters.append(adapter_data)
                
                graphics_info['video_adapters'] = video_adapters
            
            # Monitores
            monitor_results = wmi_manager.query("SELECT * FROM Win32_DesktopMonitor")
            if monitor_results:
                monitors = []
                
                for monitor in monitor_results:
                    monitor_data = {
                        'name': getattr(monitor, 'Name', 'Unknown'),
                        'description': getattr(monitor, 'Description', 'Unknown'),
                        'monitor_type': getattr(monitor, 'MonitorType', 'Unknown'),
                        'monitor_manufacturer': getattr(monitor, 'MonitorManufacturer', 'Unknown'),
                        'screen_width': getattr(monitor, 'ScreenWidth', 0),
                        'screen_height': getattr(monitor, 'ScreenHeight', 0),
                        'status': getattr(monitor, 'Status', 'Unknown')
                    }
                    
                    monitors.append(monitor_data)
                
                graphics_info['monitors'] = monitors
            
            system_info['hardware']['graphics'] = graphics_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de gráficos: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_os_info(self, system_info: Dict[str, Any]):
        """Recopila información del sistema operativo"""
        try:
            logger.debug("Recopilando información del sistema operativo...")
            
            os_info = {}
            
            # Información del SO via WMI
            os_results = wmi_manager.query("SELECT * FROM Win32_OperatingSystem")
            if os_results:
                os_data = os_results[0]
                
                total_memory = getattr(os_data, 'TotalVisibleMemorySize', 0)
                free_memory = getattr(os_data, 'FreePhysicalMemory', 0)
                
                if isinstance(total_memory, str):
                    total_memory = int(total_memory) * 1024 if total_memory.isdigit() else 0
                if isinstance(free_memory, str):
                    free_memory = int(free_memory) * 1024 if free_memory.isdigit() else 0
                
                os_info['operating_system'] = {
                    'name': getattr(os_data, 'Name', 'Unknown').split('|')[0],
                    'version': getattr(os_data, 'Version', 'Unknown'),
                    'build_number': getattr(os_data, 'BuildNumber', 'Unknown'),
                    'service_pack': getattr(os_data, 'ServicePackMajorVersion', 'Unknown'),
                    'architecture': getattr(os_data, 'OSArchitecture', 'Unknown'),
                    'install_date': getattr(os_data, 'InstallDate', 'Unknown'),
                    'last_boot_time': getattr(os_data, 'LastBootUpTime', 'Unknown'),
                    'system_directory': getattr(os_data, 'SystemDirectory', 'Unknown'),
                    'windows_directory': getattr(os_data, 'WindowsDirectory', 'Unknown'),
                    'registered_user': getattr(os_data, 'RegisteredUser', 'Unknown'),
                    'organization': getattr(os_data, 'Organization', 'Unknown'),
                    'serial_number': getattr(os_data, 'SerialNumber', 'Unknown'),
                    'total_memory': total_memory,
                    'free_memory': free_memory,
                    'total_memory_formatted': SystemUtilities.format_bytes(total_memory),
                    'free_memory_formatted': SystemUtilities.format_bytes(free_memory)
                }
            
            # Información adicional del sistema
            try:
                uptime_info = SystemUtilities.get_system_uptime()
                os_info['uptime'] = uptime_info
                
            except Exception as e:
                logger.debug(f"Error obteniendo uptime: {e}")
            
            # Variables de entorno importantes
            try:
                env_vars = {
                    'PATH': os.getenv('PATH', ''),
                    'PROCESSOR_ARCHITECTURE': os.getenv('PROCESSOR_ARCHITECTURE', ''),
                    'PROCESSOR_IDENTIFIER': os.getenv('PROCESSOR_IDENTIFIER', ''),
                    'NUMBER_OF_PROCESSORS': os.getenv('NUMBER_OF_PROCESSORS', ''),
                    'SYSTEMROOT': os.getenv('SYSTEMROOT', ''),
                    'PROGRAMFILES': os.getenv('PROGRAMFILES', ''),
                    'PROGRAMFILES(X86)': os.getenv('PROGRAMFILES(X86)', ''),
                    'USERPROFILE': os.getenv('USERPROFILE', ''),
                    'APPDATA': os.getenv('APPDATA', ''),
                    'TEMP': os.getenv('TEMP', ''),
                    'TMP': os.getenv('TMP', '')
                }
                
                os_info['environment_variables'] = {k: v for k, v in env_vars.items() if v}
                
            except Exception as e:
                logger.debug(f"Error obteniendo variables de entorno: {e}")
            
            system_info['software']['operating_system'] = os_info
            
        except Exception as e:
            logger.error(f"Error recopilando información del SO: {e}")
            raise
    
    @timeout_decorator(60)
    def _collect_installed_programs(self, system_info: Dict[str, Any]):
        """Recopila información de programas instalados"""
        try:
            logger.debug("Recopilando información de programas instalados...")
            
            programs_info = {}
            
            # Programas instalados via WMI
            product_results = wmi_manager.query("SELECT * FROM Win32_Product")
            if product_results:
                installed_programs = []
                
                for product in product_results:
                    program_data = {
                        'name': getattr(product, 'Name', 'Unknown'),
                        'version': getattr(product, 'Version', 'Unknown'),
                        'vendor': getattr(product, 'Vendor', 'Unknown'),
                        'install_date': getattr(product, 'InstallDate', 'Unknown'),
                        'install_location': getattr(product, 'InstallLocation', 'Unknown'),
                        'identifying_number': getattr(product, 'IdentifyingNumber', 'Unknown'),
                        'description': getattr(product, 'Description', '')
                    }
                    
                    installed_programs.append(program_data)
                
                programs_info['installed_programs'] = installed_programs
                programs_info['total_programs'] = len(installed_programs)
            
            # Servicios del sistema
            service_results = wmi_manager.query("SELECT * FROM Win32_Service")
            if service_results:
                services = []
                service_stats = {'running': 0, 'stopped': 0, 'auto': 0, 'manual': 0, 'disabled': 0}
                
                for service in service_results:
                    state = getattr(service, 'State', 'Unknown')
                    start_mode = getattr(service, 'StartMode', 'Unknown')
                    
                    service_data = {
                        'name': getattr(service, 'Name', 'Unknown'),
                        'display_name': getattr(service, 'DisplayName', 'Unknown'),
                        'description': getattr(service, 'Description', ''),
                        'state': state,
                        'start_mode': start_mode,
                        'path_name': getattr(service, 'PathName', 'Unknown'),
                        'service_type': getattr(service, 'ServiceType', 'Unknown'),
                        'started': getattr(service, 'Started', False)
                    }
                    
                    services.append(service_data)
                    
                    # Actualizar estadísticas
                    if state.lower() == 'running':
                        service_stats['running'] += 1
                    elif state.lower() == 'stopped':
                        service_stats['stopped'] += 1
                    
                    if start_mode.lower() == 'auto':
                        service_stats['auto'] += 1
                    elif start_mode.lower() == 'manual':
                        service_stats['manual'] += 1
                    elif start_mode.lower() == 'disabled':
                        service_stats['disabled'] += 1
                
                programs_info['services'] = services
                programs_info['service_statistics'] = service_stats
                programs_info['total_services'] = len(services)
            
            system_info['software']['programs'] = programs_info
            
        except Exception as e:
            logger.error(f"Error recopilando programas instalados: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_running_processes(self, system_info: Dict[str, Any]):
        """Recopila información de procesos en ejecución"""
        try:
            logger.debug("Recopilando información de procesos...")
            
            processes_info = {}
            
            try:
                processes = []
                total_memory = 0
                total_cpu = 0
                
                for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent', 
                                               'create_time', 'status', 'username']):
                    try:
                        pinfo = proc.info
                        memory_mb = pinfo['memory_info'].rss / (1024 * 1024) if pinfo['memory_info'] else 0
                        
                        process_data = {
                            'pid': pinfo['pid'],
                            'name': pinfo['name'],
                            'memory_mb': round(memory_mb, 2),
                            'memory_formatted': SystemUtilities.format_bytes(pinfo['memory_info'].rss if pinfo['memory_info'] else 0),
                            'cpu_percent': pinfo['cpu_percent'] or 0,
                            'status': pinfo['status'],
                            'username': pinfo['username'] or 'Unknown',
                            'create_time': datetime.fromtimestamp(pinfo['create_time']).isoformat() if pinfo['create_time'] else 'Unknown'
                        }
                        
                        processes.append(process_data)
                        total_memory += memory_mb
                        total_cpu += pinfo['cpu_percent'] or 0
                        
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        # Proceso terminó o sin permisos
                        continue
                
                processes_info['running_processes'] = processes
                processes_info['process_count'] = len(processes)
                processes_info['total_memory_mb'] = round(total_memory, 2)
                processes_info['total_memory_formatted'] = SystemUtilities.format_bytes(total_memory * 1024 * 1024)
                processes_info['average_cpu_percent'] = round(total_cpu / len(processes), 2) if processes else 0
                
            except Exception as e:
                logger.debug(f"Error obteniendo procesos con psutil: {e}")
            
            system_info['software']['processes'] = processes_info
            
        except Exception as e:
            logger.error(f"Error recopilando procesos: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_network_adapters(self, system_info: Dict[str, Any]):
        """Recopila información de adaptadores de red"""
        try:
            logger.debug("Recopilando información de red...")
            
            network_info = {}
            
            # Adaptadores de red via WMI
            adapter_results = wmi_manager.query("SELECT * FROM Win32_NetworkAdapter WHERE NetEnabled=True")
            if adapter_results:
                network_adapters = []
                
                for adapter in adapter_results:
                    adapter_data = {
                        'name': getattr(adapter, 'Name', 'Unknown'),
                        'description': getattr(adapter, 'Description', 'Unknown'),
                        'mac_address': getattr(adapter, 'MACAddress', 'Unknown'),
                        'manufacturer': getattr(adapter, 'Manufacturer', 'Unknown'),
                        'adapter_type': getattr(adapter, 'AdapterType', 'Unknown'),
                        'speed': getattr(adapter, 'Speed', 0),
                        'net_enabled': getattr(adapter, 'NetEnabled', False),
                        'physical_adapter': getattr(adapter, 'PhysicalAdapter', False),
                        'device_id': getattr(adapter, 'DeviceID', 'Unknown')
                    }
                    
                    if adapter_data['speed']:
                        adapter_data['speed_formatted'] = SystemUtilities.format_frequency(adapter_data['speed'])
                    
                    network_adapters.append(adapter_data)
                
                network_info['network_adapters'] = network_adapters
            
            # Configuración de red via psutil
            try:
                network_stats = psutil.net_io_counters(pernic=True)
                if_addrs = psutil.net_if_addrs()
                if_stats = psutil.net_if_stats()
                
                interface_details = {}
                
                for interface_name, addrs in if_addrs.items():
                    interface_info = {
                        'addresses': [],
                        'statistics': {},
                        'status': {}
                    }
                    
                    # Direcciones
                    for addr in addrs:
                        addr_info = {
                            'family': str(addr.family),
                            'address': addr.address,
                            'netmask': addr.netmask,
                            'broadcast': addr.broadcast
                        }
                        interface_info['addresses'].append(addr_info)
                    
                    # Estadísticas
                    if interface_name in network_stats:
                        stats = network_stats[interface_name]
                        interface_info['statistics'] = {
                            'bytes_sent': stats.bytes_sent,
                            'bytes_recv': stats.bytes_recv,
                            'packets_sent': stats.packets_sent,
                            'packets_recv': stats.packets_recv,
                            'bytes_sent_formatted': SystemUtilities.format_bytes(stats.bytes_sent),
                            'bytes_recv_formatted': SystemUtilities.format_bytes(stats.bytes_recv)
                        }
                    
                    # Estado
                    if interface_name in if_stats:
                        stat = if_stats[interface_name]
                        interface_info['status'] = {
                            'is_up': stat.isup,
                            'duplex': str(stat.duplex),
                            'speed': stat.speed,
                            'mtu': stat.mtu
                        }
                    
                    interface_details[interface_name] = interface_info
                
                network_info['interface_details'] = interface_details
                
            except Exception as e:
                logger.debug(f"Error obteniendo detalles de interfaces: {e}")
            
            system_info['network']['adapters'] = network_info
            
        except Exception as e:
            logger.error(f"Error recopilando adaptadores de red: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_network_connections(self, system_info: Dict[str, Any]):
        """Recopila información de conexiones de red"""
        try:
            logger.debug("Recopilando conexiones de red...")
            
            connections_info = {}
            
            try:
                connections = psutil.net_connections(kind='inet')
                
                active_connections = []
                connection_stats = {'established': 0, 'listen': 0, 'time_wait': 0, 'other': 0}
                
                for conn in connections:
                    try:
                        # Obtener información del proceso
                        process_name = 'Unknown'
                        if conn.pid:
                            try:
                                process = psutil.Process(conn.pid)
                                process_name = process.name()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        
                        conn_data = {
                            'local_address': f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else 'Unknown',
                            'remote_address': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else 'Unknown',
                            'status': conn.status,
                            'pid': conn.pid or 0,
                            'process_name': process_name,
                            'family': str(conn.family),
                            'type': str(conn.type)
                        }
                        
                        active_connections.append(conn_data)
                        
                        # Actualizar estadísticas
                        status = conn.status.lower() if conn.status else 'unknown'
                        if 'established' in status:
                            connection_stats['established'] += 1
                        elif 'listen' in status:
                            connection_stats['listen'] += 1
                        elif 'time_wait' in status:
                            connection_stats['time_wait'] += 1
                        else:
                            connection_stats['other'] += 1
                            
                    except Exception as e:
                        logger.debug(f"Error procesando conexión: {e}")
                        continue
                
                connections_info['active_connections'] = active_connections
                connections_info['connection_statistics'] = connection_stats
                connections_info['total_connections'] = len(active_connections)
                
            except Exception as e:
                logger.debug(f"Error obteniendo conexiones: {e}")
            
            system_info['network']['connections'] = connections_info
            
        except Exception as e:
            logger.error(f"Error recopilando conexiones de red: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_security_info(self, system_info: Dict[str, Any]):
        """Recopila información de seguridad"""
        try:
            logger.debug("Recopilando información de seguridad...")
            
            security_info = {}
            
            # Información de Windows Defender
            try:
                antivirus_results = wmi_manager.query("SELECT * FROM AntiVirusProduct", timeout=15)
                if antivirus_results:
                    antivirus_products = []
                    for av in antivirus_results:
                        av_data = {
                            'display_name': getattr(av, 'displayName', 'Unknown'),
                            'instance_guid': getattr(av, 'instanceGuid', 'Unknown'),
                            'path_to_signed_product_exe': getattr(av, 'pathToSignedProductExe', 'Unknown'),
                            'path_to_signed_reporting_exe': getattr(av, 'pathToSignedReportingExe', 'Unknown'),
                            'product_state': getattr(av, 'productState', 'Unknown')
                        }
                        antivirus_products.append(av_data)
                    
                    security_info['antivirus_products'] = antivirus_products
                    
            except Exception as e:
                logger.debug(f"Error obteniendo información de antivirus: {e}")
            
            # Configuración de firewall
            try:
                firewall_results = wmi_manager.query("SELECT * FROM Win32_SystemDriver WHERE Name='mpsdrv'")
                if firewall_results:
                    firewall = firewall_results[0]
                    security_info['firewall'] = {
                        'name': getattr(firewall, 'Name', 'Unknown'),
                        'state': getattr(firewall, 'State', 'Unknown'),
                        'started': getattr(firewall, 'Started', False),
                        'start_mode': getattr(firewall, 'StartMode', 'Unknown')
                    }
                    
            except Exception as e:
                logger.debug(f"Error obteniendo información de firewall: {e}")
            
            # Configuración de UAC
            try:
                import winreg
                
                uac_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
                )
                
                uac_enabled = winreg.QueryValueEx(uac_key, "EnableLUA")[0]
                consent_prompt = winreg.QueryValueEx(uac_key, "ConsentPromptBehaviorAdmin")[0]
                
                security_info['uac'] = {
                    'enabled': bool(uac_enabled),
                    'consent_prompt_behavior': consent_prompt,
                    'description': 'User Account Control configuration'
                }
                
                winreg.CloseKey(uac_key)
                
            except Exception as e:
                logger.debug(f"Error obteniendo configuración UAC: {e}")
            
            system_info['security'] = security_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de seguridad: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_user_accounts(self, system_info: Dict[str, Any]):
        """Recopila información de cuentas de usuario"""
        try:
            logger.debug("Recopilando información de usuarios...")
            
            users_info = {}
            
            # Cuentas de usuario via WMI
            user_results = wmi_manager.query("SELECT * FROM Win32_UserAccount WHERE LocalAccount=True")
            if user_results:
                user_accounts = []
                
                for user in user_results:
                    user_data = {
                        'name': getattr(user, 'Name', 'Unknown'),
                        'full_name': getattr(user, 'FullName', ''),
                        'description': getattr(user, 'Description', ''),
                        'disabled': getattr(user, 'Disabled', False),
                        'locked_out': getattr(user, 'LockedOut', False),
                        'password_changeable': getattr(user, 'PasswordChangeable', False),
                        'password_expires': getattr(user, 'PasswordExpires', False),
                        'password_required': getattr(user, 'PasswordRequired', False),
                        'sid': getattr(user, 'SID', 'Unknown'),
                        'account_type': getattr(user, 'AccountType', 'Unknown')
                    }
                    
                    user_accounts.append(user_data)
                
                users_info['local_users'] = user_accounts
                users_info['total_local_users'] = len(user_accounts)
            
            # Grupos locales
            group_results = wmi_manager.query("SELECT * FROM Win32_Group WHERE LocalAccount=True")
            if group_results:
                local_groups = []
                
                for group in group_results:
                    group_data = {
                        'name': getattr(group, 'Name', 'Unknown'),
                        'description': getattr(group, 'Description', ''),
                        'sid': getattr(group, 'SID', 'Unknown'),
                        'local_account': getattr(group, 'LocalAccount', False)
                    }
                    
                    local_groups.append(group_data)
                
                users_info['local_groups'] = local_groups
                users_info['total_local_groups'] = len(local_groups)
            
            # Usuario actual
            try:
                import getpass
                current_user = getpass.getuser()
                users_info['current_user'] = {
                    'username': current_user,
                    'domain': os.getenv('USERDOMAIN', 'WORKGROUP'),
                    'profile_path': os.getenv('USERPROFILE', ''),
                    'home_drive': os.getenv('HOMEDRIVE', ''),
                    'home_path': os.getenv('HOMEPATH', '')
                }
                
            except Exception as e:
                logger.debug(f"Error obteniendo usuario actual: {e}")
            
            system_info['security']['users'] = users_info
            
        except Exception as e:
            logger.error(f"Error recopilando información de usuarios: {e}")
            raise
    
    @timeout_decorator(30)
    def _collect_performance_counters(self, system_info: Dict[str, Any]):
        """Recopila contadores de rendimiento"""
        try:
            logger.debug("Recopilando contadores de rendimiento...")
            
            performance_info = {}
            
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
                cpu_freq = psutil.cpu_freq()
                cpu_times = psutil.cpu_times_percent(interval=1)
                
                performance_info['cpu'] = {
                    'usage_percent': psutil.cpu_percent(interval=1),
                    'usage_per_core': cpu_percent,
                    'core_count': psutil.cpu_count(logical=False),
                    'logical_count': psutil.cpu_count(logical=True),
                    'frequency': {
                        'current': cpu_freq.current if cpu_freq else 0,
                        'min': cpu_freq.min if cpu_freq else 0,
                        'max': cpu_freq.max if cpu_freq else 0
                    },
                    'times_percent': {
                        'user': cpu_times.user,
                        'system': cpu_times.system,
                        'idle': cpu_times.idle,
                        'interrupt': getattr(cpu_times, 'interrupt', 0),
                        'dpc': getattr(cpu_times, 'dpc', 0)
                    }
                }
                
                # Memoria
                virtual_memory = psutil.virtual_memory()
                swap_memory = psutil.swap_memory()
                
                performance_info['memory'] = {
                    'virtual': {
                        'total': virtual_memory.total,
                        'available': virtual_memory.available,
                        'percent': virtual_memory.percent,
                        'used': virtual_memory.used,
                        'free': virtual_memory.free
                    },
                    'swap': {
                        'total': swap_memory.total,
                        'used': swap_memory.used,
                        'free': swap_memory.free,
                        'percent': swap_memory.percent
                    }
                }
                
                # Disco
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    performance_info['disk'] = {
                        'read_count': disk_io.read_count,
                        'write_count': disk_io.write_count,
                        'read_bytes': disk_io.read_bytes,
                        'write_bytes': disk_io.write_bytes,
                        'read_time': disk_io.read_time,
                        'write_time': disk_io.write_time,
                        'read_bytes_formatted': SystemUtilities.format_bytes(disk_io.read_bytes),
                        'write_bytes_formatted': SystemUtilities.format_bytes(disk_io.write_bytes)
                    }
                
                # Red
                net_io = psutil.net_io_counters()
                if net_io:
                    performance_info['network'] = {
                        'bytes_sent': net_io.bytes_sent,
                        'bytes_recv': net_io.bytes_recv,
                        'packets_sent': net_io.packets_sent,
                        'packets_recv': net_io.packets_recv,
                        'bytes_sent_formatted': SystemUtilities.format_bytes(net_io.bytes_sent),
                        'bytes_recv_formatted': SystemUtilities.format_bytes(net_io.bytes_recv)
                    }
                
                # Carga del sistema
                try:
                    load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else None
                    performance_info['load_average'] = load_avg
                except Exception:
                    pass
                
                # Temperatura (si está disponible)
                try:
                    temps = psutil.sensors_temperatures()
                    if temps:
                        performance_info['temperatures'] = temps
                except Exception:
                    pass
                
            except Exception as e:
                logger.debug(f"Error obteniendo contadores de rendimiento: {e}")
            
            system_info['performance'] = performance_info
            
        except Exception as e:
            logger.error(f"Error recopilando contadores de rendimiento: {e}")
            raise

# Función de inicialización
def initialize_detailed_system_task():
    """Inicializa el sistema de análisis detallado"""
    try:
        logger.info("Inicializando sistema de análisis detallado...")
        
        # Verificar disponibilidad de WMI
        try:
            connection = wmi_manager.get_connection()
            if connection:
                logger.info("Conexión WMI establecida exitosamente")
            else:
                logger.warning("No se pudo establecer conexión WMI")
                
        except Exception as e:
            logger.error(f"Error verificando WMI: {e}")
        
        logger.info("Sistema de análisis detallado inicializado")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando análisis detallado: {e}")
        return False

# Test de funcionalidad
def test_detailed_analysis():
    """Prueba el análisis detallado"""
    try:
        logger.info("Ejecutando prueba de análisis detallado...")
        
        task = DetailedSystemInfoTask(
            include_hardware=True,
            include_software=False,  # Reducido para prueba rápida
            include_network=False,
            include_security=False,
            include_performance=True
        )
        
        result = task.run()
        
        if result.status.value == 'completed':
            logger.info("Prueba de análisis detallado exitosa")
            return True
        else:
            logger.error(f"Prueba falló: {result.error}")
            return False
            
    except Exception as e:
        logger.error(f"Error en prueba de análisis detallado: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_detailed_system_task()