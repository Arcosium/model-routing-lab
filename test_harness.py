import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from lab import STATE, extract_usage
from benchmarks import create, grade


class UsageParsing(unittest.TestCase):
    def test_codex_cache_is_a_subset_of_input(self):
        event={"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":800,"output_tokens":40,"reasoning_output_tokens":10}}
        actual=extract_usage('codex',json.dumps(event))
        self.assertEqual(actual['usage']['input_tokens'],1000)
        self.assertFalse(actual['is_error'])

    def test_claude_error_is_not_a_success(self):
        event={"type":"result","is_error":True,"result":"Limit reached","usage":{},"modelUsage":{}}
        self.assertTrue(extract_usage('claude',json.dumps(event))['is_error'])

    def test_missing_completion_is_an_error(self):
        self.assertTrue(extract_usage('codex','{"type":"turn.started"}')['is_error'])


class FilesystemBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=STATE)
        self.root=Path(self.temp.name)
        os.environ.update({'ROUTING_LAB_WORKSPACE':str(self.root),'ROUTING_LAB_RECORD':str(self.root/'records'),
          'ROUTING_LAB_PROVIDER':'codex','ROUTING_LAB_ARM':'frontier','ROUTING_LAB_ROLE':'main','ROUTING_LAB_CALL_ID':'unit'})
        import bridge
        self.bridge=importlib.reload(bridge)

    def tearDown(self):self.temp.cleanup()

    def test_parent_traversal_refused(self):
        with self.assertRaises(ValueError):self.bridge.path_for('../outside')

    def test_symlink_escape_refused(self):
        (self.root/'link').symlink_to('/etc/hosts')
        with self.assertRaises(ValueError):self.bridge.path_for('link')

    def test_hidden_files_refused(self):
        with self.assertRaises(ValueError):self.bridge.path_for('.env')

    def test_public_tests_are_immutable(self):
        with self.assertRaises(ValueError):self.bridge.path_for('tests/test_public.py',writing=True)

    def test_requirements_are_immutable(self):
        with self.assertRaises(ValueError):self.bridge.path_for('TASK.md',writing=True)

    def test_explorer_cannot_write(self):
        self.bridge.ROLE='explore'
        with self.assertRaises(ValueError):self.bridge.path_for('answer.json',writing=True)


class GraderChecks(unittest.TestCase):
    def test_incident_exact_answer_passes_all(self):
        with tempfile.TemporaryDirectory(dir=STATE) as d:
            root=Path(d);create(root,'incident',1)
            a=dict(affected_service='quota-worker',release='r41',first_bad_request='req-0781',
              header_seconds=120,applied_delay_ms=120,correct_delay_ms=120000,
              mitigation='retry_after_unit=seconds',distractor_service='report-exporter',
              rollback_required=False,evidence_events=['E017','E023','E024','E088'])
            (root/'answer.json').write_text(json.dumps(a))
            self.assertEqual(grade(root,'incident',1)['score'],1)
            a['correct_delay_ms']=120;(root/'answer.json').write_text(json.dumps(a))
            self.assertFalse(grade(root,'incident',1)['fully_correct'])

    def test_fixture_cache_contains_detectable_bugs(self):
        with tempfile.TemporaryDirectory(dir=STATE) as d:
            root=Path(d);create(root,'cache_fix',1)
            self.assertLess(grade(root,'cache_fix',1)['score'],1)


if __name__=='__main__':unittest.main()
