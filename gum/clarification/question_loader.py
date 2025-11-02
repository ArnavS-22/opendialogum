"""
Input loading for flagged propositions from file or database.

This module provides:
- Loading from JSON file (flagged_propositions.json)
- Loading from database (ClarificationAnalysis table)
- Standardized output format for processing
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..clarification_models import ClarificationAnalysis
from ..models import Observation, Proposition, observation_proposition
from sqlalchemy.orm import selectinload
from .question_config import get_factor_id_from_name, validate_factor_id

logger = logging.getLogger(__name__)


DEFAULT_FILE_PATH = "test_results_200_props/flagged_propositions.json"


async def load_flagged_propositions(
    source: str = "file",
    file_path: Optional[str] = None,
    db_session: Optional[AsyncSession] = None,
    enrich_with_db_observations: bool = False
) -> List[Dict[str, Any]]:
    """
    Load flagged propositions from file or database.
    
    Args:
        source: "file" or "db"
        file_path: Path to JSON file (default: DEFAULT_FILE_PATH)
        db_session: Database session (required if source="db")
        
    Returns:
        List of flagged proposition dicts with:
        - prop_id: int
        - prop_text: str
        - triggered_factors: List[str] (factor names)
        - observations: List[Dict] or List[int] (observation data)
        - prop_reasoning: Optional[str]
        
    Raises:
        ValueError: If source is invalid or required params missing
        FileNotFoundError: If file source and file doesn't exist
    """
    if source == "file":
        props = await _load_from_file(file_path)
        
        # Optionally enrich with DB observations if session provided
        if enrich_with_db_observations and db_session:
            props = await _enrich_with_db_observations(db_session, props)
        
        return props
    elif source == "db":
        if db_session is None:
            raise ValueError("db_session required when source='db'")
        return await _load_from_db(db_session)
    else:
        raise ValueError(f"Invalid source: {source}. Must be 'file' or 'db'")


async def _load_from_file(file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load flagged propositions from JSON file.
    
    Args:
        file_path: Path to JSON file (default: DEFAULT_FILE_PATH)
        
    Returns:
        List of proposition dicts
        
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    if file_path is None:
        file_path = DEFAULT_FILE_PATH
    
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Flagged propositions file not found: {file_path}")
    
    logger.info(f"Loading flagged propositions from {file_path}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(data, dict):
        # If top-level is dict, it might have a 'propositions' key
        propositions = data.get('propositions', [])
    elif isinstance(data, list):
        propositions = data
    else:
        raise ValueError(f"Unexpected data format in {file_path}")
    
    # Normalize format
    normalized = []
    for prop in propositions:
        normalized_prop = _normalize_proposition_format(prop)
        if normalized_prop:
            normalized.append(normalized_prop)
    
    logger.info(f"Loaded {len(normalized)} flagged propositions")
    return normalized


async def _load_from_db(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Load flagged propositions from database.
    
    Args:
        session: Database session
        
    Returns:
        List of proposition dicts
    """
    logger.info("Loading flagged propositions from database")
    
    # Import here to avoid circular imports
    from sqlalchemy.orm import selectinload
    
    # Query ClarificationAnalysis for flagged propositions with eager loading
    query = (
        select(ClarificationAnalysis)
        .options(selectinload(ClarificationAnalysis.proposition))
        .where(ClarificationAnalysis.needs_clarification == True)
    )
    
    result = await session.execute(query)
    analyses = result.scalars().all()
    
    propositions = []
    for analysis in analyses:
        # Get triggered factors
        triggered_factors = []
        if analysis.triggered_factors:
            if isinstance(analysis.triggered_factors, dict):
                # Handle dict format: {'factors': ['factor1', 'factor2']}
                triggered_factors = analysis.triggered_factors.get('factors', [])
            elif isinstance(analysis.triggered_factors, list):
                triggered_factors = analysis.triggered_factors
            elif isinstance(analysis.triggered_factors, str):
                # Parse if stored as string
                try:
                    parsed = json.loads(analysis.triggered_factors)
                    if isinstance(parsed, dict):
                        triggered_factors = parsed.get('factors', [])
                    elif isinstance(parsed, list):
                        triggered_factors = parsed
                    else:
                        triggered_factors = [parsed]
                except json.JSONDecodeError:
                    triggered_factors = [analysis.triggered_factors]
        
        # Get observations for this proposition
        observations = []
        if hasattr(analysis, 'proposition') and analysis.proposition:
            # Load observations associated with this proposition via join table
            obs_query = (
                select(Observation)
                .join(observation_proposition)
                .join(Proposition)
                .where(Proposition.id == analysis.proposition_id)
                .order_by(Observation.created_at.desc())
                .limit(5)
            )
            obs_result = await session.execute(obs_query)
            observations = [
                {
                    "id": obs.id,
                    "observation_text": obs.content,  # Observation model uses 'content' field
                    "timestamp": obs.created_at.isoformat() if hasattr(obs, 'created_at') and obs.created_at else None,
                    "source": "database"
                }
                for obs in obs_result.scalars().all()
            ]
        
        prop_dict = {
            "prop_id": analysis.proposition_id,
            "prop_text": analysis.proposition.text if hasattr(analysis, 'proposition') and analysis.proposition else "",  # Proposition model uses 'text' field
            "triggered_factors": triggered_factors,
            "observations": observations,
            "prop_reasoning": getattr(analysis, 'reasoning_log', None),  # ClarificationAnalysis has 'reasoning_log' not 'reasoning'
            "clarification_score": analysis.clarification_score,
            "factor_scores": {
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
            }
        }
        
        propositions.append(prop_dict)
    
    logger.info(f"Loaded {len(propositions)} flagged propositions from database")
    return propositions


