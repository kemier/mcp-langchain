# Placeholder for web template functions

def get_home_template():
    # TODO: Implement actual home page HTML template
    return "<html><body><h1>Home Page Placeholder</h1></body></html>"

def get_chat_session_template(session_id: str, history: list):
    # TODO: Implement actual chat session HTML template
    # history might be a list of tuples (query, response)
    history_html = "".join([f"<p><b>User:</b> {q}</p><p><b>Bot:</b> {r}</p>" for q, r in history])
    return f"""<html><body>
        <h1>Chat Session: {session_id}</h1>
        <div>{history_html}</div>
        <p>Chat input placeholder...</p>
    </body></html>""" 