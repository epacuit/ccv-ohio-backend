# app/services/voting_calculation.py
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from pref_voting.profiles_with_ties import ProfileWithTies
from pref_voting.pairwise_profiles import PairwiseProfile
from .ballot_process_rules import ballot_to_pairwise, infer_pairwise_comparison_from_ballot_alaska_rules


def create_profile_from_ballots(
    ballots: List[Any],
    candidates: List[Dict[str, Any]]
) -> Tuple[PairwiseProfile, List[str], Dict[str, str]]:
    
    from .ballot_process_rules import consolidate_write_ins_in_ballots, create_consolidated_candidate_list
    
    # Consolidate write-ins using NLTK
    consolidated_ballots, name_mapping = consolidate_write_ins_in_ballots(ballots)
    
    # Create complete candidate list
    all_candidates, consolidation_mapping = create_consolidated_candidate_list(candidates, ballots)
    
    # Rest of function stays the same
    candidate_ids = [c['id'] for c in all_candidates]
    candidate_names = {c['id']: c['name'] for c in all_candidates}
    id_to_index = {cid: i for i, cid in enumerate(candidate_ids)}
    
    # Convert ballots to pref_voting format
    rankings_list = []
    rcounts = []
    
    for ballot in consolidated_ballots:
        ranking = {}
        for item in ballot.rankings:
            if item['candidate_id'] in id_to_index:
                cand_idx = id_to_index[item['candidate_id']]
                ranking[cand_idx] = item['rank']
        
        rankings_list.append(ranking)
        rcounts.append(ballot.count)

    profile = PairwiseProfile([ballot_to_pairwise(b, [id_to_index[c_id] for c_id in candidate_ids], infer_pairwise_comparison_from_ballot_alaska_rules) for b in rankings_list], rcounts=rcounts)

    return profile, candidate_ids, candidate_names


