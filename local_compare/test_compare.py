import json
from pathlib import Path
import tempfile
import unittest

from bridge import ComparisonBroker
from run import usage


class Accounting(unittest.TestCase):
    def test_claude_includes_cache_creation_and_internal_model(self):
        value = usage('claude', {'model_usage': {
            'main': dict(inputTokens=10, cacheCreationInputTokens=20, cacheReadInputTokens=30, outputTokens=40),
            'internal': dict(inputTokens=5, outputTokens=7)}})
        self.assertEqual(value['total_tokens'], 112)
        self.assertEqual(value['cached_input_tokens'], 30)
        self.assertEqual(value['noncached_plus_output'], 82)

    def test_codex_cache_already_in_input_not_counted_twice(self):
        value = usage('codex', {'usage': dict(input_tokens=100, cached_input_tokens=80, output_tokens=15)})
        self.assertEqual(value['total_tokens'], 115)
        self.assertEqual(value['noncached_plus_output'], 35)

    def test_absent_usage_not_reported_as_measured_zero(self):
        self.assertFalse(usage('codex', {'usage': {}})['complete'])
        self.assertFalse(usage('claude', {'model_usage': {}})['complete'])


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / 'repo'; self.root.mkdir()
        self.record = base / 'record'; self.record.mkdir()
        (self.record / 'task.json').write_text(json.dumps(dict(kind='repository', question='test')))
        (self.root / 'source.py').write_text('VALUE = 7\n')
        (base / 'gold.json').write_text('{"answer":7}')
        self.broker = ComparisonBroker(self.root, self.record)

    def tearDown(self):
        self.temp.cleanup()

    def test_hidden_grader_and_absolute_paths_rejected(self):
        for name in ('../gold.json', str(self.root / 'source.py')):
            with self.assertRaises(ValueError): self.broker.path(name)

    def test_external_symlink_rejected(self):
        (self.root / 'escape.json').symlink_to(self.root.parent / 'gold.json')
        with self.assertRaises(ValueError): self.broker.path('escape.json')

    def test_second_delegation_rejected_before_model_call(self):
        self.broker.delegations = 1
        with self.assertRaises(ValueError): self.broker.tool_delegate_task()


if __name__ == '__main__':
    unittest.main()
