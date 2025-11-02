"use client"

import { useState, useEffect } from "react";
import { LiquidButton } from "@/components/ui/liquid-glass-button";
import { BorderTrail } from "@/components/ui/border-trail";

interface ClarifyingQuestion {
  id: number;
  proposition_id: number;
  factor_name: string;
  factor_id: number;
  factor_score: number;
  question: string;
  reasoning: string;
  evidence: string[];
  generation_method: string;
  validation_passed: boolean;
  created_at: string;
}

interface ClarifyingQuestionsResponse {
  questions: ClarifyingQuestion[];
  total_count: number;
}

interface ClarificationAnalysis {
  has_analysis: boolean;
  needs_clarification: boolean | null;
  clarification_score: number | null;
  triggered_factors: string[] | null;
  reasoning: string | null;
  factor_scores: Record<string, number> | null;
  created_at: string | null;
}

interface Proposition {
  id: number;
  text: string;
  reasoning: string;
  confidence: number | null;
  decay: number | null;
  created_at: string;
  updated_at: string;
  revision_group: string;
  version: number;
  observation_count: number;
  clarifying_questions?: ClarifyingQuestion[];  // Questions embedded
  clarification_analysis?: ClarificationAnalysis;  // Analysis embedded
}

interface PropositionsResponse {
  propositions: Proposition[];
  total_count: number;
}