def calculate_mwsl_with_explanation(
    ballots: List[Any],
    candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate MWSL results with full explanation"""
    
    # Use the extracted function
    profile, candidate_ids, candidate_names = create_profile_from_ballots(ballots, candidates)
    
    # Check for Condorcet winner first
    condorcet = profile.condorcet_winner()
    
    if condorcet is not None:
        # Condorcet winner exists
        winner_id = candidate_ids[condorcet]
        
        # Calculate margins against all others
        margins = {}
        for other_idx in range(len(candidate_ids)):
            if other_idx != condorcet:
                margin = profile.margin(condorcet, other_idx)
                other_id = candidate_ids[other_idx]
                margins[candidate_names[other_id]] = margin
        
        return {
            "winner": candidate_names[winner_id],
            "winner_id": winner_id,
            "winner_type": "condorcet",
            "explanation": {
                "type": "condorcet",
                "note": "Beats every other candidate head-to-head",
                "margins": margins
            },
            "statistics": get_ballot_statistics(profile, ballots, candidates),  # PASS CANDIDATES TOO!
            "detailed_pairwise_results": get_detailed_pairwise_results(profile, candidate_ids, candidate_names),
            "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
            "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
        }
    
    # No Condorcet winner - apply MWSL WITH BALLOTS
    return calculate_mwsl_no_condorcet(profile, candidate_ids, candidate_names, ballots, candidates)

def calculate_mwsl_no_condorcet(
    profile: PairwiseProfile,  # FIXED TYPE HINT
    candidate_ids: List[str],
    candidate_names: Dict[str, str],
    ballots: List[Any] = None,  # ADD BALLOTS PARAMETER
    candidates: List[Dict[str, Any]] = None  # ADD CANDIDATES PARAMETER
) -> Dict[str, Any]:
    """Calculate MWSL when there's no Condorcet winner"""
    
    # Get Copeland scores (with 0.5 for ties)
    scores = profile.copeland_scores(scores=(1, 0.5, 0))
    max_score = max(scores.values())
    
    # Find candidates with most wins
    most_wins_indices = [i for i in scores if scores[i] == max_score]
    most_wins_candidates = [candidate_ids[i] for i in most_wins_indices]
    
    if len(most_wins_candidates) == 1:
        # Single candidate with most wins
        winner_idx = most_wins_indices[0]
        winner_id = candidate_ids[winner_idx]
        
        return {
            "winner": candidate_names[winner_id],
            "winner_id": winner_id,
            "winner_type": "most_wins",
            "explanation": {
                "type": "most_wins",
                "note": "No Condorcet winner exists",
                "copeland_scores": {
                    candidate_names[candidate_ids[i]]: scores[i] 
                    for i in range(len(candidate_ids))
                },
                "max_wins": max_score,
                "candidates_with_most_wins": [
                    candidate_names[cid] for cid in most_wins_candidates
                ]
            },
            "statistics": get_ballot_statistics(profile, ballots, candidates),  # PASS CANDIDATES!
            "detailed_pairwise_results": get_detailed_pairwise_results(profile, candidate_ids, candidate_names),
            "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
            "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
        }
    
    # Multiple candidates with most wins - check losses
    loss_sequences = {}
    for idx in most_wins_indices:
        defeaters = profile.dominators(idx)
        if defeaters:
            losses = sorted([profile.margin(d, idx) for d in defeaters])
            loss_sequences[idx] = losses
        else:
            loss_sequences[idx] = [0]
    
    # Find minimal loss sequence
    min_sequence = min(loss_sequences.values())
    winners_indices = [idx for idx in most_wins_indices 
                      if loss_sequences[idx] == min_sequence]
    
    if len(winners_indices) == 1:
        # Single winner by smallest loss
        winner_idx = winners_indices[0]
        winner_id = candidate_ids[winner_idx]
        
        return {
            "winner": candidate_names[winner_id],
            "winner_id": winner_id,
            "winner_type": "smallest_loss",
            "explanation": {
                "type": "smallest_loss",
                "note": "No Condorcet winner exists",
                "copeland_scores": {
                    candidate_names[candidate_ids[i]]: scores[i] 
                    for i in range(len(candidate_ids))
                },
                "max_wins": max_score,
                "candidates_with_most_wins": [
                    candidate_names[cid] for cid in most_wins_candidates
                ],
                "loss_sequences": {
                    candidate_names[candidate_ids[idx]]: loss_sequences[idx]
                    for idx in most_wins_indices
                }
            },
            "statistics": get_ballot_statistics(profile, ballots, candidates),  # PASS CANDIDATES!
            "detailed_pairwise_results": get_detailed_pairwise_results(profile, candidate_ids, candidate_names),
            "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
            "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
        }
    
    # Tie - multiple winners
    winner_ids = [candidate_ids[idx] for idx in winners_indices]
    winner_names_list = [candidate_names[wid] for wid in winner_ids]
    
    return {
        "winners": winner_names_list,
        "winner_ids": winner_ids,
        "winner_type": "tie",
        "need_random_selection": True,
        "explanation": {
            "type": "tie",
            "note": "Multiple candidates have identical records",
            "copeland_scores": {
                candidate_names[candidate_ids[i]]: scores[i] 
                for i in range(len(candidate_ids))
            },
            "max_wins": max_score,
            "tied_candidates": winner_names_list,
            "loss_sequences": {
                candidate_names[candidate_ids[idx]]: loss_sequences[idx]
                for idx in winners_indices
            }
        },
        "statistics": get_ballot_statistics(profile, ballots, candidates),  # PASS CANDIDATES!
        "detailed_pairwise_results": get_detailed_pairwise_results(profile, candidate_ids, candidate_names),
        "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
        "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
    }


def get_detailed_pairwise_results(
    profile: PairwiseProfile,
    candidate_ids: List[str],
    candidate_names: Dict[str, str]
) -> Dict[str, Dict[str, int]]:
    """
    Get detailed pairwise comparison results with actual vote counts.
    """
    detailed_results = {}
    
    for i, cand_i_id in enumerate(candidate_ids):
        for j, cand_j_id in enumerate(candidate_ids):
            if i < j:  # Only process each pair once
                # Get actual vote counts using profile.support()
                i_over_j = profile.support(i, j)
                j_over_i = profile.support(j, i)
                
                # Total voters
                total_voters = profile.num_voters
                
                # Count ties using the profile's methods!
                # We need to check how many voters ranked them as indifferent
                ties = 0
                for ballot, count in zip(*profile.comparisons_counts):
                    # Check if this ballot has them as indifferent (tied)
                    if ballot.indiff(i, j):
                        ties += count
                
                # Calculate undefined (didn't rank one or both)
                # Total = i_over_j + j_over_i + ties + undefined
                undefined = total_voters - i_over_j - j_over_i - ties
                undefined = max(0, undefined)  # Can't be negative
                
                key = f"{candidate_names[cand_i_id]}_vs_{candidate_names[cand_j_id]}"
                detailed_results[key] = {
                    candidate_names[cand_i_id]: int(i_over_j),
                    candidate_names[cand_j_id]: int(j_over_i),
                    "ties": int(ties),  # ACTUAL TIE COUNT!
                    "undefined": int(undefined)
                }
    
    return detailed_results

def get_ballot_statistics(
    profile: PairwiseProfile, 
    original_ballots: List[Any] = None,
    candidates: List[Dict[str, Any]] = None  # ADD CANDIDATES PARAMETER
) -> Dict[str, Any]:
    """Get ballot statistics from profile including skipped ranks and all candidates ranked"""
    
    total_votes = profile.num_voters
    
    bullet_votes = sum([
        c for b, c in zip(*profile.comparisons_counts) 
        if b.is_transitive(profile.candidates) 
        and b.is_coherent() 
        and not b.is_empty() 
        and b.to_ranking().is_bullet_vote()
    ])
    
    linear_orders = sum([
        c for b, c in zip(*profile.comparisons_counts) 
        if b.is_transitive(profile.candidates) 
        and b.is_coherent() 
        and not b.is_empty() 
        and b.to_ranking().is_linear(len(profile.candidates))
    ])
    
    # Calculate truncated linear orders
    # These are rankings that are linear (no ties) but don't include all candidates
    truncated_linear_orders = sum([
        c for b, c in zip(*profile.comparisons_counts) 
        if b.is_transitive(profile.candidates) 
        and b.is_coherent() 
        and not b.is_empty() 
        and b.to_ranking().is_truncated_linear(len(profile.candidates))
        and not b.to_ranking().is_bullet_vote()  # And NOT a bullet vote
    ])
    
    has_tie = sum([
        c for b, c in zip(*profile.comparisons_counts) 
        if b.has_tie()
    ])
    
    # Calculate statistics from original ballots if provided
    has_skipped_ranks = 0
    all_candidates_ranked = 0  # NEW STATISTIC
    
    if original_ballots and candidates:
        from .ballot_process_rules import has_skipped_rank as check_skipped_ranks
        
        # Get the base candidate IDs from the poll
        base_candidate_ids = {c['id'] for c in candidates}
        
        for ballot in original_ballots:
            # Check if this ballot has skipped ranks
            if ballot.rankings:
                # Convert list format to dict format for the check
                ranking_dict = {item['candidate_id']: item['rank'] for item in ballot.rankings}
                
                # Check for skipped ranks
                if ranking_dict and check_skipped_ranks(ranking_dict):
                    has_skipped_ranks += ballot.count
                
                # Check if all candidates are ranked FOR THIS BALLOT
                # A ballot ranks all candidates if it ranks:
                # 1. All base poll candidates
                # 2. Plus any write-ins THIS ballot added
                
                # Get this ballot's write-in IDs
                ballot_write_in_ids = set()
                if hasattr(ballot, 'write_ins') and ballot.write_ins:
                    for write_in in ballot.write_ins:
                        if isinstance(write_in, dict) and 'id' in write_in:
                            ballot_write_in_ids.add(write_in['id'])
                
                # Required candidates for THIS ballot = base candidates + its own write-ins
                required_candidates = base_candidate_ids | ballot_write_in_ids
                
                # Get the candidates this ballot actually ranked
                ranked_candidate_ids = set(ranking_dict.keys())
                
                # Check if this ballot ranked all its required candidates
                if ranked_candidate_ids >= required_candidates:  # >= means "is superset of or equal to"
                    all_candidates_ranked += ballot.count
    
    return {
        "total_votes": total_votes,
        "bullet_votes": bullet_votes,
        "linear_orders": linear_orders,
        "truncated_linear_orders": truncated_linear_orders,  
        "has_tie": has_tie,
        "has_skipped_ranks": has_skipped_ranks,
        "all_candidates_ranked": all_candidates_ranked  # NEW STATISTIC
    }

def get_pairwise_matrix(
    profile: PairwiseProfile,  # FIXED TYPE HINT
    candidate_ids: List[str],
    candidate_names: Dict[str, str]
) -> Dict[str, Dict[str, int]]:
    """Get pairwise comparison matrix"""
    
    matrix = {}
    for i, cand_i_id in enumerate(candidate_ids):
        matrix[candidate_names[cand_i_id]] = {}
        for j, cand_j_id in enumerate(candidate_ids):
            if i != j:
                margin = profile.margin(i, j)
                matrix[candidate_names[cand_i_id]][candidate_names[cand_j_id]] = margin
    
    return matrix

def get_copeland_scores(
    profile: PairwiseProfile,  # FIXED TYPE HINT
    candidate_ids: List[str],
    candidate_names: Dict[str, str]
) -> Dict[str, float]:
    """Get Copeland scores for all candidates"""
    
    scores = profile.copeland_scores(scores=(1, 0.5, 0))
    return {
        candidate_names[candidate_ids[i]]: scores[i]
        for i in range(len(candidate_ids))
    }