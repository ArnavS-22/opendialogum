#!/usr/bin/env python3
"""
Test the clarification detection prompt with REAL API calls.
This will actually cost money but we need to verify it works.
"""

import asyncio
import json
import os
from openai import AsyncOpenAI
from gum.models import init_db, Proposition
from gum.db_utils import get_related_observations
from gum.clarification.prompts import CLARIFICATION_ANALYSIS_PROMPT
from sqlalchemy import select
from pathlib import Path

async def test_prompt():
    """Test the prompt with a real proposition and real API call."""
    
    print("=" * 80)
    print("CLARIFICATION DETECTION PROMPT TEST")
    print("=" * 80)
    
    # Initialize database
    db_path = Path.home() / ".cache" / "gum" / "gum.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return
    
    engine, Session = await init_db(
        db_path=db_path.name,
        db_directory=str(db_path.parent)
    )
    
    print(f"✓ Connected to database: {db_path}\n")
    
    # Get a real proposition
    async with Session() as session:
        result = await session.execute(
            select(Proposition)
            .order_by(Proposition.created_at.desc())
            .limit(1)
        )
        prop = result.scalar_one_or_none()
        
        if not prop:
            print("❌ No propositions found in database")
            return
        
        print(f"📝 Testing with Proposition #{prop.id}:")
        print(f"   Text: {prop.text[:100]}...")
        print(f"   Confidence: {prop.confidence}")
        print(f"   Reasoning: {prop.reasoning[:100] if prop.reasoning else 'None'}...\n")
        
        # Get observations
        observations = await get_related_observations(session, prop.id)
        print(f"   Found {len(observations)} related observations\n")
        
        # Format observations
        obs_text = "\n".join([
            f"[{i+1}] (ID: {obs.id}) {obs.observer_name}: {obs.content[:100]}..."
            for i, obs in enumerate(observations)
        ])
        
        # Extract user name (simple heuristic)
        words = prop.text.split()
        user_name = "the user"
        for i, word in enumerate(words[:5]):
            if word and len(word) > 2 and word[0].isupper():
                user_name = word
                break
        
        # Build context
        context = {
            "user_name": user_name,
            "proposition_text": prop.text,
            "reasoning": prop.reasoning or "No reasoning provided",
            "confidence": prop.confidence if prop.confidence is not None else 5,
            "observations": obs_text if obs_text else "No observations available."
        }
        
        # Format prompt
        prompt = CLARIFICATION_ANALYSIS_PROMPT.format(**context)
        
        print(f"📊 Prompt Stats:")
        print(f"   Total length: {len(prompt)} chars")
        print(f"   Estimated tokens: ~{len(prompt) // 4}")
        print()
        
        # Check for OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not set. Cannot make API call.")
            print("\nPrompt Preview (first 500 chars):")
            print("-" * 80)
            print(prompt[:500])
            print("-" * 80)
            return
        
        print("🚀 Making API call to GPT-4-turbo...")
        print("   (This will cost ~$0.03)\n")
        
        # Make the API call
        client = AsyncOpenAI(api_key=api_key)
        
        try:
            response = await client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in cognitive psychology analyzing behavioral propositions. Always return valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            print("✅ API call successful!\n")
            print(f"📊 Response Stats:")
            print(f"   Response length: {len(content)} chars")
            print(f"   Model used: {response.model}")
            print(f"   Tokens used: {response.usage.total_tokens}")
            print(f"   Cost: ~${response.usage.total_tokens * 0.00001:.4f}\n")
            
            # Try to parse JSON
            try:
                parsed = json.loads(content)
                
                print("✅ JSON parsed successfully!\n")
                
                # Validate structure
                issues = []
                
                if "factors" not in parsed:
                    issues.append("❌ Missing 'factors' field")
                else:
                    factors = parsed["factors"]
                    print(f"   Found {len(factors)} factors")
                    
                    if len(factors) != 12:
                        issues.append(f"❌ Expected 12 factors, got {len(factors)}")
                    
                    # Check each factor structure
                    for i, factor in enumerate(factors, 1):
                        if "id" not in factor:
                            issues.append(f"❌ Factor {i} missing 'id'")
                        if "name" not in factor:
                            issues.append(f"❌ Factor {i} missing 'name'")
                        if "score" not in factor:
                            issues.append(f"❌ Factor {i} missing 'score'")
                        if "triggered" not in factor:
                            issues.append(f"❌ Factor {i} missing 'triggered'")
                
                if "aggregate" not in parsed:
                    issues.append("❌ Missing 'aggregate' field")
                else:
                    agg = parsed["aggregate"]
                    if "clarification_score" not in agg:
                        issues.append("❌ Missing 'clarification_score' in aggregate")
                    if "needs_clarification" not in agg:
                        issues.append("❌ Missing 'needs_clarification' in aggregate")
                
                if issues:
                    print("\n⚠️  VALIDATION ISSUES:")
                    for issue in issues:
                        print(f"   {issue}")
                else:
                    print("   ✅ All structural checks passed!\n")
                    
                    # Print summary
                    agg = parsed.get("aggregate", {})
                    print("📊 ANALYSIS RESULTS:")
                    print(f"   Needs Clarification: {agg.get('needs_clarification')}")
                    print(f"   Clarification Score: {agg.get('clarification_score', 0):.2f}")
                    print(f"   Top Contributors: {', '.join(agg.get('top_contributors', []))}")
                    print(f"   Reasoning: {agg.get('reasoning_summary', 'N/A')}\n")
                    
                    # Show triggered factors
                    triggered = [f for f in parsed["factors"] if f.get("triggered")]
                    if triggered:
                        print(f"🚨 Triggered Factors ({len(triggered)}):")
                        for factor in triggered:
                            print(f"   [{factor['id']}] {factor['name']}: {factor['score']:.2f}")
                            print(f"       Reasoning: {factor.get('reasoning', 'N/A')}")
                            if factor.get('evidence'):
                                print(f"       Evidence: {', '.join(factor['evidence'][:2])}")
                        print()
                    
                    # Show all factor scores
                    print("📊 All Factor Scores:")
                    for factor in parsed["factors"]:
                        status = "🚨" if factor.get("triggered") else "✓"
                        print(f"   {status} [{factor['id']:2d}] {factor['name']:25s}: {factor['score']:.2f}")
                
                # Save full response for inspection
                output_file = "clarification_test_output.json"
                with open(output_file, "w") as f:
                    json.dump(parsed, f, indent=2)
                print(f"\n💾 Full response saved to: {output_file}")
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print("\nRaw response:")
                print("-" * 80)
                print(content)
                print("-" * 80)
                
        except Exception as e:
            print(f"❌ API call failed: {e}")
            import traceback
            traceback.print_exc()
    
    await engine.dispose()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_prompt())

