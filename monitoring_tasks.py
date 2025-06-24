"""
Sistema de Monitoreo de PC - Módulo 6: Tareas de Monitoreo (Temperatura, CPU, Memoria)
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Tareas específicas para monitoreo continuo de sistema
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
import queue
import statistics

try:
    import psutil
    import wmi
    import win32pdh
    import win32api
    import win32con
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias de monitoreo y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, PerformanceUtilities, cache_result
)
from base_classes import BaseTask, TaskPriority, TaskStatus
from detailed_system_task import wmi_manager

# Logger para este módulo
logger = logging.getLogger(__name__)

class PerformanceDataCollector:
    """Colector de datos de rendimiento con buffer circular"""
    
    def __init__(self, max_samples: int = 300):  # 5 minutos a 1 muestra/segundo
        self.max_samples = max_samples
        self.data_buffer = {}
        self.timestamps = []
        self._lock = threading.Lock()
        
    def add_sample(self, metric_name: str, value: float, timestamp: datetime = None):
        """Añade una muestra al buffer"""
        if timestamp is None:
            timestamp = datetime.now()
        
        with self._lock:
            if metric_name not in self.data_buffer:
                self.data_buffer[metric_name] = []
            
            # Añadir nueva muestra
            self.data_buffer[metric_name].append(value)
            
            # Mantener solo las últimas muestras
            if len(self.data_buffer[metric_name]) > self.max_samples:
                self.data_buffer[metric_name] = self.data_buffer[metric_name][-self.max_samples:]
            
            # Gestionar timestamps (solo uno por todas las métricas)
            if len(self.timestamps) == 0 or self.timestamps[-1] != timestamp:
                self.timestamps.append(timestamp)
                if len(self.timestamps) > self.max_samples:
                    self.timestamps = self.timestamps[-self.max_samples:]
    
    def get_statistics(self, metric_name: str) -> Dict[str, Any]:
        """Calcula estadísticas para una métrica"""
        with self._lock:
            if metric_name not in self.data_buffer or not self.data_buffer[metric_name]:
                return {}
            
            data = self.data_buffer[metric_name]
            
            try:
                stats = {
                    'current': data[-1] if data else 0,
                    'average': statistics.mean(data),
                    'min': min(data),
                    'max': max(data),
                    'median': statistics.median(data),
                    'std_dev': statistics.stdev(data) if len(data) > 1 else 0,
                    'samples_count': len(data),
                    'time_span_minutes': (len(data) * SystemConfig.MONITORING_INTERVAL) / 60
                }
                
                # Tendencia (últimas 10 muestras vs anteriores)
                if len(data) >= 20:
                    recent = data[-10:]
                    previous = data[-20:-10]
                    recent_avg = statistics.mean(recent)
                    previous_avg = statistics.mean(previous)
                    stats['trend'] = 'increasing' if recent_avg > previous_avg else 'decreasing'
                    stats['trend_percentage'] = ((recent_avg - previous_avg) / previous_avg) * 100
                else:
                    stats['trend'] = 'stable'
                    stats['trend_percentage'] = 0
                
                return stats
                
            except Exception as e:
                logger.error(f"Error calculando estadísticas para {metric_name}: {e}")
                return {}
    
    def get_all_data(self) -> Dict[str, Any]:
        """Obtiene todos los datos del colector"""
        with self._lock:
            return {
                'metrics': dict(self.data_buffer),
                'timestamps': [ts.isoformat() for ts in self.timestamps],
                'max_samples': self.max_samples,
                'sample_count': len(self.timestamps)
            }
    
    def clear_data(self):
        """Limpia todos los datos"""
        with self._lock:
            self.data_buffer.clear()
            self.timestamps.clear()

# Instancia global del colector
performance_collector = PerformanceDataCollector()

class TemperatureMonitoringTask(BaseTask):
    """Tarea para monitoreo de temperatura del sistema"""
    
    def __init__(self, monitoring_duration: int = 60):
        """
        Inicializa la tarea de monitoreo de temperatura
        
        Args:
            monitoring_duration: Duración del monitoreo en segundos
        """
        super().__init__(
            name="Monitoreo de Temperatura",
            description=f"Monitoreo continuo de temperatura por {monitoring_duration}s",
            priority=TaskPriority.NORMAL,
            timeout=monitoring_duration + 30
        )
        
        self.monitoring_duration = monitoring_duration
        self.sample_interval = 2  # segundos entre muestras
        self.temperature_sources = []
        self.critical_temp_threshold = 85  # °C
        self.warning_temp_threshold = 70   # °C
        
    def execute(self) -> Dict[str, Any]:
        """Ejecuta el monitoreo de temperatura"""
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for TemperatureMonitoringTask thread.")

            logger.info(f"Iniciando monitoreo de temperatura por {self.monitoring_duration}s...")
            
            start_time = time.time()
            samples_collected = 0
            temperature_data = {
                'monitoring_info': {
                    'start_time': datetime.now().isoformat(),
                    'duration_seconds': self.monitoring_duration,
                    'sample_interval': self.sample_interval,
                    'monitoring_type': 'temperature'
                },
                'temperature_sources': [],
                'samples': [],
                'alerts': [],
                'statistics': {},
                'performance_impact': {}
            }
            
            # Detectar fuentes de temperatura disponibles
            self._detect_temperature_sources()
            temperature_data['temperature_sources'] = self.temperature_sources
            
            if not self.temperature_sources:
                logger.warning("No se detectaron sensores de temperatura")
                temperature_data['error'] = "No se detectaron sensores de temperatura disponibles"
                return temperature_data
            
            # Loop de monitoreo
            while (time.time() - start_time) < self.monitoring_duration:
                if self.is_cancelled():
                    logger.info("Monitoreo de temperatura cancelado")
                    break
                
                self.wait_if_paused()
                
                # Recopilar muestra de temperatura
                sample = self._collect_temperature_sample()
                if sample:
                    temperature_data['samples'].append(sample)
                    samples_collected += 1
                    
                    # Verificar alertas de temperatura
                    alerts = self._check_temperature_alerts(sample)
                    temperature_data['alerts'].extend(alerts)
                    
                    # Añadir al colector global
                    for source, temp_data in sample['temperatures'].items():
                        if 'current' in temp_data:
                            performance_collector.add_sample(
                                f"temperature_{source}", 
                                temp_data['current']
                            )
                
                # Actualizar progreso
                elapsed = time.time() - start_time
                progress = min((elapsed / self.monitoring_duration) * 100, 100)
                self.update_progress(progress, f"Muestra {samples_collected}")
                
                # Esperar siguiente intervalo
                time.sleep(self.sample_interval)
            
            # Calcular estadísticas finales
            temperature_data['statistics'] = self._calculate_temperature_statistics(
                temperature_data['samples']
            )
            
            # Información final
            end_time = time.time()
            temperature_data['monitoring_info']['end_time'] = datetime.now().isoformat()
            temperature_data['monitoring_info']['actual_duration'] = end_time - start_time
            temperature_data['monitoring_info']['samples_collected'] = samples_collected
            temperature_data['monitoring_info']['alerts_generated'] = len(temperature_data['alerts'])
            
            logger.info(f"Monitoreo de temperatura completado: {samples_collected} muestras, {len(temperature_data['alerts'])} alertas")
            
            return temperature_data
            
        except Exception as e:
            logger.exception("Error en monitoreo de temperatura.") # Usar logger.exception
            raise
        finally:
            if initialized_com:
                pythoncom.CoUninitialize()
                logger.debug("COM uninitialized for TemperatureMonitoringTask thread.")
    
    def _detect_temperature_sources(self):
        """Detecta fuentes de temperatura disponibles"""
        try:
            self.temperature_sources = []
            
            # Intentar detectar via psutil
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for sensor_name, sensors in temps.items():
                        self.temperature_sources.append({
                            'source': 'psutil',
                            'sensor_name': sensor_name,
                            'sensor_count': len(sensors),
                            'available': True
                        })
                        logger.debug(f"Sensor de temperatura detectado (psutil): {sensor_name}")
            except Exception as e:
                logger.debug(f"Error detectando temperaturas via psutil: {e}")
            
            # Intentar detectar via WMI
            try:
                temp_results = wmi_manager.query(
                    "SELECT * FROM MSAcpi_ThermalZoneTemperature",
                    timeout=10
                )
                
                if temp_results:
                    self.temperature_sources.append({
                        'source': 'wmi_thermal',
                        'sensor_name': 'ThermalZone',
                        'sensor_count': len(temp_results),
                        'available': True
                    })
                    logger.debug(f"Sensores térmicos WMI detectados: {len(temp_results)}")
                    
            except Exception as e:
                logger.debug(f"Error detectando temperaturas via WMI: {e}")
            
            # Intentar detectar sensores de CPU específicos
            try:
                cpu_temp_results = wmi_manager.query(
                    "SELECT * FROM Win32_TemperatureProbe",
                    timeout=10
                )
                
                if cpu_temp_results:
                    self.temperature_sources.append({
                        'source': 'wmi_probe',
                        'sensor_name': 'TemperatureProbe',
                        'sensor_count': len(cpu_temp_results),
                        'available': True
                    })
                    logger.debug(f"Sondas de temperatura WMI detectadas: {len(cpu_temp_results)}")
                    
            except Exception as e:
                logger.debug(f"Error detectando sondas de temperatura: {e}")
            
            logger.info(f"Fuentes de temperatura detectadas: {len(self.temperature_sources)}")
            
        except Exception as e:
            logger.error(f"Error detectando fuentes de temperatura: {e}")
    
    @timeout_decorator(10)
    def _collect_temperature_sample(self) -> Optional[Dict[str, Any]]:
        """Recopila una muestra de temperatura"""
        try:
            sample = {
                'timestamp': datetime.now().isoformat(),
                'temperatures': {},
                'cpu_usage': 0,
                'memory_usage': 0
            }
            
            # Recopilar via psutil
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for sensor_name, sensors in temps.items():
                        sensor_data = {
                            'sensors': [],
                            'average': 0,
                            'max': 0,
                            'count': len(sensors)
                        }
                        
                        temp_values = []
                        for sensor in sensors:
                            sensor_info = {
                                'label': sensor.label or 'Unknown',
                                'current': sensor.current,
                                'high': sensor.high,
                                'critical': sensor.critical
                            }
                            sensor_data['sensors'].append(sensor_info)
                            temp_values.append(sensor.current)
                        
                        if temp_values:
                            sensor_data['average'] = sum(temp_values) / len(temp_values)
                            sensor_data['max'] = max(temp_values)
                            sensor_data['current'] = sensor_data['average']  # Para compatibilidad
                        
                        sample['temperatures'][f"psutil_{sensor_name}"] = sensor_data
                        
            except Exception as e:
                logger.debug(f"Error recopilando temperaturas psutil: {e}")
            
            # Recopilar via WMI Thermal Zones
            try:
                temp_results = wmi_manager.query(
                    "SELECT * FROM MSAcpi_ThermalZoneTemperature",
                    timeout=5
                )
                
                if temp_results:
                    thermal_temps = []
                    for i, temp_zone in enumerate(temp_results):
                        # La temperatura viene en décimos de Kelvin
                        temp_kelvin = getattr(temp_zone, 'CurrentTemperature', 0) / 10.0
                        temp_celsius = temp_kelvin - 273.15
                        
                        if temp_celsius > 0 and temp_celsius < 150:  # Validación básica
                            thermal_temps.append(temp_celsius)
                    
                    if thermal_temps:
                        sample['temperatures']['wmi_thermal'] = {
                            'current': sum(thermal_temps) / len(thermal_temps),
                            'max': max(thermal_temps),
                            'count': len(thermal_temps),
                            'temperatures': thermal_temps
                        }
                        
            except Exception as e:
                logger.debug(f"Error recopilando temperaturas WMI thermal: {e}")
            
            # Información adicional del sistema
            try:
                sample['cpu_usage'] = psutil.cpu_percent(interval=0.1)
                sample['memory_usage'] = psutil.virtual_memory().percent
            except Exception as e:
                logger.debug(f"Error obteniendo info adicional: {e}")
            
            return sample if sample['temperatures'] else None
            
        except Exception as e:
            logger.error(f"Error recopilando muestra de temperatura: {e}")
            return None
    
    def _check_temperature_alerts(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Verifica alertas de temperatura"""
        alerts = []
        
        try:
            for source, temp_data in sample['temperatures'].items():
                current_temp = temp_data.get('current', 0)
                max_temp = temp_data.get('max', current_temp)
                
                # Verificar temperatura crítica
                if max_temp >= self.critical_temp_threshold:
                    alerts.append({
                        'timestamp': sample['timestamp'],
                        'level': 'CRITICAL',
                        'source': source,
                        'temperature': max_temp,
                        'threshold': self.critical_temp_threshold,
                        'message': f"Temperatura crítica detectada en {source}: {max_temp:.1f}°C"
                    })
                
                # Verificar temperatura de advertencia
                elif max_temp >= self.warning_temp_threshold:
                    alerts.append({
                        'timestamp': sample['timestamp'],
                        'level': 'WARNING',
                        'source': source,
                        'temperature': max_temp,
                        'threshold': self.warning_temp_threshold,
                        'message': f"Temperatura elevada en {source}: {max_temp:.1f}°C"
                    })
            
        except Exception as e:
            logger.error(f"Error verificando alertas de temperatura: {e}")
        
        return alerts
    
    def _calculate_temperature_statistics(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas de temperatura"""
        try:
            if not samples:
                return {}
            
            stats = {
                'total_samples': len(samples),
                'monitoring_duration': (len(samples) * self.sample_interval) / 60,  # minutos
                'temperature_sources': {},
                'overall': {}
            }
            
            # Organizar datos por fuente
            source_data = {}
            all_temps = []
            
            for sample in samples:
                for source, temp_data in sample['temperatures'].items():
                    if source not in source_data:
                        source_data[source] = []
                    
                    current_temp = temp_data.get('current', 0)
                    source_data[source].append(current_temp)
                    all_temps.append(current_temp)
            
            # Calcular estadísticas por fuente
            for source, temps in source_data.items():
                if temps:
                    source_stats = {
                        'average': sum(temps) / len(temps),
                        'min': min(temps),
                        'max': max(temps),
                        'samples': len(temps)
                    }
                    
                    if len(temps) > 1:
                        source_stats['std_dev'] = statistics.stdev(temps)
                        
                        # Tendencia
                        mid_point = len(temps) // 2
                        first_half_avg = sum(temps[:mid_point]) / mid_point if mid_point > 0 else 0
                        second_half_avg = sum(temps[mid_point:]) / (len(temps) - mid_point)
                        
                        if second_half_avg > first_half_avg + 1:
                            source_stats['trend'] = 'increasing'
                        elif second_half_avg < first_half_avg - 1:
                            source_stats['trend'] = 'decreasing'
                        else:
                            source_stats['trend'] = 'stable'
                    
                    stats['temperature_sources'][source] = source_stats
            
            # Estadísticas generales
            if all_temps:
                stats['overall'] = {
                    'average_temperature': sum(all_temps) / len(all_temps),
                    'min_temperature': min(all_temps),
                    'max_temperature': max(all_temps),
                    'total_readings': len(all_temps)
                }
                
                # Contar lecturas por rango de temperatura
                stats['overall']['temperature_distribution'] = {
                    'normal_0_50': sum(1 for t in all_temps if 0 <= t < 50),
                    'warm_50_70': sum(1 for t in all_temps if 50 <= t < 70),
                    'hot_70_85': sum(1 for t in all_temps if 70 <= t < 85),
                    'critical_85_plus': sum(1 for t in all_temps if t >= 85)
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculando estadísticas de temperatura: {e}")
            return {}

class CPUMonitoringTask(BaseTask):
    """Tarea para monitoreo detallado de CPU"""
    
    def __init__(self, monitoring_duration: int = 60):
        """
        Inicializa la tarea de monitoreo de CPU
        
        Args:
            monitoring_duration: Duración del monitoreo en segundos
        """
        super().__init__(
            name="Monitoreo de CPU",
            description=f"Monitoreo detallado de CPU por {monitoring_duration}s",
            priority=TaskPriority.NORMAL,
            timeout=monitoring_duration + 30
        )
        
        self.monitoring_duration = monitoring_duration
        self.sample_interval = 1  # segundo entre muestras
        self.high_usage_threshold = 80  # %
        self.critical_usage_threshold = 95  # %
        
    def execute(self) -> Dict[str, Any]:
        """Ejecuta el monitoreo de CPU"""
        try:
            logger.info(f"Iniciando monitoreo de CPU por {self.monitoring_duration}s...")
            
            start_time = time.time()
            samples_collected = 0
            cpu_data = {
                'monitoring_info': {
                    'start_time': datetime.now().isoformat(),
                    'duration_seconds': self.monitoring_duration,
                    'sample_interval': self.sample_interval,
                    'monitoring_type': 'cpu'
                },
                'cpu_info': {},
                'samples': [],
                'alerts': [],
                'statistics': {},
                'top_processes': []
            }
            
            # Obtener información básica de CPU
            cpu_data['cpu_info'] = self._get_cpu_info()
            
            # Loop de monitoreo
            while (time.time() - start_time) < self.monitoring_duration:
                if self.is_cancelled():
                    logger.info("Monitoreo de CPU cancelado")
                    break
                
                self.wait_if_paused()
                
                # Recopilar muestra de CPU
                sample = self._collect_cpu_sample()
                if sample:
                    cpu_data['samples'].append(sample)
                    samples_collected += 1
                    
                    # Verificar alertas de uso de CPU
                    alerts = self._check_cpu_alerts(sample)
                    cpu_data['alerts'].extend(alerts)
                    
                    # Añadir al colector global
                    performance_collector.add_sample('cpu_usage', sample['cpu_percent'])
                    performance_collector.add_sample('cpu_frequency', sample['frequency']['current'])
                    
                    # Añadir uso por núcleo
                    for i, usage in enumerate(sample['cpu_per_core']):
                        performance_collector.add_sample(f'cpu_core_{i}', usage)
                
                # Actualizar progreso
                elapsed = time.time() - start_time
                progress = min((elapsed / self.monitoring_duration) * 100, 100)
                self.update_progress(progress, f"Muestra {samples_collected}")
                
                # Esperar siguiente intervalo
                time.sleep(self.sample_interval)
            
            # Obtener procesos con mayor uso de CPU
            cpu_data['top_processes'] = self._get_top_cpu_processes()
            
            # Calcular estadísticas finales
            cpu_data['statistics'] = self._calculate_cpu_statistics(cpu_data['samples'])
            
            # Información final
            end_time = time.time()
            cpu_data['monitoring_info']['end_time'] = datetime.now().isoformat()
            cpu_data['monitoring_info']['actual_duration'] = end_time - start_time
            cpu_data['monitoring_info']['samples_collected'] = samples_collected
            cpu_data['monitoring_info']['alerts_generated'] = len(cpu_data['alerts'])
            
            logger.info(f"Monitoreo de CPU completado: {samples_collected} muestras, {len(cpu_data['alerts'])} alertas")
            
            return cpu_data
            
        except Exception as e:
            logger.error(f"Error en monitoreo de CPU: {e}")
            raise
    
    @timeout_decorator(10)
    def _get_cpu_info(self) -> Dict[str, Any]:
        """Obtiene información básica de CPU"""
        try:
            cpu_info = {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'cpu_frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {}
            }
            
            # Información adicional via WMI
            try:
                cpu_results = wmi_manager.query("SELECT * FROM Win32_Processor", timeout=10)
                if cpu_results:
                    cpu = cpu_results[0]
                    cpu_info.update({
                        'name': getattr(cpu, 'Name', 'Unknown'),
                        'manufacturer': getattr(cpu, 'Manufacturer', 'Unknown'),
                        'max_clock_speed': getattr(cpu, 'MaxClockSpeed', 0),
                        'current_clock_speed': getattr(cpu, 'CurrentClockSpeed', 0),
                        'architecture': getattr(cpu, 'Architecture', 'Unknown'),
                        'family': getattr(cpu, 'Family', 'Unknown'),
                        'l2_cache_size': getattr(cpu, 'L2CacheSize', 0),
                        'l3_cache_size': getattr(cpu, 'L3CacheSize', 0)
                    })
            except Exception as e:
                logger.debug(f"Error obteniendo info WMI de CPU: {e}")
            
            return cpu_info
            
        except Exception as e:
            logger.error(f"Error obteniendo información de CPU: {e}")
            return {}
    
    @timeout_decorator(5)
    def _collect_cpu_sample(self) -> Optional[Dict[str, Any]]:
        """Recopila una muestra de CPU"""
        try:
            # Recopilar datos de CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            cpu_times = psutil.cpu_times_percent(interval=0.1)
            cpu_freq = psutil.cpu_freq()
            cpu_stats = psutil.cpu_stats()
            
            sample = {
                'timestamp': datetime.now().isoformat(),
                'cpu_percent': cpu_percent,
                'cpu_per_core': cpu_per_core,
                'frequency': cpu_freq._asdict() if cpu_freq else {},
                'times_percent': cpu_times._asdict(),
                'stats': cpu_stats._asdict(),
                'load_average': None
            }
            
            # Load average (si está disponible en Windows)
            try:
                if hasattr(psutil, 'getloadavg'):
                    sample['load_average'] = psutil.getloadavg()
            except Exception:
                pass
            
            return sample
            
        except Exception as e:
            logger.error(f"Error recopilando muestra de CPU: {e}")
            return None
    
    def _check_cpu_alerts(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Verifica alertas de uso de CPU"""
        alerts = []
        
        try:
            cpu_usage = sample['cpu_percent']
            
            # Verificar uso crítico
            if cpu_usage >= self.critical_usage_threshold:
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': 'CRITICAL',
                    'metric': 'cpu_usage',
                    'value': cpu_usage,
                    'threshold': self.critical_usage_threshold,
                    'message': f"Uso crítico de CPU: {cpu_usage:.1f}%"
                })
            
            # Verificar uso alto
            elif cpu_usage >= self.high_usage_threshold:
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': 'WARNING',
                    'metric': 'cpu_usage',
                    'value': cpu_usage,
                    'threshold': self.high_usage_threshold,
                    'message': f"Uso alto de CPU: {cpu_usage:.1f}%"
                })
            
            # Verificar núcleos individuales
            for i, core_usage in enumerate(sample['cpu_per_core']):
                if core_usage >= self.critical_usage_threshold:
                    alerts.append({
                        'timestamp': sample['timestamp'],
                        'level': 'WARNING',
                        'metric': f'cpu_core_{i}',
                        'value': core_usage,
                        'threshold': self.critical_usage_threshold,
                        'message': f"Uso crítico en núcleo {i}: {core_usage:.1f}%"
                    })
            
        except Exception as e:
            logger.error(f"Error verificando alertas de CPU: {e}")
        
        return alerts
    
    @timeout_decorator(10)
    def _get_top_cpu_processes(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Obtiene los procesos con mayor uso de CPU"""
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username']):
                try:
                    pinfo = proc.info
                    if pinfo['cpu_percent'] and pinfo['cpu_percent'] > 0:
                        processes.append({
                            'pid': pinfo['pid'],
                            'name': pinfo['name'],
                            'cpu_percent': pinfo['cpu_percent'],
                            'memory_percent': pinfo['memory_percent'],
                            'username': pinfo['username'] or 'Unknown'
                        })
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # Ordenar por uso de CPU y tomar los primeros
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            return processes[:top_n]
            
        except Exception as e:
            logger.error(f"Error obteniendo top procesos CPU: {e}")
            return []
    
    def _calculate_cpu_statistics(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas de CPU"""
        try:
            if not samples:
                return {}
            
            # Extraer datos
            cpu_usages = [s['cpu_percent'] for s in samples]
            frequencies = [s['frequency'].get('current', 0) for s in samples if s['frequency']]
            
            stats = {
                'total_samples': len(samples),
                'cpu_usage': {
                    'average': sum(cpu_usages) / len(cpu_usages),
                    'min': min(cpu_usages),
                    'max': max(cpu_usages),
                    'std_dev': statistics.stdev(cpu_usages) if len(cpu_usages) > 1 else 0
                },
                'frequency': {},
                'core_statistics': {},
                'time_distribution': {}
            }
            
            # Estadísticas de frecuencia
            if frequencies:
                stats['frequency'] = {
                    'average': sum(frequencies) / len(frequencies),
                    'min': min(frequencies),
                    'max': max(frequencies)
                }
            
            # Estadísticas por núcleo
            core_count = len(samples[0]['cpu_per_core']) if samples else 0
            for i in range(core_count):
                core_usages = [s['cpu_per_core'][i] for s in samples]
                stats['core_statistics'][f'core_{i}'] = {
                    'average': sum(core_usages) / len(core_usages),
                    'min': min(core_usages),
                    'max': max(core_usages)
                }
            
            # Distribución de tiempo por rango de uso
            stats['time_distribution'] = {
                'low_0_25': sum(1 for u in cpu_usages if 0 <= u < 25),
                'medium_25_50': sum(1 for u in cpu_usages if 25 <= u < 50),
                'high_50_80': sum(1 for u in cpu_usages if 50 <= u < 80),
                'critical_80_plus': sum(1 for u in cpu_usages if u >= 80)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculando estadísticas de CPU: {e}")
            return {}

class MemoryMonitoringTask(BaseTask):
    """Tarea para monitoreo detallado de memoria"""
    
    def __init__(self, monitoring_duration: int = 60):
        """
        Inicializa la tarea de monitoreo de memoria
        
        Args:
            monitoring_duration: Duración del monitoreo en segundos
        """
        super().__init__(
            name="Monitoreo de Memoria",
            description=f"Monitoreo detallado de memoria por {monitoring_duration}s",
            priority=TaskPriority.NORMAL,
            timeout=monitoring_duration + 30
        )
        
        self.monitoring_duration = monitoring_duration
        self.sample_interval = 2  # segundos entre muestras
        self.high_usage_threshold = 80  # %
        self.critical_usage_threshold = 95  # %
        
    def execute(self) -> Dict[str, Any]:
        """Ejecuta el monitoreo de memoria"""
        try:
            logger.info(f"Iniciando monitoreo de memoria por {self.monitoring_duration}s...")
            
            start_time = time.time()
            samples_collected = 0
            memory_data = {
                'monitoring_info': {
                    'start_time': datetime.now().isoformat(),
                    'duration_seconds': self.monitoring_duration,
                    'sample_interval': self.sample_interval,
                    'monitoring_type': 'memory'
                },
                'memory_info': {},
                'samples': [],
                'alerts': [],
                'statistics': {},
                'top_processes': []
            }
            
            # Obtener información básica de memoria
            memory_data['memory_info'] = self._get_memory_info()
            
            # Loop de monitoreo
            while (time.time() - start_time) < self.monitoring_duration:
                if self.is_cancelled():
                    logger.info("Monitoreo de memoria cancelado")
                    break
                
                self.wait_if_paused()
                
                # Recopilar muestra de memoria
                sample = self._collect_memory_sample()
                if sample:
                    memory_data['samples'].append(sample)
                    samples_collected += 1
                    
                    # Verificar alertas de memoria
                    alerts = self._check_memory_alerts(sample)
                    memory_data['alerts'].extend(alerts)
                    
                    # Añadir al colector global
                    performance_collector.add_sample('memory_usage', sample['virtual']['percent'])
                    performance_collector.add_sample('memory_available', sample['virtual']['available'])
                    performance_collector.add_sample('swap_usage', sample['swap']['percent'])
                
                # Actualizar progreso
                elapsed = time.time() - start_time
                progress = min((elapsed / self.monitoring_duration) * 100, 100)
                self.update_progress(progress, f"Muestra {samples_collected}")
                
                # Esperar siguiente intervalo
                time.sleep(self.sample_interval)
            
            # Obtener procesos con mayor uso de memoria
            memory_data['top_processes'] = self._get_top_memory_processes()
            
            # Calcular estadísticas finales
            memory_data['statistics'] = self._calculate_memory_statistics(memory_data['samples'])
            
            # Información final
            end_time = time.time()
            memory_data['monitoring_info']['end_time'] = datetime.now().isoformat()
            memory_data['monitoring_info']['actual_duration'] = end_time - start_time
            memory_data['monitoring_info']['samples_collected'] = samples_collected
            memory_data['monitoring_info']['alerts_generated'] = len(memory_data['alerts'])
            
            logger.info(f"Monitoreo de memoria completado: {samples_collected} muestras, {len(memory_data['alerts'])} alertas")
            
            return memory_data
            
        except Exception as e:
            logger.error(f"Error en monitoreo de memoria: {e}")
            raise
    
    @timeout_decorator(10)
    def _get_memory_info(self) -> Dict[str, Any]:
        """Obtiene información básica de memoria"""
        try:
            virtual_memory = psutil.virtual_memory()
            swap_memory = psutil.swap_memory()
            
            memory_info = {
                'virtual_memory': {
                    'total': virtual_memory.total,
                    'total_formatted': SystemUtilities.format_bytes(virtual_memory.total)
                },
                'swap_memory': {
                    'total': swap_memory.total,
                    'total_formatted': SystemUtilities.format_bytes(swap_memory.total)
                }
            }
            
            # Información adicional via WMI
            try:
                memory_results = wmi_manager.query("SELECT * FROM Win32_PhysicalMemory", timeout=10)
                if memory_results:
                    memory_modules = []
                    total_physical = 0
                    
                    for memory in memory_results:
                        capacity = getattr(memory, 'Capacity', 0)
                        if isinstance(capacity, str):
                            capacity = int(capacity) if capacity.isdigit() else 0
                        
                        module_info = {
                            'capacity': capacity,
                            'capacity_formatted': SystemUtilities.format_bytes(capacity),
                            'speed': getattr(memory, 'Speed', 0),
                            'manufacturer': getattr(memory, 'Manufacturer', 'Unknown'),
                            'part_number': getattr(memory, 'PartNumber', 'Unknown'),
                            'device_locator': getattr(memory, 'DeviceLocator', 'Unknown')
                        }
                        
                        memory_modules.append(module_info)
                        total_physical += capacity
                    
                    memory_info['physical_modules'] = memory_modules
                    memory_info['total_physical'] = total_physical
                    memory_info['total_physical_formatted'] = SystemUtilities.format_bytes(total_physical)
                    memory_info['module_count'] = len(memory_modules)
                    
            except Exception as e:
                logger.debug(f"Error obteniendo info WMI de memoria: {e}")
            
            return memory_info
            
        except Exception as e:
            logger.error(f"Error obteniendo información de memoria: {e}")
            return {}
    
    @timeout_decorator(5)
    def _collect_memory_sample(self) -> Optional[Dict[str, Any]]:
        """Recopila una muestra de memoria"""
        try:
            virtual_memory = psutil.virtual_memory()
            swap_memory = psutil.swap_memory()
            
            sample = {
                'timestamp': datetime.now().isoformat(),
                'virtual': {
                    'total': virtual_memory.total,
                    'available': virtual_memory.available,
                    'used': virtual_memory.used,
                    'free': virtual_memory.free,
                    'percent': virtual_memory.percent,
                    'buffers': getattr(virtual_memory, 'buffers', 0),
                    'cached': getattr(virtual_memory, 'cached', 0)
                },
                'swap': {
                    'total': swap_memory.total,
                    'used': swap_memory.used,
                    'free': swap_memory.free,
                    'percent': swap_memory.percent,
                    'sin': getattr(swap_memory, 'sin', 0),
                    'sout': getattr(swap_memory, 'sout', 0)
                }
            }
            
            # Formatear tamaños para legibilidad
            for memory_type in ['virtual', 'swap']:
                for key in ['total', 'available', 'used', 'free']:
                    if key in sample[memory_type]:
                        sample[memory_type][f'{key}_formatted'] = SystemUtilities.format_bytes(
                            sample[memory_type][key]
                        )
            
            return sample
            
        except Exception as e:
            logger.error(f"Error recopilando muestra de memoria: {e}")
            return None
    
    def _check_memory_alerts(self, sample: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Verifica alertas de uso de memoria"""
        alerts = []
        
        try:
            virtual_usage = sample['virtual']['percent']
            swap_usage = sample['swap']['percent']
            
            # Verificar uso crítico de memoria virtual
            if virtual_usage >= self.critical_usage_threshold:
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': 'CRITICAL',
                    'metric': 'virtual_memory',
                    'value': virtual_usage,
                    'threshold': self.critical_usage_threshold,
                    'message': f"Uso crítico de memoria: {virtual_usage:.1f}%"
                })
            
            # Verificar uso alto de memoria virtual
            elif virtual_usage >= self.high_usage_threshold:
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': 'WARNING',
                    'metric': 'virtual_memory',
                    'value': virtual_usage,
                    'threshold': self.high_usage_threshold,
                    'message': f"Uso alto de memoria: {virtual_usage:.1f}%"
                })
            
            # Verificar uso de swap
            if swap_usage >= 50:  # Umbral más bajo para swap
                level = 'CRITICAL' if swap_usage >= 80 else 'WARNING'
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': level,
                    'metric': 'swap_memory',
                    'value': swap_usage,
                    'threshold': 50,
                    'message': f"Uso {'crítico' if level == 'CRITICAL' else 'alto'} de swap: {swap_usage:.1f}%"
                })
            
            # Verificar memoria disponible muy baja
            available_gb = sample['virtual']['available'] / (1024**3)
            if available_gb < 1:  # Menos de 1GB disponible
                alerts.append({
                    'timestamp': sample['timestamp'],
                    'level': 'CRITICAL',
                    'metric': 'available_memory',
                    'value': available_gb,
                    'threshold': 1,
                    'message': f"Memoria disponible muy baja: {available_gb:.2f} GB"
                })
            
        except Exception as e:
            logger.error(f"Error verificando alertas de memoria: {e}")
        
        return alerts
    
    @timeout_decorator(10)
    def _get_top_memory_processes(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Obtiene los procesos con mayor uso de memoria"""
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'memory_percent', 'username']):
                try:
                    pinfo = proc.info
                    if pinfo['memory_info']:
                        memory_mb = pinfo['memory_info'].rss / (1024 * 1024)
                        processes.append({
                            'pid': pinfo['pid'],
                            'name': pinfo['name'],
                            'memory_mb': round(memory_mb, 2),
                            'memory_formatted': SystemUtilities.format_bytes(pinfo['memory_info'].rss),
                            'memory_percent': pinfo['memory_percent'],
                            'username': pinfo['username'] or 'Unknown'
                        })
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            # Ordenar por uso de memoria y tomar los primeros
            processes.sort(key=lambda x: x['memory_mb'], reverse=True)
            return processes[:top_n]
            
        except Exception as e:
            logger.error(f"Error obteniendo top procesos memoria: {e}")
            return []
    
    def _calculate_memory_statistics(self, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula estadísticas de memoria"""
        try:
            if not samples:
                return {}
            
            # Extraer datos
            virtual_usages = [s['virtual']['percent'] for s in samples]
            swap_usages = [s['swap']['percent'] for s in samples]
            available_memory = [s['virtual']['available'] for s in samples]
            
            stats = {
                'total_samples': len(samples),
                'virtual_memory': {
                    'usage_percent': {
                        'average': sum(virtual_usages) / len(virtual_usages),
                        'min': min(virtual_usages),
                        'max': max(virtual_usages),
                        'std_dev': statistics.stdev(virtual_usages) if len(virtual_usages) > 1 else 0
                    },
                    'available_memory': {
                        'average': sum(available_memory) / len(available_memory),
                        'min': min(available_memory),
                        'max': max(available_memory),
                        'average_formatted': SystemUtilities.format_bytes(sum(available_memory) / len(available_memory)),
                        'min_formatted': SystemUtilities.format_bytes(min(available_memory)),
                        'max_formatted': SystemUtilities.format_bytes(max(available_memory))
                    }
                },
                'swap_memory': {
                    'usage_percent': {
                        'average': sum(swap_usages) / len(swap_usages),
                        'min': min(swap_usages),
                        'max': max(swap_usages),
                        'std_dev': statistics.stdev(swap_usages) if len(swap_usages) > 1 else 0
                    }
                },
                'usage_distribution': {}
            }
            
            # Distribución de uso
            stats['usage_distribution'] = {
                'low_0_50': sum(1 for u in virtual_usages if 0 <= u < 50),
                'medium_50_80': sum(1 for u in virtual_usages if 50 <= u < 80),
                'high_80_95': sum(1 for u in virtual_usages if 80 <= u < 95),
                'critical_95_plus': sum(1 for u in virtual_usages if u >= 95)
            }
            
            # Tendencias
            if len(virtual_usages) > 10:
                mid_point = len(virtual_usages) // 2
                first_half_avg = sum(virtual_usages[:mid_point]) / mid_point
                second_half_avg = sum(virtual_usages[mid_point:]) / (len(virtual_usages) - mid_point)
                
                if second_half_avg > first_half_avg + 5:
                    stats['memory_trend'] = 'increasing'
                elif second_half_avg < first_half_avg - 5:
                    stats['memory_trend'] = 'decreasing'
                else:
                    stats['memory_trend'] = 'stable'
                
                stats['trend_change_percent'] = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculando estadísticas de memoria: {e}")
            return {}

# Función para obtener datos del colector global
def get_performance_data() -> Dict[str, Any]:
    """Obtiene todos los datos de rendimiento recopilados"""
    try:
        data = performance_collector.get_all_data()
        
        # Añadir estadísticas calculadas
        statistics = {}
        for metric_name in data['metrics'].keys():
            statistics[metric_name] = performance_collector.get_statistics(metric_name)
        
        data['statistics'] = statistics
        return data
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de rendimiento: {e}")
        return {}

def clear_performance_data():
    """Limpia todos los datos de rendimiento"""
    try:
        performance_collector.clear_data()
        logger.info("Datos de rendimiento limpiados")
        
    except Exception as e:
        logger.error(f"Error limpiando datos de rendimiento: {e}")

# Función de inicialización
def initialize_monitoring_tasks():
    """Inicializa el sistema de tareas de monitoreo"""
    try:
        logger.info("Inicializando sistema de tareas de monitoreo...")
        
        # Verificar disponibilidad de psutil
        try:
            psutil.cpu_percent()
            psutil.virtual_memory()
            logger.info("psutil disponible y funcional")
        except Exception as e:
            logger.error(f"Error verificando psutil: {e}")
            return False
        
        # Inicializar colector de datos
        global performance_collector
        performance_collector = PerformanceDataCollector()
        logger.info("Colector de datos de rendimiento inicializado")
        
        logger.info("Sistema de tareas de monitoreo inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando tareas de monitoreo: {e}")
        return False

# Test de funcionalidad
def test_monitoring_tasks():
    """Prueba las tareas de monitoreo"""
    try:
        logger.info("Ejecutando pruebas de tareas de monitoreo...")
        
        # Prueba rápida de temperatura
        temp_task = TemperatureMonitoringTask(monitoring_duration=5)
        temp_result = temp_task.run()
        
        if temp_result.status.value == 'completed':
            logger.info("Prueba de monitoreo de temperatura exitosa")
        else:
            logger.warning(f"Prueba de temperatura: {temp_result.error}")
        
        # Prueba rápida de CPU
        cpu_task = CPUMonitoringTask(monitoring_duration=5)
        cpu_result = cpu_task.run()
        
        if cpu_result.status.value == 'completed':
            logger.info("Prueba de monitoreo de CPU exitosa")
            return True
        else:
            logger.error(f"Prueba de CPU falló: {cpu_result.error}")
            return False
            
    except Exception as e:
        logger.error(f"Error en pruebas de monitoreo: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_monitoring_tasks()