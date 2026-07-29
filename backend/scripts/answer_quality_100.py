"""Answer-quality benchmark: 100 turns over real SSE, before/after RAG fallback.

Fixed 100-question set across 4 categories:
  kb       - knowledge-base audit questions (expect answer + citations)
  general  - general/definition questions NOT covered by the KB (e.g. "CCT是啥",
             "EBITDA是什么") — the target of the general-knowledge fallback
  chitchat - greetings / small talk
  mixed    - follow-ups that mix KB context with general concepts

Metrics: refusal rate (total + per category), kb citation hit rate, general
effective-answer rate (non-refusal; disclaimer presence tracked separately),
error rate, average latency.

Run (inside the backend container):
  docker compose exec -T backend python scripts/answer_quality_100.py --label baseline
  docker compose exec -T backend python scripts/answer_quality_100.py --label optimized
"""
import argparse
import json
import os
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8000/api/v1"
EMAIL = "auditor.xu@test.ey.com"
PASSWORD = "KnowPilot@2026"
SPACE_ID = "0cb246e8-c8a7-45eb-b70c-232e38e2bd04"  # 创新药械2026 IPO审计项目
ROUND_GAP_SECONDS = 7.0  # stay under the 10/min chat throttle
REFUSAL_MARKERS = (
    "没有足够的信息",
    "don't have enough information",
    "沒有足夠的信息",
)
DISCLAIMER_MARKERS = (
    "基于通用知识",
    "基於通用知識",
    "general knowledge",
    "未引用本知识库",
    "not from the knowledge base",
    "not based on the knowledge base",
)


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
    try:
        with client.stream(
            "POST", f"{BASE}/chat/sessions/{session_id}/send/",
            json=payload, headers=headers, timeout=180,
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
    except httpx.HTTPError as exc:
        return "".join(tokens), citations, f"transport_{type(exc).__name__}"
    return "".join(tokens), citations, error


# ---------------------------------------------------------------------------
# Fixed question set: (question, category)
#   Session plans: (title, answer_mode, library-names, [(question, category)])
# ---------------------------------------------------------------------------
def build_plans(pool):
    ifrs = pool.get("IFRS 参考库")
    policy = pool.get("公司制度公共参考库")
    cas = pool.get("中国会计准则参考库")
    ipo = pool.get("IPO 案例参考库")

    return [
        ("Q100-S1-项目事实", "fast", [], [
            ("这个IPO项目的签字合伙人和项目经理分别是谁？", "kb"),
            ("项目什么时候进场？外勤预计多久？", "kb"),
            ("研发支出资本化2025年的金额和占比是多少？", "kb"),
            ("收入里直销和经销各占多少？", "kb"),
            ("经销退货率Q4是多少？", "kb"),
            ("关联方一共识别了多少家？", "kb"),
            ("CCT是啥？是持续关联交易吗？", "general"),
            ("EBITDA是什么意思？", "general"),
            ("你好，今天过得怎么样？", "chitchat"),
            ("谢谢你的帮助！", "chitchat"),
        ]),
        ("Q100-S2-制度库", "fast", [n for n in [policy] if n], [
            ("差旅住宿一线城市报销上限是多少？", "kb"),
            ("那餐补呢？", "kb"),
            ("报销要在多久内提交？", "kb"),
            ("超过5000元的报销怎么审批？", "kb"),
            ("加班餐费有补贴吗？", "kb"),
            ("什么是SOX法案？", "general"),
            ("什么是四大会计师事务所？", "general"),
            ("穿透式核查是什么意思？", "general"),
            ("你是谁开发的？", "chitchat"),
            ("辛苦啦！", "chitchat"),
        ]),
        ("Q100-S3-三库深度", "deep", [n for n in [ifrs, cas, ipo] if n], [
            ("IFRS 15 收入确认的五步法是哪五步？", "kb"),
            ("中国会计准则里收入什么时候确认？", "kb"),
            ("那IFRS和中国准则在收入确认上思路一致吗？", "kb"),
            ("科创板IPO审核重点关注哪些方面？", "kb"),
            ("结合这个项目，经销收入的跨期风险该怎么核查？", "kb"),
            ("IFRS 16 租赁是怎么规定的？", "kb"),
            ("资产减值在中国准则里怎么处理？", "kb"),
            ("刚才说的五步法，跟波特五力模型有什么区别？", "mixed"),
            ("那收入确认舞弊在国际上有什么著名案例？", "mixed"),
            ("结合准则谈谈，什么是职业怀疑态度？", "mixed"),
        ]),
        ("Q100-S4-通用定义", "fast", [], [
            ("什么是重要性水平？", "general"),
            ("函证是什么意思？", "general"),
            ("审计抽样有哪些方法？", "general"),
            ("什么是内部控制五要素？", "general"),
            ("商誉减值测试怎么做？", "general"),
            ("应收账款周转率怎么计算？", "general"),
            ("什么是VIE架构？", "general"),
            ("IPO和借壳上市有什么区别？", "general"),
            ("在吗？", "chitchat"),
            ("再见！", "chitchat"),
        ]),
        ("Q100-S5-IFRS-EN", "deep", [n for n in [ifrs] if n], [
            ("What are the five steps of IFRS 15 revenue recognition?", "kb"),
            ("What does IFRS 16 require from lessees?", "kb"),
            ("What is a performance obligation under IFRS 15?", "kb"),
            ("How is the transaction price allocated under IFRS 15?", "kb"),
            ("When is revenue recognized over time under IFRS 15?", "kb"),
            ("What is CCT? Does it mean continuing connected transactions?", "general"),
            ("What does EBITDA stand for?", "general"),
            ("What is materiality in auditing?", "general"),
            ("Comparing IFRS 15 with US GAAP ASC 606, are they converged?", "mixed"),
            ("Based on IFRS 16, how would sale-and-leaseback affect gearing ratios?", "mixed"),
        ]),
        ("Q100-S6-通用-EN", "fast", [], [
            ("What is your role?", "general"),
            ("What is the difference between audit and assurance?", "general"),
            ("What is a going concern opinion?", "general"),
            ("What are audit assertions?", "general"),
            ("What is sampling risk?", "general"),
            ("What is professional skepticism?", "general"),
            ("Hello! How are you today?", "chitchat"),
            ("Thanks a lot, great job!", "chitchat"),
            ("Can you recommend a movie?", "chitchat"),
            ("Good bye!", "chitchat"),
        ]),
        ("Q100-S7-会计准则", "fast", [n for n in [cas] if n], [
            ("中国会计准则第8号讲的是什么？", "kb"),
            ("资产减值损失确认后能转回吗？", "kb"),
            ("收入准则的控制权转移怎么判断？", "kb"),
            ("合同负债和预收账款有什么区别？", "kb"),
            ("研发支出资本化的条件是什么？", "kb"),
            ("存货跌价准备怎么计提？", "kb"),
            ("这些准则跟税法上的处理差异大吗？", "mixed"),
            ("准则里的公允价值和市场价是一回事吗？", "mixed"),
            ("那递延所得税是怎么产生的？", "mixed"),
            ("刚才说的减值转回，国际准则允许吗？", "mixed"),
        ]),
        ("Q100-S8-IPO案例", "deep", [n for n in [ipo] if n], [
            ("IPO收入核查案例里提到哪些异常信号？", "kb"),
            ("科创板对研发费用资本化怎么关注？", "kb"),
            ("经销模式退货率异常说明什么风险？", "kb"),
            ("IPO审核中关联方资金往来怎么核查？", "kb"),
            ("案例里压货和跨期确认有什么关系？", "kb"),
            ("辅导期一般要多久？", "kb"),
            ("什么是红筹回归？", "general"),
            ("A股和港股上市条件主要差异是什么？", "general"),
            ("结合案例，瑞幸咖啡造假案的教训是什么？", "mixed"),
            ("那审计师在IPO造假案中一般承担什么责任？", "mixed"),
        ]),
        ("Q100-S9-闲聊混合", "fast", [], [
            ("嗨！", "chitchat"),
            ("你能做什么？", "chitchat"),
            ("今天天气怎么样？", "chitchat"),
            ("给我讲个笑话吧", "chitchat"),
            ("你喜欢喝咖啡还是茶？", "chitchat"),
            ("什么是尽职调查？", "general"),
            ("内控缺陷分几个等级？", "general"),
            ("什么是舞弊三角理论？", "general"),
            ("独立性对审计师意味着什么？", "general"),
            ("什么是关键审计事项？", "general"),
        ]),
        ("Q100-S10-双库深度", "deep", [n for n in [ifrs, cas] if n], [
            ("IFRS 15 第三步是什么？", "kb"),
            ("使用权资产是什么意思？", "kb"),
            ("中国准则下借款费用什么时候资本化？", "kb"),
            ("政府补助在中国准则里怎么核算？", "kb"),
            ("金融工具减值的预期信用损失模型是什么？", "kb"),
            ("外币折算差额计入哪里？", "kb"),
            ("这些准则差异会影响这个项目的申报报表吗？", "mixed"),
            ("准则说的重大影响和控制怎么区分？", "mixed"),
            ("那权益法和成本法的分界线是什么？", "mixed"),
            ("综合来看，这个项目最需要关注的准则问题是什么？", "mixed"),
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="baseline | optimized")
    parser.add_argument("--limit", type=int, default=0, help="debug: stop after N turns")
    args = parser.parse_args()

    results = []
    with httpx.Client(timeout=60) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}", "X-Space-Id": SPACE_ID}
        pool = get_library_pool(client, headers)
        print(f"label={args.label} library pool: {list(pool.keys())}", flush=True)
        plans = build_plans(pool)

        turn_no = 0
        stop = False
        for title, mode, lib_names, questions in plans:
            if stop:
                break
            lib_ids = [pool[name] for name in lib_names if name in pool]
            session_id = new_session(client, headers, f"{title}-{args.label}")
            print(f"\n=== {title} | mode={mode} | libs={lib_names}", flush=True)
            for question, category in questions:
                turn_no += 1
                started = time.monotonic()
                answer, citations, error = ask(
                    client, headers, session_id, question,
                    answer_mode=mode, selected_library_ids=lib_ids,
                )
                if error == "http_401":
                    # Access token expired mid-run — re-login and retry once.
                    token = login(client)
                    headers = {"Authorization": f"Bearer {token}", "X-Space-Id": SPACE_ID}
                    answer, citations, error = ask(
                        client, headers, session_id, question,
                        answer_mode=mode, selected_library_ids=lib_ids,
                    )
                outcome = classify(answer, error)
                disclaimed = any(m in answer for m in DISCLAIMER_MARKERS)
                elapsed = round(time.monotonic() - started, 1)
                print(f"[T{turn_no:03d}] {mode} {category:8s} {outcome:6s} "
                      f"{elapsed}s cite={citations} disc={int(disclaimed)} "
                      f"{question[:32]}", flush=True)
                results.append({
                    "turn": turn_no, "session": title, "mode": mode,
                    "question": question, "category": category,
                    "outcome": outcome, "citations": citations,
                    "disclaimed": disclaimed, "error": error,
                    "elapsed_s": elapsed, "answer": answer[:500],
                })
                if args.limit and turn_no >= args.limit:
                    stop = True
                    break
                time.sleep(ROUND_GAP_SECONDS)

    # ---- summary ----
    def rate(rows, pred):
        return round(100.0 * sum(1 for r in rows if pred(r)) / len(rows), 1) if rows else 0.0

    summary = {"label": args.label, "total": len(results)}
    for cat in ("kb", "general", "chitchat", "mixed"):
        rows = [r for r in results if r["category"] == cat]
        summary[cat] = {
            "n": len(rows),
            "refusal_pct": rate(rows, lambda r: r["outcome"] == "refuse"),
            "answered_pct": rate(rows, lambda r: r["outcome"] == "answer"),
            "error_pct": rate(rows, lambda r: r["outcome"] in ("error", "empty")),
            "citation_pct": rate(rows, lambda r: r["citations"] > 0),
            "disclaimer_pct": rate(rows, lambda r: r["disclaimed"]),
            "avg_latency_s": round(
                sum(r["elapsed_s"] for r in rows) / len(rows), 1) if rows else 0.0,
        }
    summary["overall_refusal_pct"] = rate(results, lambda r: r["outcome"] == "refuse")
    summary["overall_error_pct"] = rate(results, lambda r: r["outcome"] in ("error", "empty"))

    out = os.path.join(os.path.dirname(__file__), f"answer_quality_100_{args.label}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

    print("\n===== SUMMARY =====", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"results -> {out}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
