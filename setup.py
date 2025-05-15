from setuptools import setup, find_packages

setup(
    name="mcp_web_app",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi",
        "uvicorn",
        "httpx",
        "sse-starlette",
        "pydantic",
        "langchain-deepseek",
        "langchain-community",
        "langchain-mcp-adapters",
        "langchain-core",
        "langchain",
        "langgraph",
    ],
) 