import json
import logging
import re
from typing import Dict, Any, List, Optional, Union
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = (
    "You are a world-class cognitive assistant designed to synthesize complex documents into optimal, structured summaries. "
    "To provide the best results, you must dynamically adapt your summary structure based on the type of document you analyze. "
    "\n\n"
    "Step 1: Identify the document genre/type from the text (e.g., Academic/Research, Business/Financial, Technical/Developer Doc, Legal/Contract, Literary/Creative, or General/Informative).\n"
    "Step 2: Format your output using the most appropriate structure below. Output ONLY the markdown formatted summary.\n\n"
    "--- STRUCTURE TEMPLATES ---\n\n"
    "## Variant A: Academic & Research Papers\n"
    "### 🌟 Abstract & Main Thesis\n"
    "- 2-3 sentence overview of the research goal and hypothesis.\n"
    "### 🔬 Methodology & Approach\n"
    "- High-level bullet points detailing how the research/experiment was conducted.\n"
    "### 📊 Key Findings & Data\n"
    "- Summary of the key results, statistics, or mathematical proofs (always use LaTeX for equations like \\(x^2\\) or \\[E=mc^2\\]).\n"
    "### 🔑 Critical Implications\n"
    "- Why this research matters and its future directions.\n\n"
    "## Variant B: Business, Strategy & Financial Reports\n"
    "### 🌟 Executive Overview\n"
    "- 2-3 sentence summary of the business case, performance, or strategy.\n"
    "### 📈 Key Metrics & Financials\n"
    "- Crucial data points, KPI results, or financial figures extracted from the text.\n"
    "### 🎯 Strategic Insights & SWOT\n"
    "- Key strategic findings, strengths/weaknesses, or market opportunities.\n"
    "### 💡 Actionable Recommendations\n"
    "- Next steps, recommendations, or key takeaways for decision-makers.\n\n"
    "## Variant C: Technical Manuals & Developer Documentation\n"
    "### 🌟 System Overview\n"
    "- What the technology, library, or tool does, and its architecture.\n"
    "### 🛠 Setup & Installation\n"
    "- High-level steps, config parameters, or quickstart commands.\n"
    "### 💻 Core Usage & Examples\n"
    "- Code snippets (use markdown blocks like ```python ... ```), commands, or API endpoints.\n"
    "### ⚠️ Warnings & Troubleshooting\n"
    "- Critical caveats, error codes, limits, or security warnings.\n\n"
    "## Variant D: Legal Documents & Contracts\n"
    "### 🌟 Document Purpose & Parties\n"
    "- Who the parties are and what agreement is being made.\n"
    "### ⚖️ Core Obligations & Rights\n"
    "- Key terms, duties, and permissions for each party.\n"
    "### 📅 Key Dates & Deadlines\n"
    "- Execution dates, renewal windows, or project milestones.\n"
    "### 🔒 Liabilities & Risks\n"
    "- Indemnifications, penalties, dispute resolution terms, or termination clauses.\n\n"
    "## Variant E: General / Creative / Literary / Articles\n"
    "### 🌟 Main Idea\n"
    "- High-level summary of the narrative, news item, or theme.\n"
    "### 🔑 Core Themes & Highlights\n"
    "- Key themes, character developments, or major arguments.\n"
    "### 💡 Key Takeaways\n"
    "- What the reader should remember or learn from this text.\n\n"
    "--- GENERAL GUIDELINES ---\n"
    "- Always start with a brief italicized header: *Type: [Detected Type] | Tone: [Detected Tone]*\n"
    "- If the text contains mathematical notation, always use correct LaTeX format (e.g. \\(x^2\\) or \\[E=mc^2\\]).\n"
    "- Be highly informative, precise, and objective. Avoid generic filler. Do not hallucinate.\n"
    "- Output ONLY the markdown formatted summary."
)

