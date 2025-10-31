#!/usr/bin/env python3
"""
Comprehensive Concurrency Test Suite for Voting System

Tests for race conditions and concurrency issues in:
- Poll creation
- Ballot submission
- Result calculation and caching

Usage:
    python test_concurrency_suite.py https://your-app.com
    python test_concurrency_suite.py https://your-app.com --scenario all
    python test_concurrency_suite.py https://your-app.com --scenario ballot-storm
"""

import asyncio
import httpx
import sys
import time
import json
import random
from typing import Dict, Any, List, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import argparse

@dataclass
class TestResult:
    """Results from a test scenario"""
    scenario_name: str
    total_requests: int
    successful: int
    failed: int
    errors: Dict[str, int] = field(default_factory=dict)
    duration: float = 0.0
    response_times: List[float] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        return (self.successful / self.total_requests * 100) if self.total_requests > 0 else 0
    
    @property
    def p50(self) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        return sorted_times[len(sorted_times) // 2]
    
    @property
    def p95(self) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        return sorted_times[int(len(sorted_times) * 0.95)]
    
    @property
    def p99(self) -> float:
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        return sorted_times[int(len(sorted_times) * 0.99)]


class VotingSystemTester:
    """Comprehensive tester for voting system concurrency"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.test_polls: List[Dict[str, Any]] = []
        self.results: List[TestResult] = []
        
    async def create_test_poll(
        self,
        title: str,
        num_candidates: int = 4,
        settings: Dict[str, Any] = None,
        is_private: bool = False
    ) -> Dict[str, Any]:
        """Create a test poll"""
        
        candidates = [
            {"name": f"Candidate {chr(65+i)}"} 
            for i in range(num_candidates)
        ]
        
        poll_data = {
            "title": title,
            "description": f"Test poll for concurrency testing - {datetime.now()}",
            "candidates": candidates,
            "settings": settings or {"num_ranks": num_candidates},
            "is_private": is_private,
            "owner_email": "test@example.com",
            "is_test": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/polls/",
                json=poll_data,
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to create poll: {response.text}")
            
            poll = response.json()
            self.test_polls.append(poll)
            return poll
    
    async def submit_ballot(
        self,
        client: httpx.AsyncClient,
        poll_id: str,
        rankings: List[Dict[str, Any]],
        voter_fingerprint: str = None
    ) -> Tuple[int, float, str]:
        """Submit a ballot and return (status_code, duration, error_msg)"""
        
        start = time.time()
        error = None
        
        try:
            ballot_data = {
                "poll_id": poll_id,
                "rankings": rankings,
                "voter_fingerprint": voter_fingerprint or f"voter-{random.randint(1, 1000000)}"
            }
            
            response = await client.post(
                f"{self.base_url}/api/v1/ballots/",
                json=ballot_data,
                timeout=30.0
            )
            
            duration = time.time() - start
            return response.status_code, duration, None
            
        except Exception as e:
            duration = time.time() - start
            return 0, duration, str(e)
    
    async def get_results(
        self,
        client: httpx.AsyncClient,
        poll_id: str
    ) -> Tuple[int, float, str]:
        """Get poll results and return (status_code, duration, error_msg)"""
        
        start = time.time()
        
        try:
            response = await client.get(
                f"{self.base_url}/api/v1/results/{poll_id}",
                timeout=30.0
            )
            
            duration = time.time() - start
            return response.status_code, duration, None
            
        except Exception as e:
            duration = time.time() - start
            return 0, duration, str(e)
    
    # ============================================================
    # TEST SCENARIOS
    # ============================================================
    
    async def test_concurrent_ballot_submission(
        self,
        num_voters: int = 50,
        num_candidates: int = 4
    ) -> TestResult:
        """Test many users submitting ballots simultaneously"""
        
        print(f"\n{'='*60}")
        print(f"TEST: Concurrent Ballot Submission")
        print(f"Voters: {num_voters}, Candidates: {num_candidates}")
        print(f"{'='*60}")
        
        # Create test poll
        poll = await self.create_test_poll(
            f"Concurrent Ballots Test - {num_voters} voters",
            num_candidates=num_candidates
        )
        
        candidate_ids = [c['id'] for c in poll['candidates']]
        
        result = TestResult(
            scenario_name="concurrent_ballot_submission",
            total_requests=num_voters,
            successful=0,
            failed=0

        )
        
        async with httpx.AsyncClient() as client:
            # Create random ballots
            tasks = []
            for i in range(num_voters):
                # Random ranking
                shuffled = candidate_ids.copy()
                random.shuffle(shuffled)
                rankings = [
                    {"candidate_id": cid, "rank": rank + 1}
                    for rank, cid in enumerate(shuffled)
                ]
                
                tasks.append(self.submit_ballot(
                    client,
                    poll['short_id'],
                    rankings,
                    f"voter-{i}"
                ))
            
            # Execute all submissions concurrently
            print(f"Submitting {num_voters} ballots concurrently...")
            start = time.time()
            results = await asyncio.gather(*tasks)
            result.duration = time.time() - start
            
            # Analyze results
            for status, duration, error in results:
                result.response_times.append(duration)
                if status == 200:
                    result.successful += 1
                else:
                    result.failed += 1
                    error_key = error or f"HTTP {status}"
                    result.errors[error_key] = result.errors.get(error_key, 0) + 1
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    async def test_concurrent_result_viewing(
        self,
        num_voters: int = 20,
        num_viewers: int = 50
    ) -> TestResult:
        """Test many users viewing results simultaneously"""
        
        print(f"\n{'='*60}")
        print(f"TEST: Concurrent Result Viewing")
        print(f"Voters: {num_voters}, Viewers: {num_viewers}")
        print(f"{'='*60}")
        
        # Create poll and add votes
        poll = await self.create_test_poll(
            f"Concurrent Results Test - {num_viewers} viewers"
        )
        
        candidate_ids = [c['id'] for c in poll['candidates']]
        
        # Add some ballots first
        print(f"Adding {num_voters} ballots...")
        async with httpx.AsyncClient() as client:
            for i in range(num_voters):
                shuffled = candidate_ids.copy()
                random.shuffle(shuffled)
                rankings = [
                    {"candidate_id": cid, "rank": rank + 1}
                    for rank, cid in enumerate(shuffled)
                ]
                await self.submit_ballot(client, poll['short_id'], rankings, f"voter-{i}")
        
        # Now test concurrent result viewing
        result = TestResult(
            scenario_name="concurrent_result_viewing",
            total_requests=num_viewers,
            successful=0,
            failed=0

        )
        
        async with httpx.AsyncClient() as client:
            tasks = [
                self.get_results(client, poll['short_id'])
                for _ in range(num_viewers)
            ]
            
            print(f"Requesting results {num_viewers} times concurrently...")
            start = time.time()
            results = await asyncio.gather(*tasks)
            result.duration = time.time() - start
            
            for status, duration, error in results:
                result.response_times.append(duration)
                if status == 200:
                    result.successful += 1
                else:
                    result.failed += 1
                    error_key = error or f"HTTP {status}"
                    result.errors[error_key] = result.errors.get(error_key, 0) + 1
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    async def test_ballot_storm_with_results(
        self,
        num_voters: int = 30,
        num_result_checks: int = 20
    ) -> TestResult:
        """Test ballots being submitted while results are being viewed"""
        
        print(f"\n{'='*60}")
        print(f"TEST: Ballot Storm with Result Viewing")
        print(f"Voters: {num_voters}, Result checks: {num_result_checks}")
        print(f"{'='*60}")
        
        poll = await self.create_test_poll(
            f"Storm Test - {num_voters}v + {num_result_checks}r"
        )
        
        candidate_ids = [c['id'] for c in poll['candidates']]
        
        result = TestResult(
            scenario_name="ballot_storm_with_results",
            total_requests=num_voters + num_result_checks,
            successful=0,
            failed=0

        )
        
        async with httpx.AsyncClient() as client:
            tasks = []
            
            # Add ballot submission tasks
            for i in range(num_voters):
                shuffled = candidate_ids.copy()
                random.shuffle(shuffled)
                rankings = [
                    {"candidate_id": cid, "rank": rank + 1}
                    for rank, cid in enumerate(shuffled)
                ]
                tasks.append(self.submit_ballot(
                    client,
                    poll['short_id'],
                    rankings,
                    f"voter-{i}"
                ))
            
            # Add result viewing tasks
            for _ in range(num_result_checks):
                tasks.append(self.get_results(client, poll['short_id']))
            
            # Shuffle to mix ballots and result requests
            random.shuffle(tasks)
            
            print(f"Executing {len(tasks)} mixed requests concurrently...")
            start = time.time()
            results = await asyncio.gather(*tasks)
            result.duration = time.time() - start
            
            for status, duration, error in results:
                result.response_times.append(duration)
                if status == 200:
                    result.successful += 1
                else:
                    result.failed += 1
                    error_key = error or f"HTTP {status}"
                    result.errors[error_key] = result.errors.get(error_key, 0) + 1
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    async def test_staggered_load(
        self,
        waves: int = 5,
        voters_per_wave: int = 10,
        wave_delay: float = 0.5
    ) -> TestResult:
        """Test staggered loads (simulates real-world traffic spikes)"""
        
        print(f"\n{'='*60}")
        print(f"TEST: Staggered Load")
        print(f"Waves: {waves}, Voters/wave: {voters_per_wave}, Delay: {wave_delay}s")
        print(f"{'='*60}")
        
        poll = await self.create_test_poll(
            f"Staggered Test - {waves} waves"
        )
        
        candidate_ids = [c['id'] for c in poll['candidates']]
        total_voters = waves * voters_per_wave
        
        result = TestResult(
            scenario_name="staggered_load",
            total_requests=total_voters + waves,  # +waves for result checks
            successful=0,
            failed=0
        )
        
        start = time.time()
        
        async with httpx.AsyncClient() as client:
            for wave in range(waves):
                print(f"Wave {wave + 1}/{waves}...")
                
                # Submit ballots in this wave
                tasks = []
                for i in range(voters_per_wave):
                    voter_id = wave * voters_per_wave + i
                    shuffled = candidate_ids.copy()
                    random.shuffle(shuffled)
                    rankings = [
                        {"candidate_id": cid, "rank": rank + 1}
                        for rank, cid in enumerate(shuffled)
                    ]
                    tasks.append(self.submit_ballot(
                        client,
                        poll['short_id'],
                        rankings,
                        f"voter-{voter_id}"
                    ))
                
                # Add one result check per wave
                tasks.append(self.get_results(client, poll['short_id']))
                
                wave_results = await asyncio.gather(*tasks)
                
                for status, duration, error in wave_results:
                    result.response_times.append(duration)
                    if status == 200:
                        result.successful += 1
                    else:
                        result.failed += 1
                        error_key = error or f"HTTP {status}"
                        result.errors[error_key] = result.errors.get(error_key, 0) + 1
                
                # Wait before next wave
                if wave < waves - 1:
                    await asyncio.sleep(wave_delay)
        
        result.duration = time.time() - start
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    async def test_different_poll_configurations(self) -> TestResult:
        """Test with different poll settings"""
        
        print(f"\n{'='*60}")
        print(f"TEST: Different Poll Configurations")
        print(f"{'='*60}")
        
        configs = [
            ("Small poll (3 candidates)", 3, 15),
            ("Medium poll (5 candidates)", 5, 15),
            ("Large poll (10 candidates)", 10, 15),
        ]
        
        total_requests = sum(voters for _, _, voters in configs)
        result = TestResult(
            scenario_name="different_configurations",
            total_requests=total_requests * 2,  # ballots + result checks
            successful=0,
            failed=0
        )
        
        start = time.time()
        
        for config_name, num_candidates, num_voters in configs:
            print(f"\n  {config_name}...")
            
            poll = await self.create_test_poll(
                config_name,
                num_candidates=num_candidates
            )
            
            candidate_ids = [c['id'] for c in poll['candidates']]
            
            async with httpx.AsyncClient() as client:
                # Submit ballots
                tasks = []
                for i in range(num_voters):
                    shuffled = candidate_ids.copy()
                    random.shuffle(shuffled)
                    num_ranked = random.randint(1, num_candidates)  # Partial rankings
                    rankings = [
                        {"candidate_id": cid, "rank": rank + 1}
                        for rank, cid in enumerate(shuffled[:num_ranked])
                    ]
                    tasks.append(self.submit_ballot(
                        client,
                        poll['short_id'],
                        rankings,
                        f"voter-{i}"
                    ))
                
                # Add result checks
                tasks.extend([
                    self.get_results(client, poll['short_id'])
                    for _ in range(num_voters)
                ])
                
                config_results = await asyncio.gather(*tasks)
                
                for status, duration, error in config_results:
                    result.response_times.append(duration)
                    if status == 200:
                        result.successful += 1
                    else:
                        result.failed += 1
                        error_key = error or f"HTTP {status}"
                        result.errors[error_key] = result.errors.get(error_key, 0) + 1
        
        result.duration = time.time() - start
        
        self._print_result(result)
        self.results.append(result)
        return result
    
    # ============================================================
    # REPORTING
    # ============================================================
    
    def _print_result(self, result: TestResult):
        """Print results of a test"""
        print(f"\n{'-'*60}")
        print(f"RESULTS: {result.scenario_name}")
        print(f"{'-'*60}")
        print(f"Total Requests:  {result.total_requests}")
        print(f"Successful:      {result.successful} ({result.success_rate:.1f}%)")
        print(f"Failed:          {result.failed}")
        print(f"Duration:        {result.duration:.2f}s")
        
        if result.response_times:
            print(f"\nResponse Times:")
            print(f"  Min:     {min(result.response_times):.3f}s")
            print(f"  P50:     {result.p50:.3f}s")
            print(f"  P95:     {result.p95:.3f}s")
            print(f"  P99:     {result.p99:.3f}s")
            print(f"  Max:     {max(result.response_times):.3f}s")
            print(f"  Average: {sum(result.response_times)/len(result.response_times):.3f}s")
        
        if result.errors:
            print(f"\nErrors:")
            for error, count in sorted(result.errors.items(), key=lambda x: -x[1]):
                print(f"  {error}: {count}")
        
        # Verdict
        if result.success_rate == 100:
            print(f"\n✅ PASSED")
        elif result.success_rate >= 95:
            print(f"\n⚠️  MOSTLY PASSED ({result.success_rate:.1f}%)")
        else:
            print(f"\n❌ FAILED ({result.success_rate:.1f}%)")
    
    def print_summary(self):
        """Print summary of all tests"""
        print(f"\n{'='*60}")
        print(f"OVERALL SUMMARY")
        print(f"{'='*60}")
        
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r.success_rate == 100)
        partial = sum(1 for r in self.results if 95 <= r.success_rate < 100)
        failed = sum(1 for r in self.results if r.success_rate < 95)
        
        print(f"\nTests Run: {total_tests}")
        print(f"  ✅ Passed:        {passed}")
        print(f"  ⚠️  Mostly Passed: {partial}")
        print(f"  ❌ Failed:        {failed}")
        
        print(f"\nPer-Test Results:")
        for result in self.results:
            status = "✅" if result.success_rate == 100 else "⚠️ " if result.success_rate >= 95 else "❌"
            print(f"  {status} {result.scenario_name}: {result.success_rate:.1f}% "
                  f"({result.successful}/{result.total_requests})")
        
        # Overall verdict
        print(f"\n{'='*60}")
        if failed == 0:
            print("✅ ALL TESTS PASSED")
            print("Your system handles concurrency correctly!")
        elif passed + partial == total_tests:
            print("⚠️  MOSTLY PASSED")
            print("Minor issues detected. Review partial failures.")
        else:
            print("❌ SOME TESTS FAILED")
            print("Concurrency issues detected. Review failures above.")
        print(f"{'='*60}\n")


async def main():
    parser = argparse.ArgumentParser(description="Voting System Concurrency Test Suite")
    parser.add_argument("base_url", help="Base URL of your application (e.g., https://myapp.com)")
    parser.add_argument(
        "--scenario",
        choices=["all", "ballots", "results", "storm", "staggered", "configs"],
        default="all",
        help="Which test scenario to run"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"VOTING SYSTEM CONCURRENCY TEST SUITE")
    print(f"{'='*60}")
    print(f"Target: {args.base_url}")
    print(f"Scenario: {args.scenario}")
    print(f"Time: {datetime.now()}")
    print(f"{'='*60}\n")
    
    tester = VotingSystemTester(args.base_url)
    
    try:
        # Run selected scenarios
        if args.scenario in ["all", "ballots"]:
            await tester.test_concurrent_ballot_submission(num_voters=50)
        
        if args.scenario in ["all", "results"]:
            await tester.test_concurrent_result_viewing(num_voters=20, num_viewers=50)
        
        if args.scenario in ["all", "storm"]:
            await tester.test_ballot_storm_with_results(num_voters=30, num_result_checks=20)
        
        if args.scenario in ["all", "staggered"]:
            await tester.test_staggered_load(waves=5, voters_per_wave=10)
        
        if args.scenario in ["all", "configs"]:
            await tester.test_different_poll_configurations()
        
        # Print summary
        tester.print_summary()
        
        # Cleanup (optional)
        print(f"\nTest polls created: {len(tester.test_polls)}")
        print("You may want to clean these up manually if needed.")
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        tester.print_summary()
    except Exception as e:
        print(f"\n\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())