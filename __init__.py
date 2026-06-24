# ToolCase — Code Improvement Toolkit v5.4.1
# Maker: SmokerGreenOG

from pathlib import Path

TOOLCASE_DIR = Path(__file__).parent
__maker__ = "SmokerGreenOG"
__version__ = "5.4.1"

# Core safety API
from safe_run import safe_run, classify_command, Risk  # noqa: E402, F401
