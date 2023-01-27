from dstack.hub.db import engine
from dstack.hub.db.users import User


def create_all():
    User.metadata.create_all(engine)
