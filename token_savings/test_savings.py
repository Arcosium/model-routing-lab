"""Boundary and evidence integrity tests, independent of model quality."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import compact
from bridge import SavingsBroker


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'repo';self.root.mkdir()
        self.file=self.root/'sample.py';self.file.write_text('unit=seconds\nvalue=45\nnegated=false\n')
        self.raw={'analysis':json.dumps({'answer':{'value':45},'evidence':[
            {'claim':'value','path':str(self.file),'start_line':2,'end_line':2}]}),
            'sources':[{'path':str(self.file),'sha256':hashlib.sha256(self.file.read_bytes()).hexdigest()}]}
        def read_safe(name):
            p=Path(name);return p,p.read_text(),hashlib.sha256(p.read_bytes()).hexdigest()
        self.patch=patch.object(compact.api,'read_safe',side_effect=read_safe);self.patch.start()
    def tearDown(self):
        self.patch.stop();self.temp.cleanup()
    def test_context_comes_from_source_not_draft(self):
        c=compact.make_capsule(self.root,self.raw,'documents')
        self.assertEqual(c['evidence'][0]['text'],'1: unit=seconds\n2: value=45\n3: negated=false')
    def test_changed_source_rejected(self):
        self.file.write_text('value=99\n')
        c=compact.make_capsule(self.root,self.raw,'documents')
        self.assertEqual(c['evidence'],[]);self.assertTrue(c['gaps'])
    def test_scope_escape_rejected(self):
        outside=self.root.parent/'outside.py';outside.write_text('private\n')
        data=json.loads(self.raw['analysis']);data['evidence'][0]['path']=str(outside)
        self.raw['analysis']=json.dumps(data)
        self.raw['sources']=[{'path':str(outside),'sha256':hashlib.sha256(outside.read_bytes()).hexdigest()}]
        self.assertFalse(compact.make_capsule(self.root,self.raw,'documents')['evidence'])
    def test_symlink_escape_rejected(self):
        outside=self.root.parent/'outside.py';outside.write_text('private\n')
        link=self.root/'linked.py';link.symlink_to(outside)
        data=json.loads(self.raw['analysis']);data['evidence'][0]['path']=str(link)
        self.raw['analysis']=json.dumps(data)
        self.assertFalse(compact.make_capsule(self.root,self.raw,'documents')['evidence'])
    def test_oversize_draft_does_not_bypass_budget(self):
        data=json.loads(self.raw['analysis']);data['answer']={'large':'x'*10000};self.raw['analysis']=json.dumps(data)
        c=compact.make_capsule(self.root,self.raw,'documents',max_chars=800)
        self.assertLessEqual(len(compact.compact_json(c)),800)
    def test_missing_json_is_error(self):
        with self.assertRaises(ValueError):compact.parse_object('No findings')
    def test_submit_reconstructs_quote(self):
        b=SavingsBroker(self.root,self.root.parent/'record')
        b.record.mkdir()
        b.tool_submit_answer({'value':45},[{'claim':'value','path':'sample.py','start_line':2,'end_line':2,'quote':'forged'}])
        submission=json.loads((b.record/'submission.json').read_text())
        self.assertEqual(submission['evidence'][0]['quote'],'value=45')
    def test_distinct_line_ranges_in_one_call(self):
        b=SavingsBroker(self.root,self.root.parent/'record')
        spans=[{'path':'sample.py','start_line':i,'end_line':i} for i in [1,3]]
        results=b.tool_read_evidence(spans)
        self.assertEqual([x['start_line'] for x in results],[1,3])

if __name__=='__main__':unittest.main()
