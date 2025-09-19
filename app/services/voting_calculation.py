# app/services/voting_calculation.py
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from pref_voting.profiles_with_ties import ProfileWithTies


def create_profile_from_ballots(
    ballots: List[Any],
    candidates: List[Dict[str, Any]]
) -> Tuple[ProfileWithTies, List[str], Dict[str, str]]:
    """
    Convert database ballots to ProfileWithTies object.
    
    Returns:
        - profile: ProfileWithTies object with strict preference set
        - candidate_ids: List of candidate IDs in index order
        - candidate_names: Dict mapping ID to name
    """
    # Create candidate ID to index mapping
    candidate_ids = [c['id'] for c in candidates]
    candidate_names = {c['id']: c['name'] for c in candidates}
    id_to_index = {cid: i for i, cid in enumerate(candidate_ids)}
    
    # Convert ballots to pref_voting format
    rankings_list = []
    rcounts = []
    
    for ballot in ballots:
        # Convert rankings to pref_voting format (using indices)
        ranking = {}
        for item in ballot.rankings:
            cand_idx = id_to_index[item['candidate_id']]
            ranking[cand_idx] = item['rank']
        
        rankings_list.append(ranking)
        rcounts.append(ballot.count)
    
    # Create ProfileWithTies
    profile = ProfileWithTies(rankings_list, rcounts=rcounts)
    
    # CRITICAL: Set strict preference
    profile.use_extended_strict_preference()
    
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
            "statistics": get_ballot_statistics(profile),
            "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
            "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
        }
    
    # No Condorcet winner - apply MWSL
    return calculate_mwsl_no_condorcet(profile, candidate_ids, candidate_names)

def calculate_mwsl_no_condorcet(
    profile: ProfileWithTies,
    candidate_ids: List[str],
    candidate_names: Dict[str, str],
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
            "statistics": get_ballot_statistics(profile),
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
            "statistics": get_ballot_statistics(profile),
            "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
            "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
        }
    
    # Tie - multiple winners
    winner_ids = [candidate_ids[idx] for idx in winners_indices]
    winner_names = [candidate_names[wid] for wid in winner_ids]
    
    return {
        "winners": winner_names,
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
            "tied_candidates": winner_names,
            "loss_sequences": {
                candidate_names[candidate_ids[idx]]: loss_sequences[idx]
                for idx in winners_indices
            }
        },
        "statistics": get_ballot_statistics(profile),
        "pairwise_matrix": get_pairwise_matrix(profile, candidate_ids, candidate_names),
        "copeland_scores": get_copeland_scores(profile, candidate_ids, candidate_names)
    }

def get_ballot_statistics(profile: ProfileWithTies) -> Dict[str, Any]:
    """Get ballot statistics from profile"""
        
    return {
        "total_votes": profile.num_voters,
        "unique_ballots": len(profile.ranking_types),
        "bullet_votes": profile.num_bullet_votes(),
        "linear_orders": profile.num_linear_orders(),
        "truncated_linear_orders": profile.num_truncated_linear_orders(),
        "rankings_with_ties": profile.num_rankings_with_ties(),
        "ranked_all_candidates": profile.num_ranked_all_candidates(),
        "ballots_with_ties": profile.num_rankings_with_ties()
    }

def get_pairwise_matrix(
    profile: ProfileWithTies, 
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
    profile: ProfileWithTies,
    candidate_ids: List[str],
    candidate_names: Dict[str, str]
) -> Dict[str, float]:
    """Get Copeland scores for all candidates"""
    
    scores = profile.copeland_scores(scores=(1, 0.5, 0))
    return {
        candidate_names[candidate_ids[i]]: scores[i]
        for i in range(len(candidate_ids))
    }