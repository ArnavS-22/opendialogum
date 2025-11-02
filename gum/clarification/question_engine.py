"""
Main orchestrator for the clarifying question generation pipeline.

This module provides:
- ClarifyingQuestionEngine class
- Pipeline execution (load -> filter -> generate -> validate -> write)
- Statistics tracking
- JSONL output
- Database persistence (optional)
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from .question_loader import (
    load_flagged_propositions,
    filter_propositions,
    get_proposition_factor_pairs
)
from .question_generator import QuestionGenerator
from .question_validator import QuestionValidator
from .question_config import get_factor_id_from_name

logger = logging.getLogger(__name__)


class ClarifyingQuestionEngine:
    """Main orchestrator for clarifying question generation pipeline."""
    
    def __init__(
        self,
        openai_client: AsyncOpenAI,
        config: Any,
        input_source: str = "file",
        input_file_path: Optional[str] = None,
        output_path: Optional[str] = None,
        db_session: Optional[AsyncSession] = None
    ):
        """
        Initialize the question engine.
        
        Args:
            openai_client: AsyncOpenAI client
            config: Configuration object with model settings
            input_source: "file" or "db"
            input_file_path: Path to input file (for file source)
            output_path: Path to output JSONL file
            db_session: Optional database session for saving questions
        """
        self.client = openai_client
        self.config = config
        self.input_source = input_source
        self.input_file_path = input_file_path
        self.db_session = db_session
        
        # Set default output path
        if output_path is None:
            output_path = "test_results_200_props/clarifying_questions.jsonl"
        self.output_path = Path(output_path)
        
        # Initialize generator and validator
        # Config has nested clarification.model structure
        model = getattr(getattr(config, 'clarification', None), 'model', 'gpt-4') if hasattr(config, 'clarification') else 'gpt-4'
        self.generator = QuestionGenerator(openai_client, model=model)
        self.validator = QuestionValidator()
        
        # Statistics
        self.stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "validation_errors": 0,
            "generation_errors": 0
        }
        
        self.failures: List[Dict[str, Any]] = []
    
    async def run(
        self,
        prop_ids: Optional[List[int]] = None,
        factor_ids: Optional[List[int]] = None,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Main pipeline execution.
        
        Steps:
        1. Load flagged propositions
        2. Filter by prop_ids/factor_ids if provided
        3. For each (prop × factor):
            a. Generate question + reasoning + evidence
            b. Validate output
            c. If invalid, log warning and skip
            d. Append to results list
        4. Write JSONL output file
        5. Return stats summary
        
        Args:
            prop_ids: Optional list of prop IDs to process
            factor_ids: Optional list of factor IDs to process
            db_session: Database session (required if input_source="db")
            
        Returns:
            Dict with:
            - total_processed: int
            - successful: int
            - failed: int
            - output_file: str
            - failures: List[Dict]
        """
        logger.info("Starting clarifying question generation pipeline")
        start_time = datetime.now()
        
        # Step 1: Load propositions
        propositions = await load_flagged_propositions(
            source=self.input_source,
            file_path=self.input_file_path,
            db_session=db_session if db_session else self.db_session
        )
        
        logger.info(f"Loaded {len(propositions)} flagged propositions")
        
        # Step 2: Filter if needed
        if factor_ids:
            # Convert factor IDs to names for filtering
            from .question_config import get_factor_name
            factor_names = [get_factor_name(fid) for fid in factor_ids]
        else:
            factor_names = None
        
        filtered_props = filter_propositions(
            propositions,
            prop_ids=prop_ids,
            factor_names=factor_names
        )
        
        logger.info(f"Filtered to {len(filtered_props)} propositions")
        
        # Step 3: Expand into (prop, factor) pairs
        pairs = get_proposition_factor_pairs(filtered_props)
        
        logger.info(f"Processing {len(pairs)} (proposition, factor) pairs")
        
        # Step 4: Process each pair
        results = []
        
        for i, (prop, factor_name) in enumerate(pairs):
            self.stats["total_processed"] += 1
            
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(pairs)} pairs processed")
            
            try:
                result = await self._process_pair(prop, factor_name)
                
                if result:
                    results.append(result)
                    self.stats["successful"] += 1
                else:
                    self.stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"Failed to process prop {prop['prop_id']}, factor {factor_name}: {e}")
                self.stats["failed"] += 1
                self.stats["generation_errors"] += 1
                self.failures.append({
                    "prop_id": prop["prop_id"],
                    "factor": factor_name,
                    "error": str(e),
                    "error_type": "generation"
                })
        
        # Step 5: Write output
        self._write_jsonl(results)
        
        # Step 5b: Save to database if session provided
        if self.db_session:
            await self._save_to_database(results)
        
        # Step 6: Generate summary
        elapsed = (datetime.now() - start_time).total_seconds()
        
        summary = {
            "total_processed": self.stats["total_processed"],
            "successful": self.stats["successful"],
            "failed": self.stats["failed"],
            "validation_errors": self.stats["validation_errors"],
            "generation_errors": self.stats["generation_errors"],
            "output_file": str(self.output_path),
            "elapsed_seconds": elapsed,
            "failures": self.failures
        }
        
        logger.info(f"Pipeline complete: {self.stats['successful']} successful, {self.stats['failed']} failed")
        logger.info(f"Results written to {self.output_path}")
        
        return summary
    
    async def _process_pair(
        self,
        prop: Dict[str, Any],
        factor_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single (proposition, factor) pair.
        
        Args:
            prop: Proposition dict
            factor_name: Factor name
            
        Returns:
            Result dict or None if failed
        """
        prop_id = prop["prop_id"]
        prop_text = prop["prop_text"]
        observations = prop.get("observations", [])
        prop_reasoning = prop.get("prop_reasoning")
        
        # Get factor ID
        factor_id = get_factor_id_from_name(factor_name)
        if factor_id is None:
            logger.error(f"Invalid factor name: {factor_name}")
            return None
        
        # Get factor score from proposition data if available
        factor_scores = prop.get("factor_scores", {})
        factor_score = factor_scores.get(factor_name, 0.0)
        
        # Generate question
        try:
            result = await self.generator.generate_question_pair(
                prop_id=prop_id,
                prop_text=prop_text,
                factor_id=factor_id,
                observations=observations,
                prop_reasoning=prop_reasoning
            )
        except Exception as e:
            logger.error(f"Generation failed for prop {prop_id}, factor {factor_name}: {e}")
            raise
        
        # Validate
        obs_ids = self._get_observation_ids(observations)
        is_valid, errors = self.validator.validate_full_output(result, obs_ids)
        
        # Add validation metadata
        result["validation_passed"] = is_valid
        result["validation_warnings"] = errors if not is_valid else []
        
        if not is_valid:
            logger.warning(f"Validation failed for prop {prop_id}, factor {factor_name}: {errors}")
            self.stats["validation_errors"] += 1
            self.failures.append({
                "prop_id": prop_id,
                "factor": factor_name,
                "error": "; ".join(errors),
                "error_type": "validation"
            })
            # Still return result even if validation fails (for inspection)
            result["validation_errors"] = errors
        
        # Add metadata
        result["prop_text"] = prop_text
        result["timestamp"] = datetime.now().isoformat()
        result["factor_score"] = factor_score
        
        return result
    
    def _get_observation_ids(self, observations: List[Any]) -> Set[int]:
        """
        Extract observation IDs from observations list.
        
        Args:
            observations: List of observation dicts or objects
            
        Returns:
            Set of observation IDs
        """
        obs_ids = set()
        
        for obs in observations:
            if isinstance(obs, dict):
                obs_id = obs.get('id')
            else:
                obs_id = getattr(obs, 'id', None)
            
            if obs_id is not None:
                obs_ids.add(obs_id)
        
        return obs_ids
    
    def _write_jsonl(self, results: List[Dict[str, Any]]) -> None:
        """
        Write results to JSONL file.
        
        Args:
            results: List of result dicts
        """
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Writing {len(results)} results to {self.output_path}")
        
        with open(self.output_path, 'w') as f:
            for result in results:
                json_line = json.dumps(result, ensure_ascii=False)
                f.write(json_line + "\n")
        
        logger.info(f"Successfully wrote {len(results)} results")
    
    async def _save_to_database(self, results: List[Dict[str, Any]]) -> None:
        """
        Save generated questions to the database.
        
        Args:
            results: List of result dicts from question generation
        """
        if not self.db_session:
            logger.warning("No database session available, skipping DB save")
            return
        
        logger.info(f"Saving {len(results)} questions to database")
        
        # Import here to avoid circular imports
        from ..clarification_models import ClarifyingQuestion
        from sqlalchemy import select
        
        saved_count = 0
        skipped_count = 0
        
        for result in results:
            try:
                # Extract data from result dict
                prop_id = result.get('prop_id')
                factor = result.get('factor')
                question = result.get('question')
                reasoning = result.get('reasoning')
                evidence = result.get('evidence', [])
                generation_method = result.get('method', 'unknown')
                validation_passed = result.get('validation_passed', True)
                validation_warnings = result.get('validation_warnings', [])
                factor_score = result.get('factor_score', 0.0)
                
                # Skip if essential data is missing
                if not all([prop_id, factor, question, reasoning]):
                    logger.warning(f"Skipping result with missing data: {result}")
                    skipped_count += 1
                    continue
                
                # Get factor ID
                factor_id = get_factor_id_from_name(factor)
                if factor_id is None:
                    logger.error(f"Invalid factor name: {factor}, skipping")
                    skipped_count += 1
                    continue
                
                # Check for existing question to avoid duplicates
                existing_query = select(ClarifyingQuestion).where(
                    ClarifyingQuestion.proposition_id == prop_id,
                    ClarifyingQuestion.factor_id == factor_id
                )
                existing_result = await self.db_session.execute(existing_query)
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    logger.debug(f"Question already exists for prop {prop_id}, factor {factor} - skipping")
                    skipped_count += 1
                    continue
                
                # Get analysis ID if available
                analysis_id = None
                if self.input_source == "db":
                    # Try to find corresponding analysis
                    from ..clarification_models import ClarificationAnalysis
                    analysis_query = select(ClarificationAnalysis).where(
                        ClarificationAnalysis.proposition_id == prop_id
                    )
                    analysis_result = await self.db_session.execute(analysis_query)
                    analysis = analysis_result.scalar_one_or_none()
                    if analysis:
                        analysis_id = analysis.id
                
                # Create question record
                clarifying_question = ClarifyingQuestion(
                    proposition_id=prop_id,
                    analysis_id=analysis_id,
                    factor_name=factor,
                    factor_id=factor_id,
                    factor_score=factor_score,
                    question=question,
                    reasoning=reasoning,
                    evidence=evidence,
                    generation_method=generation_method,
                    model_used=self.generator.model,
                    validation_passed=validation_passed,
                    validation_warnings=validation_warnings
                )
                
                self.db_session.add(clarifying_question)
                saved_count += 1
                
            except Exception as e:
                logger.error(f"Error saving question to database: {e}")
                skipped_count += 1
                continue
        
        # Note: Don't commit here - let the caller handle transaction management
        # This allows the question generation to be part of a larger transaction
        logger.info(f"Added {saved_count} questions to session, skipped {skipped_count}")


async def run_engine_simple(
    openai_api_key: str,
    config: Any,
    input_source: str = "file",
    input_file_path: Optional[str] = None,
    output_path: Optional[str] = None,
    prop_ids: Optional[List[int]] = None,
    factor_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Simple helper to run the engine with API key.
    
    Args:
        openai_api_key: OpenAI API key
        config: Configuration object
        input_source: "file" or "db"
        input_file_path: Input file path
        output_path: Output file path
        prop_ids: Optional prop IDs to filter
        factor_ids: Optional factor IDs to filter
        
    Returns:
        Summary dict
    """
    client = AsyncOpenAI(api_key=openai_api_key)
    
    engine = ClarifyingQuestionEngine(
        openai_client=client,
        config=config,
        input_source=input_source,
        input_file_path=input_file_path,
        output_path=output_path
    )
    
    return await engine.run(
        prop_ids=prop_ids,
        factor_ids=factor_ids
    )

