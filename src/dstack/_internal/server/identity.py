import uuid

SERVER_REPLICA_ID = str(uuid.uuid4())
"""
Unique ID of this server process, regenerated on every start.
Distinguishes replicas in multi-replica deployments, e.g. in exported telemetry.
"""
