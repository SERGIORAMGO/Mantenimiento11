"""
Sistema de Monitoreo de PC - Módulo 7: Tareas de Disco y Almacenamiento
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Tareas para análisis de discos, archivos temporales y limpieza
"""

import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
import logging
import shutil
import tempfile
import glob
import hashlib

try:
    import psutil
    import wmi
    import win32api
    import win32file
    import win32con
    import win32security
    import win32netcon
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias de disco y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, SecurityUtilities, FileUtilities
)
from base_classes import BaseTask, TaskPriority, TaskStatus
from detailed_system_task import wmi_manager

# Logger para este módulo
logger = logging.getLogger(__name__)

class DiskAnalysisTask(BaseTask):
    """Tarea para análisis completo de discos"""
    
    def __init__(self, include_health: bool = True, 
                 include_performance: bool = True,
                 include_fragmentation: bool = False):
        """
        Inicializa la tarea de análisis de discos
        
        Args:
            include_health: Incluir información de salud
            include_performance: Incluir métricas de rendimiento
            include_fragmentation: Incluir análisis de fragmentación
        """
        super().__init__(
            name="Análisis de Discos",
            description="Análisis completo de discos y almacenamiento",
            priority=TaskPriority.NORMAL,
            timeout=SystemConfig.TASK_TIMEOUT * 2
        )
        
        self.include_health = include_health
        self.include_performance = include_performance
        self.include_fragmentation = include_fragmentation
        
    def execute(self) -> Dict[str, Any]:
        """Ejecuta el análisis de discos"""
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for DiskAnalysisTask thread.")

            logger.info("Iniciando análisis de discos...")
            
            disk_data = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'disk_analysis',
                    'options': {
                        'include_health': self.include_health,
                        'include_performance': self.include_performance,
                        'include_fragmentation': self.include_fragmentation
                    }
                },
                'physical_disks': [],
                'logical_drives': [],
                'disk_usage_summary': {},
                'performance_metrics': {},
                'health_status': {},
                'recommendations': [],
                'errors': []
            }
            
            # Obtener información de discos físicos
            self.update_progress(10, "Analizando discos físicos...")
            disk_data['physical_disks'] = self._analyze_physical_disks()
            
            # Obtener información de unidades lógicas
            self.update_progress(30, "Analizando unidades lógicas...")
            disk_data['logical_drives'] = self._analyze_logical_drives()
            
            # Resumen de uso de disco
            self.update_progress(50, "Calculando resumen de uso...")
            disk_data['disk_usage_summary'] = self._calculate_usage_summary(disk_data['logical_drives'])
            
            # Métricas de rendimiento
            if self.include_performance:
                self.update_progress(70, "Analizando rendimiento...")
                disk_data['performance_metrics'] = self._analyze_disk_performance()
            
            # Estado de salud
            if self.include_health:
                self.update_progress(85, "Verificando salud de discos...")
                disk_data['health_status'] = self._check_disk_health(disk_data['physical_disks'])
            
            # Recomendaciones
            self.update_progress(95, "Generando recomendaciones...")
            disk_data['recommendations'] = self._generate_disk_recommendations(disk_data)
            
            # Información final
            disk_data['scan_info']['end_time'] = datetime.now().isoformat()
            disk_data['scan_info']['total_physical_disks'] = len(disk_data['physical_disks'])
            disk_data['scan_info']['total_logical_drives'] = len(disk_data['logical_drives'])
            
            self.update_progress(100, "Análisis completado")
            logger.info(f"Análisis de discos completado: {len(disk_data['physical_disks'])} discos físicos, {len(disk_data['logical_drives'])} unidades lógicas")
            
            return disk_data
            
        except Exception as e:
            logger.exception("Error en análisis de discos.") # Usar logger.exception
            raise
        finally:
            if initialized_com:
                pythoncom.CoUninitialize()
                logger.debug("COM uninitialized for DiskAnalysisTask thread.")
    
    @timeout_decorator(60)
    def _analyze_physical_disks(self) -> List[Dict[str, Any]]:
        """Analiza discos físicos"""
        try:
            physical_disks = []
            
            # Obtener información via WMI
            disk_results = wmi_manager.query("SELECT * FROM Win32_DiskDrive")
            
            for disk in disk_results:
                disk_info = {
                    'device_id': getattr(disk, 'DeviceID', 'Unknown'),
                    'model': getattr(disk, 'Model', 'Unknown'),
                    'manufacturer': getattr(disk, 'Manufacturer', 'Unknown'),
                    'serial_number': getattr(disk, 'SerialNumber', 'Unknown'),
                    'size': int(getattr(disk, 'Size', 0)) if getattr(disk, 'Size') else 0,
                    'size_formatted': '',
                    'interface_type': getattr(disk, 'InterfaceType', 'Unknown'),
                    'media_type': getattr(disk, 'MediaType', 'Unknown'),
                    'status': getattr(disk, 'Status', 'Unknown'),
                    'partitions': getattr(disk, 'Partitions', 0),
                    'bytes_per_sector': getattr(disk, 'BytesPerSector', 0),
                    'sectors_per_track': getattr(disk, 'SectorsPerTrack', 0),
                    'tracks_per_cylinder': getattr(disk, 'TracksPerCylinder', 0),
                    'total_cylinders': getattr(disk, 'TotalCylinders', 0),
                    'total_heads': getattr(disk, 'TotalHeads', 0),
                    'total_sectors': getattr(disk, 'TotalSectors', 0),
                    'firmware_revision': getattr(disk, 'FirmwareRevision', 'Unknown'),
                    'capabilities': [],
                    'smart_status': 'Unknown'
                }
                
                # Formatear tamaño
                disk_info['size_formatted'] = SystemUtilities.format_bytes(disk_info['size'])
                
                # Obtener capacidades
                capabilities = getattr(disk, 'Capabilities', [])
                if capabilities:
                    disk_info['capabilities'] = list(capabilities)
                
                # Intentar obtener información SMART
                try:
                    smart_data = self._get_smart_data(disk_info['device_id'])
                    if smart_data:
                        disk_info['smart_status'] = smart_data.get('status', 'Unknown')
                        disk_info['smart_attributes'] = smart_data.get('attributes', [])
                except Exception as e:
                    logger.debug(f"No se pudo obtener datos SMART para {disk_info['device_id']}: {e}")
                
                physical_disks.append(disk_info)
            
            return physical_disks
            
        except Exception as e:
            logger.error(f"Error analizando discos físicos: {e}")
            return []
    
    @timeout_decorator(30)
    def _analyze_logical_drives(self) -> List[Dict[str, Any]]:
        """Analiza unidades lógicas"""
        try:
            logical_drives = []
            
            # Obtener información via psutil
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    
                    drive_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'filesystem': partition.fstype,
                        'opts': partition.opts,
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent_used': (usage.used / usage.total) * 100 if usage.total > 0 else 0,
                        'total_formatted': SystemUtilities.format_bytes(usage.total),
                        'used_formatted': SystemUtilities.format_bytes(usage.used),
                        'free_formatted': SystemUtilities.format_bytes(usage.free),
                        'drive_type': 'Unknown',
                        'volume_label': '',
                        'serial_number': '',
                        'cluster_size': 0,
                        'file_system_flags': []
                    }
                    
                    # Obtener información adicional via WMI
                    try:
                        drive_letter = partition.device.replace('\\', '').replace(':', '')
                        if drive_letter:
                            logical_disk_results = wmi_manager.query(
                                f"SELECT * FROM Win32_LogicalDisk WHERE DeviceID='{drive_letter}:'"
                            )
                            
                            if logical_disk_results:
                                logical_disk = logical_disk_results[0]
                                drive_info.update({
                                    'drive_type': self._get_drive_type_name(getattr(logical_disk, 'DriveType', 0)),
                                    'volume_label': getattr(logical_disk, 'VolumeName', ''),
                                    'serial_number': getattr(logical_disk, 'VolumeSerialNumber', ''),
                                    'description': getattr(logical_disk, 'Description', ''),
                                    'provider_name': getattr(logical_disk, 'ProviderName', ''),
                                    'compressed': getattr(logical_disk, 'Compressed', False),
                                    'supports_disk_quotas': getattr(logical_disk, 'SupportsDiskQuotas', False)
                                })
                    
                    except Exception as e:
                        logger.debug(f"Error obteniendo info WMI para {partition.device}: {e}")
                    
                    logical_drives.append(drive_info)
                    
                except PermissionError:
                    # Algunos dispositivos pueden no ser accesibles
                    logger.debug(f"Sin permisos para acceder a {partition.mountpoint}")
                    continue
                except Exception as e:
                    logger.debug(f"Error analizando partición {partition.mountpoint}: {e}")
                    continue
            
            return logical_drives
            
        except Exception as e:
            logger.error(f"Error analizando unidades lógicas: {e}")
            return []
    
    def _get_drive_type_name(self, drive_type: int) -> str:
        """Convierte el tipo de unidad numérico a nombre"""
        drive_types = {
            0: 'Unknown',
            1: 'No Root Directory',
            2: 'Removable Disk',
            3: 'Local Disk',
            4: 'Network Drive',
            5: 'Compact Disc',
            6: 'RAM Disk'
        }
        return drive_types.get(drive_type, 'Unknown')
    
    @timeout_decorator(30)
    def _get_smart_data(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene datos SMART del disco"""
        try:
            # Intentar obtener estado SMART via WMI
            smart_results = wmi_manager.query(
                f"SELECT * FROM MSStorageDriver_FailurePredictStatus WHERE InstanceName LIKE '%{device_id}%'"
            )
            
            if smart_results:
                smart_status = smart_results[0]
                return {
                    'status': 'OK' if getattr(smart_status, 'PredictFailure', True) == False else 'Warning',
                    'predict_failure': getattr(smart_status, 'PredictFailure', None),
                    'reason': getattr(smart_status, 'Reason', None)
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error obteniendo datos SMART: {e}")
            return None
    
    def _calculate_usage_summary(self, logical_drives: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula resumen de uso de disco"""
        try:
            if not logical_drives:
                return {}
            
            total_space = sum(drive['total'] for drive in logical_drives)
            total_used = sum(drive['used'] for drive in logical_drives)
            total_free = sum(drive['free'] for drive in logical_drives)
            
            # Clasificar unidades por uso
            usage_categories = {'low': [], 'medium': [], 'high': [], 'critical': []}
            
            for drive in logical_drives:
                usage_percent = drive['percent_used']
                if usage_percent < 50:
                    usage_categories['low'].append(drive['device'])
                elif usage_percent < 80:
                    usage_categories['medium'].append(drive['device'])
                elif usage_percent < 95:
                    usage_categories['high'].append(drive['device'])
                else:
                    usage_categories['critical'].append(drive['device'])
            
            # Encontrar unidades con mayor y menor uso
            drives_by_usage = sorted(logical_drives, key=lambda x: x['percent_used'], reverse=True)
            
            summary = {
                'total_drives': len(logical_drives),
                'total_space': total_space,
                'total_used': total_used,
                'total_free': total_free,
                'total_space_formatted': SystemUtilities.format_bytes(total_space),
                'total_used_formatted': SystemUtilities.format_bytes(total_used),
                'total_free_formatted': SystemUtilities.format_bytes(total_free),
                'overall_usage_percent': (total_used / total_space) * 100 if total_space > 0 else 0,
                'usage_categories': usage_categories,
                'highest_usage_drive': drives_by_usage[0] if drives_by_usage else None,
                'lowest_usage_drive': drives_by_usage[-1] if drives_by_usage else None,
                'drives_by_filesystem': {},
                'drives_by_type': {}
            }
            
            # Agrupar por sistema de archivos
            for drive in logical_drives:
                fs = drive['filesystem']
                if fs not in summary['drives_by_filesystem']:
                    summary['drives_by_filesystem'][fs] = {'count': 0, 'total_space': 0}
                summary['drives_by_filesystem'][fs]['count'] += 1
                summary['drives_by_filesystem'][fs]['total_space'] += drive['total']
            
            # Agrupar por tipo de unidad
            for drive in logical_drives:
                drive_type = drive.get('drive_type', 'Unknown')
                if drive_type not in summary['drives_by_type']:
                    summary['drives_by_type'][drive_type] = {'count': 0, 'total_space': 0}
                summary['drives_by_type'][drive_type]['count'] += 1
                summary['drives_by_type'][drive_type]['total_space'] += drive['total']
            
            return summary
            
        except Exception as e:
            logger.error(f"Error calculando resumen de uso: {e}")
            return {}
    
    @timeout_decorator(30)
    def _analyze_disk_performance(self) -> Dict[str, Any]:
        """Analiza el rendimiento de los discos"""
        try:
            performance_data = {}
            
            # Obtener estadísticas de I/O
            try:
                disk_io = psutil.disk_io_counters(perdisk=True)
                disk_io_total = psutil.disk_io_counters()
                
                if disk_io_total:
                    performance_data['total_io'] = {
                        'read_count': disk_io_total.read_count,
                        'write_count': disk_io_total.write_count,
                        'read_bytes': disk_io_total.read_bytes,
                        'write_bytes': disk_io_total.write_bytes,
                        'read_time': disk_io_total.read_time,
                        'write_time': disk_io_total.write_time,
                        'read_bytes_formatted': SystemUtilities.format_bytes(disk_io_total.read_bytes),
                        'write_bytes_formatted': SystemUtilities.format_bytes(disk_io_total.write_bytes)
                    }
                
                if disk_io:
                    performance_data['per_disk_io'] = {}
                    for disk_name, io_stats in disk_io.items():
                        performance_data['per_disk_io'][disk_name] = {
                            'read_count': io_stats.read_count,
                            'write_count': io_stats.write_count,
                            'read_bytes': io_stats.read_bytes,
                            'write_bytes': io_stats.write_bytes,
                            'read_time': io_stats.read_time,
                            'write_time': io_stats.write_time,
                            'read_bytes_formatted': SystemUtilities.format_bytes(io_stats.read_bytes),
                            'write_bytes_formatted': SystemUtilities.format_bytes(io_stats.write_bytes)
                        }
                        
                        # Calcular velocidades promedio
                        if io_stats.read_time > 0:
                            performance_data['per_disk_io'][disk_name]['avg_read_speed'] = io_stats.read_bytes / (io_stats.read_time / 1000)
                        if io_stats.write_time > 0:
                            performance_data['per_disk_io'][disk_name]['avg_write_speed'] = io_stats.write_bytes / (io_stats.write_time / 1000)
                
            except Exception as e:
                logger.debug(f"Error obteniendo estadísticas de I/O: {e}")
            
            # Intentar obtener métricas adicionales via WMI
            try:
                perf_results = wmi_manager.query("SELECT * FROM Win32_PerfRawData_PerfDisk_LogicalDisk")
                if perf_results:
                    performance_data['wmi_performance'] = []
                    for perf in perf_results:
                        perf_info = {
                            'name': getattr(perf, 'Name', 'Unknown'),
                            'disk_reads_per_sec': getattr(perf, 'DiskReadsPerSec', 0),
                            'disk_writes_per_sec': getattr(perf, 'DiskWritesPerSec', 0),
                            'disk_read_bytes_per_sec': getattr(perf, 'DiskReadBytesPerSec', 0),
                            'disk_write_bytes_per_sec': getattr(perf, 'DiskWriteBytesPerSec', 0),
                            'current_disk_queue_length': getattr(perf, 'CurrentDiskQueueLength', 0),
                            'percent_disk_time': getattr(perf, 'PercentDiskTime', 0)
                        }
                        performance_data['wmi_performance'].append(perf_info)
            
            except Exception as e:
                logger.debug(f"Error obteniendo métricas WMI: {e}")
            
            return performance_data
            
        except Exception as e:
            logger.error(f"Error analizando rendimiento de discos: {e}")
            return {}
    
    def _check_disk_health(self, physical_disks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verifica el estado de salud de los discos"""
        try:
            health_status = {
                'overall_status': 'Healthy',
                'disks_status': [],
                'warnings': [],
                'critical_issues': []
            }
            
            critical_count = 0
            warning_count = 0
            
            for disk in physical_disks:
                disk_health = {
                    'device_id': disk['device_id'],
                    'model': disk['model'],
                    'status': disk['status'],
                    'smart_status': disk.get('smart_status', 'Unknown'),
                    'health_level': 'Good',
                    'issues': []
                }
                
                # Verificar estado general
                if disk['status'] != 'OK':
                    disk_health['health_level'] = 'Critical'
                    disk_health['issues'].append(f"Estado del disco: {disk['status']}")
                    critical_count += 1
                
                # Verificar estado SMART
                if disk_health['smart_status'] == 'Warning':
                    disk_health['health_level'] = 'Warning'
                    disk_health['issues'].append("SMART indica posible fallo")
                    warning_count += 1
                elif disk_health['smart_status'] == 'Unknown':
                    disk_health['issues'].append("Estado SMART no disponible")
                
                # Verificar si es muy viejo (heurística simple)
                if 'Unknown' in disk['model'] or not disk['model']:
                    disk_health['issues'].append("Información del modelo no disponible")
                
                health_status['disks_status'].append(disk_health)
            
            # Determinar estado general
            if critical_count > 0:
                health_status['overall_status'] = 'Critical'
            elif warning_count > 0:
                health_status['overall_status'] = 'Warning'
            
            health_status['summary'] = {
                'total_disks': len(physical_disks),
                'healthy_disks': len(physical_disks) - critical_count - warning_count,
                'warning_disks': warning_count,
                'critical_disks': critical_count
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error verificando salud de discos: {e}")
            return {'overall_status': 'Unknown', 'error': str(e)}
    
    def _generate_disk_recommendations(self, disk_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera recomendaciones basadas en el análisis"""
        recommendations = []
        
        try:
            usage_summary = disk_data.get('disk_usage_summary', {})
            logical_drives = disk_data.get('logical_drives', [])
            health_status = disk_data.get('health_status', {})
            
            # Recomendaciones de espacio
            critical_drives = usage_summary.get('usage_categories', {}).get('critical', [])
            high_usage_drives = usage_summary.get('usage_categories', {}).get('high', [])
            
            if critical_drives:
                recommendations.append({
                    'type': 'CRITICAL',
                    'category': 'storage_space',
                    'title': 'Espacio en disco críticamente bajo',
                    'description': f"Las unidades {', '.join(critical_drives)} tienen menos del 5% de espacio libre",
                    'action': 'Liberar espacio inmediatamente o expandir almacenamiento',
                    'priority': 'HIGH'
                })
            
            if high_usage_drives:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'storage_space',
                    'title': 'Espacio en disco bajo',
                    'description': f"Las unidades {', '.join(high_usage_drives)} tienen menos del 20% de espacio libre",
                    'action': 'Considerar limpiar archivos innecesarios',
                    'priority': 'MEDIUM'
                })
            
            # Recomendaciones de salud
            if health_status.get('overall_status') == 'Critical':
                recommendations.append({
                    'type': 'CRITICAL',
                    'category': 'hardware_health',
                    'title': 'Problemas críticos de hardware detectados',
                    'description': 'Uno o más discos muestran signos de fallo',
                    'action': 'Realizar backup inmediato y considerar reemplazo de hardware',
                    'priority': 'CRITICAL'
                })
            
            # Recomendaciones de rendimiento
            overall_usage = usage_summary.get('overall_usage_percent', 0)
            if overall_usage > 85:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'performance',
                    'title': 'Alto uso general de almacenamiento',
                    'description': f'El uso general de almacenamiento es del {overall_usage:.1f}%',
                    'action': 'Considerar añadir más almacenamiento o migrar datos',
                    'priority': 'MEDIUM'
                })
            
            # Recomendaciones de fragmentación (si está habilitado)
            if self.include_fragmentation:
                recommendations.append({
                    'type': 'INFO',
                    'category': 'maintenance',
                    'title': 'Desfragmentación recomendada',
                    'description': 'Ejecutar desfragmentación para mejorar rendimiento',
                    'action': 'Programar desfragmentación durante horarios de bajo uso',
                    'priority': 'LOW'
                })
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones: {e}")
            recommendations.append({
                'type': 'ERROR',
                'category': 'system',
                'title': 'Error generando recomendaciones',
                'description': f'Error interno: {str(e)}',
                'action': 'Revisar logs del sistema',
                'priority': 'LOW'
            })
        
        return recommendations

