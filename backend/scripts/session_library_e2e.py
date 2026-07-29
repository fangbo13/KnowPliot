"""Session-library-selection E2E: 60+ turns over real SSE.

Drives the auditor.xu user through several sessions with different library
selections and answer modes, covering logical multi-turn, crosstalk (topic
jumps / chit-chat), and clarification ("没懂/没理解") turns. Records per-turn
outcome and library provenance, then prints a Fast/Deep x valid/invalid matrix
plus a JSON dump for the acceptance report.

Run: docker compose exec -T backend python scripts/session_library_e2e.py
"""
import json
import os
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "auditor.xu@test.ey.com"
PASSWORD = "Auditor#2026"
SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"  # 创新药械2026 IPO审计项目
ROUND_GAP_SECONDS = 7.0  # under the 10/min throttle
REFUSAL_MARKERS = ("没有足够的信息", "don't have enough information")


def login(client):
    r = client.post(f"{BASE}/auth/token/", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access"]


def get_library_pool(client, headers):
    r = client.get(f"{BASE}/documents/library-references/", headers=headers)
    r.raise_for_status()
    return {ref["library_name"]: ref["library"] for ref in r.json() if ref.get("enabled")}


def new_session(client, headers, title):
    r = client.post(f"{BASE}/chat/sessions/", json={"title": title}, headers=headers)
    r.raise_for_status()
    return r.json()["id"]


def ask(client, headers, session_id, content, *, answer_mode, selected_library_ids):
    payload = {
        "content": content,
        "client_request_id": str(uuid.uuid4()),
        "answer_mode": answer_mode,
        "selected_library_ids": selected_library_ids,
    }
    tokens, citations, error = [], 0, None
    with client.stream(
        "POST", f"{BASE}/chat/sessions/{session_id}/send/",
        json=payload, headers=headers, timeout=150,
    ) as resp:
        if resp.status_code != 200:
            resp.read()
            return "", 0, f"http_{resp.status_code}"
        event = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                if event == "token":
                    tokens.append(data.get("token", ""))
                elif event == "citations" and isinstance(data, list):
                    citations = len(data)
                elif event == "error":
                    error = data.get("code")
    return "".join(tokens), citations, error


# Session plans: (title, answer_mode, library-names, [ (question, kind, expect) ])
#   kind: logical / crosstalk / clarify
#   expect: 'answer' (should answer) or 'refuse' (should refuse / space-only)
def build_plans(pool):
    ifrs = pool.get("IFRS 参考库")
    policy = pool.get("公司制度公共参考库")
    cas = pool.get("中国会计准则参考库")
    ipo = pool.get("IPO 案例参考库")

    return [
        # A) Fast, NO libraries — project-only. Public-lib topics should refuse.
        ("A-Fast-无库-项目", "fast", [], [
            ("这个IPO项目的签字合伙人和项目经理分别是谁？", "logical", "answer"),
            ("项目什么时候进场？外勤预计多久？", "logical", "answer"),
            ("研发支出资本化2025年的金额和占比是多少？", "logical", "answer"),
            ("那资本化的审计关注点有哪些？", "logical", "answer"),
            ("收入里直销和经销各占多少？", "logical", "answer"),
            ("顺便问下，公司差旅住宿一线城市报销上限是多少？", "crosstalk", "refuse"),
            ("哎对了你喜欢喝咖啡还是茶？", "crosstalk", "refuse"),
            ("回到正题，经销退货率Q4是多少？", "logical", "answer"),
            ("没懂，这个退货率为什么值得关注？", "clarify", "answer"),
            ("关联方一共识别了多少家？", "logical", "answer"),
        ]),
        # B) Fast, policy library only — reimbursement now answerable.
        ("B-Fast-制度库", "fast", [n for n in [policy] if n], [
            ("差旅住宿一线城市报销上限是多少？", "logical", "answer"),
            ("那餐补呢？", "logical", "answer"),
            ("报销要在多久内提交？", "logical", "answer"),
            ("超过5000元的报销怎么审批？", "logical", "answer"),
            ("那这个项目的存货减值上年计提了多少？", "crosstalk", "answer"),
            ("没理解，减值和资本化是一回事吗？", "clarify", "answer"),
            ("IFRS 15 的五步法是哪五步？", "logical", "refuse"),
            ("你觉得今天天气怎么样？", "crosstalk", "refuse"),
            ("再确认下住宿上限那个数字？", "logical", "answer"),
            ("项目现场负责人是谁来着？", "logical", "answer"),
        ]),
        # C) Deep, three libraries (IFRS + CAS + IPO) — cross-domain.
        ("C-Deep-三库", "deep", [n for n in [ifrs, cas, ipo] if n], [
            ("IFRS 15 收入确认的五步法是哪五步？", "logical", "answer"),
            ("中国会计准则里收入什么时候确认？", "logical", "answer"),
            ("那IFRS和中国准则在收入确认上思路一致吗？", "logical", "answer"),
            ("科创板IPO审核重点关注哪些方面？", "logical", "answer"),
            ("结合这个项目，经销收入的跨期风险该怎么核查？", "logical", "answer"),
            ("突然想问，IFRS 16 租赁是怎么规定的？", "crosstalk", "answer"),
            ("没懂，使用权资产是什么意思？", "clarify", "answer"),
            ("资产减值在中国准则里怎么处理？", "logical", "answer"),
            ("那这个项目存货减值风险主要在哪些存货？", "logical", "answer"),
            ("IPO收入核查案例里提到哪些异常信号？", "logical", "answer"),
            ("综合来看这个项目的三个关键审计事项候选是什么？", "logical", "answer"),
            ("先不聊这个，帮我推荐一部电影？", "crosstalk", "refuse"),
        ]),
        # D) Deep, single library (IFRS) — focused deep answers + follow-ups.
        ("D-Deep-单库", "deep", [n for n in [ifrs] if n], [
            ("IFRS 15 第三步是什么？", "logical", "answer"),
            ("那第五步呢？", "logical", "answer"),
            ("IFRS 16 对承租人有什么要求？", "logical", "answer"),
            ("这个项目的研发资本化占研发投入多少？", "crosstalk", "answer"),
            ("没理解，能再解释下履约义务吗？", "clarify", "answer"),
            ("关联方拆借那笔3000万清理了吗？", "logical", "answer"),
        ]),
        # E) Fast, project + one library switch mid-session (policy).
        ("E-Fast-混合", "fast", [n for n in [policy] if n], [
            ("项目立项客户是哪家公司？主营什么？", "logical", "answer"),
            ("拟上市板块是哪个？", "logical", "answer"),
            ("差旅报销住宿上限多少？", "logical", "answer"),
            ("那内部控制关注哪些IT一般控制？", "crosstalk", "answer"),
            ("没懂，收入接口自动化控制是啥？", "clarify", "answer"),
            ("质量复核合伙人是谁？", "logical", "answer"),
            ("再问下餐补标准？", "logical", "answer"),
            ("你能帮我订火车票吗？", "crosstalk", "refuse"),
        ]),
        # F) Deep, two libraries (CAS + IPO).
        ("F-Deep-两库", "deep", [n for n in [cas, ipo] if n], [
            ("中国会计准则第8号讲的是什么？", "logical", "answer"),
            ("科创板对研发费用资本化怎么关注？", "logical", "answer"),
            ("那结合项目，资本化时点怎么审？", "logical", "answer"),
            ("经销模式退货率异常说明什么风险？", "logical", "answer"),
            ("没理解，压货和跨期确认有什么关系？", "clarify", "answer"),
            ("项目关联方交易主要关注什么？", "logical", "answer"),
        ]),
    ]


def classify(answer, error):
    if error:
        return "error"
    if not answer.strip():
        return "empty"
    if any(m in answer for m in REFUSAL_MARKERS):
        return "refuse"
    return "answer"


def main():
    results = []
    with httpx.Client(timeout=60) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}", "X-Space-Id": SPACE_ID}
        pool = get_library_pool(client, headers)
        print(f"library pool: {list(pool.keys())}", flush=True)
        plans = build_plans(pool)

        turn_no = 0
        for title, mode, lib_names, questions in plans:
            lib_ids = [pool[name] for name in lib_names if name in pool]
            session_id = new_session(client, headers, title)
            print(f"\n=== {title} | mode={mode} | libs={lib_names} | session={session_id}",
                  flush=True)
            for question, kind, expect in questions:
                turn_no += 1
                started = time.monotonic()
                answer, citations, error = ask(
                    client, headers, session_id, question,
                    answer_mode=mode, selected_library_ids=lib_ids,
                )
                outcome = classify(answer, error)
                elapsed = round(time.monotonic() - started, 1)
                ok_expect = (
                    (expect == "answer" and outcome == "answer")
                    or (expect == "refuse" and outcome in ("refuse", "empty"))
                )
                print(f"[T{turn_no:02d}] {mode} {outcome:6s} exp={expect} "
                      f"{'OK' if ok_expect else 'XX'} {elapsed}s cite={citations} "
                      f"{kind}: {question[:28]}", flush=True)
                results.append({
                    "turn": turn_no, "session": title, "mode": mode,
                    "libs": lib_names, "question": question, "kind": kind,
                    "expect": expect, "outcome": outcome, "matched": ok_expect,
                    "citations": citations, "error": error, "elapsed_s": elapsed,
                    "answer": answer[:400],
                })
                time.sleep(ROUND_GAP_SECONDS)

    out = os.path.join(os.path.dirname(__file__), "session_library_e2e_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Fast/Deep x valid/invalid matrix (valid = matched expectation).
    def bucket(mode):
        rows = [r for r in results if r["mode"] == mode]
        matched = sum(1 for r in rows if r["matched"])
        return len(rows), matched, len(rows) - matched

    print("\n===== ACCEPTANCE MATRIX =====", flush=True)
    for mode in ("fast", "deep"):
        total, valid, invalid = bucket(mode)
        print(f"{mode}: total={total} valid={valid} invalid={invalid}", flush=True)
    total = len(results)
    valid = sum(1 for r in results if r["matched"])
    print(f"ALL: total={total} valid={valid} invalid={total - valid}", flush=True)
    print(f"results -> {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
