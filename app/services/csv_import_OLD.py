# app/services/csv_import.py
import csv
from typing import List, Dict, Any, Tuple
from io import StringIO

def parse_csv_ballots(csv_content: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parse CSV content into candidates and ballots.
    First row: count, candidate1, candidate2, ...
    Data rows: count, rank1, rank2, ...
    
    Returns:
        - candidates: List of candidate dicts with id and name
        - ballots: List of ballot dicts with rankings and count
    """
    reader = csv.reader(StringIO(csv_content))
    headers = next(reader)
    
    # First column is count, rest are candidate names
    candidates = headers[1:]
    candidate_ids = [f"c{i}" for i in range(len(candidates))]
    
    # Create candidate list
    candidates_list = [
        {"id": cid, "name": name} 
        for cid, name in zip(candidate_ids, candidates)
    ]
    
    # Parse ballots
    ballots = []
    for row in reader:
        if not row or not row[0]:  # Skip empty rows
            continue
            
        count = int(row[0])
        rankings = []
        
        for i, rank_str in enumerate(row[1:]):
            if rank_str.strip():  # Only include ranked candidates
                rankings.append({
                    "candidate_id": candidate_ids[i],
                    "rank": int(rank_str)
                })
        
        if rankings:  # Only add if at least one candidate was ranked
            ballots.append({
                "rankings": rankings,
                "count": count
            })
    
    return candidates_list, ballots