def _normalize_proposition_format(prop: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize proposition format to standard structure.
    
    Args:
        prop: Raw proposition dict from file or DB
        
    Returns:
        Normalized dict or None if invalid
    """
    # Required fields
    prop_id = prop.get('prop_id') or prop.get('id')
    prop_text = prop.get('prop_text') or prop.get('text') or prop.get('proposition')
    
    if not prop_id or not prop_text:
        logger.warning(f"Skipping proposition with missing id or text: {prop}")
        return None
    
    # Get triggered factors
    triggered_factors = prop.get('triggered_factors', [])
    if isinstance(triggered_factors, str):
        # Single factor as string
        triggered_factors = [triggered_factors]
    
    # Validate and convert factor names to valid ones
    valid_factors = []
    for factor in triggered_factors:
        # Could be factor name or factor ID
        if isinstance(factor, int):
            if validate_factor_id(factor):
                from .question_config import get_factor_name
                valid_factors.append(get_factor_name(factor))
        elif isinstance(factor, str):
            # Check if it's a valid factor name
            factor_id = get_factor_id_from_name(factor)
            if factor_id:
                valid_factors.append(factor)
            else:
                logger.warning(f"Unknown factor name: {factor}")
    
    if not valid_factors:
        logger.warning(f"Proposition {prop_id} has no valid triggered factors")
        return None
    
    # Get observations - handle multiple formats
    observations = prop.get('observations', [])
    if not isinstance(observations, list):
        observations = []
    
    # If no observation objects but have observation_previews, create mock observations
    if not observations and prop.get('observation_previews'):
        # Create observation-like dicts from previews
        observation_previews = prop.get('observation_previews', [])
        observation_count = prop.get('observation_count', 0)
        
        # Create numbered observations from previews
        for i, preview in enumerate(observation_previews[:5]):  # Limit to 5
            obs_dict = {
                'id': f"preview_{prop_id}_{i}",  # Generate ID from preview index
                'observation_text': preview[:200] if len(preview) > 200 else preview,  # Truncate long previews
                'source': 'preview'  # Mark as preview
            }
            observations.append(obs_dict)
        
        # If there are more observations than previews, create placeholders
        if observation_count > len(observation_previews):
            for i in range(len(observation_previews), min(observation_count, 5)):
                obs_dict = {
                    'id': f"preview_{prop_id}_{i}",
                    'observation_text': f"[Observation {i+1} - preview not available]",
                    'source': 'placeholder'
                }
                observations.append(obs_dict)
    
    # Get reasoning if present
    prop_reasoning = prop.get('prop_reasoning') or prop.get('reasoning')
    
    return {
        "prop_id": prop_id,
        "prop_text": prop_text,
        "triggered_factors": valid_factors,
        "observations": observations,
        "prop_reasoning": prop_reasoning
    }


def filter_propositions(
    propositions: List[Dict[str, Any]],
    prop_ids: Optional[List[int]] = None,
    factor_names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Filter propositions by prop_ids and/or factor names.
    
    Args:
        propositions: List of proposition dicts
        prop_ids: Optional list of prop IDs to include
        factor_names: Optional list of factor names to include
        
    Returns:
        Filtered list of propositions
    """
    filtered = propositions
    
    # Filter by prop IDs
    if prop_ids:
        prop_id_set = set(prop_ids)
        filtered = [p for p in filtered if p["prop_id"] in prop_id_set]
    
    # Filter by factors
    if factor_names:
        factor_set = set(factor_names)
        filtered = [
            p for p in filtered
            if any(f in factor_set for f in p.get("triggered_factors", []))
        ]
    
    return filtered


async def _enrich_with_db_observations(
    session: AsyncSession,
    propositions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Enrich file-loaded propositions with actual observations from database.
    
    Args:
        session: Database session
        propositions: List of proposition dicts from file
        
    Returns:
        Enriched proposition dicts with database observations
    """
    from sqlalchemy import select
    
    enriched = []
    
    for prop in propositions:
        prop_id = prop.get("prop_id")
        if not prop_id:
            enriched.append(prop)
            continue
        
        try:
            # Query for observations linked to this proposition
            obs_query = (
                select(Observation)
                .join(observation_proposition)
                .join(Proposition)
                .where(Proposition.id == prop_id)
                .order_by(Observation.created_at.desc())
                .limit(5)
            )
            
            obs_result = await session.execute(obs_query)
            db_observations = [
                {
                    "id": obs.id,
                    "observation_text": obs.content,
                    "timestamp": obs.created_at.isoformat() if hasattr(obs, 'created_at') and obs.created_at else None,
                    "source": "database"
                }
                for obs in obs_result.scalars().all()
            ]
            
            # Replace preview-based observations with DB observations if available
            if db_observations:
                prop["observations"] = db_observations
                logger.info(f"Enriched prop {prop_id} with {len(db_observations)} DB observations")
            else:
                # Keep preview-based observations if no DB observations found
                logger.debug(f"No DB observations found for prop {prop_id}, using previews")
        
        except Exception as e:
            logger.warning(f"Failed to enrich prop {prop_id} with DB observations: {e}")
            # Keep original prop (with previews if any)
        
        enriched.append(prop)
    
    return enriched


def get_proposition_factor_pairs(
    propositions: List[Dict[str, Any]]
) -> List[tuple[Dict[str, Any], str]]:
    """
    Expand propositions into (proposition, factor) pairs.
    
    Each proposition may have multiple triggered factors, so this creates
    one pair for each factor.
    
    Args:
        propositions: List of proposition dicts
        
    Returns:
        List of (proposition_dict, factor_name) tuples
    """
    pairs = []
    
    for prop in propositions:
        for factor_name in prop.get("triggered_factors", []):
            pairs.append((prop, factor_name))
    
    return pairs