class TempFileCleanupTask(BaseTask):
    """Tarea para limpieza de archivos temporales"""
    
    def __init__(self, deep_scan: bool = False, 
                 custom_paths: List[str] = None,
                 days_old: int = 7,
                 size_threshold_mb: int = 100):
        """
        Inicializa la tarea de limpieza de archivos temporales
        
        Args:
            deep_scan: Realizar escaneo profundo
            custom_paths: Rutas personalizadas para limpiar
            days_old: Días de antigüedad para considerar archivo como temporal
            size_threshold_mb: Tamaño mínimo en MB para reportar archivos grandes
        """
        super().__init__(
            name="Limpieza de Archivos Temporales",
            description="Análisis y limpieza de archivos temporales del sistema",
            priority=TaskPriority.NORMAL,
            timeout=SystemConfig.TASK_TIMEOUT * 3
        )
        
        self.deep_scan = deep_scan
        self.custom_paths = custom_paths or []
        self.days_old = days_old
        self.size_threshold_mb = size_threshold_mb
        self.size_threshold_bytes = size_threshold_mb * 1024 * 1024
        
        # Rutas estándar de archivos temporales
        self.temp_paths = [
            os.getenv('TEMP', r'C:\Windows\Temp'),
            os.getenv('TMP', r'C:\Windows\Temp'),
            r'C:\Windows\Temp',
            os.path.join(os.getenv('USERPROFILE', ''), 'AppData\\Local\\Temp'),
            r'C:\Windows\Prefetch',
            r'C:\Windows\SoftwareDistribution\Download',
            r'C:\$Recycle.Bin',
            r'C:\Windows\Logs',
            r'C:\ProgramData\Microsoft\Windows\WER'
        ]
        
        # Extensiones de archivos temporales
        self.temp_extensions = [
            '.tmp', '.temp', '.bak', '.old', '.cache', '.log',
            '.dmp', '.chk', '.gid', '.fts', '.ftg', '.bac'
        ]
    
    def execute(self) -> Dict[str, Any]:
        """Ejecuta la limpieza de archivos temporales"""
        try:
            logger.info("Iniciando limpieza de archivos temporales...")
            
            cleanup_data = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'temp_file_cleanup',
                    'deep_scan': self.deep_scan,
                    'days_old_threshold': self.days_old,
                    'size_threshold_mb': self.size_threshold_mb
                },
                'scanned_paths': [],
                'found_files': [],
                'large_files': [],
                'cleaned_files': [],
                'statistics': {},
                'errors': [],
                'recommendations': []
            }
            
            # Combinar rutas estándar y personalizadas
            all_paths = self.temp_paths + self.custom_paths
            total_paths = len(all_paths)
            
            # Escanear cada ruta
            for i, path in enumerate(all_paths):
                if self.is_cancelled():
                    logger.info("Limpieza cancelada por el usuario")
                    break
                
                self.wait_if_paused()
                
                progress = (i / total_paths) * 80  # 80% para escaneo
                self.update_progress(progress, f"Escaneando {path}")
                
                try:
                    path_result = self._scan_temp_path(path)
                    if path_result:
                        cleanup_data['scanned_paths'].append(path_result)
                        cleanup_data['found_files'].extend(path_result.get('files', []))
                        cleanup_data['large_files'].extend(path_result.get('large_files', []))
                        
                except Exception as e:
                    error_msg = f"Error escaneando {path}: {str(e)}"
                    logger.warning(error_msg)
                    cleanup_data['errors'].append({
                        'path': path,
                        'error': error_msg,
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Calcular estadísticas
            self.update_progress(85, "Calculando estadísticas...")
            cleanup_data['statistics'] = self._calculate_cleanup_statistics(cleanup_data['found_files'])
            
            # Generar recomendaciones
            self.update_progress(90, "Generando recomendaciones...")
            cleanup_data['recommendations'] = self._generate_cleanup_recommendations(cleanup_data)
            
            # Simular limpieza (por seguridad, no eliminamos automáticamente)
            self.update_progress(95, "Preparando plan de limpieza...")
            cleanup_data['cleanup_plan'] = self._create_cleanup_plan(cleanup_data['found_files'])
            
            # Información final
            cleanup_data['scan_info']['end_time'] = datetime.now().isoformat()
            cleanup_data['scan_info']['total_files_found'] = len(cleanup_data['found_files'])
            cleanup_data['scan_info']['total_size_found'] = cleanup_data['statistics'].get('total_size', 0)
            cleanup_data['scan_info']['paths_scanned'] = len(cleanup_data['scanned_paths'])
            cleanup_data['scan_info']['errors_count'] = len(cleanup_data['errors'])
            
            self.update_progress(100, "Análisis completado")
            logger.info(f"Análisis de limpieza completado: {len(cleanup_data['found_files'])} archivos encontrados")
            
            return cleanup_data
            
        except Exception as e:
            logger.error(f"Error en limpieza de archivos temporales: {e}")
            raise
    
    @timeout_decorator(120)
    def _scan_temp_path(self, path: str) -> Optional[Dict[str, Any]]:
        """Escanea una ruta específica en busca de archivos temporales"""
        try:
            if not os.path.exists(path):
                return None
            
            path_result = {
                'path': path,
                'accessible': True,
                'files': [],
                'large_files': [],
                'total_files': 0,
                'total_size': 0,
                'scan_time': datetime.now().isoformat()
            }
            
            cutoff_time = time.time() - (self.days_old * 24 * 3600)
            
            try:
                # Escanear archivos
                if self.deep_scan:
                    # Escaneo recursivo
                    for root, dirs, files in os.walk(path):
                        for file in files:
                            if self.is_cancelled():
                                break
                            
                            try:
                                file_path = os.path.join(root, file)
                                file_info = self._analyze_file(file_path, cutoff_time)
                                if file_info:
                                    path_result['files'].append(file_info)
                                    path_result['total_size'] += file_info['size']
                                    
                                    if file_info['size'] >= self.size_threshold_bytes:
                                        path_result['large_files'].append(file_info)
                                        
                            except (OSError, PermissionError) as e:
                                continue
                else:
                    # Escaneo superficial (solo directorio actual)
                    try:
                        for item in os.listdir(path):
                            if self.is_cancelled():
                                break
                            
                            item_path = os.path.join(path, item)
                            if os.path.isfile(item_path):
                                file_info = self._analyze_file(item_path, cutoff_time)
                                if file_info:
                                    path_result['files'].append(file_info)
                                    path_result['total_size'] += file_info['size']
                                    
                                    if file_info['size'] >= self.size_threshold_bytes:
                                        path_result['large_files'].append(file_info)
                                        
                    except (OSError, PermissionError):
                        path_result['accessible'] = False
                
                path_result['total_files'] = len(path_result['files'])
                
            except Exception as e:
                logger.debug(f"Error detallado escaneando {path}: {e}")
                path_result['accessible'] = False
                path_result['error'] = str(e)
            
            return path_result
            
        except Exception as e:
            logger.error(f"Error escaneando ruta {path}: {e}")
            return None
    
    def _analyze_file(self, file_path: str, cutoff_time: float) -> Optional[Dict[str, Any]]:
        """Analiza un archivo individual"""
        try:
            stat_info = os.stat(file_path)
            
            # Verificar si es un archivo temporal candidato
            is_temp_candidate = False
            
            # Por extensión
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in self.temp_extensions:
                is_temp_candidate = True
            
            # Por antigüedad
            if stat_info.st_mtime < cutoff_time:
                is_temp_candidate = True
            
            # Por ubicación (ya está en carpeta temp)
            if any(temp_dir.lower() in file_path.lower() for temp_dir in ['temp', 'tmp', 'cache']):
                is_temp_candidate = True
            
            if not is_temp_candidate:
                return None
            
            file_info = {
                'path': file_path,
                'name': os.path.basename(file_path),
                'size': stat_info.st_size,
                'size_formatted': SystemUtilities.format_bytes(stat_info.st_size),
                'modified_time': datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                'created_time': datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
                'accessed_time': datetime.fromtimestamp(stat_info.st_atime).isoformat(),
                'extension': file_ext,
                'is_large': stat_info.st_size >= self.size_threshold_bytes,
                'age_days': (time.time() - stat_info.st_mtime) / (24 * 3600),
                'safe_to_delete': self._is_safe_to_delete(file_path, stat_info)
            }
            
            return file_info
            
        except (OSError, PermissionError):
            return None
        except Exception as e:
            logger.debug(f"Error analizando archivo {file_path}: {e}")
            return None
    
    def _is_safe_to_delete(self, file_path: str, stat_info: os.stat_result) -> bool:
        """Determina si un archivo es seguro de eliminar"""
        try:
            # No eliminar archivos muy recientes (menos de 1 día)
            if (time.time() - stat_info.st_mtime) < (24 * 3600):
                return False
            
            # No eliminar archivos del sistema críticos
            critical_patterns = [
                'system32', 'windows\\system', 'program files',
                'drivers', 'boot', 'registry'
            ]
            
            file_path_lower = file_path.lower()
            if any(pattern in file_path_lower for pattern in critical_patterns):
                return False
            
            # No eliminar archivos en uso
            try:
                with open(file_path, 'r+b'):
                    pass
            except (PermissionError, OSError):
                return False
            
            return True
            
        except Exception:
            return False
    
    def _calculate_cleanup_statistics(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas de la limpieza"""
        try:
            if not files:
                return {}
            
            total_size = sum(f['size'] for f in files)
            total_files = len(files)
            
            # Estadísticas por extensión
            ext_stats = {}
            for file in files:
                ext = file['extension'] or 'Sin extensión'
                if ext not in ext_stats:
                    ext_stats[ext] = {'count': 0, 'size': 0}
                ext_stats[ext]['count'] += 1
                ext_stats[ext]['size'] += file['size']
            
            # Estadísticas por tamaño
            size_distribution = {
                'small_0_1MB': sum(1 for f in files if f['size'] < 1024*1024),
                'medium_1_10MB': sum(1 for f in files if 1024*1024 <= f['size'] < 10*1024*1024),
                'large_10_100MB': sum(1 for f in files if 10*1024*1024 <= f['size'] < 100*1024*1024),
                'huge_100MB_plus': sum(1 for f in files if f['size'] >= 100*1024*1024)
            }
            
            # Estadísticas por antigüedad
            age_distribution = {
                'recent_0_7_days': sum(1 for f in files if f['age_days'] < 7),
                'week_7_30_days': sum(1 for f in files if 7 <= f['age_days'] < 30),
                'month_30_90_days': sum(1 for f in files if 30 <= f['age_days'] < 90),
                'old_90_plus_days': sum(1 for f in files if f['age_days'] >= 90)
            }
            
            # Archivos seguros de eliminar
            safe_files = [f for f in files if f['safe_to_delete']]
            safe_size = sum(f['size'] for f in safe_files)
            
            stats = {
                'total_files': total_files,
                'total_size': total_size,
                'total_size_formatted': SystemUtilities.format_bytes(total_size),
                'safe_to_delete_files': len(safe_files),
                'safe_to_delete_size': safe_size,
                'safe_to_delete_size_formatted': SystemUtilities.format_bytes(safe_size),
                'potential_space_savings': safe_size,
                'potential_space_savings_formatted': SystemUtilities.format_bytes(safe_size),
                'extension_statistics': ext_stats,
                'size_distribution': size_distribution,
                'age_distribution': age_distribution,
                'average_file_size': total_size / total_files if total_files > 0 else 0,
                'largest_file_size': max(f['size'] for f in files) if files else 0,
                'oldest_file_age_days': max(f['age_days'] for f in files) if files else 0
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculando estadísticas de limpieza: {e}")
            return {}
    
    def _generate_cleanup_recommendations(self, cleanup_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera recomendaciones de limpieza"""
        recommendations = []
        
        try:
            stats = cleanup_data.get('statistics', {})
            total_size = stats.get('total_size', 0)
            safe_size = stats.get('safe_to_delete_size', 0)
            
            # Recomendación principal
            if safe_size > 100 * 1024 * 1024:  # > 100MB
                recommendations.append({
                    'type': 'ACTION',
                    'category': 'cleanup',
                    'title': 'Limpieza recomendada',
                    'description': f"Se pueden liberar {SystemUtilities.format_bytes(safe_size)} eliminando archivos temporales seguros",
                    'action': 'Ejecutar limpieza de archivos seguros',
                    'priority': 'MEDIUM'
                })
            
            # Recomendaciones por extensión
            ext_stats = stats.get('extension_statistics', {})
            for ext, ext_data in ext_stats.items():
                if ext_data['size'] > 50 * 1024 * 1024:  # > 50MB
                    recommendations.append({
                        'type': 'INFO',
                        'category': 'file_types',
                        'title': f'Muchos archivos {ext}',
                        'description': f"Se encontraron {ext_data['count']} archivos {ext} ocupando {SystemUtilities.format_bytes(ext_data['size'])}",
                        'action': f'Revisar archivos {ext} para limpieza específica',
                        'priority': 'LOW'
                    })
            
            # Recomendaciones por archivos grandes
            large_files = cleanup_data.get('large_files', [])
            if large_files:
                total_large_size = sum(f['size'] for f in large_files)
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'large_files',
                    'title': 'Archivos temporales grandes detectados',
                    'description': f"Se encontraron {len(large_files)} archivos grandes ocupando {SystemUtilities.format_bytes(total_large_size)}",
                    'action': 'Revisar archivos grandes individualmente antes de eliminar',
                    'priority': 'MEDIUM'
                })
            
            # Recomendación de programación
            if total_size > 1024 * 1024 * 1024:  # > 1GB
                recommendations.append({
                    'type': 'MAINTENANCE',
                    'category': 'automation',
                    'title': 'Programar limpieza automática',
                    'description': 'Gran cantidad de archivos temporales detectados',
                    'action': 'Considerar programar limpieza automática semanal',
                    'priority': 'LOW'
                })
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones de limpieza: {e}")
            
        return recommendations
    
    def _create_cleanup_plan(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Crea un plan de limpieza detallado"""
        try:
            safe_files = [f for f in files if f['safe_to_delete']]
            unsafe_files = [f for f in files if not f['safe_to_delete']]
            
            plan = {
                'automatic_cleanup': {
                    'files': safe_files,
                    'count': len(safe_files),
                    'total_size': sum(f['size'] for f in safe_files),
                    'total_size_formatted': SystemUtilities.format_bytes(sum(f['size'] for f in safe_files))
                },
                'manual_review_required': {
                    'files': unsafe_files,
                    'count': len(unsafe_files),
                    'total_size': sum(f['size'] for f in unsafe_files),
                    'total_size_formatted': SystemUtilities.format_bytes(sum(f['size'] for f in unsafe_files))
                },
                'cleanup_steps': [
                    "1. Revisar archivos marcados para revisión manual",
                    "2. Ejecutar limpieza automática de archivos seguros",
                    "3. Verificar espacio liberado",
                    "4. Programar limpieza regular"
                ]
            }
            
            return plan
            
        except Exception as e:
            logger.error(f"Error creando plan de limpieza: {e}")
            return {}

def execute_actual_cleanup(files_to_delete: List[str], dry_run: bool = True) -> Dict[str, Any]:
    """
    Ejecuta la limpieza real de archivos (usar con precaución)
    
    Args:
        files_to_delete: Lista de rutas de archivos a eliminar
        dry_run: Si True, solo simula la eliminación
        
    Returns:
        Resultados de la limpieza
    """
    try:
        logger.warning(f"{'Simulando' if dry_run else 'Ejecutando'} limpieza de {len(files_to_delete)} archivos...")
        
        results = {
            'deleted_files': [],
            'failed_deletions': [],
            'total_deleted': 0,
            'total_size_freed': 0,
            'errors': []
        }
        
        for file_path in files_to_delete:
            try:
                if not os.path.exists(file_path):
                    continue
                
                file_size = os.path.getsize(file_path)
                
                if not dry_run:
                    os.remove(file_path)
                    logger.debug(f"Archivo eliminado: {file_path}")
                else:
                    logger.debug(f"Simulación: eliminaría {file_path}")
                
                results['deleted_files'].append({
                    'path': file_path,
                    'size': file_size,
                    'size_formatted': SystemUtilities.format_bytes(file_size)
                })
                
                results['total_deleted'] += 1
                results['total_size_freed'] += file_size
                
            except Exception as e:
                error_msg = f"Error eliminando {file_path}: {str(e)}"
                logger.error(error_msg)
                results['failed_deletions'].append(file_path)
                results['errors'].append(error_msg)
        
        results['total_size_freed_formatted'] = SystemUtilities.format_bytes(results['total_size_freed'])
        results['success_rate'] = (results['total_deleted'] / len(files_to_delete)) * 100 if files_to_delete else 0
        
        logger.info(f"Limpieza completada: {results['total_deleted']} archivos, {results['total_size_freed_formatted']} {'simulados' if dry_run else 'liberados'}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error en limpieza de archivos: {e}")
        return {'error': str(e)}

# Función de inicialización
def initialize_disk_storage_tasks():
    """Inicializa el sistema de tareas de disco y almacenamiento"""
    try:
        logger.info("Inicializando sistema de tareas de disco y almacenamiento...")
        
        # Verificar disponibilidad de psutil para operaciones de disco
        try:
            psutil.disk_partitions()
            psutil.disk_usage('C:\\')
            logger.info("psutil para operaciones de disco disponible")
        except Exception as e:
            logger.error(f"Error verificando psutil para disco: {e}")
            return False
        
        logger.info("Sistema de tareas de disco y almacenamiento inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando tareas de disco: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_disk_storage_tasks()