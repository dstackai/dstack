import argparse
import queue
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ClientError, CLIError
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
        api_client = APIClient(base_url=args.url)
        provider = args.provider
        result_queue = queue.Queue(maxsize=1)
        handler = make_handler(
            result_queue=result_queue,
            api_client=api_client,
            provider=provider,
        )
        server = _create_server(handler)
        try:
            threading.Thread(target=server.serve_forever).start()
            print(server.server_port)
            auth_resp = api_client.auth.authorize(provider=provider, local_port=server.server_port)
            console.print(f"Open the URL to log in with [code]{provider.title()}[/]:\n")
            print(f"{auth_resp.authorization_url}\n")
            token = result_queue.get()
            if token is None:
                raise CLIError("CLI authentication failed")
            print(token)
            # TODO: Do something with token
        finally:
            server.shutdown()


def make_handler(
    result_queue: queue.Queue,
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
                params = urllib.parse.parse_qs(parsed_path.query, strict_parsing=True)
            except ValueError:
                self._error_response("Bad query params")
                return
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if code is None:
                self._error_response("Missing code param")
                return
            if state is None:
                self._error_response("Missing state param")
                return
            try:
                user_with_creds = api_client.auth.callback(
                    provider=provider, code=code, state=state
                )
            except ClientError:
                self._error_response("CLI authentication failed")
                return
            token = user_with_creds.creds.token
            result_queue.put(token)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"CLI authenticated")

        def log_message(self, format: str, *args):
            # TODO: log on debug level
            pass

        def _error_response(self, message: str):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(message.encode())
            result_queue.put(None)

    return _CallbackHandler


def _create_server(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server_address = ("127.0.0.1", 0)
    server = HTTPServer(server_address, handler)
    return server
