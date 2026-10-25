"""Use HA's bundled schema library across the 2026.9/2026.10 transition."""

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

__all__ = ["vol"]
