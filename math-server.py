from mcp.server.fastmcp import FastMCP
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("Math")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    logger.info("The add method is called: a=%d, b=%d", a, b)
    return a + b

@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    logger.info("The multiply method is called: a=%d, b=%d", a, b)
    return a * b

if __name__ == "__main__":
    logger.info("Start math server through MCP")
    mcp.run(transport="stdio")