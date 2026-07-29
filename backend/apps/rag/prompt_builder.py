# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Prompt builder for bilingual (EN/ZH) system prompts."""


class PromptBuilder:
    """Constructs the system prompt with context injection."""

    SYSTEM_PROMPT_EN = """You are EY Onboarding Assistant, an AI chatbot helping new employees at Ernst & Young.

RULES:
1. Answer based on the provided context documents. Treat them as relevant evidence — they were retrieved for this question. Synthesize the best possible answer from what they contain, even when they only partially cover the question. ONLY if NONE of the context documents relate to the question at all, say "I don't have enough information to answer this question. Please add the relevant knowledge documents or contact your knowledge base administrator." — never refuse when at least one document contains related information.
2. ALWAYS cite your sources by referencing the document name and page number.
3. Be concise and professional. Use formatting (bullet points, numbered lists) for clarity.
4. If the question is about the employee's personal data, direct them to the HR portal.
5. NEVER make up policies, procedures, or benefits information.
6. If context documents conflict with each other, point out the conflict and prefer the document with the newer version / currently effective one.
7. If the question uses colloquial or abbreviated terms, first resolve them against the session memory and conversation so they map onto the formal terms used in the documents (e.g. a shorthand allowance name may refer to the meal allowance already discussed).
8. If only PART of the question lacks supporting context, answer the supported part normally and explicitly state which specific item is not covered by the documents — do NOT refuse the whole question.
9. Respond in {resolved_language}.

CONTEXT DOCUMENTS:
{context}

USER PROFILE:
Service Line: {service_line}
Office: {office}
Role Level: {role_level}
Start Date: {start_date}

SESSION MEMORY:
{memory}"""

    SYSTEM_PROMPT_ZH = """你是安永(EY)入职助手，一个帮助新员工的人工智能聊天机器人。

规则：
1. 基于提供的上下文文档回答。这些文档是针对本问题检索出的相关证据，即使只能部分覆盖问题，也要尽力结合其内容给出最佳回答。仅当所有上下文文档与问题完全无关时，才回复“我没有足够的信息来回答此问题，请补充相关知识文档或联系知识库管理员。”——只要有任一文档包含相关信息，就不得拒答。
2. 始终注明来源（文档名称、页码）。
3. 简洁专业，使用要点和编号列表。
4. 如果问题涉及员工个人数据，引导其前往HR门户。
5. 绝不编造政策、流程或福利信息。
6. 若上下文文档之间存在冲突，指出冲突并优先引用版本较新/生效中的文档。
7. 若问题中出现口语化或简称词汇，先结合会话记忆与对话历史将其对应到文档中的正式术语（例如用户的简称可能指代前面已讨论过的某项补贴）。
8. 若问题仅部分内容缺乏文档依据，应正常回答有依据的部分，并明确指出哪一项在文档中没有规定——不要整体拒绝回答。
9. Respond in {resolved_language}.

上下文文档：
{context}

用户信息：
业务线：{service_line}
办公室：{office}
职级：{role_level}
入职日期：{start_date}

会话记忆：
{memory}"""

    def build(
        self,
        context_chunks,
        conversation_history,
        user_profile,
        language="en",
        session_summary="",
        key_facts=(),
    ):
        """Build the system prompt.

        Args:
            context_chunks: List of retrieved chunk dicts.
            conversation_history: List of (role, content) tuples — legacy
                flattened history. Pass an empty list when recent history is
                sent as a real multi-turn messages array instead.
            user_profile: User model instance.
            language: resolved reply language ('en' or 'zh') — drives the
                dynamic "Respond in {resolved_language}" instruction so the
                prompt never hardcodes a fixed reply language.
            session_summary: rolling summary of earlier session rounds
                (long-term session memory).
            key_facts: structured key facts extracted from earlier rounds.

        Returns:
            System prompt string.
        """
        context_str = self._format_context(context_chunks)
        memory_str = self._format_memory(
            session_summary, key_facts, conversation_history, language
        )

        template = self.SYSTEM_PROMPT_ZH if language == "zh" else self.SYSTEM_PROMPT_EN
        # Map the resolved reply language to the human-readable name used in
        # the dynamic "Respond in {resolved_language}" instruction.
        resolved_language_name = "Chinese" if language == "zh" else "English"

        return template.format(
            context=context_str,
            service_line=getattr(user_profile, "service_line", "Not specified") or "Not specified",
            office=getattr(user_profile, "office_location", "Not specified") or "Not specified",
            role_level=getattr(user_profile, "role_level", "Not specified") or "Not specified",
            start_date=str(user_profile.start_date) if getattr(user_profile, "start_date", None) else "Not specified",
            memory=memory_str,
            resolved_language=resolved_language_name,
        )

    def _format_context(self, chunks):
        """Format retrieved chunks as context string."""
        parts = []
        has_reference = any(chunk.get("source_library") for chunk in chunks)
        for i, chunk in enumerate(chunks):
            page_info = ""
            if chunk.get("page_number"):
                page_info = f" (p.{chunk['page_number']})"
            # KB optimization spec §3.3: mark chunks that come from a shared
            # reference library so the model can attribute authoritative sources.
            library = chunk.get("source_library")
            source_tag = f" [参考库: {library}]" if library else ""
            parts.append(
                f"[文档 {i + 1}] {chunk['document_title']}{page_info}{source_tag}\n"
                f"{chunk['content']}\n"
            )
        context = "\n---\n".join(parts)
        if has_reference:
            context = (
                "说明：标有「[参考库: ...]」的文档来自共享参考库（如 IFRS / 中国会计准则 / IPO 案例），"
                "属权威参考内容；其余为当前项目本地知识。请结合本项目具体情况与参考库权威内容综合作答，"
                "若二者存在差异请明确指出。\n\n"
                + context
            )
        return context

    def _format_memory(self, session_summary, key_facts, history, language="en"):
        """Compose the session-memory block: summary + key facts (+ legacy history).

        The rolling summary keeps agreements from rounds that already fell out
        of the verbatim window; ``history`` is only rendered here in legacy
        mode (CHAT_MULTI_TURN_MESSAGES off).
        """
        zh = language == "zh"
        segments = []
        if session_summary:
            label = (
                "【本次对话早前内容的摘要】" if zh
                else "[Summary of earlier rounds in this conversation]"
            )
            segments.append(f"{label}\n{session_summary}")
        if key_facts:
            label = "【关键事实】" if zh else "[Key facts]"
            facts = "\n".join(f"- {fact}" for fact in key_facts)
            segments.append(f"{label}\n{facts}")
        if history:
            label = "【近期对话】" if zh else "[Recent conversation]"
            segments.append(f"{label}\n{self._format_history(history)}")
        if not segments:
            return "（无）" if zh else "(none)"
        return "\n\n".join(segments)

    def _format_history(self, history):
        """Format conversation history."""
        lines = []
        for role, content in history:
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
