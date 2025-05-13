import asyncio
from typing import Dict, Optional, Any
from ..models.models import ServerConfig
import os 
import logging

logger = logging.getLogger(__name__) 

class ProcessManager:
    def __init__(self):
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self._server_status: Dict[str, str] = {}
        self._discovered_capabilities: Dict[str, list] = {}  # server_id -> list of tools

    async def start_server(self, server_id: str, config: ServerConfig) -> Optional[int]:
        if self.is_server_running(server_id):
            logger.info(f"Server {server_id} is already running.")
            process = self._active_processes.get(server_id)
            return process.pid if process and isinstance(process, asyncio.subprocess.Process) else None

        try:
            logger.info(f"Attempting to start server {server_id}: {config.command} {' '.join(config.args)}")
            
            current_env = os.environ.copy()
            config_env = getattr(config, 'env', {})
            current_env.update(config_env)
            use_shell = getattr(config, 'shell', False)
            process: asyncio.subprocess.Process

            if use_shell:
                full_command_str = config.command
                if config.args:
                    full_command_str += " " + " ".join(config.args)
                logger.debug(f"Starting with shell: {full_command_str}")
                process = await asyncio.create_subprocess_shell(
                    full_command_str,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=current_env
                )
            else:
                logger.debug(f"Starting with exec: {config.command} {config.args}")
                process = await asyncio.create_subprocess_exec(
                    config.command,
                    *config.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=current_env
                )
            
            logger.info(f"Subprocess for {server_id} created with PID {process.pid}.")
            self._active_processes[server_id] = process
            self._server_status[server_id] = "connecting"
            
            asyncio.create_task(self._read_stream(process.stdout, server_id, "STDOUT"))
            asyncio.create_task(self._read_stream(process.stderr, server_id, "STDERR"))
            asyncio.create_task(self._monitor_process(server_id, process))

            await asyncio.sleep(0.2) # Give a moment for the process to start or fail
            
            if process.returncode is None: # Still running
                self._server_status[server_id] = "connected"
                logger.info(f"Server {server_id} (PID: {process.pid}) started successfully and appears to be running.")
                # Schedule background discovery of capabilities
                asyncio.create_task(self.discover_and_store_capabilities(server_id, config))
                return process.pid
            else:
                self._server_status[server_id] = "error"
                logger.error(f"Server {server_id} (PID: {process.pid}) failed to start or exited immediately. Exit code: {process.returncode}")
                if server_id in self._active_processes:
                    del self._active_processes[server_id] # Clean up
                return None

        except Exception as e:
            self._server_status[server_id] = "error"
            logger.error(f"Exception during server {server_id} start: {e}", exc_info=True)
            return None

    async def _read_stream(self, stream: Optional[asyncio.StreamReader], server_id: str, stream_name: str):
        if not stream:
            logger.warning(f"Stream {stream_name} for {server_id} is None.")
            return
        try:
            while True:
                line = await stream.readline()
                if line:
                    logger.info(f"[{server_id} {stream_name}]: {line.decode(errors='ignore').strip()}")
                else:
                    logger.info(f"{stream_name} stream for {server_id} ended.")
                    break
        except Exception as e:
            logger.error(f"Error reading {stream_name} for {server_id}: {e}", exc_info=True)

    async def _monitor_process(self, server_id: str, process: asyncio.subprocess.Process):
        pid_for_logging = process.pid
        try:
            return_code = await process.wait()
            logger.info(f"Server {server_id} (PID: {pid_for_logging}) exited with code {return_code}.")
        except Exception as e:
            logger.error(f"Exception while waiting for process {server_id} (PID: {pid_for_logging}): {e}", exc_info=True)
            # Process might be gone or other issue
        finally:
            # Ensure cleanup regardless of how wait() concludes
            if self._active_processes.get(server_id) == process:
                del self._active_processes[server_id]
            
            # Update status based on exit, unless it was intentionally stopped
            current_status = self._server_status.get(server_id)
            if current_status != "stopping": # if not being stopped by user
                if process.returncode != 0:
                    self._server_status[server_id] = "error"
                    logger.warning(f"Server {server_id} (PID: {pid_for_logging}) status set to 'error' (exit code {process.returncode}).")
                else:
                    self._server_status[server_id] = "disconnected"
                    logger.info(f"Server {server_id} (PID: {pid_for_logging}) status set to 'disconnected'.")

    async def refresh_capabilities(self, server_id: str, config):
        """Refresh the capabilities of a running server."""
        if not self.is_server_running(server_id):
            logger.warning(f"Cannot refresh capabilities for {server_id}: server is not running")
            return False
        
        try:
            logger.info(f"Refreshing capabilities for server {server_id}")
            await self.discover_and_store_capabilities(server_id, config)
            return True
        except Exception as e:
            logger.error(f"Error refreshing capabilities for {server_id}: {e}", exc_info=True)
            return False

    async def stop_server(self, server_id: str):
        process = self._active_processes.get(server_id)
        if not process:
            logger.info(f"Server {server_id} not found in active processes or already stopped.")
            self._server_status[server_id] = "disconnected" # Ensure status consistency
            return

        if process.returncode is not None:
            logger.info(f"Server {server_id} (PID: {process.pid}) was already stopped (exit code {process.returncode}). Removing from active list.")
            del self._active_processes[server_id]
            self._server_status[server_id] = "disconnected"
            return

        logger.info(f"Attempting to stop server {server_id} (PID: {process.pid}).")
        self._server_status[server_id] = "stopping"
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5.0)
            logger.info(f"Server {server_id} (PID: {process.pid}) terminated gracefully.")
        except asyncio.TimeoutError:
            logger.warning(f"Server {server_id} (PID: {process.pid}) did not terminate, killing.")
            process.kill()
            await process.wait() # Give kill a chance to be processed
            logger.info(f"Server {server_id} (PID: {process.pid}) killed.")
        except ProcessLookupError:
            logger.warning(f"ProcessLookupError for server {server_id} (PID: {process.pid}) during stop. Already gone?")
        except Exception as e:
            logger.error(f"Exception stopping server {server_id} (PID: {process.pid}): {e}", exc_info=True)
        finally:
            # Final cleanup and status update
            if server_id in self._active_processes:
                del self._active_processes[server_id]
            self._server_status[server_id] = "disconnected"
            logger.info(f"Server {server_id} definitively marked as stopped and disconnected.")

    def get_server_status(self, server_id: str) -> Dict[str, Any]:
        status_str = "disconnected"
        pid = None
        
        process = self._active_processes.get(server_id)
        if process and isinstance(process, asyncio.subprocess.Process) and process.returncode is None:
            # Server is considered running if in active_processes and no return code
            status_str = self._server_status.get(server_id, "running") # Use stored status if available, else default to "running"
            pid = process.pid
        else:
            # Server is not actively running or not found in active_processes
            status_str = self._server_status.get(server_id, "disconnected") # Use stored status, e.g., "error", "disconnected"
            # PID is not relevant or available if not running
            
        capabilities = self._discovered_capabilities.get(server_id, [])
        
        return {
            "server_name": server_id,
            "status": status_str,
            "pid": pid,
            "message": f"Server is {status_str}", # Generic message, can be enhanced
            "discovered_capabilities": capabilities
            # Consider adding "url" and "last_ping" if ProcessManager tracks them
        }

    def is_server_running(self, server_id: str) -> bool:
        process = self._active_processes.get(server_id)
        if process and isinstance(process, asyncio.subprocess.Process):
            return process.returncode is None
        return False

    def get_server_pid(self, server_id: str) -> Optional[int]:
        process = self._active_processes.get(server_id)
        if process and isinstance(process, asyncio.subprocess.Process) and process.returncode is None:
            return process.pid
        return None

    async def discover_and_store_capabilities(self, server_id: str, config: ServerConfig):
        """Connect to the running server and call list_tools(), storing the result."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import asyncio
            import os

            # Set up a new client connection for tool discovery rather than using the running process
            # This prevents the "method:initialize" command from going to stderr
            command = config.command
            args = config.args or []
            cwd = getattr(config, 'cwd', None)
            env = getattr(config, 'env', None)
            
            # We'll use the exact same command that started the server for npx commands
            # This ensures we have the same execution environment with the same packages
            if command == "npx":
                logger.info(f"[MCP] Using npx for capability discovery: {command} {args}")
                # No transformation needed - use exactly as configured
            # For other JS-based servers or scripts
            elif command == "node":
                if any(arg.endswith('.js') for arg in args):
                    logger.info(f"[MCP] Using node with JS script: {command} {args}")
                    # No transformation needed
                else:
                    logger.info(f"[MCP] Using direct node command: {command} {args}")
            # Python scripts
            elif command.endswith('.py'):
                logger.info(f"[MCP] Detected Python script for {server_id}: {command} {args}")
                args = [command] + args
                command = "python"
            # JS scripts as main command
            elif command.endswith('.js'):
                logger.info(f"[MCP] Detected JS script for {server_id}: {command} {args}")
                args = [command] + args
                command = "node"
            else:
                logger.info(f"[MCP] Using raw command for {server_id}: {command} {args}")

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
                cwd=cwd
            )
            
            self._discovered_capabilities[server_id] = []
            logger.info(f"[MCP] Discovering tools for {server_id} using: {command} {args}")
            
            try:
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        logger.info(f"[MCP] Initializing session for {server_id}")
                        await session.initialize()
                        logger.info(f"[MCP] Listing tools for {server_id}")
                        response = await session.list_tools()
                        tools = getattr(response, 'tools', response)
                        logger.info(f"[MCP] Discovered tools for {server_id}: {tools}")
                        self._discovered_capabilities[server_id] = tools
            except Exception as e:
                logger.error(f"[MCP] Error during MCP session for {server_id}: {e}", exc_info=True)
                # Try fallback to direct connection if this is a running process
                if self.is_server_running(server_id):
                    logger.info(f"[MCP] Falling back to process connection for {server_id}")
                    # This is a fallback implementation that could be developed if needed
                    pass
        except Exception as e:
            logger.error(f"[MCP] Failed to discover capabilities for {server_id}: {e}", exc_info=True)
            self._discovered_capabilities[server_id] = [] 