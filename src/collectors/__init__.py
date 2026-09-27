"""
Collectors package containing adapters and source routing logic.
"""

from src.collectors.base import BaseAdapter
from src.collectors.yahoo import YahooAdapter
from src.collectors.msn import MSNAdapter
from src.collectors.router import SourceRouter, RoutingResult
from src.collectors.batch import BatchCollector

__all__ = ["BaseAdapter", "YahooAdapter", "MSNAdapter", "SourceRouter", "RoutingResult", "BatchCollector"]

