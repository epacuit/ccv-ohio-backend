# app/services/ballot_process_rules.py
from typing import List, Dict, Any, Tuple, Optional, Set
from collections import defaultdict
import string
import re
import logging

# Set up logging
logger = logging.getLogger(__name__)

# NLTK initialization with proper error handling
NLTK_AVAILABLE = False
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize
    from nltk.stem import PorterStemmer
    
    # Try to ensure NLTK data is available
    def ensure_nltk_data():
        """Ensure NLTK data is downloaded and available"""
        try:
            # Test if data is already available
            nltk.data.find('tokenizers/punkt_tab')
            nltk.data.find('corpora/stopwords')
            return True
        except LookupError:
            try:
                logger.info("Downloading NLTK data...")
                nltk.download('punkt_tab', quiet=True)
                nltk.download('stopwords', quiet=True)
                # Test again
                nltk.data.find('tokenizers/punkt_tab')
                nltk.data.find('corpora/stopwords')
                logger.info("NLTK data downloaded successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to download NLTK data: {e}")
                return False
    
    NLTK_AVAILABLE = ensure_nltk_data()
    
except ImportError:
    logger.warning("NLTK not available - write-in matching will use basic normalization")
    NLTK_AVAILABLE = False

def normalize_candidate_name(name: str) -> str:
    """
    Normalize candidate name for matching.
    Uses NLTK if available, falls back to basic normalization.
    """
    if not name:
        return ""
    
    # Basic cleaning that always works
    cleaned = name.strip().lower()
    cleaned = cleaned.translate(str.maketrans('', '', string.punctuation))
    cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
    
    if NLTK_AVAILABLE:
        try:
            # Advanced NLTK processing
            tokens = word_tokenize(cleaned)
            stop_words = set(stopwords.words('english'))
            tokens = [token for token in tokens if token not in stop_words]
            stemmer = PorterStemmer()
            stemmed_tokens = [stemmer.stem(token) for token in tokens]
            normalized = ' '.join(stemmed_tokens)
            return normalized
        except Exception as e:
            logger.warning(f"NLTK processing failed, using basic normalization: {e}")
            # Fall through to basic normalization
    
    # Basic normalization fallback
    return cleaned

