"""
Sistema de Monitoreo de PC - Módulo 9: Tareas de Servicios, EventLog y Startup
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Tareas para análisis de servicios del sistema, Event Log y programas de inicio
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
import subprocess
import winreg
import os

try:
    import psutil
    import wmi
    import win32service
    import win32serviceutil
    import win32con
    import win32api
    import win32evtlog
    import win32evtlogutil
    import win32security
    import win32process
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias de servicios y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, SecurityUtilities
)
from base_classes import BaseTask, TaskPriority, TaskStatus
from detailed_system_task import wmi_manager

# Logger para este módulo
logger = logging.getLogger(__name__)

class StartupProgramsTask(BaseTask):
    """Tarea para análisis de programas de inicio"""
    
    def __init__(self, check_registry_startup: bool = True,
                 check_startup_folders: bool = True,
                 check_scheduled_tasks: bool = True,
                 check_services_startup: bool = True):
        """
        Inicializa la tarea de análisis de programas de inicio
        
        Args:
            check_registry_startup: Verificar entradas del registro
            check_startup_folders: Verificar carpetas de inicio
            check_scheduled_tasks: Verificar tareas programadas
            check_services_startup: Verificar servicios de inicio automático
        """
        super().__init__(
            name="Análisis de Programas de Inicio",
            description="Análisis de programas que se ejecutan al inicio del sistema",
            priority=TaskPriority.NORMAL,
            timeout=SystemConfig.TASK_TIMEOUT
        )
        
        self.check_registry_startup = check_registry_startup
        self.check_startup_folders = check_startup_folders
        self.check_scheduled_tasks = check_scheduled_tasks
        self.check_services_startup = check_services_startup
        
        # Rutas del registro para programas de inicio
        self.registry_startup_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce")
        ]
        
        # Carpetas de inicio
        self.startup_folders = [
            os.path.join(os.getenv('APPDATA', ''), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup'),
            os.path.join(os.getenv('PROGRAMDATA', ''), 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')
        ]
    
    def execute(self) -> Dict[str, Any]:
        """Ejecuta el análisis de programas de inicio"""
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for StartupProgramsTask thread.")

            logger.info("Iniciando análisis de programas de inicio...")
            
            startup_data = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'startup_programs',
                    'options': {
                        'check_registry_startup': self.check_registry_startup,
                        'check_startup_folders': self.check_startup_folders,
                        'check_scheduled_tasks': self.check_scheduled_tasks,
                        'check_services_startup': self.check_services_startup
                    }
                },
                'registry_startup': [],
                'folder_startup': [],
                'scheduled_tasks': [],
                'auto_services': [],
                'startup_summary': {},
                'performance_impact': {},
                'security_analysis': {},
                'startup_recommendations': [],
                'errors': []
            }
            
            # Analizar entradas del registro
            if self.check_registry_startup:
                self.update_progress(20, "Analizando registro de inicio...")
                startup_data['registry_startup'] = self._analyze_registry_startup()
            
            # Analizar carpetas de inicio
            if self.check_startup_folders:
                self.update_progress(40, "Analizando carpetas de inicio...")
                startup_data['folder_startup'] = self._analyze_startup_folders()
            
            # Analizar tareas programadas
            if self.check_scheduled_tasks:
                self.update_progress(60, "Analizando tareas programadas...")
                startup_data['scheduled_tasks'] = self._analyze_scheduled_tasks()
            
            # Analizar servicios automáticos
            if self.check_services_startup:
                self.update_progress(75, "Analizando servicios automáticos...")
                startup_data['auto_services'] = self._analyze_auto_services()
            
            # Generar resumen
            self.update_progress(85, "Generando resumen...")
            startup_data['startup_summary'] = self._generate_startup_summary(startup_data)
            
            # Analizar impacto en rendimiento
            self.update_progress(90, "Analizando impacto en rendimiento...")
            startup_data['performance_impact'] = self._analyze_startup_performance_impact(startup_data)
            
            # Análisis de seguridad
            self.update_progress(95, "Analizando aspectos de seguridad...")
            startup_data['security_analysis'] = self._analyze_startup_security(startup_data)
            
            # Generar recomendaciones
            startup_data['startup_recommendations'] = self._generate_startup_recommendations(startup_data)
            
            # Información final
            startup_data['scan_info']['end_time'] = datetime.now().isoformat()
            
            self.update_progress(100, "Análisis completado")
            logger.info(f"Análisis de programas de inicio completado")
            
            return startup_data
            
        except Exception as e:
            logger.exception("Error en análisis de programas de inicio.") # Usar logger.exception
            raise
        finally:
            if initialized_com:
                pythoncom.CoUninitialize()
                logger.debug("COM uninitialized for StartupProgramsTask thread.")
    
    @timeout_decorator(30)
    def _analyze_registry_startup(self) -> List[Dict[str, Any]]:
        """Analiza entradas de inicio en el registro"""
        try:
            registry_entries = []
            
            for hkey, subkey in self.registry_startup_paths:
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    
                    # Obtener información sobre la clave
                    key_info = winreg.QueryInfoKey(key)
                    num_values = key_info[1]
                    
                    for i in range(num_values):
                        try:
                            value_name, value_data, value_type = winreg.EnumValue(key, i)
                            
                            entry = {
                                'name': value_name,
                                'command': value_data,
                                'registry_path': f"{self._get_hkey_name(hkey)}\\{subkey}",
                                'value_type': value_type,
                                'hkey': self._get_hkey_name(hkey),
                                'enabled': True,
                                'file_exists': False,
                                'file_info': {},
                                'security_risk': 'Unknown',
                                'category': self._categorize_startup_entry(value_name, value_data)
                            }
                            
                            # Verificar si el archivo existe
                            exe_path = self._extract_executable_path(value_data)
                            if exe_path and os.path.exists(exe_path):
                                entry['file_exists'] = True
                                entry['file_info'] = self._get_file_info(exe_path)
                            
                            # Evaluar riesgo de seguridad
                            entry['security_risk'] = self._evaluate_security_risk(entry)
                            
                            registry_entries.append(entry)
                            
                        except Exception as e:
                            logger.debug(f"Error leyendo valor del registro: {e}")
                            continue
                    
                    winreg.CloseKey(key)
                    
                except FileNotFoundError:
                    # La clave no existe
                    continue
                except Exception as e:
                    logger.debug(f"Error accediendo a {subkey}: {e}")
                    continue
            
            return registry_entries
            
        except Exception as e:
            logger.error(f"Error analizando registro de inicio: {e}")
            return []
    
    def _get_hkey_name(self, hkey) -> str:
        """Convierte handle de clave a nombre legible"""
        hkey_names = {
            winreg.HKEY_LOCAL_MACHINE: 'HKEY_LOCAL_MACHINE',
            winreg.HKEY_CURRENT_USER: 'HKEY_CURRENT_USER',
            winreg.HKEY_CLASSES_ROOT: 'HKEY_CLASSES_ROOT',
            winreg.HKEY_USERS: 'HKEY_USERS'
        }
        return hkey_names.get(hkey, 'UNKNOWN_HKEY')
    
    def _extract_executable_path(self, command: str) -> Optional[str]:
        """Extrae la ruta del ejecutable de un comando"""
        try:
            # Limpiar comillas
            command = command.strip('"\'')
            
            # Si tiene argumentos, tomar solo la primera parte
            if ' ' in command:
                parts = command.split(' ')
                potential_path = parts[0]
            else:
                potential_path = command
            
            # Verificar si es una ruta válida
            if os.path.isabs(potential_path) and potential_path.endswith('.exe'):
                return potential_path
            
            # Intentar con la ruta completa si tiene argumentos
            if ' -' in command or ' /' in command:
                # Buscar hasta el primer argumento
                for i, char in enumerate(command):
                    if char == ' ' and i > 0:
                        if command[i+1] in ['-', '/']:
                            potential_path = command[:i]
                            break
                
                if potential_path and os.path.exists(potential_path):
                    return potential_path
            
            return potential_path if os.path.exists(potential_path) else None
            
        except Exception:
            return None
    
    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Obtiene información detallada de un archivo"""
        try:
            file_info = {
                'size': 0,
                'size_formatted': '0 B',
                'version': 'Unknown',
                'company': 'Unknown',
                'description': 'Unknown',
                'created': 'Unknown',
                'modified': 'Unknown',
                'digital_signature': False
            }
            
            # Información básica del archivo
            stat_info = os.stat(file_path)
            file_info['size'] = stat_info.st_size
            file_info['size_formatted'] = SystemUtilities.format_bytes(stat_info.st_size)
            file_info['created'] = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
            file_info['modified'] = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
            
            # Información de versión (si está disponible)
            try:
                import win32api
                version_info = win32api.GetFileVersionInfo(file_path, "\\")
                
                # Obtener información de la empresa y descripción
                file_info['company'] = win32api.GetFileVersionInfo(file_path, "\\StringFileInfo\\040904b0\\CompanyName") or 'Unknown'
                file_info['description'] = win32api.GetFileVersionInfo(file_path, "\\StringFileInfo\\040904b0\\FileDescription") or 'Unknown'
                file_info['version'] = win32api.GetFileVersionInfo(file_path, "\\StringFileInfo\\040904b0\\FileVersion") or 'Unknown'
                
            except Exception as e:
                logger.debug(f"No se pudo obtener info de versión para {file_path}: {e}")
            
            return file_info
            
        except Exception as e:
            logger.debug(f"Error obteniendo info de archivo {file_path}: {e}")
            return {'size': 0, 'size_formatted': '0 B'}
    
    def _categorize_startup_entry(self, name: str, command: str) -> str:
        """Categoriza una entrada de inicio"""
        name_lower = name.lower()
        command_lower = command.lower()
        
        # Categorías de software conocido
        if any(x in name_lower for x in ['adobe', 'reader', 'acrobat']):
            return 'Adobe Products'
        elif any(x in name_lower for x in ['microsoft', 'office', 'teams']):
            return 'Microsoft Products'
        elif any(x in name_lower for x in ['google', 'chrome']):
            return 'Google Products'
        elif any(x in name_lower for x in ['antivirus', 'defender', 'security']):
            return 'Security Software'
        elif any(x in name_lower for x in ['driver', 'audio', 'video', 'graphics']):
            return 'Drivers & Hardware'
        elif any(x in name_lower for x in ['update', 'updater']):
            return 'Update Services'
        elif any(x in command_lower for x in ['temp', 'tmp', '%temp%']):
            return 'Potentially Suspicious'
        else:
            return 'Other Software'
    
    def _evaluate_security_risk(self, entry: Dict[str, Any]) -> str:
        """Evalúa el riesgo de seguridad de una entrada"""
        try:
            risk_factors = []
            
            # Verificar ubicación sospechosa
            command = entry.get('command', '').lower()
            if any(x in command for x in ['temp', 'tmp', 'appdata\\local\\temp']):
                risk_factors.append('Suspicious location')
            
            # Verificar extensiones peligrosas
            if any(x in command for x in ['.bat', '.cmd', '.vbs', '.js', '.jar']):
                risk_factors.append('Potentially dangerous file type')
            
            # Verificar si el archivo no existe
            if not entry.get('file_exists', False):
                risk_factors.append('File does not exist')
            
            # Verificar nombres sospechosos
            name = entry.get('name', '').lower()
            if any(x in name for x in ['svchost', 'system', 'windows', 'microsoft']) and 'microsoft' not in entry.get('file_info', {}).get('company', '').lower():
                risk_factors.append('Suspicious system-like name')
            
            # Verificar empresa desconocida para archivos críticos
            file_info = entry.get('file_info', {})
            company = file_info.get('company', '').lower()
            if company in ['unknown', ''] and entry.get('file_exists', False):
                risk_factors.append('Unknown publisher')
            
            # Determinar nivel de riesgo
            if len(risk_factors) >= 3:
                return 'High'
            elif len(risk_factors) >= 2:
                return 'Medium'
            elif len(risk_factors) >= 1:
                return 'Low'
            else:
                return 'Minimal'
                
        except Exception as e:
            logger.debug(f"Error evaluando riesgo de seguridad: {e}")
            return 'Unknown'
    
    @timeout_decorator(20)
    def _analyze_startup_folders(self) -> List[Dict[str, Any]]:
        """Analiza archivos en carpetas de inicio"""
        try:
            folder_entries = []
            
            for folder_path in self.startup_folders:
                if not os.path.exists(folder_path):
                    continue
                
                try:
                    for item in os.listdir(folder_path):
                        item_path = os.path.join(folder_path, item)
                        
                        if os.path.isfile(item_path):
                            entry = {
                                'name': item,
                                'path': item_path,
                                'folder': folder_path,
                                'type': 'file',
                                'file_info': self._get_file_info(item_path),
                                'security_risk': 'Unknown',
                                'category': self._categorize_startup_entry(item, item_path)
                            }
                            
                            # Evaluar riesgo
                            entry['security_risk'] = self._evaluate_security_risk({
                                'command': item_path,
                                'file_exists': True,
                                'file_info': entry['file_info'],
                                'name': item
                            })
                            
                            folder_entries.append(entry)
                            
                        elif os.path.isdir(item_path):
                            folder_entries.append({
                                'name': item,
                                'path': item_path,
                                'folder': folder_path,
                                'type': 'directory',
                                'file_info': {},
                                'security_risk': 'Low',
                                'category': 'Folder'
                            })
                
                except Exception as e:
                    logger.debug(f"Error analizando carpeta {folder_path}: {e}")
                    continue
            
            return folder_entries
            
        except Exception as e:
            logger.error(f"Error analizando carpetas de inicio: {e}")
            return []
    
    @timeout_decorator(45)
    def _analyze_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Analiza tareas programadas relacionadas con el inicio"""
        try:
            scheduled_tasks = []
            
            # Usar schtasks para obtener tareas
            try:
                result = subprocess.run(
                    ['schtasks', '/query', '/fo', 'csv', '/v'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        # Procesar CSV
                        headers = [h.strip('"') for h in lines[0].split('","')]
                        
                        for line in lines[1:]:
                            if not line.strip():
                                continue
                                
                            try:
                                # Parsear CSV manualmente
                                fields = []
                                current_field = ""
                                in_quotes = False
                                
                                for char in line:
                                    if char == '"':
                                        in_quotes = not in_quotes
                                    elif char == ',' and not in_quotes:
                                        fields.append(current_field)
                                        current_field = ""
                                    else:
                                        current_field += char
                                
                                if current_field:
                                    fields.append(current_field)
                                
                                if len(fields) >= len(headers):
                                    task_data = dict(zip(headers, fields))
                                    
                                    # Filtrar tareas relacionadas con inicio
                                    task_name = task_data.get('TaskName', '')
                                    status = task_data.get('Status', '')
                                    trigger = task_data.get('Trigger', '')
                                    
                                    if any(x in trigger.lower() for x in ['startup', 'logon', 'boot']) or \
                                       any(x in task_name.lower() for x in ['startup', 'logon', 'boot']):
                                        
                                        task_entry = {
                                            'name': task_name.replace('\\', ' - '),
                                            'status': status,
                                            'trigger': trigger,
                                            'last_run': task_data.get('Last Run Time', 'N/A'),
                                            'next_run': task_data.get('Next Run Time', 'N/A'),
                                            'author': task_data.get('Author', 'Unknown'),
                                            'action': task_data.get('Task To Run', 'Unknown'),
                                            'enabled': status.lower() == 'ready',
                                            'category': 'Scheduled Task',
                                            'security_risk': 'Low'
                                        }
                                        
                                        # Evaluar riesgo básico
                                        if 'unknown' in task_entry['author'].lower() or not task_entry['author']:
                                            task_entry['security_risk'] = 'Medium'
                                        
                                        scheduled_tasks.append(task_entry)
                                        
                            except Exception as e:
                                logger.debug(f"Error procesando línea de tarea: {e}")
                                continue
                
            except subprocess.TimeoutExpired:
                logger.warning("Timeout analizando tareas programadas")
            except Exception as e:
                logger.debug(f"Error ejecutando schtasks: {e}")
            
            return scheduled_tasks[:50]  # Limitar a 50 tareas
            
        except Exception as e:
            logger.error(f"Error analizando tareas programadas: {e}")
            return []
    
    @timeout_decorator(30)
    def _analyze_auto_services(self) -> List[Dict[str, Any]]:
        """Analiza servicios con inicio automático"""
        try:
            auto_services = []
            
            # Obtener servicios via WMI
            service_results = wmi_manager.query(
                "SELECT Name, DisplayName, StartMode, State, PathName, StartName FROM Win32_Service WHERE StartMode='Auto'"
            )
            
            for service in service_results:
                service_entry = {
                    'name': getattr(service, 'Name', 'Unknown'),
                    'display_name': getattr(service, 'DisplayName', 'Unknown'),
                    'start_mode': getattr(service, 'StartMode', 'Unknown'),
                    'state': getattr(service, 'State', 'Unknown'),
                    'path_name': getattr(service, 'PathName', 'Unknown'),
                    'start_name': getattr(service, 'StartName', 'Unknown'),
                    'running': getattr(service, 'State', '').lower() == 'running',
                    'category': 'Auto Service',
                    'security_risk': 'Low'
                }
                
                # Evaluar riesgo básico
                path_name = service_entry['path_name'].lower()
                if any(x in path_name for x in ['temp', 'tmp', 'appdata\\local']):
                    service_entry['security_risk'] = 'Medium'
                elif not os.path.exists(service_entry['path_name'].split(' ')[0].strip('"')):
                    service_entry['security_risk'] = 'High'
                
                auto_services.append(service_entry)
            
            return auto_services
            
        except Exception as e:
            logger.error(f"Error analizando servicios automáticos: {e}")
            return []
    
    def _generate_startup_summary(self, startup_data: Dict[str, Any]) -> Dict[str, Any]:
        """Genera resumen estadístico de programas de inicio"""
        try:
            summary = {
                'total_startup_items': 0,
                'registry_entries': len(startup_data.get('registry_startup', [])),
                'folder_entries': len(startup_data.get('folder_startup', [])),
                'scheduled_tasks': len(startup_data.get('scheduled_tasks', [])),
                'auto_services': len(startup_data.get('auto_services', [])),
                'security_risks': {'High': 0, 'Medium': 0, 'Low': 0, 'Minimal': 0},
                'categories': {},
                'enabled_items': 0,
                'disabled_items': 0,
                'missing_files': 0
            }
            
            all_items = (startup_data.get('registry_startup', []) +
                        startup_data.get('folder_startup', []) +
                        startup_data.get('scheduled_tasks', []) +
                        startup_data.get('auto_services', []))
            
            summary['total_startup_items'] = len(all_items)
            
            for item in all_items:
                # Contar por riesgo de seguridad
                risk = item.get('security_risk', 'Unknown')
                if risk in summary['security_risks']:
                    summary['security_risks'][risk] += 1
                
                # Contar por categoría
                category = item.get('category', 'Unknown')
                summary['categories'][category] = summary['categories'].get(category, 0) + 1
                
                # Contar habilitados/deshabilitados
                if item.get('enabled', True):
                    summary['enabled_items'] += 1
                else:
                    summary['disabled_items'] += 1
                
                # Contar archivos faltantes
                if not item.get('file_exists', True):
                    summary['missing_files'] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generando resumen de inicio: {e}")
            return {}
    
    def _analyze_startup_performance_impact(self, startup_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza el impacto en rendimiento de los programas de inicio"""
        try:
            performance_impact = {
                'estimated_boot_delay': 0,
                'high_impact_items': [],
                'total_startup_size': 0,
                'average_item_size': 0,
                'recommendations': []
            }
            
            total_size = 0
            item_count = 0
            
            all_items = (startup_data.get('registry_startup', []) +
                        startup_data.get('folder_startup', []))
            
            for item in all_items:
                file_info = item.get('file_info', {})
                file_size = file_info.get('size', 0)
                
                if file_size > 0:
                    total_size += file_size
                    item_count += 1
                    
                    # Elementos con alto impacto (archivos grandes)
                    if file_size > 50 * 1024 * 1024:  # > 50MB
                        performance_impact['high_impact_items'].append({
                            'name': item.get('name', 'Unknown'),
                            'size': file_size,
                            'size_formatted': SystemUtilities.format_bytes(file_size),
                            'category': item.get('category', 'Unknown')
                        })
            
            performance_impact['total_startup_size'] = total_size
            performance_impact['total_startup_size_formatted'] = SystemUtilities.format_bytes(total_size)
            
            if item_count > 0:
                performance_impact['average_item_size'] = total_size / item_count
                performance_impact['average_item_size_formatted'] = SystemUtilities.format_bytes(performance_impact['average_item_size'])
            
            # Estimación simple del retraso de inicio
            total_items = startup_data.get('startup_summary', {}).get('total_startup_items', 0)
            performance_impact['estimated_boot_delay'] = min(total_items * 0.5, 60)  # Max 60 segundos
            
            return performance_impact
            
        except Exception as e:
            logger.error(f"Error analizando impacto en rendimiento: {e}")
            return {}
    
    def _analyze_startup_security(self, startup_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analiza aspectos de seguridad de los programas de inicio"""
        try:
            security_analysis = {
                'high_risk_items': [],
                'unsigned_items': [],
                'suspicious_locations': [],
                'unknown_publishers': [],
                'overall_security_level': 'Good'
            }
            
            all_items = (startup_data.get('registry_startup', []) +
                        startup_data.get('folder_startup', []))
            
            high_risk_count = 0
            
            for item in all_items:
                risk = item.get('security_risk', 'Unknown')
                
                if risk == 'High':
                    high_risk_count += 1
                    security_analysis['high_risk_items'].append({
                        'name': item.get('name', 'Unknown'),
                        'location': item.get('command', item.get('path', 'Unknown')),
                        'category': item.get('category', 'Unknown'),
                        'risk_factors': 'High security risk detected'
                    })
                
                # Verificar elementos sin firma
                file_info = item.get('file_info', {})
                if not file_info.get('digital_signature', False) and item.get('file_exists', False):
                    security_analysis['unsigned_items'].append({
                        'name': item.get('name', 'Unknown'),
                        'path': item.get('command', item.get('path', 'Unknown'))
                    })
                
                # Verificar ubicaciones sospechosas
                command = item.get('command', item.get('path', '')).lower()
                if any(x in command for x in ['temp', 'tmp', 'appdata\\local\\temp']):
                    security_analysis['suspicious_locations'].append({
                        'name': item.get('name', 'Unknown'),
                        'location': command
                    })
                
                # Verificar publicadores desconocidos
                company = file_info.get('company', '').lower()
                if company in ['unknown', ''] and item.get('file_exists', False):
                    security_analysis['unknown_publishers'].append({
                        'name': item.get('name', 'Unknown'),
                        'path': item.get('command', item.get('path', 'Unknown'))
                    })
            
            # Determinar nivel general de seguridad
            if high_risk_count > 3:
                security_analysis['overall_security_level'] = 'Poor'
            elif high_risk_count > 1:
                security_analysis['overall_security_level'] = 'Fair'
            elif len(security_analysis['suspicious_locations']) > 2:
                security_analysis['overall_security_level'] = 'Fair'
            
            return security_analysis
            
        except Exception as e:
            logger.error(f"Error analizando seguridad de inicio: {e}")
            return {}
    
    def _generate_startup_recommendations(self, startup_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera recomendaciones para optimizar el inicio"""
        recommendations = []
        
        try:
            summary = startup_data.get('startup_summary', {})
            security_analysis = startup_data.get('security_analysis', {})
            performance_impact = startup_data.get('performance_impact', {})
            
            # Recomendaciones de seguridad
            high_risk_items = security_analysis.get('high_risk_items', [])
            if high_risk_items:
                recommendations.append({
                    'type': 'CRITICAL',
                    'category': 'security',
                    'title': f'{len(high_risk_items)} elementos de alto riesgo en inicio',
                    'description': 'Se detectaron programas de inicio con alto riesgo de seguridad',
                    'action': 'Revisar y eliminar elementos sospechosos inmediatamente',
                    'priority': 'CRITICAL'
                })
            
            # Recomendaciones de rendimiento
            total_items = summary.get('total_startup_items', 0)
            if total_items > 20:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'performance',
                    'title': f'Muchos programas de inicio ({total_items})',
                    'description': 'Gran cantidad de programas pueden ralentizar el inicio del sistema',
                    'action': 'Deshabilitar programas de inicio innecesarios',
                    'priority': 'MEDIUM'
                })
            
            # Recomendaciones por archivos faltantes
            missing_files = summary.get('missing_files', 0)
            if missing_files > 0:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'maintenance',
                    'title': f'{missing_files} entradas de inicio apuntan a archivos inexistentes',
                    'description': 'Entradas de registro obsoletas pueden causar errores',
                    'action': 'Limpiar entradas de registro obsoletas',
                    'priority': 'LOW'
                })
            
            # Recomendaciones por impacto en rendimiento
            high_impact_items = performance_impact.get('high_impact_items', [])
            if high_impact_items:
                recommendations.append({
                    'type': 'INFO',
                    'category': 'performance',
                    'title': f'{len(high_impact_items)} programas grandes en inicio',
                    'description': 'Programas grandes pueden ralentizar significativamente el inicio',
                    'action': 'Considerar deshabilitar programas pesados innecesarios',
                    'priority': 'LOW'
                })
            
            # Recomendaciones por ubicaciones sospechosas
            suspicious_locations = security_analysis.get('suspicious_locations', [])
            if suspicious_locations:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'security',
                    'title': f'{len(suspicious_locations)} programas en ubicaciones sospechosas',
                    'description': 'Programas ejecutándose desde carpetas temporales pueden ser maliciosos',
                    'action': 'Investigar y verificar legitimidad de estos programas',
                    'priority': 'MEDIUM'
                })
            
            # Recomendación positiva si todo está bien
            if not recommendations and total_items <= 15 and not high_risk_items:
                recommendations.append({
                    'type': 'SUCCESS',
                    'category': 'general',
                    'title': 'Configuración de inicio optimizada',
                    'description': f'Se detectaron {total_items} programas de inicio con configuración adecuada',
                    'action': 'Mantener monitoreo regular de programas de inicio',
                    'priority': 'LOW'
                })
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones de inicio: {e}")
            recommendations.append({
                'type': 'ERROR',
                'category': 'system',
                'title': 'Error generando recomendaciones',
                'description': f'Error interno: {str(e)}',
                'action': 'Revisar logs del sistema',
                'priority': 'LOW'
            })
        
        return recommendations

# Función de inicialización
def initialize_system_service_tasks():
    """Inicializa el sistema de tareas de servicios y logs"""
    try:
        logger.info("Inicializando sistema de tareas de servicios y logs...")
        
        # Verificar disponibilidad de APIs de Windows
        try:
            win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
            logger.info("APIs de servicios de Windows disponibles")
        except Exception as e:
            logger.error(f"Error verificando APIs de servicios: {e}")
            return False
        
        # Verificar acceso al Event Log
        try:
            log_handle = win32evtlog.OpenEventLog(None, "System")
            win32evtlog.CloseEventLog(log_handle)
            logger.info("Acceso al Event Log disponible")
        except Exception as e:
            logger.warning(f"Acceso limitado al Event Log: {e}")
        
        logger.info("Sistema de tareas de servicios y logs inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando tareas de servicios: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_system_service_tasks()