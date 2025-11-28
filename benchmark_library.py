"""
SurrealDB Benchmark using surreal_basics library.

Compares connection strategies (HTTP vs WebSocket) and execution modes (Sync vs Async)
measuring performance and error rates for CRUD operations.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any

import surreal_basics
from surreal_basics import (
    init,
    repo_create,
    repo_create_sync,
    repo_delete,
    repo_delete_sync,
    repo_query,
    repo_query_sync,
    repo_select,
    repo_select_sync,
    repo_upsert,
    repo_upsert_sync,
    reset_connections,
)


@dataclass
class BenchmarkResult:
    """Stores results for a single benchmark operation."""

    operation: str
    protocol: str
    mode: str
    total_time: float
    operations_count: int
    errors_count: int
    ops_per_second: float = field(init=False)
    error_rate: float = field(init=False)

    def __post_init__(self):
        self.ops_per_second = (
            self.operations_count / self.total_time if self.total_time > 0 else 0
        )
        self.error_rate = (
            (self.errors_count / self.operations_count) * 100
            if self.operations_count > 0
            else 0
        )


@dataclass
class BenchmarkConfig:
    """Configuration for the benchmark."""

    host: str = "localhost"
    port: int = 8018
    namespace: str = "teste"
    user: str = "root"
    password: str = "root"
    operations_count: int = 1000
    table_name: str = "benchmark_lib"
    async_batch_size: int = 20


class LibraryBenchmark:
    """Benchmark runner using surreal_basics library."""

    def __init__(self, config: BenchmarkConfig):
        self.config = config

    def _generate_test_data(self, count: int) -> list[dict[str, Any]]:
        """Generate test records for benchmarking."""
        return [
            {
                "name": f"User_{i}",
                "email": f"user_{i}@test.com",
                "age": random.randint(18, 80),
                "active": random.choice([True, False]),
                "score": round(random.uniform(0, 100), 2),
            }
            for i in range(count)
        ]

    def _extract_id(self, result: Any) -> str | None:
        """Extract ID from create result."""
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get("id")
        elif result and isinstance(result, dict):
            return result.get("id")
        return None

    def run_sync_benchmark(self, protocol: str, database: str) -> list[BenchmarkResult]:
        """Run synchronous benchmark using surreal_basics."""
        # Configure library
        mode = "ws" if protocol == "WS" else "http"
        init(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            namespace=self.config.namespace,
            database=database,
            mode=mode,
        )

        results = []
        test_data = self._generate_test_data(self.config.operations_count)

        # Clean up before starting
        repo_query_sync(f"DELETE {self.config.table_name}")

        # CREATE benchmark
        created_ids = []
        errors = 0
        start = time.perf_counter()
        for data in test_data:
            try:
                record = repo_create_sync(self.config.table_name, data)
                record_id = self._extract_id(record)
                if record_id:
                    created_ids.append(record_id)
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("CREATE", protocol, "Sync", elapsed, len(test_data), errors)
        )

        # SELECT benchmark (by individual ID)
        errors = 0
        start = time.perf_counter()
        for record_id in created_ids[: self.config.operations_count]:
            try:
                repo_select_sync(record_id)
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("SELECT", protocol, "Sync", elapsed, len(created_ids), errors)
        )

        # UPDATE benchmark (using query since repo_update needs table+id)
        errors = 0
        start = time.perf_counter()
        for i, record_id in enumerate(created_ids[: self.config.operations_count]):
            try:
                repo_query_sync(
                    f"UPDATE {record_id} MERGE $data",
                    {"data": {"name": f"Updated_User_{i}", "score": 99.9}},
                )
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("UPDATE", protocol, "Sync", elapsed, len(created_ids), errors)
        )

        # UPSERT benchmark
        errors = 0
        start = time.perf_counter()
        for i in range(self.config.operations_count):
            try:
                repo_upsert_sync(
                    self.config.table_name,
                    f"{self.config.table_name}:upsert_{i}",
                    {"name": f"Upsert_User_{i}", "email": f"upsert_{i}@test.com", "age": 30},
                )
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("UPSERT", protocol, "Sync", elapsed, self.config.operations_count, errors)
        )

        # DELETE benchmark
        errors = 0
        start = time.perf_counter()
        for record_id in created_ids:
            try:
                repo_delete_sync(record_id)
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("DELETE", protocol, "Sync", elapsed, len(created_ids), errors)
        )

        # Final cleanup
        repo_query_sync(f"DELETE {self.config.table_name}")

        # Reset connections for next test
        reset_connections()

        return results

    async def run_async_benchmark(self, protocol: str, database: str) -> list[BenchmarkResult]:
        """Run asynchronous benchmark using surreal_basics."""
        # Configure library
        mode = "ws" if protocol == "WS" else "http"
        init(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            namespace=self.config.namespace,
            database=database,
            mode=mode,
        )

        results = []
        test_data = self._generate_test_data(self.config.operations_count)
        batch_size = self.config.async_batch_size

        # Clean up before starting
        await repo_query(f"DELETE {self.config.table_name}")

        # CREATE benchmark (sequential to collect IDs)
        created_ids = []
        errors = 0
        start = time.perf_counter()
        for data in test_data:
            try:
                record = await repo_create(self.config.table_name, data)
                record_id = self._extract_id(record)
                if record_id:
                    created_ids.append(record_id)
            except Exception:
                errors += 1
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("CREATE", protocol, "Async", elapsed, len(test_data), errors)
        )

        # SELECT benchmark (concurrent batches)
        start = time.perf_counter()
        errors = 0
        for i in range(0, len(created_ids), batch_size):
            batch_ids = created_ids[i : i + batch_size]
            tasks = [repo_select(rid) for rid in batch_ids]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            errors += sum(1 for r in batch_results if isinstance(r, Exception))
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("SELECT", protocol, "Async", elapsed, len(created_ids), errors)
        )

        # UPDATE benchmark (concurrent batches)
        start = time.perf_counter()
        errors = 0
        for i in range(0, len(created_ids), batch_size):
            batch_ids = created_ids[i : i + batch_size]
            tasks = [
                repo_query(
                    f"UPDATE {rid} MERGE $data",
                    {"data": {"name": f"Updated_User_{j}", "score": 99.9}},
                )
                for j, rid in enumerate(batch_ids, start=i)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            errors += sum(1 for r in batch_results if isinstance(r, Exception))
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("UPDATE", protocol, "Async", elapsed, len(created_ids), errors)
        )

        # UPSERT benchmark (concurrent batches)
        start = time.perf_counter()
        errors = 0
        for i in range(0, self.config.operations_count, batch_size):
            batch_range = range(i, min(i + batch_size, self.config.operations_count))
            tasks = [
                repo_upsert(
                    self.config.table_name,
                    f"{self.config.table_name}:upsert_{j}",
                    {"name": f"Upsert_User_{j}", "email": f"upsert_{j}@test.com", "age": 30},
                )
                for j in batch_range
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            errors += sum(1 for r in batch_results if isinstance(r, Exception))
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("UPSERT", protocol, "Async", elapsed, self.config.operations_count, errors)
        )

        # DELETE benchmark (concurrent batches)
        start = time.perf_counter()
        errors = 0
        for i in range(0, len(created_ids), batch_size):
            batch_ids = created_ids[i : i + batch_size]
            tasks = [repo_delete(rid) for rid in batch_ids]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            errors += sum(1 for r in batch_results if isinstance(r, Exception))
        elapsed = time.perf_counter() - start
        results.append(
            BenchmarkResult("DELETE", protocol, "Async", elapsed, len(created_ids), errors)
        )

        # Final cleanup
        await repo_query(f"DELETE {self.config.table_name}")

        # Reset connections for next test
        reset_connections()

        return results


def print_scenario_results(results: list[BenchmarkResult], protocol: str, mode: str, database: str):
    """Print results for a single scenario."""
    print(f"\nProtocol: {protocol} | Mode: {mode} | Database: {database}")
    print("-" * 70)
    print(f"{'Operation':<12} {'Count':>8} {'Time(s)':>10} {'Ops/s':>12} {'Errors':>8} {'Error Rate':>12}")
    print("-" * 70)

    for r in results:
        print(
            f"{r.operation:<12} {r.operations_count:>8} {r.total_time:>10.3f} "
            f"{r.ops_per_second:>12.2f} {r.errors_count:>8} {r.error_rate:>11.2f}%"
        )
    print("-" * 70)


def print_summary(all_results: dict[str, list[BenchmarkResult]]):
    """Print comparative summary of all scenarios."""
    print("\n" + "=" * 80)
    print(" " * 25 + "SUMMARY COMPARISON")
    print("=" * 80)

    operations = ["CREATE", "SELECT", "UPDATE", "UPSERT", "DELETE"]
    scenarios = list(all_results.keys())

    # Header
    header = f"{'Operation':<12}"
    for scenario in scenarios:
        header += f"{scenario:>16}"
    print(header)
    print("-" * (12 + 16 * len(scenarios)))

    # Data rows
    for op in operations:
        row = f"{op:<12}"
        for scenario in scenarios:
            results = all_results[scenario]
            op_result = next((r for r in results if r.operation == op), None)
            if op_result:
                row += f"{op_result.ops_per_second:>16.2f}"
            else:
                row += f"{'N/A':>16}"
        print(row)

    print("-" * (12 + 16 * len(scenarios)))
    print("Values shown are operations per second (higher is better)")

    # Error summary
    print("\n" + "-" * 80)
    print("ERROR RATES")
    print("-" * 80)
    header = f"{'Operation':<12}"
    for scenario in scenarios:
        header += f"{scenario:>16}"
    print(header)
    print("-" * (12 + 16 * len(scenarios)))

    for op in operations:
        row = f"{op:<12}"
        for scenario in scenarios:
            results = all_results[scenario]
            op_result = next((r for r in results if r.operation == op), None)
            if op_result:
                row += f"{op_result.error_rate:>15.2f}%"
            else:
                row += f"{'N/A':>16}"
        print(row)


def main():
    """Run all benchmark scenarios."""
    print("=" * 80)
    print(" " * 15 + "SurrealDB Benchmark (using surreal_basics library)")
    print("=" * 80)

    config = BenchmarkConfig()
    benchmark = LibraryBenchmark(config)

    print("\nConfiguration:")
    print(f"  Host: {config.host}:{config.port}")
    print(f"  Namespace: {config.namespace}")
    print(f"  Operations per test: {config.operations_count}")
    print(f"  Async batch size: {config.async_batch_size}")
    print(f"  Table: {config.table_name}")

    all_results: dict[str, list[BenchmarkResult]] = {}

    # Scenario 1: HTTP Sync
    print("\n[1/4] Running HTTP Sync benchmark...")
    try:
        results = benchmark.run_sync_benchmark("HTTP", "http")
        all_results["HTTP Sync"] = results
        print_scenario_results(results, "HTTP", "Sync", "http")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Scenario 2: HTTP Async
    print("\n[2/4] Running HTTP Async benchmark...")
    try:
        results = asyncio.run(benchmark.run_async_benchmark("HTTP", "http"))
        all_results["HTTP Async"] = results
        print_scenario_results(results, "HTTP", "Async", "http")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Scenario 3: WebSocket Sync
    print("\n[3/4] Running WebSocket Sync benchmark...")
    try:
        results = benchmark.run_sync_benchmark("WS", "ws")
        all_results["WS Sync"] = results
        print_scenario_results(results, "WebSocket", "Sync", "ws")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Scenario 4: WebSocket Async
    print("\n[4/4] Running WebSocket Async benchmark...")
    try:
        results = asyncio.run(benchmark.run_async_benchmark("WS", "ws"))
        all_results["WS Async"] = results
        print_scenario_results(results, "WebSocket", "Async", "ws")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Print summary
    if all_results:
        print_summary(all_results)

    print("\n" + "=" * 80)
    print(" " * 30 + "Benchmark Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
