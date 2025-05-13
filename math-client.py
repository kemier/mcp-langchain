from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import AgentExecutor, create_react_agent, create_openai_tools_agent
from langchain_deepseek import ChatDeepSeek
from langgraph.checkpoint.memory import MemorySaver
from langchain import hub
from queue import Queue
from concurrent.futures import Future
import os, threading, asyncio
import json # Import json for parsing stringified JSON
import re # Import re for robust string extraction
from langchain_core.messages import HumanMessage, AIMessage # Import message types

import getpass
import os

import logging
logging.basicConfig(level=logging.DEBUG)

# os.environ["LANGCHAIN_TRACING_V2"] = "true"
# os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
# os.environ["LANGCHAIN_API_KEY"] = "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"
# os.environ["LANGCHAIN_PROJECT"] = "My_project"

# 初始化DeepSeek模型
llm = ChatDeepSeek(model="deepseek-chat", api_key="sk-88f2e3f45fe646809142bfdd257e0376")

# 全局请求队列与会话上下文存储
request_queue: Queue[tuple[str, str, Future]] = Queue()
sessions: dict[str, dict] = {}

# LLM用全局实例变量，便于切换不同的LLM
# 官方对 OpenAI 客户端明确保证"所有实例方法本身线程安全"
system_prompt = "你是一个有用的助手，能够根据需要自动决定调用哪个工具回答问题。"

# 连接多个MCP Server的配置
mcp_config = {
    "math": {
        "command": "python",
        "args": ["/Users/zaedinzeng/projects/mcp-client/math-server.py"],
        "transport": "stdio",
    },
    "weather":{
        "command": "uv",
        "args": ["--directory","/Users/zaedinzeng/projects/china-weather-mcp-server","run","weather.py"],
        "transport": "stdio",
        
        }
}


async def _dispatcher_loop():
    """
    后台单循环调度器：取出请求，根据 session_id 初始化或复用 Agent 上下文，
    执行 ainvoke 并通过 Future 回写结果。
    """
    global sessions
    # MCP 客户端上下文可在外层复用，或按需延迟创建
    async with MultiServerMCPClient(mcp_config) as client:
        logging.info("_dispatcher_loop: MultiServerMCPClient context entered.")
        while True:
            logging.debug("_dispatcher_loop: Waiting for item from request_queue...")
            session_id, question, fut = await asyncio.to_thread(request_queue.get)
            logging.info(f"_dispatcher_loop: Got request for session_id='{session_id}', question='{question[:50]}...'")
            
            # 主线程向队列中压入一个(None,None,None)来结束事件循环退出
            if session_id is None:
                logging.info("_dispatcher_loop: Shutdown signal received.")
                break
            
            try:
                current_chat_history = [] # Default to empty history

                # 若无该会话，初始化上下文
                if session_id not in sessions:
                    logging.info(f"_dispatcher_loop: Session '{session_id}' not found, creating new context.")
                    memory = MemorySaver() 
                    
                    # Pull the OpenAI tools agent prompt from Langchain Hub
                    # prompt = hub.pull("hwchase17/react-chat") # Old ReAct prompt
                    prompt = hub.pull("hwchase17/openai-tools-agent") # OpenAI Tools Agent prompt
                    logging.info(f"_dispatcher_loop: Fetched openai-tools-agent prompt for session '{session_id}'.")

                    agent_tools = list(client.get_tools()) # Get tools for the agent
                    logging.info(f"_dispatcher_loop: Got {len(agent_tools)} tools for session '{session_id}': {[t.name for t in agent_tools]}")
                    
                    # Use create_openai_tools_agent
                    agent = create_openai_tools_agent(
                        llm,
                        agent_tools,
                        prompt 
                    )
                    
                    # Wrap the agent in an AgentExecutor
                    agent_executor = AgentExecutor(
                        agent=agent, 
                        tools=agent_tools, 
                        verbose=True 
                        # handle_parsing_errors=robust_handle_parsing_error, # Removed, as OpenAI tools agent handles this
                        # return_intermediate_steps=True # Might be useful for more detailed logging if needed
                    )
                    sessions[session_id] = {
                        "executor": agent_executor, 
                        "memory": memory, 
                        "chat_history": [] # Initialize chat history for the new session
                    }
                    logging.info(f"_dispatcher_loop: Created and cached context for session '{session_id}'.")
                else:
                    logging.info(f"_dispatcher_loop: Reusing existing context for session '{session_id}'.")
                    # Retrieve existing chat history for the session
                    current_chat_history = sessions[session_id]["chat_history"]

                ctx = sessions[session_id]
                
                logging.info(f"_dispatcher_loop: Invoking agent executor for session '{session_id}' with question: '{question[:50]}...' and {len(current_chat_history)} history messages.")
                # 异步调用 Agent - pass the actual current_chat_history
                resp = await ctx["executor"].ainvoke(
                    {"input": question, "chat_history": current_chat_history}, # Pass the retrieved/current history
                    config={"configurable": {"thread_id": session_id}}
                )
                logging.info(f"_dispatcher_loop: Agent executor invocation complete for session '{session_id}'. Response keys: {list(resp.keys())}")
                
                # Update chat history
                ctx["chat_history"].append(HumanMessage(content=question))
                ctx["chat_history"].append(AIMessage(content=resp["output"]))
                logging.info(f"_dispatcher_loop: Updated chat_history for session '{session_id}'. Total messages: {len(ctx['chat_history'])}")

                fut.set_result(resp["output"])
                logging.info(f"_dispatcher_loop: Result set for Future for session '{session_id}'.")

            except Exception as e:
                logging.error(f"_dispatcher_loop: Error processing request for session '{session_id}': {e}", exc_info=True)
                fut.set_exception(e) # Propagate exception to the caller
                    
    # 后台线程结束，退出后台事件循环
    logging.info("_dispatcher_loop: Exited main loop, stopping asyncio event loop.")
    asyncio.get_running_loop().stop()


