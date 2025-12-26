import argparse
import queue
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.utils.common import console, resolve_url
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
            help="The server URL, e.g. https://sky.dstack.ai",
            required=True,
        )
        self._parser.add_argument(
            "-p",
            "--provider",
            help=(
                "The SSO provider name."
                " Selected automatically if the server supports only one provider."
            ),
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        base_url = _normalize_url_or_error(args.url)
        api_client = APIClient(base_url=base_url)
        provider = self._select_provider_or_error(api_client=api_client, provider=args.provider)
        server = _LoginServer(api_client=api_client, provider=provider)
        try:
            server.start()
            auth_resp = api_client.auth.authorize(provider=provider, local_port=server.port)
            opened = webbrowser.open(auth_resp.authorization_url)
            if opened:
                console.print(
                    f"Your browser has been opened to log in with [code]{provider.title()}[/]:\n"
                )
            else:
                console.print(f"Open the URL to log in with [code]{provider.title()}[/]:\n")
            print(f"{auth_resp.authorization_url}\n")
            user = server.get_logged_in_user()
        finally:
            server.shutdown()
        if user is None:
            raise CLIError("CLI authentication failed")
        console.print(f"Logged in as [code]{user.username}[/].")
        api_client = APIClient(base_url=base_url, token=user.creds.token)
        self._configure_projects(api_client=api_client, user=user)

    def _select_provider_or_error(self, api_client: APIClient, provider: Optional[str]) -> str:
        providers = api_client.auth.list_providers()
        available_providers = [p.name for p in providers if p.enabled]
        if len(available_providers) == 0:
            raise CLIError("No SSO providers configured on the server.")
        if provider is None:
            if len(available_providers) > 1:
                raise CLIError(
                    "Specify -p/--provider to choose SSO provider"
                    f" Available providers: {', '.join(available_providers)}"
                )
            return available_providers[0]
        if provider not in available_providers:
            raise CLIError(
                f"Provider {provider} not configured on the server."
                f" Available providers: {', '.join(available_providers)}"
            )
        return provider

    def _configure_projects(self, api_client: APIClient, user: UserWithCreds):
        projects = api_client.projects.list(include_not_joined=False)
        if len(projects) == 0:
            console.print(
                "No projects configured."
                " Create your own project via the UI or contact a project manager to add you to the project."
            )
            return
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
                url=api_client.base_url,
                token=user.creds.token,
                default=set_as_default,
            )
        config_manager.save()
        console.print(
            f"Configured projects: {', '.join(f'[code]{p.project_name}[/]' for p in projects)}."
        )
        if new_default_project:
            console.print(
                f"Set project [code]{new_default_project.project_name}[/] as default project."
            )


class _BadRequestError(Exception):
    pass


class _LoginServer:
    def __init__(self, api_client: APIClient, provider: str):
        self._api_client = api_client
        self._provider = provider
        self._result_queue: queue.Queue[Optional[UserWithCreds]] = queue.Queue()
        # Using built-in HTTP server to avoid extra deps.
        callback_handler = self._make_callback_handler(
            result_queue=self._result_queue,
            api_client=api_client,
            provider=provider,
        )
        self._server = self._create_server(handler=callback_handler)

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.start()

    def shutdown(self):
        self._server.shutdown()

    def get_logged_in_user(self) -> Optional[UserWithCreds]:
        return self._result_queue.get()

    @property
    def port(self) -> int:
        return self._server.server_port

    def _make_callback_handler(
        self,
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
                    return
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

    def _create_server(self, handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
        server_address = ("127.0.0.1", 0)
        server = HTTPServer(server_address, handler)
        return server


def _normalize_url_or_error(url: str) -> str:
    try:
        # Validate the URL and determine the URL scheme.
        # Need to resolve the scheme before making first POST request
        # since for some redirect codes (301), clients change POST to GET.
        url = resolve_url(url)
    except ValueError as e:
        raise CLIError(e.args[0])
    return url


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
