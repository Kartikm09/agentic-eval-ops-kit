"""Synthetic acceptance tests: real SQLite, processes and concurrent connections."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from agentic_eval_ops.workflow import Workflow, compare_traces


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'workflow.db'
        self.now = 1000.0
        self.engine = Workflow(self.db, 'alpha', clock=lambda: self.now)
        self.engine.put_memory('policy', 1, 'draft response', 'synthetic://alpha/policy-v1')

    def request(self, key='request-1', approval=True):
        return self.engine.request(key, 'case-7', 'policy', 1, requires_approval=approval, timeout=100)

    def proposed(self, approval=True):
        job = self.request(approval=approval)
        for _ in range(4):
            self.engine.advance(job)
        return job

    def complete(self, job):
        for _ in range(10):
            report = self.engine.advance(job)
            if report['state'] in ('completed', 'failed', 'awaiting_approval'):
                return report
        self.fail('workflow did not reach a terminal or approval state')

    def test_request_replay_and_conflicting_duplicate(self):
        job = self.request()
        self.assertEqual(job, self.request())
        with self.assertRaises(ValueError):
            self.engine.request('request-1', 'different-case', 'policy', 1)
        self.assertEqual(self.engine.report(job)['state'], 'requested')

    def test_exact_action_approval_and_single_effect(self):
        job = self.proposed()
        report = self.engine.report(job)
        self.assertEqual(report['state'], 'awaiting_approval')
        self.assertEqual(report['effects'], [])
        with self.assertRaises(PermissionError):
            self.engine.approve(job, 'wrong-digest', expires_at=1050)
        self.engine.approve(job, report['action_digest'], expires_at=1050)
        self.assertEqual(self.complete(job)['state'], 'completed')
        self.complete(job)
        result = self.engine.report(job)
        self.assertEqual(len(result['effects']), 1)
        self.assertEqual(result['effects'][0]['action_digest'], report['action_digest'])
        self.assertIsNone(result['token_usage'])
        self.assertIsNone(result['cost'])
        self.assertTrue(all(row['latency_ms'] >= 0 for row in result['trace']))

    def test_expired_approval_cannot_execute_and_can_be_renewed(self):
        job = self.proposed()
        digest = self.engine.report(job)['action_digest']
        self.engine.approve(job, digest, expires_at=1001)
        self.now = 1002
        self.assertEqual(self.engine.advance(job)['state'], 'awaiting_approval')
        self.assertEqual(self.engine.report(job)['effects'], [])
        self.engine.approve(job, digest, expires_at=1090)
        self.assertEqual(self.complete(job)['state'], 'completed')

    def test_tenant_context_and_job_access_are_separate(self):
        other = Workflow(self.db, 'beta', clock=lambda: self.now)
        other.put_memory('policy', 1, 'private beta value', 'synthetic://beta/policy-v1')
        job = self.request(approval=False)
        with self.assertRaises(PermissionError):
            other.report(job)
        with self.assertRaises(PermissionError):
            self.engine.get_memory('policy', 1, tenant='beta')
        done = self.complete(job)
        self.assertEqual(done['state'], 'completed')
        self.assertIn('draft response', done['action']['body'])
        self.assertNotIn('private beta value', json.dumps(done))
        self.assertEqual(done['action']['source'], 'synthetic://alpha/policy-v1')

    def test_memory_versions_are_immutable(self):
        with self.assertRaises(ValueError):
            self.engine.put_memory('policy', 1, 'contradiction', 'synthetic://alpha/changed')
        self.engine.put_memory('policy', 2, 'updated', 'synthetic://alpha/policy-v2')
        job = self.request(approval=False)
        self.assertIn('draft response', self.complete(job)['action']['body'])

    def test_malformed_tool_output_has_bounded_retries(self):
        job = self.request()
        self.engine.advance(job)
        for _ in range(3):
            result = self.engine.advance(job, tool_output={'body': 42})
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['attempts'], 3)
        self.assertEqual(result['effects'], [])

    def test_failure_does_not_poison_independent_job(self):
        bad = self.engine.request('bad', 'case-1', 'missing', 1)
        for _ in range(3):
            self.engine.advance(bad)
        self.assertEqual(self.engine.report(bad)['state'], 'failed')
        good = self.request(approval=False)
        self.assertEqual(self.complete(good)['state'], 'completed')

    def test_recoverable_failure_then_success_resets_attempts(self):
        job = self.engine.request('late', 'case-1', 'late', 1, requires_approval=False)
        self.engine.advance(job)
        self.engine.put_memory('late', 1, 'now available', 'synthetic://alpha/late')
        result = self.complete(job)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(len(result['effects']), 1)

    def test_committed_effect_completes_after_restart_beyond_deadline(self):
        job = self.request(approval=False)
        for _ in range(5):
            self.engine.advance(job)
        self.assertEqual(self.engine.report(job)['state'], 'executed')
        self.now = 1101
        restarted = Workflow(self.db, 'alpha', clock=lambda: self.now)
        result = restarted.advance(job)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(len(result['effects']), 1)
        self.assertIsNone(result['error'])

    def test_timeout_prevents_effect(self):
        job = self.request(approval=False)
        self.now = 1101
        result = self.complete(job)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error'], 'deadline exceeded')
        self.assertEqual(result['effects'], [])

    def test_termination_after_every_step_recovers_without_duplicate_effect(self):
        job = self.request(approval=False)
        code = ('import os,sys; from agentic_eval_ops.workflow import Workflow; '
                'w=Workflow(sys.argv[1], "alpha", clock=lambda:1000.0); '
                'w.advance(sys.argv[2]); os._exit(23)')
        for _ in range(7):
            process = subprocess.run([sys.executable, '-c', code, str(self.db), job], check=False)
            self.assertEqual(process.returncode, 23)
        fresh = Workflow(self.db, 'alpha', clock=lambda: self.now)
        self.assertEqual(fresh.report(job)['state'], 'completed')
        self.assertEqual(len(fresh.report(job)['effects']), 1)

    def test_controlled_concurrent_replays_are_idempotent(self):
        barrier = threading.Barrier(2)
        errors = []
        results = []
        def worker():
            try:
                w = Workflow(self.db, 'alpha', clock=lambda: self.now)
                barrier.wait(timeout=5)
                job = w.request('parallel', 'case-1', 'policy', 1, requires_approval=False)
                for _ in range(8):
                    w.advance(job)
                results.append(w.report(job))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['job_id'], results[1]['job_id'])
        self.assertEqual(len(results[0]['effects']), 1)

    def test_different_keys_produce_independent_jobs(self):
        a = self.request('a', approval=False)
        b = self.request('b', approval=False)
        self.assertNotEqual(a, b)
        self.assertEqual(self.complete(a)['state'], 'completed')
        self.assertEqual(self.complete(b)['state'], 'completed')

    def test_trace_comparison_reports_actual_transition_differences(self):
        a = self.request('a', approval=False)
        b = self.request('b', approval=True)
        ra, rb = self.complete(a), self.complete(b)
        result = compare_traces(ra, rb)
        self.assertFalse(result['same_transitions'])
        self.assertGreater(result['left_latency_ms'], 0)
        self.assertIsNone(result['token_delta'])

    def test_invalid_schema_does_not_create_job(self):
        for version in (True, 0, '1'):
            with self.assertRaises(ValueError):
                self.engine.request('bad', 'case-1', 'policy', version)
        with self.assertRaises(ValueError):
            self.engine.request('', 'case-1', 'policy', 1)
        with self.assertRaises(ValueError):
            self.engine.request('bad', 'case-1', 'policy', 1, timeout=float('nan'))

if __name__ == '__main__':
    unittest.main()
