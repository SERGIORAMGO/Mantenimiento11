"""
Sistema de Monitoreo de PC - Módulo 3: Captura de Pantalla
Autor: SERGIORAMGO
Fecha: 2025-06-22
Descripción: Sistema de captura de pantalla con múltiples monitores y procesamiento
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import queue
import logging

try:
    from PIL import Image, ImageDraw, ImageFont, ImageGrab
    import tkinter as tk
    from tkinter import messagebox
    import win32gui
    import win32con
    import win32api
except ImportError as e:
    logging.error(f"Error importando dependencias para captura: {e}")

from config_and_imports import SystemConfig, SystemConstants
from utilities import (
    timeout_decorator, retry_decorator, log_execution_time,
    SecurityUtilities, FileUtilities, SystemUtilities, timer_context
)

# Logger para este módulo
logger = logging.getLogger(__name__)

class ScreenshotCapture:
    """Clase principal para captura de pantalla"""
    
    def __init__(self):
        self.capture_lock = threading.Lock()
        self.last_capture_time = 0
        self.capture_queue = queue.Queue()
        self.is_capturing = False
        self._setup_directories()
        
    def _setup_directories(self):
        """Configura los directorios necesarios"""
        try:
            FileUtilities.ensure_directory(SystemConfig.SCREENSHOTS_DIR)
            FileUtilities.ensure_directory(SystemConfig.TEMP_DIR)
            logger.debug("Directorios de captura configurados")
        except Exception as e:
            logger.error(f"Error configurando directorios: {e}")
    
    @timeout_decorator(SystemConfig.SCREENSHOT_TIMEOUT)
    @retry_decorator(max_retries=2, delay=0.5)
    @log_execution_time
    def capture_screenshot(self, 
                          monitor_index: Optional[int] = None,
                          include_cursor: bool = False,
                          add_timestamp: bool = True,
                          add_watermark: bool = True) -> Optional[Dict[str, Any]]:
        """
        Captura screenshot de uno o todos los monitores
        
        Args:
            monitor_index: Índice del monitor (None para todos)
            include_cursor: Incluir cursor en la captura
            add_timestamp: Añadir timestamp a la imagen
            add_watermark: Añadir marca de agua
            
        Returns:
            Diccionario con información de la captura
        """
        with self.capture_lock:
            try:
                self.is_capturing = True
                logger.info("Iniciando captura de pantalla...")
                
                monitors = self._get_monitor_info()
                if not monitors:
                    raise Exception("No se detectaron monitores")
                
                captured_images = []
                timestamp = datetime.now()
                
                if monitor_index is not None:
                    # Capturar monitor específico
                    if 0 <= monitor_index < len(monitors):
                        image_data = self._capture_monitor(
                            monitors[monitor_index], 
                            include_cursor,
                            add_timestamp,
                            add_watermark,
                            timestamp
                        )
                        if image_data:
                            captured_images.append(image_data)
                    else:
                        raise Exception(f"Índice de monitor inválido: {monitor_index}")
                else:
                    # Capturar todos los monitores
                    for i, monitor in enumerate(monitors):
                        try:
                            image_data = self._capture_monitor(
                                monitor, 
                                include_cursor,
                                add_timestamp,
                                add_watermark,
                                timestamp,
                                monitor_index=i
                            )
                            if image_data:
                                captured_images.append(image_data)
                        except Exception as e:
                            logger.warning(f"Error capturando monitor {i}: {e}")
                
                if not captured_images:
                    raise Exception("No se capturó ninguna imagen")
                
                # Crear imagen combinada si hay múltiples monitores
                combined_image = None
                if len(captured_images) > 1:
                    combined_image = self._combine_images(captured_images)
                
                result = {
                    'timestamp': timestamp,
                    'monitors_captured': len(captured_images),
                    'images': captured_images,
                    'combined_image': combined_image,
                    'total_monitors': len(monitors)
                }
                
                self.last_capture_time = time.time()
                logger.info(f"Captura completada: {len(captured_images)} imágenes")
                
                return result
                
            except Exception as e:
                logger.error(f"Error en captura de pantalla: {e}")
                return None
            finally:
                self.is_capturing = False
    
    def _get_monitor_info(self) -> List[Dict[str, Any]]:
        """
        Obtiene información de todos los monitores
        
        Returns:
            Lista de diccionarios con información de monitores
        """
        try:
            monitors = []
            
            def enum_callback(hmon, hdc, rect, data):
                monitor_info = win32api.GetMonitorInfo(hmon)
                monitor_rect = monitor_info['Monitor']
                work_rect = monitor_info['Work']
                
                monitors.append({
                    'handle': hmon,
                    'rect': monitor_rect,
                    'work_rect': work_rect,
                    'width': monitor_rect[2] - monitor_rect[0],
                    'height': monitor_rect[3] - monitor_rect[1],
                    'is_primary': monitor_info['Flags'] & win32con.MONITORINFOF_PRIMARY != 0,
                    'device_name': monitor_info.get('Device', f'Monitor_{len(monitors)}')
                })
                return True
            
            win32api.EnumDisplayMonitors(None, None, enum_callback, None)
            
            logger.debug(f"Detectados {len(monitors)} monitores")
            return monitors
            
        except Exception as e:
            logger.error(f"Error obteniendo información de monitores: {e}")
            # Fallback: usar información básica del monitor principal
            try:
                screen_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                screen_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                
                return [{
                    'handle': None,
                    'rect': (0, 0, screen_width, screen_height),
                    'work_rect': (0, 0, screen_width, screen_height),
                    'width': screen_width,
                    'height': screen_height,
                    'is_primary': True,
                    'device_name': 'Primary Monitor'
                }]
            except Exception as e2:
                logger.error(f"Error en fallback de monitor: {e2}")
                return []
    
    def _capture_monitor(self, 
                        monitor: Dict[str, Any], 
                        include_cursor: bool,
                        add_timestamp: bool,
                        add_watermark: bool,
                        timestamp: datetime,
                        monitor_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        Captura un monitor específico
        
        Args:
            monitor: Información del monitor
            include_cursor: Incluir cursor
            add_timestamp: Añadir timestamp
            add_watermark: Añadir marca de agua
            timestamp: Timestamp de la captura
            monitor_index: Índice del monitor
            
        Returns:
            Diccionario con datos de la imagen
        """
        try:
            rect = monitor['rect']
            
            # Capturar imagen
            if include_cursor:
                # Método más complejo para incluir cursor
                image = self._capture_with_cursor(rect)
            else:
                # Método simple sin cursor
                image = ImageGrab.grab(bbox=rect)
            
            if not image:
                raise Exception("No se pudo capturar la imagen")
            
            # Procesar imagen
            if add_timestamp or add_watermark:
                image = self._process_image(image, add_timestamp, add_watermark, timestamp, monitor_index)
            
            # Redimensionar si es necesario
            image = self._resize_if_needed(image)
            
            # Generar nombre de archivo
            filename = self._generate_filename(timestamp, monitor_index)
            filepath = SystemConfig.SCREENSHOTS_DIR / filename
            
            # Guardar imagen
            image.save(filepath, 
                      format=SystemConfig.SCREENSHOT_FORMAT,
                      quality=SystemConfig.SCREENSHOT_QUALITY,
                      optimize=True)
            
            # Información de la imagen
            image_info = {
                'monitor_index': monitor_index,
                'monitor_name': monitor['device_name'],
                'filepath': str(filepath),
                'filename': filename,
                'size': image.size,
                'file_size': FileUtilities.get_file_size(filepath),
                'file_size_formatted': SystemUtilities.format_bytes(FileUtilities.get_file_size(filepath)),
                'timestamp': timestamp,
                'rect': rect,
                'is_primary': monitor['is_primary']
            }
            
            logger.debug(f"Monitor {monitor_index} capturado: {filename}")
            return image_info
            
        except Exception as e:
            logger.error(f"Error capturando monitor {monitor_index}: {e}")
            return None
    
    def _capture_with_cursor(self, rect: Tuple[int, int, int, int]) -> Optional[Image.Image]:
        """
        Captura pantalla incluyendo el cursor
        
        Args:
            rect: Rectángulo del área a capturar
            
        Returns:
            Imagen PIL con cursor
        """
        try:
            # Capturar pantalla sin cursor
            image = ImageGrab.grab(bbox=rect)
            
            # Obtener información del cursor
            cursor_info = win32gui.GetCursorInfo()
            if cursor_info[0] == 0:  # Cursor no visible
                return image
            
            cursor_pos = cursor_info[1]
            cursor_handle = cursor_info[2]
            
            # Ajustar posición del cursor al rectángulo
            cursor_x = cursor_pos[0] - rect[0]
            cursor_y = cursor_pos[1] - rect[1]
            
            # Verificar si el cursor está dentro del área capturada
            if (0 <= cursor_x <= rect[2] - rect[0] and 
                0 <= cursor_y <= rect[3] - rect[1]):
                
                # Obtener información del cursor
                try:
                    icon_info = win32gui.GetIconInfo(cursor_handle)
                    cursor_bitmap = icon_info[4] if icon_info[4] else icon_info[3]
                    
                    if cursor_bitmap:
                        # Convertir bitmap a imagen PIL (implementación simplificada)
                        # En una implementación completa, aquí se convertiría el bitmap
                        # Por ahora, dibujamos un indicador simple
                        draw = ImageDraw.Draw(image)
                        draw.ellipse([cursor_x-5, cursor_y-5, cursor_x+5, cursor_y+5], 
                                   fill='red', outline='black', width=2)
                        
                except Exception as e:
                    logger.debug(f"No se pudo dibujar cursor real, usando indicador: {e}")
                    # Dibujar indicador simple del cursor
                    draw = ImageDraw.Draw(image)
                    draw.ellipse([cursor_x-3, cursor_y-3, cursor_x+3, cursor_y+3], 
                               fill='red', outline='white', width=1)
            
            return image
            
        except Exception as e:
            logger.warning(f"Error capturando con cursor: {e}")
            # Fallback: captura sin cursor
            return ImageGrab.grab(bbox=rect)
    
    def _process_image(self, 
                      image: Image.Image, 
                      add_timestamp: bool,
                      add_watermark: bool,
                      timestamp: datetime,
                      monitor_index: int) -> Image.Image:
        """
        Procesa la imagen añadiendo timestamp y marca de agua
        
        Args:
            image: Imagen a procesar
            add_timestamp: Añadir timestamp
            add_watermark: Añadir marca de agua
            timestamp: Timestamp de la captura
            monitor_index: Índice del monitor
            
        Returns:
            Imagen procesada
        """
        try:
            draw = ImageDraw.Draw(image)
            
            # Intentar cargar fuente personalizada
            try:
                font_size = max(12, min(24, image.height // 50))
                font = ImageFont.truetype("arial.ttf", font_size)
                small_font = ImageFont.truetype("arial.ttf", max(8, font_size - 4))
            except Exception:
                # Usar fuente por defecto
                font = ImageFont.load_default()
                small_font = font
            
            # Añadir timestamp
            if add_timestamp:
                timestamp_text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                monitor_text = f"Monitor {monitor_index + 1}"
                
                # Calcular posición (esquina superior izquierda)
                bbox = draw.textbbox((0, 0), timestamp_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Fondo semi-transparente para el texto
                padding = 5
                bg_rect = [
                    padding, 
                    padding, 
                    text_width + padding * 2, 
                    text_height * 2 + padding * 3
                ]
                
                # Crear imagen temporal para el fondo transparente
                overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                
                # Dibujar fondo
                overlay_draw.rectangle(bg_rect, fill=(0, 0, 0, 128))
                
                # Combinar con la imagen original
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                image = Image.alpha_composite(image, overlay)
                
                # Dibujar texto
                draw = ImageDraw.Draw(image)
                draw.text((padding * 2, padding * 2), timestamp_text, 
                         fill=(255, 255, 255, 255), font=font)
                draw.text((padding * 2, padding * 2 + text_height + 2), monitor_text, 
                         fill=(200, 200, 200, 255), font=small_font)
            
            # Añadir marca de agua
            if add_watermark:
                watermark_text = f"{SystemConfig.APP_NAME} v{SystemConfig.APP_VERSION}"
                
                # Posición en esquina inferior derecha
                bbox = draw.textbbox((0, 0), watermark_text, font=small_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = image.width - text_width - 10
                y = image.height - text_height - 10
                
                # Dibujar con transparencia
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                
                overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.text((x, y), watermark_text, 
                                fill=(255, 255, 255, 100), font=small_font)
                
                image = Image.alpha_composite(image, overlay)
            
            # Convertir de vuelta a RGB si no se necesita transparencia
            if image.mode == 'RGBA':
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            
            return image
            
        except Exception as e:
            logger.warning(f"Error procesando imagen: {e}")
            return image
    
    def _resize_if_needed(self, image: Image.Image) -> Image.Image:
        """
        Redimensiona la imagen si excede el tamaño máximo
        
        Args:
            image: Imagen a redimensionar
            
        Returns:
            Imagen redimensionada
        """
        try:
            max_width, max_height = SystemConfig.MAX_SCREENSHOT_SIZE
            
            if image.width <= max_width and image.height <= max_height:
                return image
            
            # Calcular nueva escala manteniendo aspecto
            scale_x = max_width / image.width
            scale_y = max_height / image.height
            scale = min(scale_x, scale_y)
            
            new_width = int(image.width * scale)
            new_height = int(image.height * scale)
            
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"Imagen redimensionada de {image.size} a {resized_image.size}")
            
            return resized_image
            
        except Exception as e:
            logger.warning(f"Error redimensionando imagen: {e}")
            return image
    
    def _combine_images(self, image_data_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Combina múltiples imágenes en una sola
        
        Args:
            image_data_list: Lista de datos de imágenes
            
        Returns:
            Diccionario con información de la imagen combinada
        """
        try:
            if len(image_data_list) <= 1:
                return None
            
            # Cargar imágenes
            images = []
            for img_data in image_data_list:
                try:
                    img = Image.open(img_data['filepath'])
                    images.append((img, img_data))
                except Exception as e:
                    logger.warning(f"Error cargando imagen {img_data['filepath']}: {e}")
            
            if not images:
                return None
            
            # Calcular disposición (horizontal si hay pocos monitores, grid si hay muchos)
            if len(images) <= 2:
                # Disposición horizontal
                total_width = sum(img.width for img, _ in images)
                max_height = max(img.height for img, _ in images)
                
                combined = Image.new('RGB', (total_width, max_height), (0, 0, 0))
                
                x_offset = 0
                for img, img_data in images:
                    combined.paste(img, (x_offset, 0))
                    x_offset += img.width
                    
            else:
                # Disposición en grid
                cols = 2 if len(images) <= 4 else 3
                rows = (len(images) + cols - 1) // cols
                
                # Encontrar tamaño máximo
                max_img_width = max(img.width for img, _ in images)
                max_img_height = max(img.height for img, _ in images)
                
                total_width = max_img_width * cols
                total_height = max_img_height * rows
                
                combined = Image.new('RGB', (total_width, total_height), (0, 0, 0))
                
                for i, (img, img_data) in enumerate(images):
                    row = i // cols
                    col = i % cols
                    
                    x = col * max_img_width
                    y = row * max_img_height
                    
                    # Centrar imagen en su celda
                    x_offset = (max_img_width - img.width) // 2
                    y_offset = (max_img_height - img.height) // 2
                    
                    combined.paste(img, (x + x_offset, y + y_offset))
            
            # Generar nombre para imagen combinada
            timestamp = image_data_list[0]['timestamp']
            filename = self._generate_filename(timestamp, suffix='combined')
            filepath = SystemConfig.SCREENSHOTS_DIR / filename
            
            # Guardar imagen combinada
            combined.save(filepath, 
                         format=SystemConfig.SCREENSHOT_FORMAT,
                         quality=SystemConfig.SCREENSHOT_QUALITY,
                         optimize=True)
            
            combined_info = {
                'filepath': str(filepath),
                'filename': filename,
                'size': combined.size,
                'file_size': FileUtilities.get_file_size(filepath),
                'file_size_formatted': SystemUtilities.format_bytes(FileUtilities.get_file_size(filepath)),
                'monitors_combined': len(images),
                'timestamp': timestamp
            }
            
            logger.info(f"Imagen combinada creada: {filename}")
            return combined_info
            
        except Exception as e:
            logger.error(f"Error combinando imágenes: {e}")
            return None
    
    def _generate_filename(self, timestamp: datetime, monitor_index: int = None, suffix: str = None) -> str:
        """
        Genera nombre de archivo para la captura
        
        Args:
            timestamp: Timestamp de la captura
            monitor_index: Índice del monitor
            suffix: Sufijo adicional
            
        Returns:
            Nombre de archivo
        """
        try:
            # Formato base: screenshot_YYYYMMDD_HHMMSS
            base_name = f"screenshot_{timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            # Añadir índice de monitor
            if monitor_index is not None:
                base_name += f"_monitor{monitor_index + 1}"
            
            # Añadir sufijo
            if suffix:
                base_name += f"_{suffix}"
            
            # Añadir extensión
            extension = SystemConfig.SCREENSHOT_FORMAT.lower()
            filename = f"{base_name}.{extension}"
            
            # Asegurar que el nombre es único
            filepath = SystemConfig.SCREENSHOTS_DIR / filename
            if filepath.exists():
                counter = 1
                while True:
                    new_filename = f"{base_name}_{counter}.{extension}"
                    new_filepath = SystemConfig.SCREENSHOTS_DIR / new_filename
                    if not new_filepath.exists():
                        filename = new_filename
                        break
                    counter += 1
            
            return SecurityUtilities.sanitize_filename(filename)
            
        except Exception as e:
            logger.error(f"Error generando nombre de archivo: {e}")
            return f"screenshot_{int(time.time())}.png"
    
    def capture_window(self, window_title: str = None, window_handle: int = None) -> Optional[Dict[str, Any]]:
        """
        Captura una ventana específica
        
        Args:
            window_title: Título de la ventana
            window_handle: Handle de la ventana
            
        Returns:
            Diccionario con información de la captura
        """
        try:
            if not window_handle and not window_title:
                raise ValueError("Se debe especificar window_title o window_handle")
            
            # Encontrar ventana
            if not window_handle:
                window_handle = win32gui.FindWindow(None, window_title)
            
            if not window_handle:
                raise Exception(f"No se encontró ventana: {window_title}")
            
            # Obtener rectángulo de la ventana
            window_rect = win32gui.GetWindowRect(window_handle)
            
            # Verificar si la ventana es visible
            if not win32gui.IsWindowVisible(window_handle):
                raise Exception("La ventana no es visible")
            
            # Traer ventana al frente
            win32gui.SetForegroundWindow(window_handle)
            time.sleep(0.1)  # Pequeña pausa para que la ventana se actualice
            
            # Capturar
            image = ImageGrab.grab(bbox=window_rect)
            
            # Procesar y guardar
            timestamp = datetime.now()
            window_title_clean = SecurityUtilities.sanitize_filename(
                window_title or f"window_{window_handle}"
            )
            
            filename = f"window_{window_title_clean}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
            filepath = SystemConfig.SCREENSHOTS_DIR / filename
            
            image.save(filepath, format='PNG', quality=95, optimize=True)
            
            result = {
                'window_handle': window_handle,
                'window_title': window_title,
                'window_rect': window_rect,
                'filepath': str(filepath),
                'filename': filename,
                'size': image.size,
                'file_size': FileUtilities.get_file_size(filepath),
                'file_size_formatted': SystemUtilities.format_bytes(FileUtilities.get_file_size(filepath)),
                'timestamp': timestamp
            }
            
            logger.info(f"Ventana capturada: {window_title or window_handle}")
            return result
            
        except Exception as e:
            logger.error(f"Error capturando ventana: {e}")
            return None
    
    def get_capture_status(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual del sistema de captura
        
        Returns:
            Diccionario con estado de captura
        """
        try:
            monitors = self._get_monitor_info()
            
            return {
                'is_capturing': self.is_capturing,
                'last_capture_time': self.last_capture_time,
                'last_capture_formatted': datetime.fromtimestamp(self.last_capture_time).strftime('%Y-%m-%d %H:%M:%S') if self.last_capture_time > 0 else 'Nunca',
                'monitors_available': len(monitors),
                'queue_size': self.capture_queue.qsize(),
                'screenshots_directory': str(SystemConfig.SCREENSHOTS_DIR),
                'directory_exists': SystemConfig.SCREENSHOTS_DIR.exists()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estado de captura: {e}")
            return {
                'is_capturing': False,
                'last_capture_time': 0,
                'last_capture_formatted': 'Error',
                'monitors_available': 0,
                'queue_size': 0,
                'screenshots_directory': str(SystemConfig.SCREENSHOTS_DIR),
                'directory_exists': False
            }
    
    def cleanup_old_screenshots(self, days_old: int = 7) -> Dict[str, Any]:
        """
        Limpia capturas de pantalla antiguas
        
        Args:
            days_old: Días de antigüedad para eliminar
            
        Returns:
            Estadísticas de limpieza
        """
        try:
            if not SystemConfig.SCREENSHOTS_DIR.exists():
                return {'deleted': 0, 'total_size_freed': 0, 'error': 'Directorio no existe'}
            
            cutoff_time = time.time() - (days_old * 24 * 3600)
            deleted_count = 0
            total_size_freed = 0
            
            for file_path in SystemConfig.SCREENSHOTS_DIR.iterdir():
                if file_path.is_file():
                    try:
                        file_time = file_path.stat().st_mtime
                        if file_time < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            total_size_freed += file_size
                            logger.debug(f"Eliminado: {file_path.name}")
                    except Exception as e:
                        logger.warning(f"Error eliminando {file_path}: {e}")
            
            result = {
                'deleted': deleted_count,
                'total_size_freed': total_size_freed,
                'size_freed_formatted': SystemUtilities.format_bytes(total_size_freed),
                'days_old': days_old
            }
            
            logger.info(f"Limpieza completada: {deleted_count} archivos, {result['size_freed_formatted']} liberados")
            return result
            
        except Exception as e:
            logger.error(f"Error en limpieza de screenshots: {e}")
            return {'deleted': 0, 'total_size_freed': 0, 'error': str(e)}

# Clase para captura automática programada
class ScheduledCapture:
    """Clase para capturas automáticas programadas"""
    
    def __init__(self, capture_system: ScreenshotCapture):
        self.capture_system = capture_system
        self.is_running = False
        self.capture_thread = None
        self.interval_seconds = 300  # 5 minutos por defecto
        self.stop_event = threading.Event()
        
    def start_scheduled_capture(self, interval_seconds: int = 300):
        """
        Inicia captura programada
        
        Args:
            interval_seconds: Intervalo entre capturas en segundos
        """
        try:
            if self.is_running:
                logger.warning("Captura programada ya está ejecutándose")
                return False
            
            self.interval_seconds = interval_seconds
            self.stop_event.clear()
            self.is_running = True
            
            self.capture_thread = threading.Thread(
                target=self._capture_loop,
                daemon=True,
                name="ScheduledCapture"
            )
            self.capture_thread.start()
            
            logger.info(f"Captura programada iniciada (intervalo: {interval_seconds}s)")
            return True
            
        except Exception as e:
            logger.error(f"Error iniciando captura programada: {e}")
            self.is_running = False
            return False
    
    def stop_scheduled_capture(self):
        """Detiene captura programada"""
        try:
            if not self.is_running:
                return True
            
            self.stop_event.set()
            self.is_running = False
            
            if self.capture_thread and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=5)
            
            logger.info("Captura programada detenida")
            return True
            
        except Exception as e:
            logger.error(f"Error deteniendo captura programada: {e}")
            return False
    
    def _capture_loop(self):
        """Loop principal de captura programada"""
        while not self.stop_event.is_set():
            try:
                # Realizar captura
                result = self.capture_system.capture_screenshot(
                    add_timestamp=True,
                    add_watermark=True
                )
                
                if result:
                    logger.debug(f"Captura programada completada: {result['monitors_captured']} monitores")
                else:
                    logger.warning("Captura programada falló")
                
            except Exception as e:
                logger.error(f"Error en captura programada: {e}")
            
            # Esperar hasta el siguiente intervalo
            self.stop_event.wait(self.interval_seconds)
    
    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado de captura programada"""
        return {
            'is_running': self.is_running,
            'interval_seconds': self.interval_seconds,
            'interval_formatted': SystemUtilities.format_duration(self.interval_seconds),
            'thread_alive': self.capture_thread.is_alive() if self.capture_thread else False
        }

# Funciones de inicialización
def initialize_screenshot_system() -> Tuple[ScreenshotCapture, ScheduledCapture]:
    """
    Inicializa el sistema de capturas
    
    Returns:
        Tupla con sistemas de captura
    """
    try:
        logger.info("Inicializando sistema de capturas...")
        
        # Crear sistema de captura
        capture_system = ScreenshotCapture()
        
        # Crear sistema de captura programada
        scheduled_capture = ScheduledCapture(capture_system)
        
        # Verificar capacidades
        monitors = capture_system._get_monitor_info()
        logger.info(f"Sistema de capturas inicializado - {len(monitors)} monitores detectados")
        
        return capture_system, scheduled_capture
        
    except Exception as e:
        logger.error(f"Error inicializando sistema de capturas: {e}")
        return None, None

# Test de funcionalidad
def test_screenshot_functionality():
    """Prueba la funcionalidad de captura"""
    try:
        logger.info("Probando funcionalidad de captura...")
        
        capture_system = ScreenshotCapture()
        
        # Probar captura básica
        result = capture_system.capture_screenshot(add_timestamp=True, add_watermark=False)
        
        if result:
            logger.info(f"Prueba exitosa: {result['monitors_captured']} monitores capturados")
            return True
        else:
            logger.error("Prueba de captura falló")
            return False
            
    except Exception as e:
        logger.error(f"Error en prueba de captura: {e}")
        return False

# Auto-inicialización para pruebas
if __name__ == "__main__":
    test_screenshot_functionality()