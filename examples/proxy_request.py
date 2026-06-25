"""Example dry-run proxy request preparation."""

from kompressor.proxy import prepare_messages_request

request = {"messages": [{"role": "user", "content": '[{"id":"AX-912","event":"auth_timeout_error"}]'}]}
print(prepare_messages_request(request))
