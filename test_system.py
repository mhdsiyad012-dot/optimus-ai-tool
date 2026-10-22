"""
Optimus AI — System Verification & Test Suite
"""

import json
from pathlib import Path
from agent.llm_router import ToolSchema, LLMRouter
from agent.optimus_assistant import OptimusAssistant

def test_directory_schema():
    print("Testing data/ai_directory.json schema...")
    db_path = Path("data/ai_directory.json")
    assert db_path.exists(), "ai_directory.json does not exist"
    
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "version" in data
    assert "organizations" in data
    assert len(data["organizations"]) > 0
    
    tool_count = 0
    for org in data["organizations"]:
        assert org.get("id"), f"Org missing id: {org}"
        assert org.get("name"), f"Org missing name: {org}"
        assert isinstance(org.get("tools"), list), f"Org missing tools list: {org}"
        for t in org["tools"]:
            validated = ToolSchema(**t)
            assert validated.id
            assert validated.name
            assert validated.parent_org
            assert validated.category
            assert validated.release_date
            assert validated.status in ["Active", "Beta", "Deprecated", "Experimental"]
            assert validated.pricing in ["Free", "Freemium", "Paid", "Open Source"]
            assert validated.official_url.startswith("http")
            assert validated.short_description
            assert isinstance(validated.key_features, list)
            assert isinstance(validated.tags, list)
            assert validated.last_verified
            tool_count += 1

    print(f"Schema test passed: {len(data['organizations'])} organizations, {tool_count} tools validated.")

def test_assistant_merger_and_deduplication():
    print("\nTesting deduplication and merger logic in OptimusAssistant...")
    assistant = OptimusAssistant()
    
    # 1. Existing tool update test
    existing_tool = ToolSchema(
        id="google-antigravity",
        name="Google Antigravity",
        parent_org="Google",
        category="Autonomous Agents & Coding",
        release_date="2025-11-15",
        status="Active",
        pricing="Free",
        official_url="https://antigravity.google",
        short_description="Updated description for testing deduplication engine.",
        key_features=["Subagent auto-coding", "Verification loop"],
        tags=["coding", "agent"],
        last_verified="2026-10-22"
    )
    
    is_new, msg = assistant.merge_tool(existing_tool)
    assert not is_new, "Existing tool was erroneously treated as new!"
    print(f" -> Existing tool correctly recognized: {msg}")

    # 2. Brand new tool addition test
    new_test_tool = ToolSchema(
        id="optimus-spark-test-agent",
        name="Optimus Spark Test Agent",
        parent_org="Optimus Labs",
        category="Autonomous Agents & Coding",
        release_date="2026-10-22",
        status="Active",
        pricing="Open Source",
        official_url="https://github.com/optimus-ai/test-agent",
        short_description="Autonomous test agent for validating directory integration.",
        key_features=["Self-healing tests", "Automated directory updates"],
        tags=["test-agent", "autonomous"],
        last_verified="2026-10-22"
    )
    
    is_new, msg = assistant.merge_tool(new_test_tool)
    assert is_new, "New tool was not marked as new!"
    print(f" -> New tool correctly merged: {msg}")

    # Verify that Optimus Labs org was created and tool exists
    labs_org = next((o for o in assistant.directory_data["organizations"] if o["id"] == "optimus-labs"), None)
    assert labs_org is not None, "New organization was not dynamically created!"
    assert any(t["id"] == "optimus-spark-test-agent" for t in labs_org["tools"]), "Tool not found in new org!"
    print(f" -> Dynamic parent org creation verified for '{labs_org['name']}' with {len(labs_org['tools'])} tool.")

def test_llm_router_heuristic():
    print("\nTesting LLM router deterministic fallback / dry-run extraction...")
    router = LLMRouter()
    sample_text = """
    # DeepMind Genie 2: Large-Scale Foundation World Model
    Google DeepMind announces Genie 2, a generative interactive environment simulator that can generate infinite 3D action-controllable virtual worlds from a single prompt image.
    Official link: https://deepmind.google/discover/blog/genie-2-a-large-scale-foundation-world-model/
    Key features:
    - Generates 3D interactive playable worlds from image prompts
    - Simulates complex camera actions, character physics, and lighting
    - Real-time keyboard and mouse control over generated game environments
    """
    
    res = router.extract_ai_tools(sample_text, source_hint="Google DeepMind Genie 2", force_dry_run=True)
    assert res and res.tools, "Heuristic extraction returned no tools!"
    extracted = res.tools[0]
    print(f" -> Extracted tool: {extracted.name} | Org: {extracted.parent_org} | Cat: {extracted.category} | URL: {extracted.official_url}")
    assert extracted.parent_org == "Google", f"Expected Google, got {extracted.parent_org}"
    assert len(extracted.key_features) > 0, "Expected extracted features"
    print("LLM router heuristic extraction test passed successfully.")

if __name__ == "__main__":
    test_directory_schema()
    test_assistant_merger_and_deduplication()
    test_llm_router_heuristic()
    print("\n[SUCCESS] ALL SYSTEM TESTS PASSED SUCCESSFULLY!")
