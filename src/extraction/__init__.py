"""
Extraction package for metadata, article text, and comment parsing.
"""

from src.extraction.metadata import MetadataExtractor, ExtractedMetadata
from src.extraction.article_text import ArticleTextExtractor, ExtractedArticleText
from src.extraction.comments import CommentDiagnosticInspector, CommentDiagnosticsResult

__all__ = [
    "MetadataExtractor",
    "ExtractedMetadata",
    "ArticleTextExtractor",
    "ExtractedArticleText",
    "CommentDiagnosticInspector",
    "CommentDiagnosticsResult"
]
