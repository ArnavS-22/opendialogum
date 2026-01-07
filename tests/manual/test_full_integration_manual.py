#!/usr/bin/env python3
"""
End-to-end integration test for clarification detection.
Tests the full pipeline: detector -> database -> API.
"""

import asyncio
import os
from pathlib import Path
from openai import AsyncOpenAI
from sqlalchemy import select

from gum.models import init_db, Proposition
from gum.clarification_models import ClarificationAnalysis
from gum.clarification import ClarificationDetector
from gum.config import GumConfig

async def test_full_integration():
    """Test the complete integration pipeline."""
    
    print("="  * 80)
    print("FULL INTEGRATION TEST")
    print("=" * 80)
    
    # Setup
    db_path = Path.home() / ".cache" / "gum" / "gum.db"
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    # Initialize database
    engine, Session = await init_db(
        db_path=db_path.name,
        db_directory=str(db_path.parent)
    )
    
    print(f"✓ Connected to database: {db_path}\n")
    
    # Initialize detector
    client = AsyncOpenAI(api_key=api_key)
    config = GumConfig()
    detector = ClarificationDetector(client, config)
    
    print("✓ Created ClarificationDetector\n")
    
    # Get a proposition
    async with Session() as session:
        result = await session.execute(
            select(Proposition)
            .order_by(Proposition.created_at.desc())
            .limit(1)
        )
        prop = result.scalar_one_or_none()
        
        if not prop:
            print("❌ No propositions found")
            return
        
        print(f"📝 Testing with Proposition #{prop.id}:")
        print(f"   Text: {prop.text[:80]}...")
        print()
        
        # Check if analysis already exists
        existing = await session.execute(
            select(ClarificationAnalysis)
            .where(ClarificationAnalysis.proposition_id == prop.id)
        )
        if existing.scalar_one_or_none():
            print("⚠️  Analysis already exists for this proposition")
            print("   Skipping to avoid duplicate\n")
        else:
            # Run the detector
            print("🚀 Running clarification detector...")
            print("   (This will make an API call and cost ~$0.04)\n")
            
            try:
                analysis = await detector.analyze(prop, session)
                
                print("✅ Analysis complete!\n")
                print(f"📊 Results:")
                print(f"   Needs Clarification: {analysis.needs_clarification}")
                print(f"   Clarification Score: {analysis.clarification_score:.2f}")
                print(f"   Validation Passed: {analysis.validation_passed}")
                print(f"   Model Used: {analysis.model_used}")
                print()
                
                if analysis.triggered_factors.get("factors"):
                    print(f"🚨 Triggered Factors:")
                    for factor_name in analysis.triggered_factors["factors"]:
                        print(f"   - {factor_name}")
                    print()
                
                print(f"💡 Reasoning: {analysis.reasoning_log}\n")
                
                # Verify it was persisted
                check = await session.execute(
                    select(ClarificationAnalysis)
                    .where(ClarificationAnalysis.proposition_id == prop.id)
                )
                persisted = check.scalar_one_or_none()
                
                if persisted:
                    print("✅ Analysis successfully persisted to database")
                    print(f"   Analysis ID: {persisted.id}")
                else:
                    print("❌ Analysis not found in database after creation!")
                    
            except Exception as e:
                print(f"❌ Detector failed: {e}")
                import traceback
                traceback.print_exc()
        
        # Test querying
        print("\n" + "-" * 80)
        print("TESTING DATABASE QUERY")
        print("-" * 80 + "\n")
        
        all_analyses = await session.execute(
            select(ClarificationAnalysis)
            .order_by(ClarificationAnalysis.created_at.desc())
            .limit(5)
        )
        analyses_list = all_analyses.scalars().all()
        
        print(f"Found {len(analyses_list)} total analyses in database:\n")
        for a in analyses_list:
            flag = "🚨" if a.needs_clarification else "✓"
            print(f"{flag} Prop #{a.proposition_id}: score={a.clarification_score:.2f}, "
                  f"valid={a.validation_passed}")
        
        if not analyses_list:
            print("   (No analyses found - run detector first)")
    
    await engine.dispose()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    # API key should be set via environment variable
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    asyncio.run(test_full_integration())

