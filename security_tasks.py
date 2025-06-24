"""
Sistema de Monitoreo de PC - Módulo 8: Tareas de Seguridad (Antivirus y Windows Update)
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Tareas para verificación de antivirus, Windows Update y seguridad
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
import subprocess
import json
import winreg

try:
    import psutil
    import wmi
    import win32api
    import win32con
    import win32security
    import win32net
    import win32netcon
    import win32service
    import win32serviceutil
    import win32evtlog
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias de seguridad y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, SecurityUtilities
)
from base_classes import BaseTask, TaskPriority, TaskStatus
from detailed_system_task import wmi_manager

# Logger para este módulo
logger = logging.getLogger(__name__)

class AntivirusStatusTask(BaseTask):
    """Tarea para verificación del estado del antivirus"""
    
    def __init__(self, check_real_time_protection: bool = True,
                 check_definitions: bool = True,
                 check_scan_history: bool = True):
        """
        Inicializa la tarea de verificación de antivirus
        
        Args:
            check_real_time_protection: Verificar protección en tiempo real
            check_definitions: Verificar estado de definiciones
            check_scan_history: Verificar historial de escaneos
        """
        super().__init__(
            name="Verificación de Antivirus",
            description="Análisis completo del estado del antivirus",
            priority=TaskPriority.HIGH,
            timeout=SystemConfig.TASK_TIMEOUT
        )
        
        self.check_real_time_protection = check_real_time_protection
        self.check_definitions = check_definitions
        self.check_scan_history = check_scan_history
        
    def execute(self) -> Dict[str, Any]:
        """Ejecuta la verificación del antivirus"""
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for AntivirusStatusTask thread.")

            logger.info("Iniciando verificación de antivirus...")
            
            antivirus_data = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'antivirus_status',
                    'options': {
                        'check_real_time_protection': self.check_real_time_protection,
                        'check_definitions': self.check_definitions,
                        'check_scan_history': self.check_scan_history
                    }
                },
                'antivirus_products': [],
                'windows_defender': {},
                'security_center_status': {},
                'real_time_protection': {},
                'definitions_status': {},
                'scan_history': [],
                'security_recommendations': [],
                'overall_security_level': 'Unknown',
                'errors': []
            }
            
            # Detectar productos antivirus
            self.update_progress(20, "Detectando productos antivirus...")
            antivirus_data['antivirus_products'] = self._detect_antivirus_products()
            
            # Verificar Windows Defender específicamente
            self.update_progress(40, "Verificando Windows Defender...")
            antivirus_data['windows_defender'] = self._check_windows_defender()
            
            # Verificar Security Center
            self.update_progress(60, "Verificando Security Center...")
            antivirus_data['security_center_status'] = self._check_security_center()
            
            # Verificar protección en tiempo real
            if self.check_real_time_protection:
                self.update_progress(75, "Verificando protección en tiempo real...")
                antivirus_data['real_time_protection'] = self._check_real_time_protection()
            
            # Verificar estado de definiciones
            if self.check_definitions:
                self.update_progress(85, "Verificando definiciones...")
                antivirus_data['definitions_status'] = self._check_definitions_status()
            
            # Verificar historial de escaneos
            if self.check_scan_history:
                self.update_progress(90, "Verificando historial de escaneos...")
                antivirus_data['scan_history'] = self._check_scan_history()
            
            # Evaluar nivel de seguridad general
            self.update_progress(95, "Evaluando seguridad general...")
            antivirus_data['overall_security_level'] = self._evaluate_security_level(antivirus_data)
            
            # Generar recomendaciones
            antivirus_data['security_recommendations'] = self._generate_security_recommendations(antivirus_data)
            
            # Información final
            antivirus_data['scan_info']['end_time'] = datetime.now().isoformat()
            antivirus_data['scan_info']['products_detected'] = len(antivirus_data['antivirus_products'])
            
            self.update_progress(100, "Verificación completada")
            logger.info(f"Verificación de antivirus completada: {len(antivirus_data['antivirus_products'])} productos detectados")
            
            return antivirus_data
            
        except Exception as e:
            logger.exception("Error en verificación de antivirus.") # Usar logger.exception
            raise
        finally:
            if initialized_com:
                pythoncom.CoUninitialize()
                logger.debug("COM uninitialized for AntivirusStatusTask thread.")
    
    @timeout_decorator(30)
    def _detect_antivirus_products(self) -> List[Dict[str, Any]]:
        """Detecta productos antivirus instalados"""
        try:
            antivirus_products = []
            
            # Detectar via WMI Security Center
            try:
                security_center_results = wmi_manager.query(
                    "SELECT * FROM AntiVirusProduct",
                    timeout=15
                )
                
                if security_center_results:
                    for av_product in security_center_results:
                        product_info = {
                            'name': getattr(av_product, 'displayName', 'Unknown'),
                            'instance_guid': getattr(av_product, 'instanceGuid', ''),
                            'path_to_signed_product_exe': getattr(av_product, 'pathToSignedProductExe', ''),
                            'path_to_signed_reporting_exe': getattr(av_product, 'pathToSignedReportingExe', ''),
                            'product_state': getattr(av_product, 'productState', 0),
                            'timestamp': getattr(av_product, 'timestamp', ''),
                            'source': 'SecurityCenter2',
                            'enabled': False,
                            'up_to_date': False,
                            'status': 'Unknown'
                        }
                        
                        # Decodificar product_state
                        product_state = product_info['product_state']
                        if product_state:
                            product_info.update(self._decode_product_state(product_state))
                        
                        antivirus_products.append(product_info)
                        
            except Exception as e:
                logger.debug(f"Error detectando via SecurityCenter2: {e}")
            
            # Detectar productos específicos conocidos
            known_products = self._detect_known_antivirus()
            antivirus_products.extend(known_products)
            
            # Eliminar duplicados
            seen_names = set()
            unique_products = []
            for product in antivirus_products:
                if product['name'] not in seen_names:
                    unique_products.append(product)
                    seen_names.add(product['name'])
            
            return unique_products
            
        except Exception as e:
            logger.error(f"Error detectando productos antivirus: {e}")
            return []
    
    def _decode_product_state(self, product_state: int) -> Dict[str, Any]:
        """Decodifica el estado del producto antivirus"""
        try:
            state_info = {
                'enabled': False,
                'up_to_date': False,
                'status': 'Unknown'
            }
            
            if product_state:
                enabled_status = (product_state & 0x1000) != 0
                up_to_date_status = (product_state & 0x10) == 0
                
                state_info['enabled'] = enabled_status
                state_info['up_to_date'] = up_to_date_status
                
                if enabled_status and up_to_date_status:
                    state_info['status'] = 'Active and Updated'
                elif enabled_status and not up_to_date_status:
                    state_info['status'] = 'Active but Outdated'
                elif not enabled_status:
                    state_info['status'] = 'Disabled'
                else:
                    state_info['status'] = 'Unknown State'
            
            return state_info
            
        except Exception as e:
            logger.debug(f"Error decodificando product_state: {e}")
            return {'enabled': False, 'up_to_date': False, 'status': 'Unknown'}
    
    @timeout_decorator(20)
    def _detect_known_antivirus(self) -> List[Dict[str, Any]]:
        """Detecta productos antivirus conocidos por nombre de proceso/servicio"""
        try:
            known_products = []
            
            known_antivirus = {
                'avast': {'name': 'Avast Antivirus', 'processes': ['avast.exe', 'avastui.exe']},
                'avg': {'name': 'AVG Antivirus', 'processes': ['avg.exe', 'avgui.exe']},
                'norton': {'name': 'Norton Antivirus', 'processes': ['norton.exe', 'navapsvc.exe']},
                'mcafee': {'name': 'McAfee Antivirus', 'processes': ['mcafee.exe', 'mcshield.exe']},
                'kaspersky': {'name': 'Kaspersky', 'processes': ['kaspersky.exe', 'avp.exe']},
                'bitdefender': {'name': 'Bitdefender', 'processes': ['bitdefender.exe', 'vsserv.exe']},
                'eset': {'name': 'ESET NOD32', 'processes': ['nod32.exe', 'ekrn.exe']},
                'malwarebytes': {'name': 'Malwarebytes', 'processes': ['malwarebytes.exe', 'mbam.exe']},
                'trendmicro': {'name': 'Trend Micro', 'processes': ['trendmicro.exe', 'tmproxy.exe']},
                'sophos': {'name': 'Sophos', 'processes': ['sophos.exe', 'savservice.exe']}
            }
            
            # Obtener procesos en ejecución
            running_processes = [p.name().lower() for p in psutil.process_iter(['name'])]
            
            for av_key, av_info in known_antivirus.items():
                for process in av_info['processes']:
                    if process.lower() in running_processes:
                        product = {
                            'name': av_info['name'],
                            'source': 'process_detection',
                            'detected_process': process,
                            'enabled': True,
                            'up_to_date': 'Unknown',
                            'status': 'Running'
                        }
                        known_products.append(product)
                        break
            
            return known_products
            
        except Exception as e:
            logger.error(f"Error detectando antivirus conocidos: {e}")
            return []
    
    @timeout_decorator(30)
    def _check_windows_defender(self) -> Dict[str, Any]:
        """Verifica específicamente Windows Defender"""
        try:
            defender_info = {
                'installed': False,
                'enabled': False,
                'real_time_protection': False,
                'tamper_protection': False,
                'cloud_protection': False,
                'sample_submission': False,
                'version': 'Unknown',
                'engine_version': 'Unknown',
                'definitions_version': 'Unknown',
                'definitions_age': 'Unknown',
                'last_scan': 'Unknown',
                'scan_results': {},
                'status': 'Unknown'
            }
            
            try:
                # Verificar via PowerShell
                ps_command = 'Get-MpComputerStatus | ConvertTo-Json'
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0 and result.stdout:
                    defender_status = json.loads(result.stdout)
                    
                    defender_info.update({
                        'installed': True,
                        'enabled': defender_status.get('AntivirusEnabled', False),
                        'real_time_protection': defender_status.get('RealTimeProtectionEnabled', False),
                        'tamper_protection': defender_status.get('TamperProtectionEnabled', False),
                        'cloud_protection': defender_status.get('CloudProtectionEnabled', False),
                        'sample_submission': defender_status.get('SubmitSamplesConsent', False),
                        'engine_version': defender_status.get('AMEngineVersion', 'Unknown'),
                        'definitions_version': defender_status.get('AntivirusSignatureVersion', 'Unknown'),
                        'definitions_age': str(defender_status.get('AntivirusSignatureAge', 'Unknown')),
                        'last_scan': defender_status.get('LastFullScanStartTime', 'Unknown')
                    })
                    
                    # Determinar estado general
                    if defender_info['enabled'] and defender_info['real_time_protection']:
                        defender_info['status'] = 'Active'
                    elif defender_info['enabled']:
                        defender_info['status'] = 'Enabled but Limited Protection'
                    else:
                        defender_info['status'] = 'Disabled'
                        
            except subprocess.TimeoutExpired:
                logger.warning("Timeout verificando Windows Defender via PowerShell")
            except Exception as e:
                logger.debug(f"Error verificando Defender via PowerShell: {e}")
            
            # Fallback: verificar via WMI
            if not defender_info['installed']:
                try:
                    defender_results = wmi_manager.query(
                        "SELECT * FROM MSFT_MpComputerStatus",
                        timeout=10
                    )
                    
                    if defender_results:
                        defender_wmi = defender_results[0]
                        defender_info.update({
                            'installed': True,
                            'enabled': getattr(defender_wmi, 'AntivirusEnabled', False),
                            'real_time_protection': getattr(defender_wmi, 'RealTimeProtectionEnabled', False),
                            'version': getattr(defender_wmi, 'AMProductVersion', 'Unknown')
                        })
                        
                except Exception as e:
                    logger.debug(f"Error verificando Defender via WMI: {e}")
            
            # Verificar servicio de Windows Defender
            try:
                service_name = 'WinDefend'
                service_status = win32serviceutil.QueryServiceStatus(service_name)
                if service_status[1] == win32service.SERVICE_RUNNING:
                    defender_info['service_running'] = True
                else:
                    defender_info['service_running'] = False
                    
            except Exception as e:
                logger.debug(f"Error verificando servicio Defender: {e}")
                defender_info['service_running'] = 'Unknown'
            
            return defender_info
            
        except Exception as e:
            logger.error(f"Error verificando Windows Defender: {e}")
            return {'error': str(e)}
    
    @timeout_decorator(20)
    def _check_security_center(self) -> Dict[str, Any]:
        """Verifica el estado del Security Center de Windows"""
        try:
            security_center = {
                'firewall_status': 'Unknown',
                'antivirus_status': 'Unknown',
                'antispyware_status': 'Unknown',
                'automatic_updates_status': 'Unknown',
                'uac_status': 'Unknown',
                'internet_settings_status': 'Unknown',
                'overall_status': 'Unknown'
            }
            
            # Verificar estado del firewall
            try:
                firewall_results = wmi_manager.query(
                    "SELECT * FROM FirewallProduct",
                    timeout=10
                )
                
                if firewall_results:
                    firewall = firewall_results[0]
                    product_state = getattr(firewall, 'productState', 0)
                    security_center['firewall_status'] = 'Enabled' if (product_state & 0x1000) != 0 else 'Disabled'
                    
            except Exception as e:
                logger.debug(f"Error verificando firewall: {e}")
            
            # Verificar UAC via registro
            try:
                uac_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
                )
                
                uac_enabled = winreg.QueryValueEx(uac_key, "EnableLUA")[0]
                security_center['uac_status'] = 'Enabled' if uac_enabled else 'Disabled'
                winreg.CloseKey(uac_key)
                
            except Exception as e:
                logger.debug(f"Error verificando UAC: {e}")
            
            # Verificar Windows Update
            try:
                au_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update"
                )
                
                au_options = winreg.QueryValueEx(au_key, "AUOptions")[0]
                if au_options == 4:
                    security_center['automatic_updates_status'] = 'Automatic'
                elif au_options == 3:
                    security_center['automatic_updates_status'] = 'Download and Notify'
                elif au_options == 2:
                    security_center['automatic_updates_status'] = 'Notify Only'
                else:
                    security_center['automatic_updates_status'] = 'Disabled'
                    
                winreg.CloseKey(au_key)
                
            except Exception as e:
                logger.debug(f"Error verificando Windows Update: {e}")
            
            return security_center
            
        except Exception as e:
            logger.error(f"Error verificando Security Center: {e}")
            return {'error': str(e)}
    
    def _check_real_time_protection(self) -> Dict[str, Any]:
        """Verifica el estado de la protección en tiempo real"""
        try:
            protection_status = {
                'defender_real_time': False,
                'third_party_real_time': False,
                'overall_real_time': False,
                'protection_details': []
            }
            
            # Verificar Windows Defender real-time
            try:
                ps_command = 'Get-MpPreference | Select-Object DisableRealtimeMonitoring | ConvertTo-Json'
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    defender_prefs = json.loads(result.stdout)
                    protection_status['defender_real_time'] = not defender_prefs.get('DisableRealtimeMonitoring', True)
                    
            except Exception as e:
                logger.debug(f"Error verificando protección tiempo real Defender: {e}")
            
            # Verificar productos de terceros activos
            for product in self._detect_antivirus_products():
                if product.get('enabled', False) and 'real_time' in product.get('name', '').lower():
                    protection_status['third_party_real_time'] = True
                    protection_status['protection_details'].append({
                        'product': product['name'],
                        'real_time_enabled': True
                    })
            
            protection_status['overall_real_time'] = (
                protection_status['defender_real_time'] or 
                protection_status['third_party_real_time']
            )
            
            return protection_status
            
        except Exception as e:
            logger.error(f"Error verificando protección tiempo real: {e}")
            return {'error': str(e)}
    
    def _check_definitions_status(self) -> Dict[str, Any]:
        """Verifica el estado de las definiciones de antivirus"""
        try:
            definitions_status = {
                'defender_definitions': {},
                'last_update': 'Unknown',
                'update_frequency': 'Unknown',
                'definitions_age_days': 'Unknown',
                'update_source': 'Unknown',
                'status': 'Unknown'
            }
            
            try:
                # Verificar definiciones de Defender
                ps_command = 'Get-MpComputerStatus | Select-Object AntivirusSignatureVersion, AntivirusSignatureLastUpdated, AntivirusSignatureAge | ConvertTo-Json'
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    defender_defs = json.loads(result.stdout)
                    
                    definitions_status['defender_definitions'] = {
                        'version': defender_defs.get('AntivirusSignatureVersion', 'Unknown'),
                        'last_updated': defender_defs.get('AntivirusSignatureLastUpdated', 'Unknown'),
                        'age_days': defender_defs.get('AntivirusSignatureAge', 'Unknown')
                    }
                    
                    # Determinar estado basado en antigüedad
                    age_days = defender_defs.get('AntivirusSignatureAge', 999)
                    if isinstance(age_days, int):
                        if age_days <= 1:
                            definitions_status['status'] = 'Up to Date'
                        elif age_days <= 3:
                            definitions_status['status'] = 'Slightly Outdated'
                        elif age_days <= 7:
                            definitions_status['status'] = 'Outdated'
                        else:
                            definitions_status['status'] = 'Severely Outdated'
                        
                        definitions_status['definitions_age_days'] = age_days
                    
            except Exception as e:
                logger.debug(f"Error verificando definiciones Defender: {e}")
            
            return definitions_status
            
        except Exception as e:
            logger.error(f"Error verificando estado de definiciones: {e}")
            return {'error': str(e)}
    
    def _check_scan_history(self) -> List[Dict[str, Any]]:
        """Verifica el historial de escaneos de antivirus"""
        try:
            scan_history = []
            
            try:
                # Obtener historial de escaneos de Defender
                ps_command = 'Get-MpThreatDetection | Select-Object -First 10 | ConvertTo-Json'
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    detections = json.loads(result.stdout)
                    if not isinstance(detections, list):
                        detections = [detections]
                    
                    for detection in detections:
                        scan_entry = {
                            'product': 'Windows Defender',
                            'detection_time': detection.get('DetectionTime', 'Unknown'),
                            'threat_name': detection.get('ThreatName', 'Unknown'),
                            'severity': detection.get('SeverityID', 'Unknown'),
                            'action_taken': detection.get('ActionSuccess', 'Unknown'),
                            'resource': detection.get('Resources', 'Unknown')
                        }
                        scan_history.append(scan_entry)
                        
            except subprocess.TimeoutExpired:
                logger.warning("Timeout obteniendo historial de escaneos")
            except Exception as e:
                logger.debug(f"Error obteniendo historial Defender: {e}")
            
            # Verificar últimos escaneos via Event Log
            try:
                event_log_scans = self._get_scan_events_from_log()
                scan_history.extend(event_log_scans)
                
            except Exception as e:
                logger.debug(f"Error obteniendo eventos de escaneo: {e}")
            
            return scan_history[:10]  # Limitar a últimos 10
            
        except Exception as e:
            logger.error(f"Error verificando historial de escaneos: {e}")
            return []
    
    def _get_scan_events_from_log(self) -> List[Dict[str, Any]]:
        """Obtiene eventos de escaneo del Event Log"""
        try:
            scan_events = []
            
            # Abrir log de aplicaciones
            log_handle = win32evtlog.OpenEventLog(None, "Application")
            
            # Leer eventos recientes
            events = win32evtlog.ReadEventLog(
                log_handle,
                win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ,
                0
            )
            
            for event in events[:50]:  # Revisar últimos 50 eventos
                if 'antivirus' in str(event.StringInserts).lower() or 'defender' in str(event.StringInserts).lower():
                    event_info = {
                        'source': event.SourceName,
                        'event_id': event.EventID,
                        'time_generated': event.TimeGenerated.isoformat(),
                        'event_type': event.EventType,
                        'description': str(event.StringInserts) if event.StringInserts else 'No description'
                    }
                    scan_events.append(event_info)
            
            win32evtlog.CloseEventLog(log_handle)
            return scan_events
            
        except Exception as e:
            logger.debug(f"Error leyendo Event Log: {e}")
            return []
    
    def _evaluate_security_level(self, antivirus_data: Dict[str, Any]) -> str:
        """Evalúa el nivel general de seguridad"""
        try:
            score = 0
            max_score = 0
            
            # Evaluar productos antivirus (30 puntos)
            max_score += 30
            products = antivirus_data.get('antivirus_products', [])
            active_products = [p for p in products if p.get('enabled', False)]
            if active_products:
                score += 30
            elif products:
                score += 15
            
            # Evaluar Windows Defender (25 puntos)
            max_score += 25
            defender = antivirus_data.get('windows_defender', {})
            if defender.get('enabled', False) and defender.get('real_time_protection', False):
                score += 25
            elif defender.get('enabled', False):
                score += 15
            
            # Evaluar protección tiempo real (20 puntos)
            max_score += 20
            real_time = antivirus_data.get('real_time_protection', {})
            if real_time.get('overall_real_time', False):
                score += 20
            
            # Evaluar definiciones (15 puntos)
            max_score += 15
            definitions = antivirus_data.get('definitions_status', {})
            def_status = definitions.get('status', 'Unknown')
            if def_status == 'Up to Date':
                score += 15
            elif def_status == 'Slightly Outdated':
                score += 10
            elif def_status == 'Outdated':
                score += 5
            
            # Evaluar Security Center (10 puntos)
            max_score += 10
            security_center = antivirus_data.get('security_center_status', {})
            if security_center.get('firewall_status') == 'Enabled':
                score += 5
            if security_center.get('uac_status') == 'Enabled':
                score += 5
            
            # Calcular porcentaje
            security_percentage = (score / max_score) * 100 if max_score > 0 else 0
            
            # Determinar nivel
            if security_percentage >= 90:
                return 'Excellent'
            elif security_percentage >= 80:
                return 'Good'
            elif security_percentage >= 60:
                return 'Fair'
            elif security_percentage >= 40:
                return 'Poor'
            else:
                return 'Critical'
                
        except Exception as e:
            logger.error(f"Error evaluando nivel de seguridad: {e}")
            return 'Unknown'
    
    def _generate_security_recommendations(self, antivirus_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera recomendaciones de seguridad"""
        recommendations = []
        
        try:
            # Verificar si hay antivirus activo
            products = antivirus_data.get('antivirus_products', [])
            active_products = [p for p in products if p.get('enabled', False)]
            
            if not active_products:
                recommendations.append({
                    'type': 'CRITICAL',
                    'category': 'antivirus',
                    'title': 'Sin protección antivirus activa',
                    'description': 'No se detectó ningún antivirus activo en el sistema',
                    'action': 'Instalar y activar un antivirus confiable inmediatamente',
                    'priority': 'CRITICAL'
                })
            
            # Verificar protección tiempo real
            real_time = antivirus_data.get('real_time_protection', {})
            if not real_time.get('overall_real_time', False):
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'real_time_protection',
                    'title': 'Protección en tiempo real deshabilitada',
                    'description': 'La protección en tiempo real no está activa',
                    'action': 'Habilitar protección en tiempo real en su antivirus',
                    'priority': 'HIGH'
                })
            
            # Verificar definiciones
            definitions = antivirus_data.get('definitions_status', {})
            def_status = definitions.get('status', 'Unknown')
            
            if def_status in ['Outdated', 'Severely Outdated']:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'definitions',
                    'title': 'Definiciones de antivirus desactualizadas',
                    'description': f'Las definiciones están {def_status.lower()}',
                    'action': 'Actualizar definiciones de antivirus inmediatamente',
                    'priority': 'HIGH'
                })
            
            # Verificar Windows Defender
            defender = antivirus_data.get('windows_defender', {})
            if not defender.get('enabled', False) and not active_products:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'windows_defender',
                    'title': 'Windows Defender deshabilitado',
                    'description': 'Windows Defender está deshabilitado y no hay otros antivirus activos',
                    'action': 'Habilitar Windows Defender o instalar antivirus alternativo',
                    'priority': 'HIGH'
                })
            
            # Verificar Security Center
            security_center = antivirus_data.get('security_center_status', {})
            
            if security_center.get('firewall_status') != 'Enabled':
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'firewall',
                    'title': 'Firewall deshabilitado',
                    'description': 'El firewall de Windows no está activo',
                    'action': 'Habilitar el firewall de Windows',
                    'priority': 'MEDIUM'
                })
            
            if security_center.get('uac_status') != 'Enabled':
                recommendations.append({
                    'type': 'INFO',
                    'category': 'uac',
                    'title': 'Control de Cuentas de Usuario (UAC) deshabilitado',
                    'description': 'UAC proporciona una capa adicional de seguridad',
                    'action': 'Considerar habilitar UAC para mayor seguridad',
                    'priority': 'LOW'
                })
            
            # Recomendación general si todo está bien
            if not recommendations:
                recommendations.append({
                    'type': 'SUCCESS',
                    'category': 'general',
                    'title': 'Configuración de seguridad adecuada',
                    'description': 'El sistema tiene una configuración de seguridad apropiada',
                    'action': 'Mantener las definiciones actualizadas y realizar escaneos regulares',
                    'priority': 'LOW'
                })
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones de seguridad: {e}")
            recommendations.append({
                'type': 'ERROR',
                'category': 'system',
                'title': 'Error generando recomendaciones',
                'description': f'Error interno: {str(e)}',
                'action': 'Revisar logs del sistema',
                'priority': 'LOW'
            })
        
        return recommendations