export default function PropositionsPage() {
  const [propositions, setPropositions] = useState<Proposition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [filterMode, setFilterMode] = useState<'all' | 'with_questions' | 'without_questions'>('all');

  useEffect(() => {
    fetchPropositions();

    // Lightweight polling to auto-refresh while CLI runs
    let isCancelled = false;
    const POLL_MS = 3000;

    const silentRefresh = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/propositions?limit=200', {
          cache: 'no-store',
        });
        if (!response.ok) return;
        const data: PropositionsResponse = await response.json();
        
        // Fetch questions and analysis for each proposition
        const propositionsWithData = await Promise.all(
          data.propositions.map(async (prop) => {
            const questions: ClarifyingQuestion[] = [];
            let analysis: ClarificationAnalysis | undefined = undefined;
            
            // Fetch questions
            try {
              const qResponse = await fetch(`http://localhost:8000/api/propositions/${prop.id}/questions`, {
                cache: 'no-store',
              });
              if (qResponse.ok) {
                const qData: ClarifyingQuestionsResponse = await qResponse.json();
                questions.push(...qData.questions);
              }
            } catch {
              // Swallow errors
            }
            
            // Fetch analysis
            try {
              const aResponse = await fetch(`http://localhost:8000/api/propositions/${prop.id}/analysis`, {
                cache: 'no-store',
              });
              if (aResponse.ok) {
                analysis = await aResponse.json();
              }
            } catch {
              // Swallow errors
            }
            
            return { 
              ...prop, 
              clarifying_questions: questions,
              clarification_analysis: analysis
            };
          })
        );
        
        if (!isCancelled) {
          setPropositions(propositionsWithData);
          setTotalCount(data.total_count);
        }
      } catch {
        // swallow errors in background polling to avoid UI interruptions
      }
    };

    const id = setInterval(silentRefresh, POLL_MS);
    return () => {
      isCancelled = true;
      clearInterval(id);
    };
  }, []);

  const fetchPropositions = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:8000/api/propositions?limit=200', {
        cache: 'no-store',
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const data: PropositionsResponse = await response.json();
      
      // Fetch questions and analysis for each proposition in parallel
      const propositionsWithData = await Promise.all(
        data.propositions.map(async (prop) => {
          const questions: ClarifyingQuestion[] = [];
          let analysis: ClarificationAnalysis | undefined = undefined;
          
          // Fetch questions
          try {
            const qResponse = await fetch(`http://localhost:8000/api/propositions/${prop.id}/questions`, {
              cache: 'no-store',
            });
            if (qResponse.ok) {
              const qData: ClarifyingQuestionsResponse = await qResponse.json();
              questions.push(...qData.questions);
            }
          } catch {
            // Swallow errors
          }
          
          // Fetch analysis
          try {
            const aResponse = await fetch(`http://localhost:8000/api/propositions/${prop.id}/analysis`, {
              cache: 'no-store',
            });
            if (aResponse.ok) {
              analysis = await aResponse.json();
            }
          } catch {
            // Swallow errors
          }
          
          return { 
            ...prop, 
            clarifying_questions: questions,
            clarification_analysis: analysis
          };
        })
      );
      
      setPropositions(propositionsWithData);
      setTotalCount(data.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch propositions');
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (confidence: number | null) => {
    if (!confidence) return 'text-gray-400';
    if (confidence >= 8) return 'text-green-400';
    if (confidence >= 6) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getFactorColor = (factorScore: number) => {
    if (factorScore >= 0.8) return 'bg-red-500/20 text-red-300 border-red-500/50';
    if (factorScore >= 0.6) return 'bg-yellow-500/20 text-yellow-300 border-yellow-500/50';
    return 'bg-blue-500/20 text-blue-300 border-blue-500/50';
  };

  const getFactorScoreColor = (factorScore: number) => {
    if (factorScore >= 0.8) return 'text-red-400';
    if (factorScore >= 0.6) return 'text-yellow-400';
    return 'text-blue-400';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black p-8">
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center justify-center h-64">
            <div className="text-white text-xl">Loading propositions...</div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-black p-8">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-xl bg-red-500/20 p-6 backdrop-blur-sm border border-red-500/30">
            <h2 className="text-xl font-semibold text-red-400 mb-2">Error Loading Propositions</h2>
            <p className="text-red-300 mb-4">{error}</p>
            <LiquidButton onClick={fetchPropositions}>
              🔄 Retry
            </LiquidButton>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black p-8">
      <div className="mx-auto max-w-6xl">
        {/* Simple Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            GUM Propositions
          </h1>
          <p className="text-gray-300">
            {totalCount} propositions • Confidence overview
          </p>
        </div>

        {/* Simple Stats */}
        <div className="grid grid-cols-2 gap-4 mb-8">
          <div className="relative rounded-xl bg-white/10 p-4 backdrop-blur-sm">
            <BorderTrail size={40} />
            <div className="text-2xl font-bold text-white">{totalCount}</div>
            <div className="text-sm text-gray-300">Total</div>
          </div>
          <div className="relative rounded-xl bg-white/10 p-4 backdrop-blur-sm">
            <BorderTrail size={40} />
            <div className="text-2xl font-bold text-blue-400">
              {propositions.length > 0 
                ? Math.round(propositions.reduce((acc, p) => acc + (p.confidence || 0), 0) / propositions.length * 10) / 10
                : '—'}
            </div>
            <div className="text-sm text-gray-300">Avg Conf</div>
          </div>
        </div>

        {/* Propositions - Simple Cards */}
        {(() => {
          const filteredPropositions = propositions.filter((proposition) => {
            const hasQuestions = proposition.clarifying_questions && proposition.clarifying_questions.length > 0;
            if (filterMode === 'all') return true;
            if (filterMode === 'with_questions') return hasQuestions;
            if (filterMode === 'without_questions') return !hasQuestions;
            return true;
          });
          
          const withQuestionsCount = propositions.filter(p => p.clarifying_questions && p.clarifying_questions.length > 0).length;
          const withoutQuestionsCount = propositions.length - withQuestionsCount;
          
          return (
            <>
              {/* Filter Buttons */}
              <div className="mb-6 flex gap-3">
                <button
                  onClick={() => setFilterMode('all')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    filterMode === 'all'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  All ({propositions.length})
                </button>
                <button
                  onClick={() => setFilterMode('with_questions')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    filterMode === 'with_questions'
                      ? 'bg-green-500 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  With Questions ({withQuestionsCount})
                </button>
                <button
                  onClick={() => setFilterMode('without_questions')}
                  className={`px-4 py-2 rounded-lg transition-all ${
                    filterMode === 'without_questions'
                      ? 'bg-orange-500 text-white'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                  }`}
                >
                  Without Questions ({withoutQuestionsCount})
                </button>
              </div>

              {filteredPropositions.length === 0 ? (
                <div className="text-center py-16">
                  <div className="text-6xl mb-4">🔍</div>
                  <h3 className="text-xl font-semibold text-white mb-2">No Matching Propositions</h3>
                  <p className="text-gray-300 mb-6">
                    No propositions match the "{filterMode === 'with_questions' ? 'With Questions' : filterMode === 'without_questions' ? 'Without Questions' : 'All'}" filter
                  </p>
                  <button
                    onClick={() => setFilterMode('all')}
                    className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                  >
                    Show All Propositions
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {filteredPropositions.map((proposition) => (
                    <div
                      key={proposition.id}
                      className="relative rounded-xl bg-white/10 p-6 backdrop-blur-sm border border-white/20 hover:bg-white/15 transition-all duration-300"
                    >
                      <BorderTrail size={60} />
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-white mb-2">
                            {proposition.text}
                          </h3>
                        </div>
                        <div className={`text-2xl ${getConfidenceColor(proposition.confidence)}`}>
                          {proposition.confidence || '?'}/10
                        </div>
                      </div>

                      <div className="flex items-center justify-between mt-4 mb-4">
                        <div className="flex items-center gap-4">
                          <span className="text-sm text-gray-300">
                            {proposition.observation_count} observations
                          </span>
                        </div>
                        <div className="text-xs text-gray-400">
                          {new Date(proposition.created_at).toLocaleString()}
                        </div>
                      </div>

                      {/* Clarification Analysis Display */}
                      {proposition.clarification_analysis?.has_analysis && (
                        <div className="mt-4 pt-4 border-t border-white/20">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="text-sm font-semibold text-white">
                              Clarification Analysis
                            </h4>
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-1 rounded text-xs font-medium ${
                                proposition.clarification_analysis.needs_clarification 
                                  ? 'bg-orange-500/20 text-orange-300 border border-orange-500/50' 
                                  : 'bg-green-500/20 text-green-300 border border-green-500/50'
                              }`}>
                                {proposition.clarification_analysis.needs_clarification ? 'Flagged' : 'Not Flagged'}
                              </span>
                              <span className="text-sm text-gray-300">
                                Score: {(proposition.clarification_analysis.clarification_score! * 100).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                          
                          {/* Triggered Factors */}
                          {proposition.clarification_analysis.triggered_factors && 
                           proposition.clarification_analysis.triggered_factors.length > 0 && (
                            <div className="mb-3">
                              <p className="text-xs text-gray-400 mb-2">Triggered Factors:</p>
                              <div className="flex flex-wrap gap-2">
                                {proposition.clarification_analysis.triggered_factors.map((factor) => (
                                  <span 
                                    key={factor}
                                    className="px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-300 border border-blue-500/50"
                                  >
                                    {factor}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {/* Factor Scores - Top 5 */}
                          {proposition.clarification_analysis.factor_scores && (
                            <div>
                              <p className="text-xs text-gray-400 mb-2">Top Factor Scores:</p>
                              <div className="grid grid-cols-2 gap-2">
                                {Object.entries(proposition.clarification_analysis.factor_scores)
                                  .sort(([, a], [, b]) => b - a)
                                  .slice(0, 5)
                                  .map(([factor, score]) => (
                                    <div 
                                      key={factor}
                                      className="flex items-center justify-between px-2 py-1 rounded bg-white/5"
                                    >
                                      <span className="text-xs text-gray-300">{factor}</span>
                                      <span className={`text-xs font-medium ${
                                        score >= 0.6 ? 'text-red-400' : score >= 0.4 ? 'text-yellow-400' : 'text-gray-400'
                                      }`}>
                                        {(score * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                  ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Clarifying Questions Display */}
                      {proposition.clarifying_questions && proposition.clarifying_questions.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-white/20">
                          <h4 className="text-sm font-semibold text-white mb-3">
                            Clarifying Questions ({proposition.clarifying_questions.length})
                          </h4>
                          <div className="space-y-3">
                            {proposition.clarifying_questions.map((question) => (
                              <div
                                key={question.id}
                                className="relative rounded-lg bg-white/5 p-4 border border-white/10"
                              >
                                <div className="flex items-center justify-between mb-2">
                                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getFactorColor(question.factor_score)}`}>
                                    {question.factor_name}
                                  </span>
                                  <span className={`text-sm font-bold ${getFactorScoreColor(question.factor_score)}`}>
                                    {(question.factor_score * 100).toFixed(0)}%
                                  </span>
                                </div>
                                <p className="text-white text-sm mb-2">
                                  {question.question}
                                </p>
                                {question.reasoning && (
                                  <p className="text-gray-400 text-xs">
                                    Why: {question.reasoning}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          );
        })()}

        {propositions.length === 0 && !loading && (
          <div className="text-center py-16">
            <div className="text-6xl mb-4">🧠</div>
            <h3 className="text-xl font-semibold text-white mb-2">No Propositions Found</h3>
            <p className="text-gray-300 mb-6">
              Run GUM to start generating propositions about user behavior
            </p>
            <LiquidButton onClick={fetchPropositions}>
              🔄 Refresh
            </LiquidButton>
          </div>
        )}
      </div>

    </div>
  );
}