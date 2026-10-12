from dstack._internal.server import bootstrap

bootstrap.set_up_process()

from dstack._internal.server.app import create_app, register_routes  # noqa: E402

app = create_app()
register_routes(app)
