import torch.serialization
import logging

logger = logging.getLogger(__name__)

# Mock safe_globals context manager
class SafeGlobalsContext:
    def __init__(self, globals_list):
        self.globals_list = globals_list
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def apply_patch():
    if not hasattr(torch.serialization, "safe_globals"):
        logger.warning("⚠️ Patching torch.serialization.safe_globals for Senko compatibility")
        torch.serialization.safe_globals = SafeGlobalsContext
    else:
        logger.info("✅ torch.serialization.safe_globals already exists")

apply_patch()
