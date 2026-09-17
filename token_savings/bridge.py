"""Same compact read/submit tools for all experimental arms."""
import json
import os
from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP
sys.path.insert(0, '/home/arcosium/projects/exploration-bench')
from broker import Broker
from compact import prepare


class SavingsBroker(Broker):
    def tool_read_evidence(self, spans):
        if not isinstance(spans, list) or not 1 <= len(spans) <= 12:
            raise ValueError('Use 1-12 ranges')
        output = []
        for span in spans:
            path = self.path(span['path'])
            a, b = span['start_line'], span['end_line']
            lines = path.read_text().splitlines()
            if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(lines) or b-a >= 30:
                raise ValueError('Use valid ranges, at most 30 lines each')
            output.append({'path':span['path'],'start_line':a,'end_line':b,
                           'text':'\n'.join(f'{i}: {lines[i-1]}' for i in range(a,b+1))})
        if len(json.dumps(output)) > 14000:
            raise ValueError('Maximum 14000 characters')
        return output

    def tool_local_brief(self):
        if os.environ['ROUTING_LAB_ARM'] != 'tool':
            raise ValueError('This arm does not use on-demand delegation')
        task = json.loads((self.record/'task.json').read_text())
        return prepare(self.root, task, self.record)

    def tool_submit_answer(self, answer, evidence, uncertainty=''):
        if not isinstance(answer, dict) or not isinstance(evidence, list) or len(evidence)>24:
            raise ValueError('Object answer; at most 24 source references')
        resolved = []
        for e in evidence:
            path = self.path(e['path']); lines = path.read_text().splitlines()
            a, b = e['start_line'], e['end_line']
            if type(a) is not int or type(b) is not int or not 1<=a<=b<=len(lines) or b-a>=30:
                raise ValueError('Invalid evidence span')
            resolved.append({'claim':str(e['claim']), 'path':e['path'], 'start_line':a, 'end_line':b,
                             'quote':'\n'.join(lines[a-1:b])})
        (self.record/'submission.json').write_text(json.dumps(
            {'answer':answer,'evidence':resolved,'uncertainty':uncertainty},ensure_ascii=False,indent=2))
        self.finished = True
        return {'submitted':True}


def serve():
    b = SavingsBroker(os.environ['ROUTING_LAB_WORKSPACE'],os.environ['ROUTING_LAB_RECORD'])
    m = FastMCP('lab')
    @m.tool()
    def list_files(glob: str = '*') -> str:
        """List source paths and byte counts. Optional glob."""
        return b.invoke('list_files',dict(glob=glob))
    @m.tool()
    def search(query: str, glob: str = '*', limit: int = 20) -> str:
        """Literal source search, up to 30 results with line numbers."""
        return b.invoke('search',dict(query=query,glob=glob,limit=limit))
    @m.tool()
    def read_files(paths: list[str], start_line: int = 1, max_lines: int = 120) -> str:
        """Read 1-6 files with line numbers; <=160 lines/file, <=14000 chars total."""
        return b.invoke('read_files',dict(paths=paths,start_line=start_line,max_lines=max_lines))
    @m.tool()
    def read_evidence(spans: list[dict]) -> str:
        """Batch up to 12 different ranges: {path,start_line,end_line}, <=30 lines each."""
        return b.invoke('read_evidence',dict(spans=spans))
    @m.tool()
    def local_brief() -> str:
        """Use only in the on-demand arm, once: local findings plus authentic source excerpts."""
        return b.invoke('local_brief',{})
    @m.tool()
    def submit_answer(answer: dict, evidence: list[dict], uncertainty: str = '') -> str:
        """Finish with answer and <=24 {claim,path,start_line,end_line} citations. Quotes added automatically."""
        return b.invoke('submit_answer',dict(answer=answer,evidence=evidence,uncertainty=uncertainty))
    m.run(transport='stdio')

if __name__ == '__main__':
    serve()