class AICascade:
    async def summarise(self, text: str, chat_id: Optional[str] = None, task: Optional[str] = None) -> Union[Dict[str, Any], str]:
        """
        Generate a summary and auto-tags for the given text content.
        Uses a cascading fallback structure (Modal -> Groq -> Gemini).
        If ENV is 'test' and no keys are present, returns mock values.
        """
        import sys
        if task == "label":
            if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
                return "Mock Theme"
            return await self._run_label_cascade(text)

        summary = ""
        tags = []

        # 1. Generate Summary
        import sys
        if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
            # Under test, return mock summary if not patched/intercepted
            summary = f"Mock summary for text: {text[:30]}..."
        else:
            # Real cascade implementation
            summary = await self._run_summary_cascade(text, chat_id)

        # Clean thinking blocks if present
        summary = self._strip_thinking(summary)

        # If summary failed or empty, set a fallback
        if not summary:
            summary = f"Summary snippet: {text[:100]}..."

        # 2. Generate Tags (after summary, using the summary/content as context)
        if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
            # Under test, return mock tags if not patched/intercepted
            tags = ["mock", "test", "tags"]
        else:
            try:
                tags = await self._generate_tags_llm(text, summary)
            except Exception as e:
                logger.error("Tag generation failed, saving with empty tags. Error: %s", e)
                tags = []

        # Normalize tags
        normalized_tags = self._normalize_tags(tags)

        return {
            "summary": summary,
            "tags": normalized_tags
        }

    async def _run_summary_cascade(self, text: str, chat_id: Optional[str]) -> str:
        # Determine providers order
        providers = ["modal", "groq", "gemini"]
        if settings.COMPUTE_PROVIDER:
            if settings.COMPUTE_PROVIDER in providers:
                providers.remove(settings.COMPUTE_PROVIDER)
            providers.insert(0, settings.COMPUTE_PROVIDER)

        for provider in providers:
            try:
                if provider == "modal" and settings.MODAL_API_TOKEN:
                    res = await self._call_modal_summary(text)
                    if res:
                        logger.info("Summary generated successfully via Modal")
                        return res
                elif provider == "groq" and settings.GROQ_API_KEY:
                    res = await self._call_groq_summary(text)
                    if res:
                        logger.info("Summary generated successfully via Groq")
                        return res
                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini_summary(text)
                    if res:
                        logger.info("Summary generated successfully via Gemini")
                        return res
            except Exception as e:
                logger.warning("Summary generation failed on provider %s: %s", provider, e)
                continue

        return ""

    async def _run_label_cascade(self, text: str) -> str:
        providers = ["groq", "gemini"]
        if settings.COMPUTE_PROVIDER:
            if settings.COMPUTE_PROVIDER in providers:
                providers.remove(settings.COMPUTE_PROVIDER)
            providers.insert(0, settings.COMPUTE_PROVIDER)

        for provider in providers:
            try:
                if provider == "groq" and settings.GROQ_API_KEY:
                    res = await self._call_groq_label(text)
                    if res:
                        res = self._strip_thinking(res).strip().strip('"\'')
                        logger.info("Label generated successfully via Groq")
                        return res
                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini_label(text)
                    if res:
                        res = self._strip_thinking(res).strip().strip('"\'')
                        logger.info("Label generated successfully via Gemini")
                        return res
            except Exception as e:
                logger.warning("Label generation failed on provider %s: %s", provider, e)
                continue

        return "Clustered Items"

    async def _call_groq_label(self, text: str) -> Optional[str]:
        messages = [
            {"role": "system", "content": "You are a precise classifier. What single theme connects these items? Answer in 4 words or less. Do not write anything else. Keep your answer brief and descriptive."},
            {"role": "user", "content": f"Summaries of items:\n\n{text}"}
        ]
        return await self._call_groq_llm(messages, temperature=0.2, timeout=10.0)

    async def _call_gemini_label(self, text: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "You are a precise classifier. What single theme connects these items? Answer in 4 words or less. Do not write anything else. Keep your answer brief and descriptive.\n\nSummaries of items:\n\n" + text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        return None

    async def _call_modal_summary(self, text: str) -> Optional[str]:
        url = "https://pri27--llama-summary.modal.run/summarize"
        headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"text": text}, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("summary")
        return None

    async def _call_groq_llm(self, messages: List[Dict[str, str]], temperature: float, timeout: float = 15.0) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        models = ["qwen/qwen3.6-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        
        for model in models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096
            }
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        logger.warning("Groq call failed for model %s with status %d: %s", model, resp.status_code, resp.text)
            except Exception as e:
                logger.warning("Groq call failed for model %s with exception: %s", model, e)
                continue
        return None

    async def _call_groq_summary(self, text: str) -> Optional[str]:
        max_groq_chars = 22000
        if len(text) > max_groq_chars:
            head_size = 14000
            tail_size = 8000
            truncated_text = f"{text[:head_size]}\n\n[... Text Truncated for Groq limits ...]\n\n{text[-tail_size:]}"
        else:
            truncated_text = text
            
        messages = [
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT + "\n- Keep your thinking process extremely brief and proceed to the summary content quickly."},
            {"role": "user", "content": f"Summarize the following text:\n\n{truncated_text}"}
        ]
        return await self._call_groq_llm(messages, temperature=0.3, timeout=15.0)

    async def _call_gemini_summary(self, text: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        # Truncate text to prevent long timeouts (~25,000 tokens)
        truncated_text = text[:100000]
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{SUMMARIZE_SYSTEM_PROMPT}\n\nSummarize the following text:\n\n{truncated_text}"}
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        return None

    async def _generate_tags_llm(self, content: str, summary: str) -> List[str]:
        # Determine provider to use for tag generation
        provider = settings.COMPUTE_PROVIDER or "groq"
        if provider == "modal" and not settings.MODAL_API_TOKEN:
            provider = "groq"
        if provider == "groq" and not settings.GROQ_API_KEY:
            provider = "gemini"
        if provider == "gemini" and not settings.GEMINI_API_KEY:
            if settings.MODAL_API_TOKEN:
                provider = "modal"
            elif settings.GROQ_API_KEY:
                provider = "groq"
            else:
                return []

        prompt = (
            "Generate 3-5 single-word or two-word tags for this content. "
            "Output ONLY a raw JSON array. Do NOT output any thinking/reasoning process (no <think> tags). "
            "Example: [\"machine learning\", \"python\", \"research\"]"
        )
        context = f"Content:\n{content[:1000]}\n\nSummary:\n{summary}"

        response_text = ""
        if provider == "modal" and settings.MODAL_API_TOKEN:
            url = "https://pri27--llama-summary.modal.run/generate-tags"
            headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json={"text": context, "prompt": prompt}, headers=headers)
                if resp.status_code == 200:
                    response_text = resp.json().get("tags_raw", "")
        elif provider == "groq" and settings.GROQ_API_KEY:
            messages = [
                {"role": "system", "content": "You are a precise tag generator. Output ONLY a valid JSON array of strings."},
                {"role": "user", "content": f"{prompt}\n\nContent context:\n{context}"}
            ]
            response_text = await self._call_groq_llm(messages, temperature=0.2, timeout=15.0)
        elif provider == "gemini" and settings.GEMINI_API_KEY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{prompt}\n\nContent context:\n{context}"}
                        ]
                    }
                ]
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    response_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        if not response_text:
            return []

        return self.parse_tags_response(response_text)

    def parse_tags_response(self, text: str) -> List[str]:
        """Parse JSON tags from response. On parse failure: return []"""
        cleaned = self._strip_thinking(text)
        # Clean markdown formatting if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [str(t) for t in data]
        except Exception as e:
            logger.warning("Failed to parse tags JSON: %s. Raw text: %s", e, text)
            
        return []

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize tags to lowercase, strip whitespace, keep first 5."""
        normalized = []
        for tag in tags:
            if isinstance(tag, str):
                t = tag.strip().lower()
                if t:
                    normalized.append(t)
        return normalized[:5]

    async def transcribe(
        self, 
        audio_bytes: bytes, 
        chat_id: Optional[str] = None, 
        file_extension: str = "ogg"
    ) -> Optional[str]:
        """
        Transcribe the given audio bytes into text.
        Follows the cascade fallback structure (Modal -> Groq -> Gemini).
        If ENV is 'test', returns a mock transcript.
        """
        import sys
        if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
            return f"Mock audio transcription content for voice note."

        # Real STT cascade
        providers = ["modal", "groq", "gemini"]
        if settings.COMPUTE_PROVIDER:
            if settings.COMPUTE_PROVIDER in providers:
                providers.remove(settings.COMPUTE_PROVIDER)
            providers.insert(0, settings.COMPUTE_PROVIDER)

        for provider in providers:
            try:
                if provider == "modal" and settings.MODAL_API_TOKEN:
                    res = await self._call_modal_transcribe(audio_bytes, file_extension)
                    if res:
                        logger.info("Transcription generated successfully via Modal")
                        return res
                elif provider == "groq" and settings.GROQ_API_KEY:
                    res = await self._call_groq_transcribe(audio_bytes, file_extension)
                    if res:
                        logger.info("Transcription generated successfully via Groq")
                        return res
                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini_transcribe(audio_bytes, file_extension)
                    if res:
                        logger.info("Transcription generated successfully via Gemini")
                        return res
            except Exception as e:
                logger.warning("Transcription failed on provider %s: %s", provider, e)
                continue

        return None

    def _get_audio_mime_type(self, extension: str) -> str:
        ext = extension.lower().strip()
        mapping = {
            "ogg": "audio/ogg",
            "opus": "audio/ogg",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
            "mp4": "audio/mp4",
            "wav": "audio/wav",
            "aac": "audio/aac",
            "flac": "audio/flac",
        }
        return mapping.get(ext, "audio/ogg")

    async def _call_modal_transcribe(self, audio_bytes: bytes, file_extension: str) -> Optional[str]:
        url = "https://pri27--modal-whisper-transcribe.modal.run/transcribe"
        headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, content=audio_bytes, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("transcript")
        return None

    async def _call_groq_transcribe(self, audio_bytes: bytes, file_extension: str) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        mime_type = self._get_audio_mime_type(file_extension)
        filename = f"audio.{file_extension}"
        files = {"file": (filename, audio_bytes, mime_type)}
        data = {"model": "whisper-large-v3-turbo"}
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(url, files=files, data=data, headers=headers)
                if resp.status_code == 200:
                    return resp.json().get("text")
            except Exception as e:
                logger.warning("Groq whisper-large-v3-turbo failed, falling back to whisper-large-v3: %s", e)
                
            # Fallback to whisper-large-v3 on Groq
            data["model"] = "whisper-large-v3"
            resp = await client.post(url, files=files, data=data, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("text")
        return None

    async def _call_gemini_transcribe(self, audio_bytes: bytes, file_extension: str) -> Optional[str]:
        import base64
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        mime_type = self._get_audio_mime_type(file_extension)
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_audio
                            }
                        },
                        {
                            "text": "Transcribe the following audio precisely. Output only the transcription."
                        }
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        return None

    async def caption_image(self, image_bytes: bytes) -> Optional[str]:
        """
        Generate a caption for the given image bytes using Gemini.
        If ENV is 'test', returns a mock caption.
        """
        import sys
        if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
            return "Mock image caption."

        if not settings.GEMINI_API_KEY:
            logger.warning("Gemini API key missing, cannot caption image.")
            return None

        # Detect correct mimeType from binary file signatures
        mime_type = "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            mime_type = "image/png"
        elif image_bytes.startswith(b"\xff\xd8"):
            mime_type = "image/jpeg"
        elif image_bytes.startswith(b"GIF8"):
            mime_type = "image/gif"
        elif image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
            mime_type = "image/webp"

        import base64
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_image
                            }
                        },
                        {
                            "text": "Provide a detailed caption or summary of this image."
                        }
                    ]
                }
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                else:
                    logger.error("Gemini image captioning failed with status %d: %s", resp.status_code, resp.text)
        except Exception as e:
            logger.error("Gemini image captioning failed: %s", e)
        return None

    async def answer_question(self, query: str, summaries: List[str]) -> Optional[str]:
        """
        Generate a synthesised answer using context from summaries.
        Uses Map-Reduce RAG flow with the same cascade tiers (Modal -> Groq -> Gemini).
        """
        # Ensure summaries are joined
        summaries_joined = "\n\n".join(f"- {s}" for s in summaries)
        
        # Format the prompt
        prompt = (
            f"Answer the user's question using ONLY the provided context. Question: {query}\n"
            f"Context: {summaries_joined}\n"
            f"Answer concisely in 2-3 sentences."
        )

        # Enforce prompt size limit of 3000 tokens (approx 12000 chars)
        # If total prompt length is too big, truncate context to fit
        max_prompt_chars = 12000
        if len(prompt) > max_prompt_chars:
            allowed_chars = max_prompt_chars - (len(prompt) - len(summaries_joined))
            if allowed_chars > 0:
                summaries_joined = summaries_joined[:allowed_chars]
                prompt = (
                    f"Answer the user's question using ONLY the provided context. Question: {query}\n"
                    f"Context: {summaries_joined}\n"
                    f"Answer concisely in 2-3 sentences."
                )
            else:
                return None

        # Call LLM using cascade tiers
        import sys
        if (settings.ENV == "test" or "pytest" in sys.modules) and not getattr(self, "_force_production_llm", False):
            # Under test, return mock answer
            return f"Mock synthesised answer for query: {query}"
        
        # Real cascade execution
        providers = ["modal", "groq", "gemini"]
        if settings.COMPUTE_PROVIDER:
            if settings.COMPUTE_PROVIDER in providers:
                providers.remove(settings.COMPUTE_PROVIDER)
            providers.insert(0, settings.COMPUTE_PROVIDER)

        for provider in providers:
            try:
                res = None
                if provider == "modal" and settings.MODAL_API_TOKEN:
                    res = await self._call_modal_rag(prompt)
                elif provider == "groq" and settings.GROQ_API_KEY:
                    res = await self._call_groq_rag(prompt)
                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini_rag(prompt)
                if res:
                    return self._strip_thinking(res)
            except Exception as e:
                logger.warning("RAG answer generation failed on provider %s: %s", provider, e)
                continue

        return None

    async def _call_modal_rag(self, prompt: str) -> Optional[str]:
        url = "https://pri27--llama-summary.modal.run/rag"
        headers = {"Authorization": f"Bearer {settings.MODAL_API_TOKEN}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json={"prompt": prompt}, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("answer")
        return None

    async def _call_groq_rag(self, prompt: str) -> Optional[str]:
        messages = [
            {"role": "system", "content": "You are a factual assistant that answers questions using only provided context. Do not hallucinate or use external knowledge."},
            {"role": "user", "content": prompt}
        ]
        return await self._call_groq_llm(messages, temperature=0.0, timeout=15.0)

    async def _call_gemini_rag(self, prompt: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0
            }
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        return None

    def _strip_thinking(self, text: str) -> str:
        if not text:
            return ""
        # Remove closed think blocks
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Remove any unclosed think block (if <think> is still in text)
        cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
        # Clean up any stray closing tags
        cleaned = cleaned.replace("</think>", "")
        return cleaned.strip()
