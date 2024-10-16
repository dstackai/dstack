"""
Temporary patch to python-dxf.
TODO(#1828): remove once https://github.com/davedoesdev/dxf/issues/57 is resolved.
"""

import base64
import urllib.parse as urlparse
import warnings
from typing import List, Optional
from urllib.parse import urlencode

import requests
import www_authenticate
from dxf import DXF, _ignore_warnings, _raise_for_status, _to_bytes_2and3, exceptions


class PatchedDXF(DXF):
    # copied from python-dxf + this bugfix: https://github.com/davedoesdev/dxf/pull/58
    def authenticate(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        actions: Optional[List[str]] = None,
        response: Optional[requests.Response] = None,
        authorization: Optional[str] = None,
        user_agent: str = "Docker-Client/19.03.2 (linux)",
    ) -> Optional[str]:
        if response is None:
            with warnings.catch_warnings():
                _ignore_warnings(self)
                response = self._sessions[0].get(
                    self._base_url, verify=self._tlsverify, timeout=self._timeout
                )

        if not self._response_needs_auth(response):
            return None

        if self._insecure:
            raise exceptions.DXFAuthInsecureError()

        parsed = www_authenticate.parse(response.headers["www-authenticate"])

        if username is not None and password is not None:
            headers = {
                "Authorization": "Basic "
                + base64.b64encode(_to_bytes_2and3(username + ":" + password)).decode("utf-8")
            }
        elif authorization is not None:
            headers = {"Authorization": authorization}
        else:
            headers = {}
        headers["User-Agent"] = user_agent

        if "bearer" in parsed:
            info = parsed["bearer"]
            if actions and self._repo:
                scope = "repository:" + self._repo + ":" + ",".join(actions)
            elif "scope" in info:
                scope = info["scope"]
            elif not self._repo:
                # Issue #28: gcr.io doesn't return scope for non-repo requests
                scope = "registry:catalog:*"
            else:
                scope = ""
            url_parts = list(urlparse.urlparse(info["realm"]))
            query = urlparse.parse_qsl(url_parts[4])
            if "service" in info:
                query.append(("service", info["service"]))
            query.extend(("scope", s) for s in scope.split())
            url_parts[4] = urlencode(query, True)
            url_parts[0] = "https"
            if self._auth_host:
                url_parts[1] = self._auth_host
            auth_url = urlparse.urlunparse(url_parts)
            with warnings.catch_warnings():
                _ignore_warnings(self)
                r = self._sessions[0].get(
                    auth_url, headers=headers, verify=self._tlsverify, timeout=self._timeout
                )
            _raise_for_status(r)
            rjson = r.json()
            # Use 'access_token' value if present and not empty, else 'token' value.
            self.token = rjson.get("access_token") or rjson["token"]
            return self._token

        self._headers = headers
        return None
