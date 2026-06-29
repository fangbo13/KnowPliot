# Copyright (c) 2026 Haibo Fang.
# Licensed under the CC BY-NC-SA 4.0 License.
# See LICENSE file in the project root for full license details.

"""Prompt builder for bilingual (EN/ZH) system prompts."""


class PromptBuilder:
    """Constructs the system prompt with context injection."""

    SYSTEM_PROMPT_EN = """You are EY Onboarding Assistant, an AI chatbot helping new employees at Ernst & Young.

RULES:
1. ONLY answer based on the provided context. If the context does not contain sufficient information, say "I don't have enough information to answer this question. Please contact your HR buddy or HR team."
2. ALWAYS cite your sources by referencing the document name and page number.
3. Be concise and professional. Use formatting (bullet points, numbered lists) for clarity.
4. If the question is about the employee's personal data, direct them to the HR portal.
5. NEVER make up policies, procedures, or benefits information.
6. Respond in English.

CONTEXT DOCUMENTS:
{context}

USER PROFILE:
Service Line: {service_line}
Office: {office}
Role Level: {role_level}
Start Date: {start_date}

CONVERSATION HISTORY:
{history}"""

    SYSTEM_PROMPT_ZH = """你是安永(EY)入职助手，一个帮助新员工的人工智能聊天机器人。

规则：
1. 仅基于提供的上下文回答。如信息不足，回复"我没有足够的信息来回答此问题，请联系您的人力资源伙伴或HR团队。"
2. 始终注明来源（文档名称、页码）。
3. 简洁专业，使用要点和编号列表。
4. 如果问题涉及员工个人数据，引导其前往HR门户。
5. 绝不编造政策、流程或福利信息。
6. 使用中文回复。

上下文文档：
{context}

用户信息：
业务线：{service_line}
办公室：{office}
职级：{role_level}
入职日期：{start_date}

对话历史：
{history}"""

    def build(self, context_chunks, conversation_history, user_profile, language="en"):
        """Build the system prompt.

        Args:
            context_chunks: List of retrieved chunk dicts.
            conversation_history: List of (role, content) tuples.
            user_profile: User model instance.
            language: 'en' or 'zh'.

        Returns:
            System prompt string.
        """
        context_str = self._format_context(context_chunks)
        history_str = self._format_history(conversation_history)

        template = self.SYSTEM_PROMPT_ZH if language == "zh" else self.SYSTEM_PROMPT_EN

        return template.format(
            context=context_str,
            service_line=getattr(user_profile, "service_line", "Not specified") or "Not specified",
            office=getattr(user_profile, "office_location", "Not specified") or "Not specified",
            role_level=getattr(user_profile, "role_level", "Not specified") or "Not specified",
            start_date=str(user_profile.start_date) if getattr(user_profile, "start_date", None) else "Not specified",
            history=history_str,
        )

    def _format_context(self, chunks):
        """Format retrieved chunks as context string."""
        parts = []
        for i, chunk in enumerate(chunks):
            page_info = ""
            if chunk.get("page_number"):
                page_info = f" (p.{chunk['page_number']})"

            parts.append(
                f"[文档 {i + 1}] {chunk['document_title']}{page_info}\n"
                f"{chunk['content']}\n"
            )
        return "\n---\n".join(parts)

    def _format_history(self, history):
        """Format conversation history."""
        lines = []
        for role, content in history:
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
