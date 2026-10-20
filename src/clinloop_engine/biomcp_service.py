"""Start the pinned BioMCP service with explicit internal Docker host protection."""


def configure_security(app):
    from mcp.server.transport_security import TransportSecuritySettings
    app.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=['biomcp:8000', 'localhost:8000', '127.0.0.1:8000'],
        allowed_origins=['http://biomcp:8000', 'http://localhost:8000', 'http://127.0.0.1:8000'],
    )


def main() -> None:
    from biomcp import mcp_app
    from biomcp.cli.server import run_http_server, ServerMode
    configure_security(mcp_app)
    # Preserve the upstream authentication middleware and health endpoint.
    run_http_server('0.0.0.0', 8000, ServerMode('streamable_http'))


if __name__ == '__main__':
    main()
