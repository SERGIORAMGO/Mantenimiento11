"""
Sistema de Monitoreo de PC - Módulo 15: Deployment y Distribución
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Módulo para empaquetado, distribución e instalación del sistema
"""

import os
import sys
import shutil
import zipfile
import tarfile
import json
import subprocess
import tempfile
import hashlib
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging
import platform
import urllib.request
import urllib.parse

# Importar módulos del sistema
from config_and_imports import SystemConfig, SystemConstants
from utilities import SystemUtilities, FileUtilities, SecurityUtilities
from main_runner import SystemMonitorRunner

# Logger para este módulo
logger = logging.getLogger(__name__)

class DeploymentPackager:
    """Empaquetador para distribución del sistema"""
    
    def __init__(self):
        """Inicializa el empaquetador"""
        self.version = SystemConfig.APP_VERSION
        self.author = "SERGIORAMGO"
        self.build_date = "2025-06-22"
        self.current_user = "SERGIORAMGO"
        
        # Configuración de empaquetado
        self.source_dir = Path(__file__).parent
        self.build_dir = Path("build")
        self.dist_dir = Path("dist")
        self.temp_dir = Path(tempfile.gettempdir()) / "sysmonitor_build"
        
        # Archivos a incluir
        self.module_files = [
            "config_and_imports.py",
            "utilities.py",
            "screenshot_capture.py",
            "base_classes.py",
            "detailed_system_task.py",
            "monitoring_tasks.py",
            "disk_storage_tasks.py",
            "security_tasks.py",
            "system_service_tasks.py",
            "basic_tasks.py",
            "main_interface.py",
            "gui_interface.py",
            "cli_interface.py",
            "main_runner.py",
            "deployment_and_distribution.py"
        ]
        
        # Archivos adicionales
        self.additional_files = [
            "README.md",
            "LICENSE.txt",
            "CHANGELOG.md",
            "requirements.txt"
        ]
        
        # Metadatos del paquete
        self.package_metadata = {
            "name": "SystemMonitor",
            "version": self.version,
            "author": self.author,
            "build_date": self.build_date,
            "current_user": self.current_user,
            "description": "Sistema de Monitoreo de PC completo",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": platform.system(),
            "architecture": platform.architecture()[0],
            "dependencies": [
                "psutil>=5.8.0",
                "pywin32>=227",
                "Pillow>=8.0.0",
                "tkinter"
            ]
        }
    
    def create_distribution_package(self, package_type: str = "zip", 
                                  include_installer: bool = True) -> str:
        """
        Crea paquete de distribución
        
        Args:
            package_type: Tipo de paquete ('zip', 'tar', 'exe', 'msi')
            include_installer: Incluir scripts de instalación
            
        Returns:
            Ruta del paquete creado
        """
        try:
            logger.info(f"Creando paquete de distribución tipo: {package_type}")
            
            # Preparar directorios
            self._prepare_build_environment()
            
            # Copiar archivos fuente
            self._copy_source_files()
            
            # Generar archivos adicionales
            self._generate_additional_files()
            
            # Crear scripts de instalación
            if include_installer:
                self._create_installation_scripts()
            
            # Crear documentación
            self._generate_documentation()
            
            # Empaquetar según tipo
            if package_type == "zip":
                package_path = self._create_zip_package()
            elif package_type == "tar":
                package_path = self._create_tar_package()
            elif package_type == "exe":
                package_path = self._create_exe_package()
            elif package_type == "msi":
                package_path = self._create_msi_package()
            else:
                raise ValueError(f"Tipo de paquete no soportado: {package_type}")
            
            # Generar checksums
            self._generate_checksums(package_path)
            
            logger.info(f"Paquete creado exitosamente: {package_path}")
            return str(package_path)
            
        except Exception as e:
            logger.error(f"Error creando paquete de distribución: {e}")
            raise
    
    def _prepare_build_environment(self):
        """Prepara el entorno de construcción"""
        try:
            # Limpiar directorios anteriores
            if self.build_dir.exists():
                shutil.rmtree(self.build_dir)
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
            
            # Crear directorios
            self.build_dir.mkdir(parents=True, exist_ok=True)
            self.dist_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Estructura del paquete
            package_structure = [
                "SystemMonitor",
                "SystemMonitor/modules",
                "SystemMonitor/docs",
                "SystemMonitor/scripts",
                "SystemMonitor/config",
                "SystemMonitor/templates"
            ]
            
            for dir_path in package_structure:
                (self.build_dir / dir_path).mkdir(parents=True, exist_ok=True)
            
            logger.info("Entorno de construcción preparado")
            
        except Exception as e:
            logger.error(f"Error preparando entorno: {e}")
            raise
    
    def _copy_source_files(self):
        """Copia archivos fuente al directorio de construcción"""
        try:
            dest_modules = self.build_dir / "SystemMonitor" / "modules"
            
            # Copiar módulos principales
            for module_file in self.module_files:
                src_path = self.source_dir / module_file
                if src_path.exists():
                    # Usar el nombre de archivo directamente ya que han sido renombrados
                    dest_path = dest_modules / module_file
                    shutil.copy2(src_path, dest_path)
                    logger.debug(f"Copiado: {module_file} -> {module_file}")
                else:
                    logger.warning(f"Archivo no encontrado: {module_file}")
            
            # Crear __init__.py para módulos
            init_content = f'''"""
Mantenimiento de PC v{self.version}
Autor: {self.author}
Fecha: {self.build_date}
Usuario: {self.current_user}
"""

__version__ = "{self.version}"
__author__ = "{self.author}"
__build_date__ = "{self.build_date}"

# Importaciones principales
from .config_and_imports import SystemConfig, SystemConstants
from .main_runner import SystemMonitorRunner, main

__all__ = [
    'SystemConfig', 'SystemConstants', 'SystemMonitorRunner', 'main'
]
'''
            
            with open(dest_modules / "__init__.py", "w", encoding="utf-8") as f:
                f.write(init_content)
            
            # Copiar archivo principal
            main_content = f'''#!/usr/bin/env python3
"""
Mantenimiento de PC - Punto de entrada principal
Autor: {self.author}
Fecha: {self.build_date}
"""

import sys
from pathlib import Path

# Agregar módulos al path
sys.path.insert(0, str(Path(__file__).parent / "modules"))

from main_runner import main # Actualizado

if __name__ == "__main__":
    main()
'''
            
            with open(self.build_dir / "SystemMonitor" / "main.py", "w", encoding="utf-8") as f:
                f.write(main_content)
            
            logger.info("Archivos fuente copiados")
            
        except Exception as e:
            logger.error(f"Error copiando archivos fuente: {e}")
            raise
    
    def _generate_additional_files(self):
        """Genera archivos adicionales necesarios"""
        try:
            base_dir = self.build_dir / "SystemMonitor"
            
            # README.md
            readme_content = f"""# Mantenimiento de PC v{self.version}

**Autor:** {self.author}  
**Fecha:** {self.build_date}  
**Usuario:** {self.current_user}

## Descripción

Sistema completo de monitoreo de PC para Windows que permite:

- ✅ Monitoreo en tiempo real de CPU, memoria y temperatura
- ✅ Análisis detallado del sistema y hardware
- ✅ Verificación de seguridad (antivirus, Windows Update)
- ✅ Análisis de servicios y programas de inicio
- ✅ Capturas de pantalla automáticas
- ✅ Generación de reportes detallados
- ✅ Interfaz gráfica (GUI) e interfaz de línea de comandos (CLI)

## Requisitos del Sistema

- **Sistema Operativo:** Windows 10/11 (recomendado)
- **Python:** 3.7 o superior
- **RAM:** Mínimo 2GB, recomendado 4GB
- **Espacio en disco:** 100MB libres
- **Privilegios:** Usuario estándar (algunos análisis requieren administrador)

## Instalación Rápida

### Opción 1: Instalador Automático
1. Ejecutar `install.bat` como administrador
2. Seguir las instrucciones en pantalla
3. El sistema se instalará en `%USERPROFILE%\\SystemMonitor`

### Opción 2: Instalación Manual
```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar sistema
python main.py