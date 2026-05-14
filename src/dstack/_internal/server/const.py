GLOBAL_EXPORTS_LOCK_NAMESPACE = "global_exports"
"""
Lock used to avoid race conditions between promoting an export to global and creating new projects.
Ensures that all projects always import all global exports.
"""
