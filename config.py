# pyramid_app/config.py
"""
Helper to manage config UI and default settings.
Wraps db.get_config / set_config with typed defaults.
"""

from .db import get_config, set_config

def get_commission_rates():
    return get_config("commission_rates", [0.10, 0.05, 0.02])

def set_commission_rates(rates):
    set_config("commission_rates", rates)

def get_max_levels():
    return get_config("max_levels", 10)

def set_max_levels(n):
    set_config("max_levels", n)
