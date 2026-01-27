import argparse
import queue
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

import questionary
from rich.prompt import Prompt as RichPrompt
from rich.text import Text

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.commands.project import select_default_project
from dstack._internal.cli.utils.common import console, resolve_url
from dstack._internal.core.errors import ClientError, CLIError
from dstack._internal.core.models.users import UserWithCreds
from dstack._internal.utils.logging import get_logger
from dstack.api._public.runs import ConfigManager
from dstack.api.server import APIClient

logger = get_logger(__name__)

is_project_menu_supported = sys.stdin.isatty()


class UrlPrompt(RichPrompt):
    def render_default(self, default: Any) -> Text:
        return Text(f"({default})", style="bold orange1")


class LoginCommand(BaseCommand):
    NAME = "login"
    DESCRIPTION = "Authorize the CLI using Single Sign-On"

    def _register(self):
        super()._register()
        self._parser.add_argument(
            "--url",
            help="The server URL, e.g. https://sky.dstack.ai",
            required=not is_project_menu_supported,
        )
        self._parser.add_argument(
            "-p",
            "--provider",
            help=(
                "The SSO provider name."
                " Selected automatically if the server supports only one provider."
            ),
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Don't ask for confirmation (e.g. set first project as default)",
            action="store_true",
        )
        self._parser.add_argument(
            "-n",
            "--no",
            help="Don't ask for confirmation (e.g. do not change default project)",
            action="store_true",
        )

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        url = args.url
        if url is None:
            url = self._prompt_url()
        base_url = _normalize_url_or_error(url)
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
        console.print(f"Logged in as [code]{user.username}[/]")
        api_client = APIClient(base_url=base_url, token=user.creds.token)
        self._configure_projects(api_client=api_client, user=user, args=args)

    def _select_provider_or_error(self, api_client: APIClient, provider: Optional[str]) -> str:
        providers = api_client.auth.list_providers()
        available_providers = [p.name for p in providers if p.enabled]
        if len(available_providers) == 0:
            raise CLIError("No SSO providers configured on the server.")
        if provider is None:
            if len(available_providers) > 1:
                if is_project_menu_supported:
                    return self._prompt_provider(available_providers)
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

    def _prompt_url(self) -> str:
        try:
            url = UrlPrompt.ask(
                "Enter the server URL",
                default="https://sky.dstack.ai",
                console=console,
            )
        except KeyboardInterrupt:
            console.print("\nCancelled by user")
            raise SystemExit(1)
        if url is None:
            raise CLIError("URL is required")
        return url

    def _prompt_provider(self, available_providers: list[str]) -> str:
        choices = [
            questionary.Choice(title=provider, value=provider) for provider in available_providers
        ]
        selected_provider = questionary.select(
            message="Select SSO provider:",
            choices=choices,
            qmark="",
            instruction="(↑↓ Enter)",
        ).ask()
        if selected_provider is None:
            raise SystemExit(1)
        return selected_provider

    def _configure_projects(
        self, api_client: APIClient, user: UserWithCreds, args: argparse.Namespace
    ):
        projects = api_client.projects.list(include_not_joined=False)
        if len(projects) == 0:
            console.print(
                "No projects configured."
                " Create your own project via the UI or contact a project manager to add you to the project."
            )
            return
        config_manager = ConfigManager()
        default_project = config_manager.get_project_config()
        for project in projects:
            config_manager.configure_project(
                name=project.project_name,
                url=api_client.base_url,
                token=user.creds.token,
                default=False,
            )
        config_manager.save()
        project_names = ", ".join(f"[code]{p.project_name}[/]" for p in projects)
        console.print(
            f"Added {project_names} project{'' if len(projects) == 1 else 's'} at {config_manager.config_filepath}"
        )

        project_configs = config_manager.list_project_configs()

        if args.no:
            return

        if args.yes:
            if len(projects) > 0:
                first_project_from_server = projects[0]
                first_project_config = next(
                    (
                        pc
                        for pc in project_configs
                        if pc.name == first_project_from_server.project_name
                    ),
                    None,
                )
                if first_project_config is not None:
                    config_manager.configure_project(
                        name=first_project_config.name,
                        url=first_project_config.url,
                        token=first_project_config.token,
                        default=True,
                    )
                    config_manager.save()
                    console.print(
                        f"Set [code]{first_project_config.name}[/] project as default at {config_manager.config_filepath}"
                    )
            return

        if len(project_configs) == 1 or not is_project_menu_supported:
            selected_project = None
            if len(project_configs) == 1:
                selected_project = project_configs[0]
            else:
                for i, project in enumerate(projects):
                    set_as_default = (
                        default_project is None
                        and i == 0
                        or default_project is not None
                        and default_project.name == project.project_name
                    )
                    if set_as_default:
                        selected_project = next(
                            (pc for pc in project_configs if pc.name == project.project_name),
                            None,
                        )
                        break
            if selected_project is not None:
                config_manager.configure_project(
                    name=selected_project.name,
                    url=selected_project.url,
                    token=selected_project.token,
                    default=True,
                )
                config_manager.save()
                console.print(
                    f"Set [code]{selected_project.name}[/] project as default at {config_manager.config_filepath}"
                )
        else:
            console.print()
            selected_project = select_default_project(project_configs, default_project)
            if selected_project is not None:
                config_manager.configure_project(
                    name=selected_project.name,
                    url=selected_project.url,
                    token=selected_project.token,
                    default=True,
                )
                config_manager.save()


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
