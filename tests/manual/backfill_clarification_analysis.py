#!/usr/bin/env python3
"""Backfill clarification analysis for all unanalyzed propositions"""

import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from openai import AsyncOpenAI
from gum.models import Proposition
from gum.clarification_models import ClarificationAnalysis
from gum.clarification import ClarificationDetector
from gum.config import GumConfig

async def main():
    # Get API key
    api_key = (
        os.getenv('OPENAI_API_KEY') or 
        os.getenv('GUM_LM_API_KEY') or
        None
    )
    
    if not api_key:
        print('❌ No API key found in environment')
        return
    
    print(f'✅ API Key found in environment')
    
    # DB setup
    db_path = os.path.expanduser('~/.cache/gum/gum.db')
    engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
    Session = async_sessionmaker(engine, expire_on_commit=False)
    
    # Config and client
    config = GumConfig()
    client = AsyncOpenAI(api_key=api_key)
    
    print('🔍 Finding unanalyzed propositions...')
    
    async with Session() as session:
        # Get count of all propositions
        total_props = await session.scalar(select(func.count()).select_from(Proposition))
        
        # Get IDs of analyzed propositions
        analyzed_ids_result = await session.execute(
            select(ClarificationAnalysis.proposition_id)
        )
        analyzed_ids = {row[0] for row in analyzed_ids_result.all()}
        
        # Get unanalyzed propositions
        unanalyzed_result = await session.execute(
            select(Proposition).where(~Proposition.id.in_(analyzed_ids) if analyzed_ids else True)
        )
        unanalyzed_props = unanalyzed_result.scalars().all()
        
        print(f'📊 Statistics:')
        print(f'   Total Propositions: {total_props}')
        print(f'   Already Analyzed: {len(analyzed_ids)}')
        print(f'   Need Analysis: {len(unanalyzed_props)}')
        print()
        
        if not unanalyzed_props:
            print('✅ All propositions already analyzed!')
            return
        
        # Initialize detector
        detector = ClarificationDetector(client, config)
        
        print(f'🚀 Analyzing {len(unanalyzed_props)} propositions...')
        
        analyzed_count = 0
        flagged_count = 0
        error_count = 0
        
        for i, prop in enumerate(unanalyzed_props, 1):
            try:
                analysis = await detector.analyze(prop, session)
                analyzed_count += 1
                
                if analysis.needs_clarification:
                    flagged_count += 1
                    print(f'   [{i}/{len(unanalyzed_props)}] Prop {prop.id}: FLAGGED (score={analysis.clarification_score:.2f})')
                else:
                    print(f'   [{i}/{len(unanalyzed_props)}] Prop {prop.id}: ok (score={analysis.clarification_score:.2f})')
                
                # Commit every 10 to avoid losing progress
                if i % 10 == 0:
                    await session.commit()
                    print(f'   💾 Committed batch {i//10}')
                    
            except Exception as e:
                error_count += 1
                print(f'   ❌ [{i}/{len(unanalyzed_props)}] Error analyzing prop {prop.id}: {e}')
                continue
        
        # Final commit
        await session.commit()
        
        print()
        print('✅ Backfill Complete!')
        print(f'   Analyzed: {analyzed_count}')
        print(f'   Flagged: {flagged_count}')
        print(f'   Errors: {error_count}')

if __name__ == '__main__':
    asyncio.run(main())

