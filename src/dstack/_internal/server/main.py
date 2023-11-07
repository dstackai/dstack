from dstack._internal.server.app import create_app, register_routes

app = create_app()
register_routes(app)
