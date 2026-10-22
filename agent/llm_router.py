"""
Optimus AI — Zero-Cost Multi-Provider LLM Rotator with Auto-Fallback
====================================================================
A production-grade, resilient LLM client engineered to guarantee 100% uptime
and eliminate rate-limit halts through automated key rotation, exponential backoff,
and a multi-provider fallback hierarchy:

Priority Queue:
  1. Google Gemini API (gemini-2.5-flash with multi-key rotation)
  2. Groq API (llama-3.3-70b-versatile with multi-key rotation)
  3. OpenRouter Free Router (openrouter/free or meta-llama/llama-3.3-70b-instruct:free)
  4. Local Ollama Fallback (http://localhost:11434)
  5. Built-in Deterministic Heuristic Extractor (for dry-run & offline mode)

Every response is strictly validated against the Optimus AI Tool Schema using Pydantic.
"""

import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import requests
from pydantic import BaseModel, Field, ValidationError

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [LLMRouter] %(message)s")
logger = logging.getLogger("LLMRouter")


# ============================================================================
# PYDANTIC STRICT SCHEMAS
# ============================================================================

class ToolSchema(BaseModel):
    id: str = Field(..., description="Unique slugified identifier, e.g., 'google-antigravity'")
    name: str = Field(..., description="Full official product/tool name")
    parent_org: str = Field(..., description="Parent company or organization name")
    category: str = Field(..., description="AI category, e.g., 'Autonomous Agents & Coding'")
    release_date: str = Field(..., description="Release date in YYYY-MM-DD or YYYY-MM format")
    status: str = Field("Active", description="Lifecycle status: Active, Beta, Deprecated, or Experimental")
    pricing: str = Field("Free", description="Pricing model: Free, Freemium, Paid, or Open Source")
    official_url: str = Field(..., description="Official website or repository URL")
    short_description: str = Field(..., description="Concise 1-2 sentence high-impact summary")
    key_features: List[str] = Field(default_factory=list, description="List of 3-5 core capabilities")
    tags: List[str] = Field(default_factory=list, description="Keywords and tags")
    last_verified: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def normalize(self) -> "ToolSchema":
        """Clean and normalize fields."""
        norm_id = re.sub(r"[^a-z0-9\-]", "-", self.id.lower().strip())
        norm_id = re.sub(r"-+", "-", norm_id).strip("-")
        if not norm_id:
            norm_id = re.sub(r"[^a-z0-9\-]", "-", f"{self.parent_org}-{self.name}".lower().strip())
            norm_id = re.sub(r"-+", "-", norm_id).strip("-")
        
        valid_pricing = ["Free", "Freemium", "Paid", "Open Source"]
        p_match = next((p for p in valid_pricing if p.lower() == self.pricing.lower()), self.pricing)

        valid_status = ["Active", "Beta", "Deprecated", "Experimental"]
        s_match = next((s for s in valid_status if s.lower() == self.status.lower()), self.status)

        # Normalize date
        rel_date = self.release_date.strip()
        if not re.match(r"^\d{4}(-\d{2})?(-\d{2})?$", rel_date):
            rel_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return ToolSchema(
            id=norm_id,
            name=self.name.strip(),
            parent_org=self.parent_org.strip(),
            category=self.category.strip() or "General AI",
            release_date=rel_date,
            status=s_match,
            pricing=p_match,
            official_url=self.official_url.strip(),
            short_description=self.short_description.strip(),
            key_features=[f.strip() for f in self.key_features if f.strip()][:6],
            tags=[t.lower().strip().replace(" ", "-") for t in self.tags if t.strip()][:8],
            last_verified=self.last_verified or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )


class ExtractionPayload(BaseModel):
    tools: List[ToolSchema]
    organization_summary: Optional[str] = None
    organization_website: Optional[str] = None


# ============================================================================
# PROMPT DEFINITIONS
# ============================================================================

