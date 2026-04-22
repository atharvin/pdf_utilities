import logging
import translation_service.env_config as ec

# configure logger
logger = logging.getLogger("translation_service_logger")
logger.setLevel(logging.INFO)
log_file = ec.log_file
formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
