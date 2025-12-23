import argparse
import queue
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ClientError, CLIError
from dstack._internal.core.models.users import UserWithCreds
from dstack.api._public.runs import ConfigManager
from dstack.api.server import APIClient


class LoginCommand(BaseCommand):
    NAME = "login"
    DESCRIPTION = "Authorize the CLI using Single Sign-On"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "--url",
            help="The server URL",
            required=True,
        )
        self._parser.add_argument(
            "-p", "--provider", help="The Single Sign-On provider name", required=True
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        base_url = args.url
        api_client = APIClient(base_url=base_url)
        provider = args.provider
        result_queue = queue.Queue[Optional[UserWithCreds]](maxsize=1)
        handler = _make_handler(
            result_queue=result_queue,
            api_client=api_client,
            provider=provider,
        )
        # Using built-in HTTP server to avoid extra deps.
        server = _create_server(handler)
        try:
            threading.Thread(target=server.serve_forever).start()
            auth_resp = api_client.auth.authorize(provider=provider, local_port=server.server_port)
            console.print(f"Open the URL to log in with [code]{provider.title()}[/]:\n")
            print(f"{auth_resp.authorization_url}\n")
            user = result_queue.get()
        finally:
            server.shutdown()
        if user is None:
            raise CLIError("CLI authentication failed")
        console.print(f"Logged in as [code]{user.username}[/].")
        api_client = APIClient(base_url=base_url, token=user.creds.token)
        projects = api_client.projects.list(include_not_joined=False)
        if len(projects) == 0:
            console.print("No projects configured.")
        config_manager = ConfigManager()
        default_project = config_manager.get_project_config()
        new_default_project = None
        for i, project in enumerate(projects):
            set_as_default = (
                default_project is None
                and i == 0
                or default_project is not None
                and default_project.name == project.project_name
            )
            if set_as_default:
                new_default_project = project
            config_manager.configure_project(
                name=project.project_name,
                url=base_url,
                token=user.creds.token,
                default=set_as_default,
            )
        config_manager.save()
        console.print(
            f"Configured projects: {', '.join(f'[code]{p.project_name}[/]' for p in projects)}."
        )
        if new_default_project:
            console.print(f"Set project {new_default_project} as default project.")


class _BadRequestError(Exception):
    pass


def _make_handler(
    result_queue: queue.Queue[Optional[UserWithCreds]],
    api_client: APIClient,
    provider: str,
) -> type[BaseHTTPRequestHandler]:
    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed_path = urllib.parse.urlparse(self.path)
            if parsed_path.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
            try:
                self._handle_auth_callback(parsed_path)
            except _BadRequestError as e:
                self.send_error(400, e.args[0])
                result_queue.put(None)

        def log_message(self, format: str, *args):
            # Do not log server requests.
            pass

        def _handle_auth_callback(self, parsed_path: urllib.parse.ParseResult):
            try:
                params = urllib.parse.parse_qs(parsed_path.query, strict_parsing=True)
            except ValueError:
                raise _BadRequestError("Bad query params")
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if code is None or state is None:
                raise _BadRequestError("Missing required params")
            try:
                user = api_client.auth.callback(provider=provider, code=code, state=state)
            except ClientError:
                raise _BadRequestError("Authentication failed")
            self._send_success_html()
            result_queue.put(user)

        def _send_success_html(self):
            body = _SUCCESS_HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _CallbackHandler


def _create_server(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server_address = ("127.0.0.1", 0)
    server = HTTPServer(server_address, handler)
    return server


_SUCCESS_HTML = """\
<!DOCTYPE HTML>
<html lang="en">
    <head>
        <meta charset="utf-8">
        <title>CLI authenticated</title>
        <style>
            body {font-family: system-ui, sans-serif; }
            h1 { font-weight: 500; }
        </style>
    </head>
    <body>
        <h1>dstack CLI authenticated</h1>
        <p>You may close this page.</p>
    </body>
</html>
"""
