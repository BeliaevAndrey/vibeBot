from typing import Dict


def swap(params: Dict[str, str]) -> Dict[str, str]:
    """
    Поменять местами ключи и значения в словаре.
    """
    return dict(zip(params.values(), params.keys()))