SYSTEM_PROMPT = """You are Optimus AI's Chief Autonomous Knowledge Architect.
Your task is to analyze raw content (news, announcement, GitHub repo, product page, or feed) and extract structured AI tool profiles.

You MUST respond strictly with a valid JSON object matching this schema:
{
  "tools": [
    {
      "id": "kebab-case-parent-and-tool-slug",
      "name": "Exact Tool Name",
      "parent_org": "Official Company or Creator Name",
      "category": "One of: Autonomous Agents & Coding, LLMs & Frontier Models, Reasoning & Math, Video & Animation, Voice & Audio, Image Generation, Computer Vision, Search & Research, Developer Platforms & APIs, Productivity & Office, Design & UI Generation",
      "release_date": "YYYY-MM-DD or YYYY-MM",
      "status": "Active or Beta or Deprecated",
      "pricing": "Free or Freemium or Paid or Open Source",
      "official_url": "https://valid.official.link",
      "short_description": "1-2 sentence compelling summary of what it does and why it matters.",
      "key_features": ["Feature 1", "Feature 2", "Feature 3", "Feature 4"],
      "tags": ["tag1", "tag2", "tag3", "tag4"],
      "last_verified": "YYYY-MM-DD"
    }
  ],
  "organization_summary": "Brief 1-sentence bio of the parent company if mentioned",
  "organization_website": "https://company.com if mentioned"
}

RULES:
1. Output ONLY the JSON block. Do not include markdown preamble, commentary, or conversational remarks.
2. If multiple distinct AI tools are announced in the text, extract each one as a separate object in the 'tools' array.
3. Every tool must have an accurate, functioning URL (or GitHub repo link if open source).
4. Categorize precisely using one of the recognized categories.
5. Pricing must be exactly one of: Free, Freemium, Paid, Open Source.
"""


# ============================================================================
# KEY ROTATOR HELPER
# ============================================================================

class KeyRotator:
    """Manages comma-separated API keys with rotational state and cooldowns."""

    def __init__(self, env_var_name: str):
        self.env_var_name = env_var_name
        raw = os.getenv(env_var_name, "").strip()
        if raw:
            # Split on commas or whitespace
            self.keys = [k.strip() for k in re.split(r"[,;\s]+", raw) if k.strip()]
        else:
            self.keys = []
        self.current_idx = 0
        self.exhausted_keys: Dict[str, float] = {}

    def has_keys(self) -> bool:
        return len(self.keys) > 0

    def get_key(self) -> Optional[str]:
        if not self.keys:
            return None
        now = time.time()
        # Clean cooldowns older than 60 seconds
        self.exhausted_keys = {k: ts for k, ts in self.exhausted_keys.items() if now - ts < 60}
        
        # Find next available key
        for _ in range(len(self.keys)):
            k = self.keys[self.current_idx]
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            if k not in self.exhausted_keys:
                return k
        
        # If all temporarily cooled down, return least recently used
        return self.keys[self.current_idx]

    def mark_rate_limited(self, key: str):
        logger.warning(f"Key for {self.env_var_name} ({key[:6]}...{key[-4:] if len(key)>10 else ''}) hit rate limit (429). Rotating...")
        self.exhausted_keys[key] = time.time()


# ============================================================================
# MULTI-PROVIDER LLM ROUTER
# ============================================================================

