"""
Модуль вакансий VaxtaRekrut: API, фильтры, обогащение, отчёт для HR.
"""

from .api_client import get_job_offerings, get_places
from .filter_builder import filter_from_short, generate_filter, choose_filters
from .transform import enrich_offerings, format_top_vacancies_report, print_offerings

__all__ = [
    "get_places",
    "get_job_offerings",
    "enrich_offerings",
    "generate_filter",
    "filter_from_short",
    "choose_filters",
    "format_top_vacancies_report",
    "print_offerings",
]
