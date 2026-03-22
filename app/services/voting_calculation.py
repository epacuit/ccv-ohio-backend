# app/services/voting_calculation.py
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from pref_voting.pairwise_profiles import PairwiseProfile, PairwiseBallot


def create_profile_from_ballots(
    ballots: List[Any],
    candidates: List[Dict[str, Any]]
) -> Tuple[PairwiseProfile, List[str], Dict[str, str]]:
    """
    Create a PairwiseProfile directly from pairwise choice ballots.

    Each ballot's pairwise_choices field contains pairwise choices:
    [{"cand1_id": "...", "cand2_id": "...", "choice": "cand1"|"cand2"|"tie"}, ...]

    Creates PairwiseBallot objects directly using pref_voting library.
    """
    candidate_ids = [c['id'] for c in candidates]
    candidate_names = {c['id']: c['name'] for c in candidates}
    id_to_index = {cid: i for i, cid in enumerate(candidate_ids)}

    pairwise_ballots = []
    rcounts = []

    for ballot in ballots:
        comparisons = []

        for choice in ballot.pairwise_choices:
            cand1_id = choice.get('cand1_id')
            cand2_id = choice.get('cand2_id')
            choice_val = choice.get('choice')

            if cand1_id not in id_to_index or cand2_id not in id_to_index:
                continue

            idx1 = id_to_index[cand1_id]
            idx2 = id_to_index[cand2_id]

            menu = {idx1, idx2}

            if choice_val == 'cand1':
                # Strict preference for cand1
                chosen = {idx1}
            elif choice_val == 'cand2':
                # Strict preference for cand2
                chosen = {idx2}
            elif choice_val == 'tie':
                # Indifference
                chosen = {idx1, idx2}
            else:
                continue

            comparisons.append((menu, chosen))

        if comparisons:
            pb = PairwiseBallot(comparisons, candidates=list(range(len(candidate_ids))))
            pairwise_ballots.append(pb)
            rcounts.append(ballot.count)

    profile = PairwiseProfile(pairwise_ballots, rcounts=rcounts)

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
            "statistics": get_ballot_statistics_v2(profile, ballots, candidates),  # USE V2!
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
            "statistics": get_ballot_statistics_v2(profile, ballots, candidates),  # USE V2!
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
            "statistics": get_ballot_statistics_v2(profile, ballots, candidates),  # USE V2!
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
        "statistics": get_ballot_statistics_v2(profile, ballots, candidates),  # USE V2!
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
                # We need to check how many voters marked them as indifferent
                ties = 0
                for ballot, count in zip(*profile.comparisons_counts):
                    # Check if this ballot has them as indifferent (tied)
                    if ballot.indiff(i, j):
                        ties += count
                
                # Calculate undefined (didn't compare one or both)
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

def get_ballot_statistics_v2(
    profile: PairwiseProfile,
    original_ballots: List[Any] = None,
    candidates: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Get ballot statistics for pairwise comparison voting:
    - completed_all_matchups: % who filled in every head-to-head matchup
    - partial_ballot: % who skipped at least one matchup
    - has_ties: % who indicated indifference (selected both) in at least one matchup
    """

    total_votes = profile.num_voters
    num_candidates = len(candidates) if candidates else len(profile.candidates)
    total_matchups = (num_candidates * (num_candidates - 1)) // 2

    completed_all = 0
    partial = 0
    has_ties_count = 0

    if original_ballots:
        for ballot in original_ballots:
            if ballot.pairwise_choices:
                # Count actual selections (not 'neither')
                active_choices = sum(
                    1 for c in ballot.pairwise_choices
                    if c.get('choice') in ('cand1', 'cand2', 'tie')
                )

                if active_choices >= total_matchups:
                    completed_all += ballot.count
                else:
                    partial += ballot.count

                has_tie = any(
                    c.get('choice') == 'tie'
                    for c in ballot.pairwise_choices
                )
                if has_tie:
                    has_ties_count += ballot.count

    if total_votes > 0:
        return {
            "total_votes": total_votes,
            "completed_all_matchups": round((completed_all / total_votes) * 100, 1),
            "partial_ballot": round((partial / total_votes) * 100, 1),
            "has_ties": round((has_ties_count / total_votes) * 100, 1),
        }
    else:
        return {
            "total_votes": 0,
            "completed_all_matchups": 0,
            "partial_ballot": 0,
            "has_ties": 0,
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