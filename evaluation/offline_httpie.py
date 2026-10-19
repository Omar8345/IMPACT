"""Keep HTTPie's remote pie.dev cases out of the reproducible CI run."""

import socket


def pytest_sessionstart(session):
    original = socket.gethostbyname

    def resolve(host):
        if host == "pie.dev":
            raise socket.gaierror("remote pie.dev tests are disabled in CI")
        return original(host)

    socket.gethostbyname = resolve