def find_candidate_matches(
    candidate_name: str, 
    existing_candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Find existing candidates that match the given name.
    """
    normalized_input = normalize_candidate_name(candidate_name)
    
    matches = []
    for candidate in existing_candidates:
        normalized_existing = normalize_candidate_name(candidate.get('name', ''))
        
        if normalized_input == normalized_existing:
            matches.append(candidate)
    
    return matches

def consolidate_write_ins_in_ballots(ballots: List[Any]) -> Tuple[List[Any], Dict[str, str]]:
    """
    Consolidate write-in candidates across ballots using name matching.
    
    Returns:
        - Updated ballots with consolidated candidate IDs
        - Mapping of original write-in names to canonical names
    """
    # Collect all write-in candidates from all ballots
    all_write_ins = {}  # normalized_name -> canonical_info
    write_in_mapping = {}  # original_id -> canonical_id
    
    # First pass: identify unique write-ins
    for ballot in ballots:
        if hasattr(ballot, 'write_ins') and ballot.write_ins:
            for write_in in ballot.write_ins:
                normalized = normalize_candidate_name(write_in['name'])
                
                if normalized not in all_write_ins:
                    # First occurrence of this normalized name
                    canonical_id = f"writein_{normalized.replace(' ', '_')}"
                    all_write_ins[normalized] = {
                        'id': canonical_id,
                        'name': write_in['name'],  # Use first occurrence as canonical
                        'is_write_in': True,
                        'normalized': normalized
                    }
                    write_in_mapping[write_in['id']] = canonical_id
                else:
                    # Map this write-in to the canonical one
                    write_in_mapping[write_in['id']] = all_write_ins[normalized]['id']
    
    # Second pass: update ballot rankings with consolidated IDs
    updated_ballots = []
    name_mapping = {}  # original_name -> canonical_name
    
    for ballot in ballots:
        updated_rankings = []
        
        for ranking in ballot.rankings:
            candidate_id = ranking['candidate_id']
            
            if candidate_id in write_in_mapping:
                # This is a write-in that needs to be consolidated
                updated_rankings.append({
                    'candidate_id': write_in_mapping[candidate_id],
                    'rank': ranking['rank']
                })
                
                # Track name mapping for reporting
                original_name = next(
                    (wi['name'] for wi in (ballot.write_ins or []) if wi['id'] == candidate_id),
                    candidate_id
                )
                canonical_name = next(
                    (wi['name'] for wi in all_write_ins.values() if wi['id'] == write_in_mapping[candidate_id]),
                    candidate_id
                )
                if original_name != canonical_name:
                    name_mapping[original_name] = canonical_name
            else:
                # Regular candidate, keep as-is
                updated_rankings.append(ranking)
        
        # Create updated ballot object
        updated_ballot = type(ballot)(
            poll_id=ballot.poll_id,
            rankings=updated_rankings,
            count=ballot.count,
            voter_fingerprint=getattr(ballot, 'voter_fingerprint', None),
            voter_token=getattr(ballot, 'voter_token', None),
            ip_hash=getattr(ballot, 'ip_hash', None),
            import_batch_id=getattr(ballot, 'import_batch_id', None),
            is_test=getattr(ballot, 'is_test', False)
        )
        
        updated_ballots.append(updated_ballot)
    
    return updated_ballots, name_mapping

def create_consolidated_candidate_list(
    poll_candidates: List[Dict[str, Any]], 
    ballots: List[Any]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Create consolidated candidate list including normalized write-ins.
    
    Returns:
        - Complete candidate list (poll + consolidated write-ins)
        - Name consolidation mapping for reporting
    """
    # Start with poll candidates
    all_candidates = poll_candidates.copy()
    
    # Collect unique write-ins
    write_in_names = set()
    for ballot in ballots:
        if hasattr(ballot, 'write_ins') and ballot.write_ins:
            for write_in in ballot.write_ins:
                write_in_names.add(write_in['name'])
    
    # Group write-ins by normalized name
    normalized_groups = defaultdict(list)
    for name in write_in_names:
        normalized = normalize_candidate_name(name)
        normalized_groups[normalized].append(name)
    
    # Create consolidated write-in candidates
    name_mapping = {}
    for normalized, names in normalized_groups.items():
        if not normalized:  # Skip empty normalized names
            continue
            
        # Use the first name as canonical (or implement better selection logic)
        canonical_name = min(names, key=len)  # Shortest name as canonical
        canonical_id = f"writein_{normalized.replace(' ', '_')}"
        
        # Add to candidate list
        all_candidates.append({
            'id': canonical_id,
            'name': canonical_name,
            'is_write_in': True,
            'normalized': normalized
        })
        
        # Track name mappings
        for name in names:
            if name != canonical_name:
                name_mapping[name] = canonical_name
    
    return all_candidates, name_mapping

# Alaska rules implementation (unchanged from original)
def infer_pairwise_comparison_from_ballot_alaska_rules(ballot, cand1, cand2):
    """
    Alaska rules implementation - matches your Python implementation exactly.
    """
    rank_cand1 = ballot.get(cand1, None)
    rank_cand2 = ballot.get(cand2, None)
    menu = {cand1, cand2}
    
    if rank_cand1 is not None and rank_cand2 is not None:
        if rank_cand1 < rank_cand2:
            return (menu, {cand1})
        elif rank_cand2 < rank_cand1:
            return (menu, {cand2})
        else:
            return (menu, menu)
    elif (rank_cand1 is None or rank_cand2 is None) and not (rank_cand1 is None and rank_cand2 is None): 
        ranked_cand = cand1 if rank_cand1 is not None else cand2
        if not has_skipped_rank_above(ballot, ranked_cand):
            return (menu, {ranked_cand})
        else:
            return None
    else:
        if not has_skipped_rank(ballot):
            return (menu, menu)
        else:
            return None

def has_skipped_rank(ballot):
    """Check if there are skipped ranks in the ballot."""
    if not ballot:
        return False
    
    print("ballot is ", ballot)
    ranks = sorted(ballot.values())
    expected_ranks = list(range(1, len(ranks) + 1))
    return ranks != expected_ranks

def has_skipped_rank_above(ballot, candidate):
    """Check if there are skipped ranks above the given candidate."""
    if candidate not in ballot:
        return False
    
    candidate_rank = ballot[candidate]
    ranks_below = [r for r in ballot.values() if r < candidate_rank]
    
    if not ranks_below:
        return candidate_rank > 1
    
    # Check if ranks below form continuous sequence
    expected_ranks = list(range(1, len(ranks_below) + 1))
    if sorted(ranks_below) != expected_ranks:
        return True
    
    # CRITICAL FIX: Check if there's a gap between highest rank below and candidate's rank
    # If candidate is at rank 3 and highest below is 1, there's a skipped rank 2
    highest_rank_below = max(ranks_below)
    return candidate_rank > highest_rank_below + 1

def ballot_to_pairwise(ballot, candidates, ballot_to_comparison_fnc):
    """
    Convert ballot to pairwise comparisons using pref_voting PairwiseBallot.
    """
    from pref_voting.pairwise_profiles import PairwiseBallot
    
    comparisons = []
    for c1 in candidates:
        for c2 in candidates:
            if c1 != c2:
                comparison = ballot_to_comparison_fnc(ballot, c1, c2)
                if comparison is not None:
                    if all([comparison[0] != menu for menu, _ in comparisons]):
                        comparisons.append(comparison)

    return PairwiseBallot(comparisons, candidates=candidates)