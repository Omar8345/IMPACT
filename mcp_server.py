"""Expose the graph tools over MCP so any MCP client (Claude Desktop, Cursor...) can use them."""
from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("pr-impact-graph")
for _fn in tools.TOOLS.values():
    mcp.tool()(_fn)


def run():
    mcp.run()
