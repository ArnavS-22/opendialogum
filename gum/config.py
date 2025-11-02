"""
Configuration management for Conversational GUM Refinement system.
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass 
class DecisionConfig:
    """Configuration for mixed-initiative decision engine."""
    base_p_no_action_dialogue: float = 0.3
    base_p_dialogue_action: float = 0.7
    
    # Base utility values
    u_action_goal_true: float = 1.0
    u_action_goal_false: float = -0.5
    u_no_action_goal_true: float = -0.6
    u_no_action_goal_false: float = 0.0
    u_dialogue_goal_true: float = 0.7
    u_dialogue_goal_false: float = -0.15
    
    # Attention-based adjustments
    high_focus_threshold: float = 0.8
    low_focus_threshold: float = 0.3
    high_focus_penalty_multiplier: float = 2.4  # -0.5 -> -1.2
    low_focus_penalty_reduction: float = 0.6   # -0.5 -> -0.2

@dataclass
class AttentionConfig:
    """Configuration for attention monitoring."""
    history_window_seconds: int = 300  # 5 minutes
    update_interval: float = 2.0
    app_detection_timeout: float = 2.0
    
    # Focus calculation parameters
    max_activity_for_boost: int = 20
    activity_weight: float = 0.3
    app_weight: float = 0.7
    idle_grace_period: float = 30.0
    max_idle_penalty: float = 0.8
    idle_penalty_window: float = 300.0  # 5 minutes
    distraction_threshold: float = 2.0  # switches per minute
    max_distraction_penalty: float = 0.5

@dataclass
class ClarificationConfig:
    """Configuration for clarification detection system."""
    enabled: bool = True
    shadow_mode: bool = True  # Collect data but don't route to Gates yet
    auto_generate_questions: bool = True  # Automatically generate questions after detection
    threshold: float = 0.6  # Aggregate score threshold for flagging
    model: str = "gpt-4o"  # LLM model to use (changed to gpt-4o for JSON support)
    temperature: float = 0.1  # Low temperature for consistency


@dataclass
class GumConfig:
    """Main configuration for GUM system."""
    decision: DecisionConfig
    attention: AttentionConfig
    clarification: ClarificationConfig
    
    def __init__(self):
        self.decision = DecisionConfig()
        self.attention = AttentionConfig()
        self.clarification = ClarificationConfig()
        
        # Load from environment variables if available
        self._load_from_env()
    
    def _load_from_env(self):
        """Load configuration from environment variables."""
        
        # Decision engine config
        if os.getenv('P_NO_ACTION_DIALOGUE'):
            self.decision.base_p_no_action_dialogue = float(os.getenv('P_NO_ACTION_DIALOGUE'))
        if os.getenv('P_DIALOGUE_ACTION'):
            self.decision.base_p_dialogue_action = float(os.getenv('P_DIALOGUE_ACTION'))
            
        # Attention config
        if os.getenv('ATTENTION_UPDATE_INTERVAL'):
            self.attention.update_interval = float(os.getenv('ATTENTION_UPDATE_INTERVAL'))
        if os.getenv('ATTENTION_HISTORY_WINDOW'):
            self.attention.history_window_seconds = int(os.getenv('ATTENTION_HISTORY_WINDOW'))
            
        # Clarification config
        if os.getenv('CLARIFICATION_ENABLED'):
            self.clarification.enabled = os.getenv('CLARIFICATION_ENABLED').lower() == 'true'
        if os.getenv('CLARIFICATION_SHADOW_MODE'):
            self.clarification.shadow_mode = os.getenv('CLARIFICATION_SHADOW_MODE').lower() == 'true'
        if os.getenv('CLARIFICATION_MODEL'):
            self.clarification.model = os.getenv('CLARIFICATION_MODEL')
            
    @classmethod
    def load_from_dict(cls, config_dict: Dict) -> 'GumConfig':
        """Load configuration from a dictionary."""
        config = cls()
        
        if 'decision' in config_dict:
            for key, value in config_dict['decision'].items():
                if hasattr(config.decision, key):
                    setattr(config.decision, key, value)
                    
        if 'attention' in config_dict:
            for key, value in config_dict['attention'].items():
                if hasattr(config.attention, key):
                    setattr(config.attention, key, value)
                    
        if 'clarification' in config_dict:
            for key, value in config_dict['clarification'].items():
                if hasattr(config.clarification, key):
                    setattr(config.clarification, key, value)
                    
        return config

# Global default configuration
DEFAULT_CONFIG = GumConfig()
