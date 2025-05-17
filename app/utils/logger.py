# app/utils/logger.py
import logging

def setup_logger(name, log_file, level=logging.ERROR):
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding multiple handlers if already configured
    if not logger.handlers:
        logger.addHandler(handler)
        
    return logger

error_logger = setup_logger('error_logger', 'error.log', level=logging.ERROR)
