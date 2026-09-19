"""Audio generation stub — audio feature removed."""

import logging

logger = logging.getLogger(__name__)


class AudioGenerator:
    """No-op stub. Audio generation has been removed."""

    def __init__(self, config: dict | None = None):
        pass

    def generate(self, text: str, output_path: str) -> bool:
        logger.info("Audio generation is disabled (feature removed)")
        return False
