#!/usr/bin/env python3
"""
FastAPI server for GUM dashboard
Connects to GUM SQLite database and provides API endpoints
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add the parent directory to Python path to import GUM modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import aiosqlite
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.orm import sessionmaker

# Import GUM models
from gum.models import Proposition, Observation, init_db
from gum.clarification_models import ClarificationAnalysis, ClarifyingQuestion

app = FastAPI(title="GUM Dashboard API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files not needed for API-only server

class PropositionResponse(BaseModel):
    id: int
    text: str
    reasoning: str
    confidence: Optional[int]
    decay: Optional[int]
    created_at: str
    updated_at: str
    revision_group: str
    version: int
    observation_count: int

class PropositionsListResponse(BaseModel):
    propositions: List[PropositionResponse]
    total_count: int

class ClarificationAnalysisResponse(BaseModel):
    has_analysis: bool
    needs_clarification: Optional[bool] = None
    clarification_score: Optional[float] = None
    triggered_factors: Optional[List[str]] = None
    reasoning: Optional[str] = None
    factor_scores: Optional[Dict[str, float]] = None
    created_at: Optional[str] = None

class FlaggedPropositionResponse(BaseModel):
    proposition: PropositionResponse
    clarification_score: float
    triggered_factors: List[str]
    reasoning: str

class ClarifyingQuestionResponse(BaseModel):
    id: int
    proposition_id: int
    factor_name: str
    factor_id: int
    factor_score: float
    question: str
    reasoning: str
    evidence: List[str]
    generation_method: str
    validation_passed: bool
    created_at: str

class ClarifyingQuestionsListResponse(BaseModel):
    questions: List[ClarifyingQuestionResponse]
    total_count: int

# Database connection
db_path = os.path.expanduser("~/.cache/gum/gum.db")
engine = None
Session = None

async def init_database():
    """Initialize database connection"""
    global engine, Session
    
    # Ensure directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    try:
        # init_db will create the database if it doesn't exist
        engine, Session = await init_db(
            db_path=os.path.basename(db_path),
            db_directory=db_dir
        )
        print(f"Connected to database: {db_path}")
        return True
    except Exception as e:
        print(f"Failed to connect to database: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    await init_database()

@app.get("/api/propositions", response_model=PropositionsListResponse)
async def get_propositions(
    limit: int = 50,
    offset: int = 0,
    confidence_min: Optional[int] = None
):
    """Get propositions from GUM database"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            # Build query
            query = select(Proposition)
            
            if confidence_min is not None:
                query = query.where(Proposition.confidence >= confidence_min)
            
            # Get total count
            count_query = select(func.count(Proposition.id))
            if confidence_min is not None:
                count_query = count_query.where(Proposition.confidence >= confidence_min)
            total_count_result = await session.execute(count_query)
            total_count = total_count_result.scalar()
            
            # Get propositions with pagination
            propositions_result = await session.execute(
                query.order_by(Proposition.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            
            # Convert to response format
            proposition_responses = []
            for prop in propositions_result.scalars():
                proposition_responses.append(PropositionResponse(
                    id=prop.id,
                    text=prop.text,
                    reasoning=prop.reasoning,
                    confidence=prop.confidence,
                    decay=prop.decay,
                    created_at=prop.created_at.isoformat() if prop.created_at else "",
                    updated_at=prop.updated_at.isoformat() if prop.updated_at else "",
                    revision_group=prop.revision_group,
                    version=prop.version,
                    observation_count=len(prop.observations) if prop.observations else 0,
                ))
            
            return PropositionsListResponse(
                propositions=proposition_responses,
                total_count=total_count
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def _noop():
    return None

@app.get("/api/propositions/{proposition_id}")
async def get_proposition(proposition_id: int):
    """Get a specific proposition by ID"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            proposition = await session.get(Proposition, proposition_id)
            if not proposition:
                raise HTTPException(status_code=404, detail="Proposition not found")

            return PropositionResponse(
                id=proposition.id,
                text=proposition.text,
                reasoning=proposition.reasoning,
                confidence=proposition.confidence,
                decay=proposition.decay,
                created_at=proposition.created_at.isoformat() if proposition.created_at else "",
                updated_at=proposition.updated_at.isoformat() if proposition.updated_at else "",
                revision_group=proposition.revision_group,
                version=proposition.version,
                observation_count=len(proposition.observations) if proposition.observations else 0,
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database_connected": Session is not None,
        "database_path": db_path,
        "database_exists": os.path.exists(db_path)
    }

@app.get("/api/propositions/{proposition_id}/clarification", response_model=ClarificationAnalysisResponse)
async def get_clarification_analysis(proposition_id: int):
    """Get clarification analysis for a specific proposition"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            # Check if proposition exists
            proposition = await session.get(Proposition, proposition_id)
            if not proposition:
                raise HTTPException(status_code=404, detail="Proposition not found")
            
            # Get clarification analysis
            analysis_result = await session.execute(
                select(ClarificationAnalysis)
                .where(ClarificationAnalysis.proposition_id == proposition_id)
                .order_by(ClarificationAnalysis.created_at.desc())
                .limit(1)
            )
            analysis = analysis_result.scalar_one_or_none()
            
            if not analysis:
                return ClarificationAnalysisResponse(has_analysis=False)
            
            # Get triggered factor names from the dictionary
            triggered = analysis.triggered_factors.get("factors", [])
            
            return ClarificationAnalysisResponse(
                has_analysis=True,
                needs_clarification=analysis.needs_clarification,
                clarification_score=analysis.clarification_score,
                triggered_factors=triggered,
                reasoning=analysis.reasoning_log,
                factor_scores={
                    "identity_mismatch": analysis.factor_1_identity,
                    "surveillance": analysis.factor_2_surveillance,
                    "inferred_intent": analysis.factor_3_intent,
                    "face_threat": analysis.factor_4_face_threat,
                    "over_positive": analysis.factor_5_over_positive,
                    "opacity": analysis.factor_6_opacity,
                    "generalization": analysis.factor_7_generalization,
                    "privacy": analysis.factor_8_privacy,
                    "actor_observer": analysis.factor_9_actor_observer,
                    "reputation_risk": analysis.factor_10_reputation,
                    "ambiguity": analysis.factor_11_ambiguity,
                    "tone_imbalance": analysis.factor_12_tone,
                },
                created_at=analysis.created_at.isoformat() if analysis.created_at else None
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/propositions/flagged", response_model=List[FlaggedPropositionResponse])
async def get_flagged_propositions(limit: int = 50):
    """Get propositions flagged for clarification"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            # Query propositions with clarification analyses where needs_clarification=True
            query = (
                select(Proposition, ClarificationAnalysis)
                .join(ClarificationAnalysis, Proposition.id == ClarificationAnalysis.proposition_id)
                .where(ClarificationAnalysis.needs_clarification == True)
                .order_by(ClarificationAnalysis.clarification_score.desc())
                .limit(limit)
            )
            
            results = await session.execute(query)
            
            flagged_responses = []
            for prop, analysis in results:
                triggered = analysis.triggered_factors.get("factors", [])
                
                flagged_responses.append(FlaggedPropositionResponse(
                    proposition=PropositionResponse(
                        id=prop.id,
                        text=prop.text,
                        reasoning=prop.reasoning,
                        confidence=prop.confidence,
                        decay=prop.decay,
                        created_at=prop.created_at.isoformat() if prop.created_at else "",
                        updated_at=prop.updated_at.isoformat() if prop.updated_at else "",
                        revision_group=prop.revision_group,
                        version=prop.version,
                        observation_count=len(prop.observations) if prop.observations else 0,
                    ),
                    clarification_score=analysis.clarification_score,
                    triggered_factors=triggered,
                    reasoning=analysis.reasoning_log
                ))
            
            return flagged_responses
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/propositions/{proposition_id}/questions", response_model=ClarifyingQuestionsListResponse)
async def get_clarifying_questions(proposition_id: int):
    """Get clarifying questions for a specific proposition"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            # Check if proposition exists
            proposition = await session.get(Proposition, proposition_id)
            if not proposition:
                raise HTTPException(status_code=404, detail="Proposition not found")
            
            # Get clarifying questions
            questions_query = select(ClarifyingQuestion).where(
                ClarifyingQuestion.proposition_id == proposition_id
            ).order_by(ClarifyingQuestion.created_at.desc())
            
            questions_result = await session.execute(questions_query)
            questions = questions_result.scalars().all()
            
            # Convert to response format
            question_responses = []
            for q in questions:
                question_responses.append(ClarifyingQuestionResponse(
                    id=q.id,
                    proposition_id=q.proposition_id,
                    factor_name=q.factor_name,
                    factor_id=q.factor_id,
                    factor_score=q.factor_score,
                    question=q.question,
                    reasoning=q.reasoning,
                    evidence=q.evidence,
                    generation_method=q.generation_method,
                    validation_passed=q.validation_passed,
                    created_at=q.created_at.isoformat() if q.created_at else ""
                ))
            
            return ClarifyingQuestionsListResponse(
                questions=question_responses,
                total_count=len(question_responses)
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/propositions/{proposition_id}/analysis", response_model=ClarificationAnalysisResponse)
async def get_clarification_analysis(proposition_id: int):
    """Get clarification analysis for a specific proposition"""
    if not Session:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    try:
        async with Session() as session:
            # Check if proposition exists
            proposition = await session.get(Proposition, proposition_id)
            if not proposition:
                raise HTTPException(status_code=404, detail="Proposition not found")
            
            # Get clarification analysis
            analysis_query = select(ClarificationAnalysis).where(
                ClarificationAnalysis.proposition_id == proposition_id
            )
            
            analysis_result = await session.execute(analysis_query)
            analysis = analysis_result.scalar_one_or_none()
            
            if not analysis:
                # No analysis exists yet
                return ClarificationAnalysisResponse(
                    has_analysis=False,
                    needs_clarification=None,
                    clarification_score=None,
                    triggered_factors=None,
                    reasoning=None,
                    factor_scores=None,
                    created_at=None
                )
            
            # Parse triggered factors
            triggered_factors = []
            if analysis.triggered_factors:
                if isinstance(analysis.triggered_factors, dict):
                    triggered_factors = analysis.triggered_factors.get('factors', [])
                elif isinstance(analysis.triggered_factors, list):
                    triggered_factors = analysis.triggered_factors
            
            # Get factor scores
            factor_scores = analysis.get_factor_scores()
            
            return ClarificationAnalysisResponse(
                has_analysis=True,
                needs_clarification=analysis.needs_clarification,
                clarification_score=analysis.clarification_score,
                triggered_factors=triggered_factors,
                reasoning=analysis.reasoning_log,
                factor_scores=factor_scores,
                created_at=analysis.created_at.isoformat() if analysis.created_at else None
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
