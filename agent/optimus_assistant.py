"""
Optimus AI — The Autonomous Manager & CLI Assistant (Optimus Spark Agent)
=========================================================================
Autonomous 24/7 intelligence director for the global AI ecosystem.

Execution Modes:
  1. Autonomous Daemon / Cron:
     python agent/optimus_assistant.py --cron
     python agent/optimus_assistant.py --daemon --interval 3600

  2. Deep Historical Backfill:
     python agent/optimus_assistant.py --backfill "Google"
     python agent/optimus_assistant.py --backfill "Autonomous Coding Agents"

  3. Interactive Assistant CLI:
     python agent/optimus_assistant.py --interactive

  4. Safe Dry-Run (Verification without API consumption):
     python agent/optimus_assistant.py --cron --dry-run
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

# Ensure local imports work regardless of CWD
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load .env if present
try:
    from dotenv import load_dotenv
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass

from agent.llm_router import LLMRouter, ToolSchema, ExtractionPayload
from agent.web_researcher import WebResearcher, DiscoveryItem

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [OptimusSpark] %(message)s"
)
logger = logging.getLogger("OptimusSpark")


class OptimusAssistant:
    """Core manager handling directory state, deduplication, backfills, and CLI."""

    def __init__(self, db_path: Optional[Path] = None, changelog_path: Optional[Path] = None):
        self.db_path = db_path or (BASE_DIR / "data" / "ai_directory.json")
        self.changelog_path = changelog_path or (BASE_DIR / "data" / "changelog.md")
        self.llm_router = LLMRouter()
        self.researcher = WebResearcher()
        self.directory_data = self._load_directory()

    # ========================================================================
    # DIRECTORY PERSISTENCE & SCHEMAS
    # ========================================================================
    def _load_directory(self) -> Dict[str, Any]:
        """Loads and validates existing data/ai_directory.json."""
        if not self.db_path.exists():
            logger.warning(f"Database file not found at {self.db_path}. Initializing empty template.")
            return {
                "version": "1.0.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_organizations": 0,
                "total_tools": 0,
                "organizations": []
            }
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"Failed to read {self.db_path}: {e}")
            raise

    def save_directory(self) -> None:
        """Saves current state to ai_directory.json with formatted indentation."""
        # Recount totals
        total_orgs = len(self.directory_data.get("organizations", []))
        total_tools = sum(len(org.get("tools", [])) for org in self.directory_data.get("organizations", []))
        self.directory_data["total_organizations"] = total_orgs
        self.directory_data["total_tools"] = total_tools
        self.directory_data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.directory_data, f, indent=2, ensure_ascii=False)

        # Mirror to web/data/ai_directory.json for static server compatibility
        web_db = BASE_DIR / "web" / "data" / "ai_directory.json"
        try:
            web_db.parent.mkdir(parents=True, exist_ok=True)
            with open(web_db, "w", encoding="utf-8") as f:
                json.dump(self.directory_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        logger.info(f"Directory saved: {total_tools} tools across {total_orgs} organizations.")

    # ========================================================================
    # DEDUPLICATION & MERGE ENGINE
    # ========================================================================
    def merge_tool(self, tool: ToolSchema, org_summary: Optional[str] = None, org_website: Optional[str] = None) -> Tuple[bool, str]:
        """
        Merges a tool into the directory database.
        Returns: (is_new, status_message)
        """
        tool = tool.normalize()
        norm_url = self._normalize_url(tool.official_url)
        tool_dict = tool.model_dump()

        # Check for existing tool by ID or normalized URL
        for org in self.directory_data.get("organizations", []):
            for existing_idx, existing in enumerate(org.get("tools", [])):
                existing_url = self._normalize_url(existing.get("official_url", ""))
                if (existing.get("id") == tool.id) or (norm_url and norm_url == existing_url):
                    # Tool exists: update mutable fields
                    org["tools"][existing_idx]["short_description"] = tool.short_description or existing.get("short_description")
                    org["tools"][existing_idx]["last_verified"] = tool.last_verified
                    org["tools"][existing_idx]["pricing"] = tool.pricing or existing.get("pricing")
                    org["tools"][existing_idx]["status"] = tool.status or existing.get("status")
                    
                    # Merge features and tags
                    current_feats = set(existing.get("key_features", []))
                    for f in tool.key_features:
                        current_feats.add(f)
                    org["tools"][existing_idx]["key_features"] = list(current_feats)[:6]

                    current_tags = set(existing.get("tags", []))
                    for t in tool.tags:
                        current_tags.add(t)
                    org["tools"][existing_idx]["tags"] = list(current_tags)[:8]

                    return False, f"Updated existing tool '{tool.name}' under '{org['name']}'"

        # If not found, add as new tool under correct organization
        target_org_name = tool.parent_org.strip() or "Independent"
        matched_org = None
        for org in self.directory_data.get("organizations", []):
            if (org.get("name", "").lower() == target_org_name.lower() or 
                org.get("id", "").lower() == self._slugify(target_org_name)):
                matched_org = org
                break

        if not matched_org:
            # Create new parent organization
            org_id = self._slugify(target_org_name)
            matched_org = {
                "id": org_id,
                "name": target_org_name,
                "website": org_website or tool.official_url,
                "description": org_summary or f"{target_org_name} AI research, products, and applications ecosystem.",
                "logo_symbol": org_id,
                "tags": [t for t in ["AI", "Innovation", tool.category.split()[0]] if t],
                "tools": []
            }
            self.directory_data["organizations"].append(matched_org)
            logger.info(f"Created new parent organization: {target_org_name} (ID: {org_id})")

        matched_org["tools"].append(tool_dict)
        return True, f"Added brand new tool '{tool.name}' to '{target_org_name}'"

    def record_changelog(self, added_tools: List[ToolSchema], updated_tools: List[ToolSchema], context: str) -> None:
        """Appends structured audit log to data/changelog.md."""
        if not added_tools and not updated_tools:
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"\n### [{now_str}] Autonomous Discovery Sync ({context})",
            f"- **New Tools Added:** {len(added_tools)}",
            f"- **Existing Tools Refreshed:** {len(updated_tools)}"
        ]

        if added_tools:
            lines.append("  - **Added:**")
            for t in added_tools:
                lines.append(f"    - **[{t.name}]({t.official_url})** ({t.parent_org}) — *{t.category}* ({t.pricing}): {t.short_description}")

        if updated_tools:
            lines.append("  - **Refreshed:**")
            for t in updated_tools:
                lines.append(f"    - **{t.name}** ({t.parent_org}) verified on {t.last_verified}")

        self.changelog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.changelog_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        logger.info(f"Recorded changelog update for {len(added_tools)} additions and {len(updated_tools)} updates.")

    # ========================================================================
    # MODE A: 24/7 AUTONOMOUS DISCOVERY (CRON / DAEMON)
    # ========================================================================
    def run_autonomous_sync(self, max_items: int = 10, dry_run: bool = False) -> Dict[str, Any]:
        """
        Pulls latest RSS/Atom feeds, filters for AI tools, analyzes through LLM Router,
        and merges new entries into directory.
        """
        logger.info("Starting Autonomous 24/7 Discovery Run...")
        feed_items = self.researcher.fetch_latest_feed_items(max_items_per_feed=4)
        
        # Deduplicate candidates against current database before expensive scraping/LLM
        candidates: List[DiscoveryItem] = []
        for item in feed_items:
            norm_link = self._normalize_url(item.link)
            if not self._url_exists_in_db(norm_link):
                candidates.append(item)
            if len(candidates) >= max_items:
                break

        logger.info(f"Identified {len(candidates)} new candidates to analyze out of {len(feed_items)} feed items.")

        added_list: List[ToolSchema] = []
        updated_list: List[ToolSchema] = []

        for idx, candidate in enumerate(candidates, 1):
            logger.info(f"[{idx}/{len(candidates)}] Processing: {candidate.title} ({candidate.link})")
            
            # Fetch clean markdown/text content
            raw_content = self.researcher.fetch_clean_page_content(candidate.link)
            if len(raw_content) < 50:
                raw_content = f"Title: {candidate.title}\nURL: {candidate.link}\nSummary: {candidate.summary}"

            # LLM Extraction
            hint = f"Title: {candidate.title} | Link: {candidate.link}"
            extraction = self.llm_router.extract_ai_tools(raw_content, source_hint=hint, force_dry_run=dry_run)

            if extraction and extraction.tools:
                for tool in extraction.tools:
                    # Guarantee valid URL
                    if not tool.official_url or "example.com" in tool.official_url:
                        tool.official_url = candidate.link

                    is_new, msg = self.merge_tool(
                        tool,
                        org_summary=extraction.organization_summary,
                        org_website=extraction.organization_website
                    )
                    logger.info(f" -> {msg}")
                    if is_new:
                        added_list.append(tool)
                    else:
                        updated_list.append(tool)

        # Save and log if modifications occurred
        if added_list or updated_list:
            self.save_directory()
            self.record_changelog(added_list, updated_list, context="24/7 Autonomous Feed Monitor")

        return {
            "scanned_candidates": len(candidates),
            "added_count": len(added_list),
            "updated_count": len(updated_list),
            "added_tools": [t.name for t in added_list]
        }

    # ========================================================================
    # MODE B: DEEP HISTORICAL BACKFILL
    # ========================================================================
    def run_backfill(self, query: str, max_results: int = 8, dry_run: bool = False) -> Dict[str, Any]:
        """
        Deep historical discovery mode for a company or category (e.g. "Google", "DeepSeek", "Autonomous Agents").
        """
        logger.info(f"Initiating Deep Historical Backfill for: '{query}'...")
        search_queries = [
            f"{query} AI",
            query,
            f"{query} foundation model"
        ]

        all_search_items: List[DiscoveryItem] = []
        for sq in search_queries[:2]:
            items = self.researcher.search_web_free(sq, max_results=max_results)
            all_search_items.extend(items)

        # Deduplicate search items by URL
        seen_urls = set()
        unique_items = []
        for it in all_search_items:
            norm = self._normalize_url(it.link)
            if norm and norm not in seen_urls:
                seen_urls.add(norm)
                unique_items.append(it)

        logger.info(f"Discovered {len(unique_items)} unique reference sources for '{query}'.")

        added_list: List[ToolSchema] = []
        updated_list: List[ToolSchema] = []

        for idx, item in enumerate(unique_items[:max_results], 1):
            logger.info(f"[{idx}/{min(len(unique_items), max_results)}] Backfill analyzing: {item.title} ({item.link})")
            page_content = self.researcher.fetch_clean_page_content(item.link)
            hint = f"Backfill Query: {query} | Source: {item.title} | Link: {item.link}"
            
            extraction = self.llm_router.extract_ai_tools(page_content, source_hint=hint, force_dry_run=dry_run)

            if extraction and extraction.tools:
                for tool in extraction.tools:
                    # If backfilling a specific company, override generic parent org
                    if not tool.parent_org or tool.parent_org.lower() == "independent":
                        tool.parent_org = query.title()

                    is_new, msg = self.merge_tool(
                        tool,
                        org_summary=extraction.organization_summary,
                        org_website=extraction.organization_website
                    )
                    logger.info(f" -> {msg}")
                    if is_new:
                        added_list.append(tool)
                    else:
                        updated_list.append(tool)

        if added_list or updated_list:
            self.save_directory()
            self.record_changelog(added_list, updated_list, context=f"Deep Backfill: {query}")

        return {
            "query": query,
            "sources_analyzed": min(len(unique_items), max_results),
            "added_count": len(added_list),
            "updated_count": len(updated_list),
            "added_tools": [t.name for t in added_list]
        }

    # ========================================================================
    # MODE C: INTERACTIVE CLI ASSISTANT
    # ========================================================================
    def run_interactive(self) -> None:
        """Launches interactive terminal prompt for on-demand analysis and testing."""
        print("\n" + "=" * 70)
        print("⚡ OPTIMUS SPARK ASSISTANT — INTERACTIVE TERMINAL STUDIO ⚡")
        print("======================================================================")
        print("Commands:")
        print("  - Type any URL (e.g., https://github.com/org/tool) to analyze & add")
        print("  - Type any tool or company name (e.g., 'Google Stitch') to research")
        print("  - Type 'scan' to run 24/7 discovery on latest feeds")
        print("  - Type 'backfill <Company>' to run deep ecosystem discovery")
        print("  - Type 'stats' to view current directory metrics")
        print("  - Type 'exit' or 'quit' to close")
        print("=" * 70 + "\n")

        while True:
            try:
                user_input = input("\n[Optimus] > ").strip()
                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    print("Exiting Optimus Assistant Studio. Have a great day!")
                    break

                elif user_input.lower() == "stats":
                    total_orgs = len(self.directory_data.get("organizations", []))
                    total_tools = sum(len(o.get("tools", [])) for o in self.directory_data.get("organizations", []))
                    print(f"📊 Current Directory Status:")
                    print(f"   - Total Organizations: {total_orgs}")
                    print(f"   - Total AI Tools:      {total_tools}")
                    print(f"   - Last Synchronized:   {self.directory_data.get('last_updated')}")

                elif user_input.lower() == "scan":
                    print("🚀 Running autonomous feed discovery scan...")
                    res = self.run_autonomous_sync(max_items=5)
                    print(f"✅ Scan Complete! Added: {res['added_count']} | Updated: {res['updated_count']}")

                elif user_input.lower().startswith("backfill "):
                    target = user_input[9:].strip()
                    print(f"🔍 Launching deep backfill for '{target}'...")
                    res = self.run_backfill(target, max_results=5)
                    print(f"✅ Backfill Complete! Added: {res['added_count']} | Updated: {res['updated_count']}")

                elif user_input.startswith("http://") or user_input.startswith("https://"):
                    url = user_input.strip()
                    print(f"🌐 Fetching clean content from: {url}")
                    content = self.researcher.fetch_clean_page_content(url)
                    print(f"🧠 Analyzing with Multi-Provider LLM Router...")
                    result = self.llm_router.extract_ai_tools(content, source_hint=url)
                    if result and result.tools:
                        for tool in result.tools:
                            if not tool.official_url or "example.com" in tool.official_url:
                                tool.official_url = url
                            is_new, msg = self.merge_tool(tool, result.organization_summary, result.organization_website)
                            print(f"\n{msg}")
                            print("----------------------------------------------------------------------")
                            print(json.dumps(tool.model_dump(), indent=2))
                            print("----------------------------------------------------------------------")
                        self.save_directory()
                        self.record_changelog(result.tools, [], context=f"Interactive URL Analysis: {url}")
                    else:
                        print("❌ Could not extract structured tool from provided URL.")

                else:
                    # Treat as search query
                    print(f"🔎 Researching AI tool or ecosystem: '{user_input}'...")
                    res = self.run_backfill(user_input, max_results=3)
                    print(f"✅ Completed! Added: {res['added_count']} | Updated: {res['updated_count']}")

            except (KeyboardInterrupt, EOFError):
                print("\nSession interrupted. Exiting.")
                break
            except Exception as e:
                logger.error(f"Error handling interactive command: {e}", exc_info=True)

    # ========================================================================
    # UTILITY HELPERS
    # ========================================================================
    def _normalize_url(self, raw_url: str) -> str:
        """Returns clean normalized URL for deduplication."""
        if not raw_url:
            return ""
        try:
            p = urlparse(raw_url.strip())
            netloc = p.netloc.lower().replace("www.", "")
            path = p.path.rstrip("/")
            return f"{p.scheme.lower()}://{netloc}{path}"
        except Exception:
            return raw_url.strip().lower()

    def _url_exists_in_db(self, normalized_url: str) -> bool:
        """Checks if a normalized URL already exists in database."""
        if not normalized_url:
            return False
        for org in self.directory_data.get("organizations", []):
            for tool in org.get("tools", []):
                if self._normalize_url(tool.get("official_url", "")) == normalized_url:
                    return True
        return False

    def _slugify(self, text: str) -> str:
        """Slugifies string for IDs."""
        import re
        s = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
        return s.strip("-")


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Optimus AI — Autonomous Global AI Directory & 24/7 Discovery Assistant"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cron", action="store_true", help="Execute single autonomous discovery batch (ideal for GitHub Actions)")
    group.add_argument("--daemon", action="store_true", help="Run continuously in background with a specified sleep interval")
    group.add_argument("--backfill", type=str, metavar="COMPANY_OR_CATEGORY", help="Execute deep historical discovery for specified company or category")
    group.add_argument("--interactive", action="store_true", help="Launch interactive CLI assistant studio")

    parser.add_argument("--interval", type=int, default=21600, help="Daemon sleep interval in seconds (default: 21600 / 6 hours)")
    parser.add_argument("--limit", type=int, default=8, help="Max candidates or search items to process per execution")
    parser.add_argument("--dry-run", action="store_true", help="Run without consuming external LLM API quota (tests deduplication and merge pipeline)")

    args = parser.parse_args()
    assistant = OptimusAssistant()

    if args.cron:
        assistant.run_autonomous_sync(max_items=args.limit, dry_run=args.dry_run)
    elif args.daemon:
        logger.info(f"Optimus Spark Daemon initiated. Running discovery every {args.interval} seconds...")
        while True:
            try:
                assistant.run_autonomous_sync(max_items=args.limit, dry_run=args.dry_run)
                logger.info(f"Sleeping for {args.interval}s until next autonomous cycle...")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Daemon halted by user.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in daemon loop: {e}", exc_info=True)
                time.sleep(60)
    elif args.backfill:
        assistant.run_backfill(query=args.backfill, max_results=args.limit, dry_run=args.dry_run)
    elif args.interactive:
        assistant.run_interactive()
    else:
        # Default behavior if run without arguments: display status and help
        total_orgs = len(assistant.directory_data.get("organizations", []))
        total_tools = sum(len(o.get("tools", [])) for o in assistant.directory_data.get("organizations", []))
        print("=" * 65)
        print("Optimus AI — Autonomous Global AI Directory & 24/7 Discovery Assistant")
        print("=" * 65)
        print(f"Status: {total_tools} tools across {total_orgs} organizations.")
        print(f"Last Synchronized: {assistant.directory_data.get('last_updated')}")
        print("\nAvailable flags:")
        print("  --cron         Run single autonomous discovery batch")
        print("  --backfill     Run deep historical discovery for a company/topic")
        print("  --daemon       Run 24/7 background agent")
        print("  --interactive  Launch terminal studio")
        print("  --dry-run      Run pipeline without external LLM API quota")
        print("=" * 65)


if __name__ == "__main__":
    main()
