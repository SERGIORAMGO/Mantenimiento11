"""
Sistema de Monitoreo de PC - Módulo 10: Tareas Básicas del Sistema
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Implementación de tareas básicas para análisis rápido del sistema
"""

import time
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging
import platform
import socket
import os

try:
    import psutil
    import wmi
    import pythoncom # Importar pythoncom
except ImportError as e:
    logging.error(f"Error importando dependencias básicas y pythoncom: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SystemUtilities, PerformanceUtilities
)
from base_classes import BaseTask, TaskPriority, TaskStatus
from detailed_system_task import wmi_manager

# Logger para este módulo
logger = logging.getLogger(__name__)

class SystemInfoTask(BaseTask):
    """Tarea básica para obtener información rápida del sistema"""
    
    def __init__(self, include_processes: bool = True,
                 include_network: bool = True,
                 include_hardware_summary: bool = True):
        """
        Inicializa la tarea de información básica del sistema
        
        Args:
            include_processes: Incluir información de procesos
            include_network: Incluir información de red
            include_hardware_summary: Incluir resumen de hardware
        """
        super().__init__(
            name="Información Básica del Sistema",
            description="Recopilación rápida de información esencial del sistema",
            priority=TaskPriority.NORMAL,
            timeout=30  # Timeout más corto para tarea básica
        )
        
        self.include_processes = include_processes
        self.include_network = include_network
        self.include_hardware_summary = include_hardware_summary
    
    def execute(self) -> Dict[str, Any]:
        """Ejecuta la recopilación básica de información del sistema"""
        initialized_com = False
        try:
            # Inicializar COM para este hilo de tarea
            pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            initialized_com = True
            logger.debug("COM initialized for SystemInfoTask thread.")

            logger.info("Iniciando recopilación básica de información del sistema...")
            
            system_info = {
                'scan_info': {
                    'start_time': datetime.now().isoformat(),
                    'scan_type': 'basic_system_info