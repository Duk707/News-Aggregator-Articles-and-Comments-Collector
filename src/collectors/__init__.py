"""
Collectors package containing adapters and source routing logic.
"""

from src.collectors.base import BaseAdapter
from src.collectors.yahoo import YahooAdapter
from src.collectors.msn import MSNAdapter
from src.collectors.tesl_ontario import TESLOntarioAdapter
from src.collectors.hepi import HEPIAdapter
from src.collectors.engagement_hq import EngagementHQAdapter
from src.collectors.cult_of_pedagogy import CultOfPedagogyAdapter
from src.collectors.spencer_education import SpencerEducationAdapter
from src.collectors.wonkhe import WonkheAdapter
from src.collectors.granicus_ideas import GranicusIdeasAdapter
from src.collectors.legistar import LegistarAdapter
from src.collectors.router import SourceRouter, RoutingResult
from src.collectors.batch import BatchCollector

__all__ = [
    "BaseAdapter",
    "YahooAdapter",
    "MSNAdapter",
    "TESLOntarioAdapter",
    "HEPIAdapter",
    "EngagementHQAdapter",
    "CultOfPedagogyAdapter",
    "SpencerEducationAdapter",
    "WonkheAdapter",
    "GranicusIdeasAdapter",
    "LegistarAdapter",
    "SourceRouter",
    "RoutingResult",
    "BatchCollector"
]
