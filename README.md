# MCP-App: Model Context Protocol Web Application

A web-based application demonstrating the Model Context Protocol (MCP) for extensible AI agent capabilities. It features a Python FastAPI backend integrated with Langchain for agentic logic and a Vue.js frontend for user interaction.

## Project Structure

- `mcp_web_app/`: Python FastAPI backend. Handles agent logic, LLM communication, MCP server management, and WebSocket streaming.
- `mcp_vue_frontend/`: Vue.js frontend. Provides the user interface for chat, server management, and configuration.

## Key Technologies

- **Backend:** Python, FastAPI, Langchain, Uvicorn
- **Frontend:** Vue.js 3, Vite, JavaScript, HTML, CSS
- **Communication:** Model Context Protocol (MCP), WebSockets, REST APIs
- **Package Management:** `uv` (Python), `npm` (Node.js)

## Features

- **Agentic Chat:** Engage with an AI agent powered by Langchain, capable of using configured LLMs.
- **MCP Tool Integration:** Connects to and utilizes MCP-compliant tool servers, extending agent capabilities.
- **Dynamic LLM Configuration:** Supports multiple LLM configurations (e.g., DeepSeek, Ollama) selectable at runtime.
- **Real-time Streaming:** WebSocket-based streaming for chat responses and agent events.
- **Markdown Rendering:** Displays chat responses in Markdown with syntax highlighting for various languages (including Python, JavaScript, XML, CSS, Bash, JSON, Rust, and more).
- **Tool Server Management UI:** Interface to list, start, stop, get status, and refresh capabilities of configured MCP tool servers.
- **Configuration UI:** Manage LLM provider settings and tool server definitions.

## Recent Improvements (May 2025)

- **Enhanced WebSocket Stability:** Resolved issues related to WebSocket disconnections and improved error handling in the chat streaming components (`mcp_web_app/main.py`, `mcp_web_app/utils/chat.py`).
- **Robust Agent Service:** Added more resilient error handling within the Langchain agent service (`mcp_web_app/services/langchain_agent_service.py`).
- **Extended Syntax Highlighting:** Added Rust language support to the frontend Markdown renderer (`mcp_vue_frontend/src/components/MarkdownRenderer.vue`).
- **General Code Refinements:** Various minor bug fixes and logging improvements across the backend.

## Manual Setup

### Prerequisites

- [Python 3.10+](https://www.python.org/downloads/) (Python 3.13+ recommended)
- [Node.js](https://nodejs.org/) (LTS version recommended)
- [uv](https://github.com/astral-sh/uv) - Modern Python package installer and resolver

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Backend Setup

1.  **Create a virtual environment** (from the project root):
    ```bash
    uv venv .venv
    ```

2.  **Activate the virtual environment**:
    ```bash
    # On macOS/Linux
    source .venv/bin/activate

    # On Windows
    .venv\Scripts\activate
    ```

3.  **Install dependencies**:
    ```bash
    uv pip install -e ".[dev]"
    ```
    (Ensure you have necessary build tools if a dependency requires compilation, e.g., `rustc` for `tokenizers` if not using pre-built wheels).

4.  **Environment Variables**:
    Copy `.env.example` to `.env` and fill in necessary API keys (e.g., `DEEPSEEK_API_KEY`).

### Frontend Setup

1.  **Navigate to the frontend directory**:
    ```bash
    cd mcp_vue_frontend
    ```

2.  **Install dependencies**:
    ```bash
    npm install
    ```

## Running the Application

### Backend

From the project root, with the virtual environment activated:
```bash
# Default port is 8010 as per recent logs
uvicorn mcp_web_app.main:app --reload --host 0.0.0.0 --port 8010
```
You can change the port with the `--port` argument.

### Frontend

In a new terminal, from the `mcp_vue_frontend` directory:
```bash
npm run dev
```
This typically runs on `http://localhost:5173`.

## Accessing the Application

- **Backend API Base:** `http://localhost:8010` (or your configured port)
- **Frontend UI:** `http://localhost:5173` (or as indicated by `npm run dev`)

### API Documentation

When the backend is running, API documentation is available at:
- Swagger UI: `http://localhost:8010/docs`
- ReDoc: `http://localhost:8010/redoc`

## Development

### Updating Dependencies

-   **Python Backend**:
    ```bash
    # From project root, with .venv activated
    uv pip sync
    ```
-   **Vue.js Frontend**:
    ```bash
    # From mcp_vue_frontend directory
    npm update
    ```
