# services/logging_service.py
import os
import logging
from datetime import datetime
from django.conf import settings
from file_handling.models import ImportSession

class ImportLoggerService:
    def __init__(self, import_session_id):
        self.import_session_id = import_session_id
        self.log_file_path = self._create_log_file_path()
        self.logger = self._setup_logger()
        
    def _create_log_file_path(self):
        """Crée le chemin du fichier de log pour cette session d'import"""
        logs_dir = os.path.join(settings.MEDIA_ROOT, 'import_logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"import_session_{self.import_session_id}_{timestamp}.txt"
        return os.path.join(logs_dir, filename)
    
    def _setup_logger(self):
        """Configure un logger spécifique pour cette session d'import"""
        logger_name = f"import_session_{self.import_session_id}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        
        logger.handlers.clear()
        
        file_handler = logging.FileHandler(self.log_file_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s\n' + '='*80 + '\n',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    def log_info(self, message, details=None):
        """Log une information"""
        full_message = self._format_message("INFO", message, details)
        self.logger.info(full_message)
    
    def log_warning(self, message, details=None, line_index=None):
        """Log un warning"""
        full_message = self._format_message("WARNING", message, details, line_index)
        self.logger.warning(full_message)
    
    def log_error(self, message, details=None, line_index=None, exception=None):
        """Log une erreur"""
        full_message = self._format_message("ERROR", message, details, line_index, exception)
        self.logger.error(full_message)
    
    def log_critical(self, message, details=None, exception=None):
        """Log une erreur critique"""
        full_message = self._format_message("CRITICAL", message, details, exception=exception)
        self.logger.critical(full_message)
    
    def _format_message(self, level, message, details=None, line_index=None, exception=None):
        """Formate le message avec tous les détails"""
        formatted_parts = [f"[{level}] {message}"]
        
        if line_index is not None:
            formatted_parts.append(f"Ligne concernée: {line_index}")
        
        if details:
            if isinstance(details, dict):
                formatted_parts.append("Détails:")
                for key, value in details.items():
                    formatted_parts.append(f"  - {key}: {value}")
            else:
                formatted_parts.append(f"Détails: {details}")
        
        if exception:
            formatted_parts.append(f"Exception: {type(exception).__name__}: {str(exception)}")
            if hasattr(exception, '__traceback__') and exception.__traceback__:
                import traceback
                formatted_parts.append("Traceback:")
                formatted_parts.append(traceback.format_exc())
        
        return "\n".join(formatted_parts)
    
    def log_step_start(self, step_name, step_number=None):
        """Log le début d'une étape"""
        separator = "🔹" * 50
        if step_number:
            message = f"\n{separator}\nÉTAPE {step_number}: {step_name}\n{separator}"
        else:
            message = f"\n{separator}\n{step_name}\n{separator}"
        self.log_info(message)
    
    def log_step_end(self, step_name, success=True, stats=None):
        """Log la fin d'une étape"""
        status = "✅ SUCCÈS" if success else "❌ ÉCHEC"
        message = f"Fin de l'étape: {step_name} - {status}"
        
        if stats:
            message += f"\nStatistiques: {stats}"
        
        if success:
            self.log_info(message)
        else:
            self.log_error(message)
    
    def get_log_file_path(self):
        """Retourne le chemin du fichier de log"""
        return self.log_file_path
    
    def close(self):
        """Ferme le logger et ses handlers"""
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()