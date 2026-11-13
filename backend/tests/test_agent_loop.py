from kelvo.components.agent import (NUDGE, estimate_tokens, fit_context, looks_unfinished,
                                    parse_text_tool_calls)
from tests.test_app import build, final_messages


def done_steps(evs):
    return [e["data"]["step"] for e in evs if e["event"] == "step" and e["data"]["step"]["status"] == "done"]


def test_looks_unfinished():
    for t in ["I'll search the web for that.", "Let me check the files first:", "Now I'll run the tests…", "", "   "]:
        assert looks_unfinished(t), t
    for t in ["Paris is the capital of France.", "Done! Let me know if you need anything else.",
              "Should I also update the README?", "The answer is 42. I hope this helps."]:
        assert not looks_unfinished(t), t


def test_parse_text_tool_calls():
    tools = {"calculator": 1, "web_search": 1}
    calls, rest = parse_text_tool_calls('Ok.\n<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>', tools)
    assert calls == [{"function": {"name": "web_search", "arguments": {"query": "x"}}}] and rest == "Ok."
    calls, _ = parse_text_tool_calls('```json\n{"name": "calculator", "parameters": {"expression": "1+1"}}\n```', tools)
    assert calls[0]["function"]["arguments"] == {"expression": "1+1"}
    assert parse_text_tool_calls('{"name": "rm_rf", "arguments": {}}', tools) == ([], '{"name": "rm_rf", "arguments": {}}')
    assert parse_text_tool_calls("Just an answer.", tools)[0] == []


def test_fit_context_trims_oldest_tool_output_first():
    msgs = [{"role": "system", "content": "rules"}, {"role": "user", "content": "go"}]
    for i in range(5):
        msgs.append({"role": "tool", "content": f"output{i} " + "x" * 6000})
    used, trimmed = fit_context(msgs, 4096)
    assert trimmed >= 1 and msgs[0]["content"] == "rules"
    assert "were removed to fit" in msgs[2]["content"]  # oldest trimmed
    assert msgs[-1]["content"].startswith("output4") and "removed" not in msgs[-1]["content"]  # newest two intact
    assert "removed" not in msgs[-2]["content"]
    small = [{"role": "user", "content": "hi"}]
    assert fit_context(small, 4096)[1] == 0 and estimate_tokens(small) < 10


def test_agent_is_nudged_to_actually_call_the_tool(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "announce:calculator:6*7")
    assert any(e["event"] == "status" and "Reminding" in e["data"]["text"] for e in evs)
    steps = done_steps(evs)
    assert steps and steps[0]["name"] == "calculator" and '"result": 42' in steps[0]["output"]
    assert final_messages(evs)[0].startswith("Result:")


def test_text_tool_calls_are_executed(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "rawcall:calculator:10/4")
    steps = done_steps(evs)
    assert steps[0]["name"] == "calculator" and "2.5" in steps[0]["output"]


def test_nudges_are_limited(client):
    """A model that never calls the tool gets at most two reminders, then its reply is the answer."""
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "announce:no_such_tool:x")
    assert sum(1 for e in evs if e["event"] == "status") == 2
    assert final_messages(evs)[0] == "I'll use no_such_tool to do that now."


def test_plain_answers_are_not_nudged(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    evs = build(client, f["id"], "What is Ollama?")
    assert not any(e["event"] == "status" for e in evs)


def test_thinking_streams_to_the_chat(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path))
    f = client.post("/api/flows", json={"template": "power-agent"}).json()  # Think is on
    evs = build(client, f["id"], "hello")
    assert "".join(e["data"]["chunk"] for e in evs if e["event"] == "thinking") == "Let me work this out."


def test_context_warning_event(client):
    f = client.post("/api/flows", json={"template": "simple-agent"}).json()
    data = f["data"]
    for n in data["nodes"]:
        if n["data"].get("type") == "Agent":
            n["data"]["params"]["num_ctx"] = 256  # tiny window: the first message already fills it
    evs = build(client, f["id"], "word " * 400, data=data)
    w = [e["data"] for e in evs if e["event"] == "context_warning"]
    assert len(w) == 1 and w[0]["limit"] == 256 and w[0]["used"] > 200
    assert NUDGE  # exported for the UI wording