class WindowsUpdateTask(BaseTask):
    """Tarea para verificación del estado de Windows Update"""
    
    def __init__(self, check_pending_updates: bool = True,
                 check_update_history: bool = True,
                 check_auto_update_settings: bool = True):
        """
        Inicializa la tarea de verificación de Windows Update
        
        Args:
            check_pending_updates: Verificar actualizaciones pendientes
            check_update_history: Verificar historial de actualizaciones
            check_auto_update_settings: Verificar configuración automática
        """
        super().__init__(
            name="Verificación de Windows Update",
            description="Análisis del estado de Windows Update",
            priority=TaskPriority.NORMAL,
            timeout=SystemConfig.TASK_TIMEOUT * 2
        )
        
        self.check_pending_updates = check_pending_updates
        self.check_update_history = check_update_history
        self.check_auto_update_settings = check_auto_update_settings
    
    def execute(self) -> Dict[str, Any]:
        """Ejecuta la verificación de Windows Update"""
        try:
            logger.info("Iniciando verificación de Windows Update...")
            
            update_data = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'windows_update',
                    'options': {
                        'check_pending_updates': self.check_pending_updates,
                        'check_update_history': self.check_update_history,
                        'check_auto_update_settings': self.check_auto_update_settings
                    }
                },
                'auto_update_settings': {},
                'pending_updates': [],
                'update_history': [],
                'last_check_time': 'Unknown',
                'last_install_time': 'Unknown',
                'reboot_required': False,
                'update_recommendations': [],
                'overall_update_status': 'Unknown',
                'errors': []
            }
            
            # Verificar configuración de actualizaciones automáticas
            if self.check_auto_update_settings:
                self.update_progress(20, "Verificando configuración de actualizaciones...")
                update_data['auto_update_settings'] = self._check_auto_update_settings()
            
            # Verificar actualizaciones pendientes
            if self.check_pending_updates:
                self.update_progress(50, "Verificando actualizaciones pendientes...")
                update_data['pending_updates'] = self._check_pending_updates()
                update_data['reboot_required'] = self._check_reboot_required()
            
            # Verificar historial de actualizaciones
            if self.check_update_history:
                self.update_progress(75, "Verificando historial de actualizaciones...")
                update_data['update_history'] = self._check_update_history()
            
            # Verificar tiempos de última verificación e instalación
            self.update_progress(85, "Verificando tiempos de actualización...")
            update_data['last_check_time'] = self._get_last_check_time()
            update_data['last_install_time'] = self._get_last_install_time()
            
            # Evaluar estado general
            self.update_progress(95, "Evaluando estado general...")
            update_data['overall_update_status'] = self._evaluate_update_status(update_data)
            
            # Generar recomendaciones
            update_data['update_recommendations'] = self._generate_update_recommendations(update_data)
            
            # Información final
            update_data['scan_info']['end_time'] = datetime.now().isoformat()
            update_data['scan_info']['pending_count'] = len(update_data['pending_updates'])
            update_data['scan_info']['history_count'] = len(update_data['update_history'])
            
            self.update_progress(100, "Verificación completada")
            logger.info(f"Verificación de Windows Update completada: {len(update_data['pending_updates'])} pendientes")
            
            return update_data
            
        except Exception as e:
            logger.error(f"Error en verificación de Windows Update: {e}")
            raise
    
    @timeout_decorator(30)
    def _check_auto_update_settings(self) -> Dict[str, Any]:
        """Verifica la configuración de actualizaciones automáticas"""
        try:
            settings = {
                'auto_update_enabled': False,
                'auto_update_option': 'Unknown',
                'maintenance_window': 'Unknown',
                'metered_connection_updates': False,
                'driver_updates': False,
                'other_products_updates': False,
                'notification_settings': 'Unknown'
            }
            
            try:
                # Verificar configuración via PowerShell
                ps_command = """
                $wu = New-Object -ComObject Microsoft.Update.AutoUpdate
                $settings = $wu.Settings
                @{
                    NotificationLevel = $settings.NotificationLevel
                    ReadOnly = $settings.ReadOnly
                    Required = $settings.Required
                } | ConvertTo-Json
                """
                
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    au_settings = json.loads(result.stdout)
                    notification_level = au_settings.get('NotificationLevel', 0)
                    
                    # Interpretar nivel de notificación
                    if notification_level == 0:
                        settings['auto_update_option'] = 'Not Configured'
                    elif notification_level == 1:
                        settings['auto_update_option'] = 'Disabled'
                    elif notification_level == 2:
                        settings['auto_update_option'] = 'Notify before download'
                    elif notification_level == 3:
                        settings['auto_update_option'] = 'Notify before install'
                    elif notification_level == 4:
                        settings['auto_update_option'] = 'Automatic'
                        settings['auto_update_enabled'] = True
                    elif notification_level == 5:
                        settings['auto_update_option'] = 'Users can configure'
                        
            except Exception as e:
                logger.debug(f"Error verificando configuración AU via PowerShell: {e}")
            
            # Verificar via registro como fallback
            try:
                au_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update"
                )
                
                try:
                    au_options = winreg.QueryValueEx(au_key, "AUOptions")[0]
                    if au_options == 4:
                        settings['auto_update_option'] = 'Automatic'
                        settings['auto_update_enabled'] = True
                    elif au_options == 3:
                        settings['auto_update_option'] = 'Download and notify'
                    elif au_options == 2:
                        settings['auto_update_option'] = 'Notify only'
                    else:
                        settings['auto_update_option'] = 'Disabled'
                except FileNotFoundError:
                    pass
                
                winreg.CloseKey(au_key)
                
            except Exception as e:
                logger.debug(f"Error verificando registro AU: {e}")
            
            # Verificar configuración moderna de Windows 10/11
            try:
                update_policy_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
                )
                
                try:
                    no_auto_update = winreg.QueryValueEx(update_policy_key, "NoAutoUpdate")[0]
                    settings['auto_update_enabled'] = not bool(no_auto_update)
                except FileNotFoundError:
                    pass
                
                winreg.CloseKey(update_policy_key)
                
            except Exception as e:
                logger.debug(f"Error verificando políticas de actualización: {e}")
            
            return settings
            
        except Exception as e:
            logger.error(f"Error verificando configuración de AU: {e}")
            return {'error': str(e)}
    
    @timeout_decorator(60)
    def _check_pending_updates(self) -> List[Dict[str, Any]]:
        """Verifica actualizaciones pendientes"""
        try:
            pending_updates = []
            
            try:
                # Usar PowerShell para verificar actualizaciones
                ps_command = """
                $Session = New-Object -ComObject Microsoft.Update.Session
                $Searcher = $Session.CreateUpdateSearcher()
                $SearchResult = $Searcher.Search("IsInstalled=0")
                
                $Updates = @()
                foreach ($Update in $SearchResult.Updates) {
                    $UpdateInfo = @{
                        Title = $Update.Title
                        Description = $Update.Description
                        Size = $Update.MaxDownloadSize
                        IsDownloaded = $Update.IsDownloaded
                        IsMandatory = $Update.IsMandatory
                        RebootRequired = $Update.RebootRequired
                        UpdateID = $Update.Identity.UpdateID
                        Categories = ($Update.Categories | ForEach-Object { $_.Name }) -join ", "
                        Severity = if ($Update.MsrcSeverity) { $Update.MsrcSeverity } else { "Unknown" }
                        PublishedDate = if ($Update.LastDeploymentChangeTime) { $Update.LastDeploymentChangeTime.ToString() } else { "Unknown" }
                    }
                    $Updates += $UpdateInfo
                }
                
                $Updates | ConvertTo-Json
                """
                
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=45
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    updates_json = result.stdout.strip()
                    if updates_json:
                        updates = json.loads(updates_json)
                        if not isinstance(updates, list):
                            updates = [updates]
                        
                        for update in updates:
                            update_info = {
                                'title': update.get('Title', 'Unknown'),
                                'description': update.get('Description', ''),
                                'size': update.get('Size', 0),
                                'size_formatted': SystemUtilities.format_bytes(update.get('Size', 0)),
                                'is_downloaded': update.get('IsDownloaded', False),
                                'is_mandatory': update.get('IsMandatory', False),
                                'reboot_required': update.get('RebootRequired', False),
                                'update_id': update.get('UpdateID', ''),
                                'categories': update.get('Categories', 'Unknown'),
                                'severity': update.get('Severity', 'Unknown'),
                                'published_date': update.get('PublishedDate', 'Unknown')
                            }
                            pending_updates.append(update_info)
                            
            except subprocess.TimeoutExpired:
                logger.warning("Timeout verificando actualizaciones pendientes")
            except Exception as e:
                logger.debug(f"Error verificando actualizaciones pendientes: {e}")
            
            return pending_updates
            
        except Exception as e:
            logger.error(f"Error obteniendo actualizaciones pendientes: {e}")
            return []
    
    @timeout_decorator(20)
    def _check_reboot_required(self) -> bool:
        """Verifica si se requiere reinicio"""
        try:
            # Verificar claves de registro que indican reinicio pendiente
            reboot_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\PendingFileRenameOperations")
            ]
            
            for hkey, subkey in reboot_keys:
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    winreg.CloseKey(key)
                    return True  # Si la clave existe, se requiere reinicio
                except FileNotFoundError:
                    continue
                except Exception:
                    continue
            
            # Verificar via PowerShell
            try:
                ps_command = """
                if (Get-ChildItem "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired" -ErrorAction SilentlyContinue) {
                    "True"
                } else {
                    "False"
                }
                """
                
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    return result.stdout.strip() == "True"
                    
            except Exception as e:
                logger.debug(f"Error verificando reinicio via PowerShell: {e}")
            
            return False
            
        except Exception as e:
            logger.debug(f"Error verificando reinicio requerido: {e}")
            return False
    
    @timeout_decorator(30)
    def _check_update_history(self) -> List[Dict[str, Any]]:
        """Verifica el historial de actualizaciones"""
        try:
            update_history = []
            
            try:
                # Obtener historial via PowerShell
                ps_command = """
                $Session = New-Object -ComObject Microsoft.Update.Session
                $Searcher = $Session.CreateUpdateSearcher()
                $HistoryCount = $Searcher.GetTotalHistoryCount()
                
                if ($HistoryCount -gt 0) {
                    $History = $Searcher.QueryHistory(0, [Math]::Min($HistoryCount, 20))
                    
                    $HistoryItems = @()
                    foreach ($Item in $History) {
                        $HistoryInfo = @{
                            Title = $Item.Title
                            Date = $Item.Date.ToString()
                            Operation = $Item.Operation
                            ResultCode = $Item.ResultCode
                            HResult = $Item.HResult
                            UpdateID = $Item.UpdateIdentity.UpdateID
                            Categories = if ($Item.Categories) { ($Item.Categories | ForEach-Object { $_.Name }) -join ", " } else { "Unknown" }
                        }
                        $HistoryItems += $HistoryInfo
                    }
                    
                    $HistoryItems | ConvertTo-Json
                }
                """
                
                result = subprocess.run(
                    ['powershell', '-Command', ps_command],
                    capture_output=True,
                    text=True,
                    timeout=20
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    history_json = result.stdout.strip()
                    if history_json:
                        history_items = json.loads(history_json)
                        if not isinstance(history_items, list):
                            history_items = [history_items]
                        
                        for item in history_items:
                            # Interpretar códigos de operación y resultado
                            operation_code = item.get('Operation', 0)
                            result_code = item.get('ResultCode', 0)
                            
                            operation_names = {
                                1: 'Installation',
                                2: 'Uninstallation',
                                3: 'Other'
                            }
                            
                            result_names = {
                                0: 'Not Started',
                                1: 'In Progress',
                                2: 'Succeeded',
                                3: 'Succeeded With Errors',
                                4: 'Failed',
                                5: 'Aborted'
                            }
                            
                            history_info = {
                                'title': item.get('Title', 'Unknown'),
                                'date': item.get('Date', 'Unknown'),
                                'operation': operation_names.get(operation_code, 'Unknown'),
                                'result': result_names.get(result_code, 'Unknown'),
                                'result_code': result_code,
                                'hresult': item.get('HResult', 0),
                                'update_id': item.get('UpdateID', ''),
                                'categories': item.get('Categories', 'Unknown'),
                                'success': result_code == 2
                            }
                            update_history.append(history_info)
                            
            except subprocess.TimeoutExpired:
                logger.warning("Timeout obteniendo historial de actualizaciones")
            except Exception as e:
                logger.debug(f"Error obteniendo historial de actualizaciones: {e}")
            
            return update_history
            
        except Exception as e:
            logger.error(f"Error verificando historial de actualizaciones: {e}")
            return []
    
    def _get_last_check_time(self) -> str:
        """Obtiene el tiempo de la última verificación de actualizaciones"""
        try:
            # Verificar via registro
            try:
                au_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Detect"
                )
                
                last_success_time = winreg.QueryValueEx(au_key, "LastSuccessTime")[0]
                winreg.CloseKey(au_key)
                
                # Convertir formato de tiempo de Windows
                return last_success_time
                
            except Exception as e:
                logger.debug(f"Error obteniendo último tiempo de verificación: {e}")
            
            return 'Unknown'
            
        except Exception as e:
            logger.debug(f"Error obteniendo tiempo de última verificación: {e}")
            return 'Unknown'
    
    def _get_last_install_time(self) -> str:
        """Obtiene el tiempo de la última instalación de actualizaciones"""
        try:
            # Verificar via registro
            try:
                au_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\Results\Install"
                )
                
                last_success_time = winreg.QueryValueEx(au_key, "LastSuccessTime")[0]
                winreg.CloseKey(au_key)
                
                return last_success_time
                
            except Exception as e:
                logger.debug(f"Error obteniendo último tiempo de instalación: {e}")
            
            return 'Unknown'
            
        except Exception as e:
            logger.debug(f"Error obteniendo tiempo de última instalación: {e}")
            return 'Unknown'
    
    def _evaluate_update_status(self, update_data: Dict[str, Any]) -> str:
        """Evalúa el estado general de las actualizaciones"""
        try:
            # Factores a considerar
            auto_update_enabled = update_data.get('auto_update_settings', {}).get('auto_update_enabled', False)
            pending_count = len(update_data.get('pending_updates', []))
            reboot_required = update_data.get('reboot_required', False)
            
            # Verificar actualizaciones críticas pendientes
            pending_updates = update_data.get('pending_updates', [])
            critical_pending = sum(1 for u in pending_updates if u.get('is_mandatory', False) or 'critical' in u.get('severity', '').lower())
            
            # Verificar historial reciente
            history = update_data.get('update_history', [])
            recent_failures = sum(1 for h in history[:5] if not h.get('success', False))  # Últimas 5
            
            # Evaluar estado
            if not auto_update_enabled and pending_count > 0:
                return 'Poor - Manual updates with pending items'
            elif critical_pending > 0:
                return 'Critical - Critical updates pending'
            elif pending_count > 10:
                return 'Poor - Many updates pending'
            elif reboot_required:
                return 'Warning - Reboot required'
            elif recent_failures > 2:
                return 'Warning - Recent update failures'
            elif pending_count > 0:
                return 'Good - Some updates pending'
            elif auto_update_enabled:
                return 'Excellent - Up to date with auto-updates'
            else:
                return 'Good - Up to date'
                
        except Exception as e:
            logger.error(f"Error evaluando estado de actualizaciones: {e}")
            return 'Unknown'
    
    def _generate_update_recommendations(self, update_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Genera recomendaciones para Windows Update"""
        recommendations = []
        
        try:
            auto_update_enabled = update_data.get('auto_update_settings', {}).get('auto_update_enabled', False)
            pending_updates = update_data.get('pending_updates', [])
            reboot_required = update_data.get('reboot_required', False)
            
            # Recomendar habilitar actualizaciones automáticas
            if not auto_update_enabled:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'auto_update',
                    'title': 'Actualizaciones automáticas deshabilitadas',
                    'description': 'Las actualizaciones automáticas no están habilitadas',
                    'action': 'Habilitar actualizaciones automáticas para mantener el sistema seguro',
                    'priority': 'HIGH'
                })
            
            # Recomendar instalar actualizaciones pendientes
            if pending_updates:
                critical_updates = [u for u in pending_updates if u.get('is_mandatory', False)]
                security_updates = [u for u in pending_updates if 'security' in u.get('categories', '').lower()]
                
                if critical_updates:
                    recommendations.append({
                        'type': 'CRITICAL',
                        'category': 'critical_updates',
                        'title': 'Actualizaciones críticas pendientes',
                        'description': f'{len(critical_updates)} actualizaciones críticas requieren instalación',
                        'action': 'Instalar actualizaciones críticas inmediatamente',
                        'priority': 'CRITICAL'
                    })
                
                if security_updates:
                    recommendations.append({
                        'type': 'WARNING',
                        'category': 'security_updates',
                        'title': 'Actualizaciones de seguridad pendientes',
                        'description': f'{len(security_updates)} actualizaciones de seguridad disponibles',
                        'action': 'Instalar actualizaciones de seguridad pronto',
                        'priority': 'HIGH'
                    })
                
                if len(pending_updates) > len(critical_updates) + len(security_updates):
                    other_count = len(pending_updates) - len(critical_updates) - len(security_updates)
                    recommendations.append({
                        'type': 'INFO',
                        'category': 'general_updates',
                        'title': 'Otras actualizaciones disponibles',
                        'description': f'{other_count} actualizaciones adicionales disponibles',
                        'action': 'Considerar instalar durante próximo mantenimiento',
                        'priority': 'LOW'
                    })
            
            # Recomendar reinicio si es necesario
            if reboot_required:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'reboot',
                    'title': 'Reinicio requerido',
                    'description': 'Se requiere reiniciar el sistema para completar las actualizaciones',
                    'action': 'Reiniciar el sistema cuando sea conveniente',
                    'priority': 'MEDIUM'
                })
            
            # Verificar historial de fallos
            history = update_data.get('update_history', [])
            recent_failures = [h for h in history[:5] if not h.get('success', False)]
            
            if len(recent_failures) > 2:
                recommendations.append({
                    'type': 'WARNING',
                    'category': 'update_failures',
                    'title': 'Fallos recientes en actualizaciones',
                    'description': f'{len(recent_failures)} actualizaciones fallaron recientemente',
                    'action': 'Revisar logs de Windows Update y considerar solución de problemas',
                    'priority': 'MEDIUM'
                })
            
            # Recomendación positiva si todo está bien
            if not recommendations:
                recommendations.append({
                    'type': 'SUCCESS',
                    'category': 'general',
                    'title': 'Sistema actualizado correctamente',
                    'description': 'Windows Update está funcionando correctamente',
                    'action': 'Mantener configuración actual y continuar con actualizaciones regulares',
                    'priority': 'LOW'
                })
            
        except Exception as e:
            logger.error(f"Error generando recomendaciones de actualización: {e}")
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
def initialize_security_tasks():
    """Inicializa el sistema de tareas de seguridad"""
    try:
        logger.info("Inicializando sistema de tareas de seguridad...")
        
        # Verificar disponibilidad de APIs de Windows
        try:
            win32api.GetVersion()
            logger.info("APIs de Windows disponibles")
        except Exception as e:
            logger.error(f"Error verificando APIs de Windows: {e}")
            return False
        
        logger.info("Sistema de tareas de seguridad inicializado correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error inicializando tareas de seguridad: {e}")
        return False

# Auto-inicialización
if __name__ != "__main__":
    initialize_security_tasks()