class LLMRouter:
    """Resilient multi-provider LLM coordinator with automated fallback."""

    def __init__(self):
        self.gemini_rotator = KeyRotator("GEMINI_API_KEY")
        self.groq_rotator = KeyRotator("GROQ_API_KEY")
        self.openrouter_rotator = KeyRotator("OPENROUTER_API_KEY")
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")

    def extract_ai_tools(self, content: str, source_hint: str = "", force_dry_run: bool = False) -> ExtractionPayload:
        """
        Extracts structured AI tools from raw content by trying providers in order:
        1. Google Gemini
        2. Groq
        3. OpenRouter
        4. Ollama
        5. Heuristic fallback (dry-run or offline)
        """
        if force_dry_run:
            logger.info("Executing under force_dry_run mode. Using heuristic extractor.")
            return self._heuristic_fallback(content, source_hint)

        # 1. Google Gemini
        if self.gemini_rotator.has_keys():
            result = self._try_gemini(content, source_hint)
            if result:
                return result

        # 2. Groq API
        if self.groq_rotator.has_keys():
            result = self._try_groq(content, source_hint)
            if result:
                return result

        # 3. OpenRouter Free Router
        if self.openrouter_rotator.has_keys():
            result = self._try_openrouter(content, source_hint)
            if result:
                return result

        # 4. Local Ollama Fallback
        result = self._try_ollama(content, source_hint)
        if result:
            return result

        # 5. Deterministic Offline Heuristic Extractor
        logger.info("No external LLM provider available or reachable. Falling back to deterministic heuristic extractor.")
        return self._heuristic_fallback(content, source_hint)

    # ------------------------------------------------------------------------
    # PROVIDER: GOOGLE GEMINI (gemini-2.5-flash)
    # ------------------------------------------------------------------------
    def _try_gemini(self, content: str, source_hint: str) -> Optional[ExtractionPayload]:
        url_template = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
        user_message = f"SOURCE METADATA: {source_hint}\n\nRAW CONTENT TO ANALYZE:\n{content[:25000]}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_message}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        # Attempt with available keys
        for attempt in range(len(self.gemini_rotator.keys)):
            key = self.gemini_rotator.get_key()
            if not key:
                break
            try:
                logger.info(f"Invoking Google Gemini 2.5 Flash (Key {key[:6]}...)")
                resp = requests.post(
                    url_template.format(key=key),
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=45
                )

                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = self._clean_and_parse_json(raw_text)
                    if parsed:
                        logger.info(f"Gemini successfully extracted {len(parsed.tools)} tools.")
                        return parsed
                elif resp.status_code in (429, 403):
                    self.gemini_rotator.mark_rate_limited(key)
                    time.sleep(1)
                    continue
                else:
                    logger.warning(f"Gemini returned status {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Gemini request exception with key {key[:6]}...: {e}")
                time.sleep(1)

        return None

    # ------------------------------------------------------------------------
    # PROVIDER: GROQ (llama-3.3-70b-versatile)
    # ------------------------------------------------------------------------
    def _try_groq(self, content: str, source_hint: str) -> Optional[ExtractionPayload]:
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        user_message = f"SOURCE METADATA: {source_hint}\n\nRAW CONTENT TO ANALYZE:\n{content[:20000]}"

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        for attempt in range(len(self.groq_rotator.keys)):
            key = self.groq_rotator.get_key()
            if not key:
                break
            try:
                logger.info(f"Invoking Groq API (llama-3.3-70b-versatile, Key {key[:6]}...)")
                resp = requests.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json=body,
                    timeout=40
                )

                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data["choices"][0]["message"]["content"]
                    parsed = self._clean_and_parse_json(raw_text)
                    if parsed:
                        logger.info(f"Groq successfully extracted {len(parsed.tools)} tools.")
                        return parsed
                elif resp.status_code in (429, 403):
                    self.groq_rotator.mark_rate_limited(key)
                    time.sleep(1)
                    continue
                else:
                    logger.warning(f"Groq status {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Groq request exception: {e}")
                time.sleep(1)

        return None

    # ------------------------------------------------------------------------
    # PROVIDER: OPENROUTER (openrouter/free)
    # ------------------------------------------------------------------------
    def _try_openrouter(self, content: str, source_hint: str) -> Optional[ExtractionPayload]:
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        user_message = f"SOURCE METADATA: {source_hint}\n\nRAW CONTENT TO ANALYZE:\n{content[:18000]}"

        # Models in free tier
        models = ["meta-llama/llama-3.3-70b-instruct:free", "openrouter/free", "mistralai/mistral-7b-instruct:free"]

        for attempt in range(len(self.openrouter_rotator.keys)):
            key = self.openrouter_rotator.get_key()
            if not key:
                break
            for model_name in models:
                try:
                    logger.info(f"Invoking OpenRouter ({model_name})")
                    resp = requests.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "HTTP-Referer": "https://github.com/optimus-ai/optimus-spark",
                            "X-Title": "Optimus AI Directory",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_message}
                            ],
                            "temperature": 0.1
                        },
                        timeout=40
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["choices"][0]["message"]["content"]
                        parsed = self._clean_and_parse_json(raw_text)
                        if parsed:
                            logger.info(f"OpenRouter successfully extracted {len(parsed.tools)} tools.")
                            return parsed
                    elif resp.status_code == 429:
                        self.openrouter_rotator.mark_rate_limited(key)
                        break
                except Exception as e:
                    logger.warning(f"OpenRouter exception on {model_name}: {e}")

        return None

    # ------------------------------------------------------------------------
    # PROVIDER: LOCAL OLLAMA FALLBACK
    # ------------------------------------------------------------------------
    def _try_ollama(self, content: str, source_hint: str) -> Optional[ExtractionPayload]:
        endpoint = f"{self.ollama_host}/api/chat"
        user_message = f"SOURCE METADATA: {source_hint}\n\nRAW CONTENT TO ANALYZE:\n{content[:10000]}"

        try:
            logger.info(f"Attempting local Ollama fallback at {self.ollama_host} (model: {self.ollama_model})...")
            resp = requests.post(
                endpoint,
                json={
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    "format": "json",
                    "stream": False
                },
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["message"]["content"]
                parsed = self._clean_and_parse_json(raw_text)
                if parsed:
                    logger.info("Ollama successfully extracted tools locally.")
                    return parsed
        except requests.exceptions.ConnectionError:
            logger.info("Local Ollama daemon is not running on localhost:11434 (Skipping).")
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")

        return None

    # ------------------------------------------------------------------------
    # DETERMINISTIC HEURISTIC FALLBACK (Offline / Dry-Run Guarantee)
    # ------------------------------------------------------------------------
    def _heuristic_fallback(self, content: str, source_hint: str) -> ExtractionPayload:
        """
        Rule-based parser that guarantees valid ToolSchema output even with no internet
        or when running in dry-run mode. Extracts title, url, domain, and bullet points.
        """
        logger.info("Running deterministic heuristic parser on content...")

        # Extract URLs
        url_match = re.search(r"https?://[^\s\"'\<\>]+", content)
        official_url = url_match.group(0).rstrip(".,)") if url_match else "https://ai.example.com"
        
        domain = ""
        try:
            parsed_u = urlparse(official_url)
            domain = parsed_u.netloc.replace("www.", "")
        except Exception:
            domain = "unknown"

        # Extract name from source_hint or first markdown title or text line
        tool_name = ""
        parent_org = "Independent"

        if source_hint:
            source_m = re.search(r"(?:Title|Source):\s*([^\|\n]+)", source_hint, flags=re.IGNORECASE)
            if source_m:
                tool_name = source_m.group(1).strip()
            elif ":" in source_hint and not source_hint.startswith("http"):
                parts = [p.strip() for p in source_hint.split(":") if len(p.strip()) > 3 and not p.strip().startswith("//")]
                if parts:
                    tool_name = parts[-1]

        if not tool_name:
            title_match = re.search(r"^(?:#+\s*|Title:\s*)([^\n]+)", content, re.MULTILINE)
            if title_match:
                tool_name = title_match.group(1).strip()
            else:
                first_line = content.strip().split("\n")[0]
                tool_name = re.sub(r"[^\w\s\-\.]", "", first_line)[:40].strip()

        # Clean common prefixes from title
        tool_name = re.sub(r"^(?:Show|Launch)\s+HN:\s*", "", tool_name, flags=re.IGNORECASE).strip()
        # If tool_name is still a URL, starts with slashes, or is generic
        if tool_name.startswith("//") or tool_name.startswith("http") or not tool_name or tool_name.lower() in ("backfill query", "source", "link", "independent"):
            if "github.com" in domain and "/" in official_url:
                tool_name = official_url.rstrip("/").split("/")[-1].replace("-", " ").title()
            else:
                tool_name = domain.split(".")[0].capitalize()

        # Deduce parent org
        name_lower = tool_name.lower()
        content_lower = content.lower()
        if "google" in name_lower or "google" in domain:
            parent_org = "Google"
        elif "openai" in name_lower or "openai" in domain:
            parent_org = "OpenAI"
        elif "anthropic" in name_lower or "claude" in name_lower:
            parent_org = "Anthropic"
        elif "meta" in name_lower or "meta" in domain:
            parent_org = "Meta"
        elif "microsoft" in name_lower or "azure" in name_lower:
            parent_org = "Microsoft"
        elif "mistral" in name_lower:
            parent_org = "Mistral AI"
        elif "deepseek" in name_lower:
            parent_org = "DeepSeek"
        elif "hugging face" in content_lower or "huggingface.co" in domain:
            parent_org = "Hugging Face"
        elif "github.com" in domain:
            # Extract owner from github url
            parts = official_url.split("github.com/")
            if len(parts) > 1:
                repo_parts = parts[1].strip("/").split("/")
                if len(repo_parts) >= 1:
                    parent_org = repo_parts[0].capitalize()

        # Category deduction
        category = "Autonomous Agents & Coding"
        if any(w in content_lower for w in ["video", "sora", "veo", "cinematic", "animation"]):
            category = "Video & Animation"
        elif any(w in content_lower for w in ["voice", "speech", "audio", "tts", "music", "whisper"]):
            category = "Voice & Audio"
        elif any(w in content_lower for w in ["vision", "image", "diffusion", "segmentation", "midjourney"]):
            category = "Image Generation"
        elif any(w in content_lower for w in ["search", "citations", "research", "browse", "paper"]):
            category = "Search & Research"
        elif any(w in content_lower for w in ["foundation model", "llm", "weights", "70b", "reasoning"]):
            category = "LLMs & Frontier Models"

        # Pricing deduction
        pricing = "Free"
        if any(w in content_lower for w in ["apache-2.0", "mit license", "open source", "open weights", "github.com"]):
            pricing = "Open Source"
        elif any(w in content_lower for w in ["subscription", "$", "credit card", "pricing plan"]):
            pricing = "Paid"
        elif any(w in content_lower for w in ["free tier", "freemium", "credits"]):
            pricing = "Freemium"

        # Features extraction from bullet points
        bullets = re.findall(r"(?:^|\n)\s*[\-\*•]\s+([^\n]+)", content)
        features = [b.strip() for b in bullets if len(b.strip()) > 10][:4]
        if not features:
            features = [
                f"Automated AI capabilities powered by {parent_org}",
                "Streamlined developer workflow and production integration",
                "High performance architecture and domain-specific modeling"
            ]

        # Short description
        sentences = [s.strip() for s in re.split(r"[.\n]", content) if len(s.strip()) > 25]
        desc = sentences[0] if sentences else f"Autonomous AI tool created by {parent_org}."
        if len(desc) > 220:
            desc = desc[:217] + "..."

        tool_id = re.sub(r"[^a-z0-9]+", "-", f"{parent_org}-{tool_name}".lower()).strip("-")

        tool = ToolSchema(
            id=tool_id,
            name=tool_name or f"AI Tool by {parent_org}",
            parent_org=parent_org,
            category=category,
            release_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            status="Active",
            pricing=pricing,
            official_url=official_url,
            short_description=desc,
            key_features=features,
            tags=[re.sub(r"[^a-z0-9]", "", w.lower()) for w in (tool_name.split() + [parent_org, category.split()[0]]) if len(w) > 2][:6],
            last_verified=datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ).normalize()

        return ExtractionPayload(
            tools=[tool],
            organization_summary=f"{parent_org} AI research and product ecosystem.",
            organization_website=official_url
        )

    # ------------------------------------------------------------------------
    # JSON SANITIZATION & STRICT VALIDATION
    # ------------------------------------------------------------------------
    def _clean_and_parse_json(self, raw: str) -> Optional[ExtractionPayload]:
        """Cleans markdown fences, trailing commas, and parses via Pydantic."""
        if not raw:
            return None
        text = raw.strip()

        # Remove markdown code blocks if wrapped
        if "```" in text:
            matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if matches:
                text = matches[0].strip()

        # Find first '{' and last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]

        # Fix common JSON formatting issues (trailing commas before closing brackets)
        text = re.sub(r",\s*([\]}])", r"\1", text)

        try:
            data = json.loads(text)
            
            # If model returned a single tool object or array directly
            if isinstance(data, list):
                tools_list = [ToolSchema(**item).normalize() for item in data]
                return ExtractionPayload(tools=tools_list)
            elif isinstance(data, dict):
                if "tools" in data and isinstance(data["tools"], list):
                    normalized_tools = []
                    for t in data["tools"]:
                        try:
                            normalized_tools.append(ToolSchema(**t).normalize())
                        except ValidationError as ve:
                            logger.warning(f"Skipping malformed tool entry: {ve}")
                    return ExtractionPayload(
                        tools=normalized_tools,
                        organization_summary=data.get("organization_summary"),
                        organization_website=data.get("organization_website")
                    )
                # Single tool dict returned
                elif "name" in data and "parent_org" in data:
                    t = ToolSchema(**data).normalize()
                    return ExtractionPayload(tools=[t])

        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Failed to parse LLM JSON output: {e}\nRaw output was: {raw[:300]}...")
            return None

        return None