def start_dispatcher():
    """启动后台事件循环线程，仅调用一次"""
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=lambda: loop.run_forever(), daemon=True)
    t.start()
    asyncio.run_coroutine_threadsafe(_dispatcher_loop(), loop)
    print("后台事件循环线程已启动。")


def ask_agent(session_id: str, question: str) -> str:
    """主线程同步接口"""
    fut = Future()
    request_queue.put((session_id, question, fut))
    result = fut.result() # result is now the direct string output from the agent
    # return result.get("output", "Error: No output or messages key from agent.") # Old line causing error
    return result # Return the string directly


def stop_dispatcher():
    """优雅关闭"""
    request_queue.put((None, None, None))
    print("后台事件循环线程已退出。")
    
# 清除对话历史
# 参看https://langchain-ai.github.io/langgraph/how-tos/memory/delete-messages/
# langgraph.graph.message.py有bug，导致第1条消息始终没有被删掉。
# LangGraph现在还不支持删除整个对话，删除至保留第1轮对话。
# 所以最简便的清空方法是销毁实例并在新对话中建立新的实例
def clear_session(session_id: str):
    """清除用户对话"""
    global sessions
    if session_id in sessions:
        sessions.pop(session_id)
        print("Session ",session_id,"已清空。")
    

# ──────主线程交互示例 & 优雅退出 ──────
if __name__ == "__main__":
    # 启动后台事件循环线程
    start_dispatcher()
    
    # 用户226多轮连续对话
    session_id = "226"
    query = "what's (3 + 5) x 12?"
    ans = ask_agent(session_id, query)
    print(query)
    print(ans) # Directly print the output string
    query = "what's the result divided by 6?"
    ans = ask_agent(session_id, query)
    print(query)
    print(ans) # Directly print the output string
    query = "what is the weather in chengdu?"
    ans = ask_agent(session_id, query)
    print(query)
    print(ans) # Directly print the output string

    # 用户161多轮连续对话
    session_id = "161"
    query = "what is the weather in chongqing?"
    ans2 = ask_agent(session_id, query)
    print(query)
    print(ans2) # Directly print the output string
    query = "what's (3 + 5) x 12?"
    ans2 = ask_agent(session_id, query)
    print(query)
    print(ans2) # Directly print the output string
    query = "what's the result divided by 6?"
    ans2 = ask_agent(session_id, query)
    print(query)
    print(ans2) # Directly print the output string

    # 测试清除用户session
    clear_session("161")
    
    # 开始新的session
    session_id = "161"
    query = "what's (3 + 5) x 12?"
    ans3 = ask_agent(session_id, query)
    print(query)
    print(ans3) # Directly print the output string
   
    # 退出后台事件循环，关闭Agent
    stop_dispatcher()