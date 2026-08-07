"""Ask Crump Python backend package."""

# 5.2 applies narrow compatibility patches before runtime service instances are
# created. This preserves the proven auth/chat persistence architecture while
# upgrading multimodal continuity, document context, artifacts, and persona.
from .crump52_patches import apply_crump52_patches

apply_crump52_patches()
