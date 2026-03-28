# Handlers package
from .admin import router as admin_router
from .main import router as main_router

__all__ = ["main_router", "admin_router"]
