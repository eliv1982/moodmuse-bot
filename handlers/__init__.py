# Handlers package
from .admin import router as admin_router
from .main import router as main_router
from .profile import router as profile_router

__all__ = ["main_router", "admin_router", "profile_router"]
