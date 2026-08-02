"""Session-memory E2E: drive a real 25-round conversation over HTTP + SSE.

Runs inside the backend container (same network path a browser uses:
JWT login -> session create -> /send/ SSE streaming), then inspects the
SessionMemory rolling summary. Round pacing respects the 10/min throttle.

Run: docker compose exec -T backend python scripts/memory_e2e_conversation.py
"""
import json
import os
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "auditor.xu@test.ey.com"  # 普通用户（审计助理 徐明）——真人视角
PASSWORD = "Auditor#2026"
SPACE_ID = "0eea99d7-36b4-4476-839d-e53b9f535d7b"  # 星辰科技2026年报审计项目
ROUND_GAP_SECONDS = 7.0  # SendMessageRateThrottle = 10/minute

QUESTIONS = [
    "我是新来的审计助理，下周第一次出差深圳，住宿报销标准是多少？",
    "那餐补呢？",
    "报销要在多久之内提交？超过5000元的报销怎么审批？",
    "入职满一年的话年假有几天？",
    "请病假有什么提交要求？",
    "公司的核心工作时间是几点到几点？",
    "客户数据存放有什么信息安全要求？",
    "如果怀疑发生了数据泄露，要在多久之内向谁上报？",
    "星辰科技项目的签字合伙人和项目经理分别是谁？",
    "这个项目什么时候进场？外勤预计多久？",
    "收入循环有哪些重点风险？",
    "那细节测试的样本量是多少笔？",
    "截止测试怎么选样本？",
    "存货监盘安排在哪些地点？账面余额大概多少？",
    "A类存货怎么盘？",
    "库龄超过一年的呆滞芯片物料去年计提了多少减值？",
    "应收账款函证覆盖率要求是多少？前十大客户要发函吗？",
    "回函率目标是多少？",
    "没收到回函怎么办？",
    "项目风险评估会上识别了哪些舞弊风险？",
    "关键审计事项候选有哪几个？",
    "IFRS 15 的五步法收入确认模型是哪五步？",
    "我们最开始聊的住宿报销，一线城市的上限是多少来着？",
    "帮我把今天讨论的星辰科技项目审计要点总结成几条。",
    "第2条再展开说说。",
]


def login(client):
    resp = client.post(f"{BASE}/auth/token/", json={"email": EMAIL, "password": PASSWORD})
    resp.raise_for_status()
    return resp.json()["access"]


def create_session(client, headers):
    resp = client.post(
        f"{BASE}/chat/sessions/",
        json={"title": "记忆系统E2E-25轮真人测试"},
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def ask(client, headers, session_id, content):
    payload = {
        "content": content,
        "client_request_id": str(uuid.uuid4()),
    }
    tokens = []
    citations = 0
    error = None
    with client.stream(
        "POST",
        f"{BASE}/chat/sessions/{session_id}/send/",
        json=payload,
        headers=headers,
        timeout=120,
    ) as resp:
        if resp.status_code != 200:
            resp.read()
            return "", 0, f"http_{resp.status_code}:{resp.text[:200]}"
        event = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_raw = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(data_raw)
                except ValueError:
                    continue
                if event == "token":
                    tokens.append(data.get("token", ""))
                elif event == "citations" and isinstance(data, list):
                    citations = len(data)
                elif event == "error":
                    error = data.get("code")
    return "".join(tokens), citations, error


def main():
    results = []
    with httpx.Client(timeout=60) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}", "X-Space-Id": SPACE_ID}
        session_id = create_session(client, headers)
        print(f"SESSION_ID={session_id}", flush=True)

        for i, question in enumerate(QUESTIONS, start=1):
            started = time.monotonic()
            answer, citations, error = ask(client, headers, session_id, question)
            elapsed = round(time.monotonic() - started, 1)
            ok = bool(answer) and error is None
            refused = "没有足够的信息" in answer
            print(
                f"[R{i:02d}] {'OK ' if ok else 'ERR'} {elapsed}s cites={citations}"
                f"{' REFUSED' if refused else ''} Q: {question}",
                flush=True,
            )
            print(f"      A: {answer[:160].replace(chr(10), ' ')}", flush=True)
            results.append({
                "round": i, "question": question, "answer": answer,
                "citations": citations, "error": error, "elapsed_s": elapsed,
                "refused": refused,
            })
            if i < len(QUESTIONS):
                time.sleep(ROUND_GAP_SECONDS)

    out_path = os.path.join(os.path.dirname(__file__), "memory_e2e_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "rounds": results}, f,
                  ensure_ascii=False, indent=2)
    print(f"results written to {out_path}")

    # Inspect the rolling session memory produced by the Celery task.
    import django

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.docker")
    django.setup()
    from apps.chat.models import Message, SessionMemory

    memory = SessionMemory.objects.filter(session_id=session_id).first()
    total_messages = Message.objects.filter(session_id=session_id).count()
    print(f"session messages: {total_messages}")
    if memory:
        print(f"SessionMemory v{memory.summary_version} "
              f"summarized_until={memory.summarized_until}")
        print(f"summary: {memory.summary[:600]}")
        print(f"key_facts: {memory.key_facts}")
    else:
        print("SessionMemory: NOT CREATED")


if __name__ == "__main__":
    main()
