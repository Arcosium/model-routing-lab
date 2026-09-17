"""Identical scoped tools for two subscription clients and the installed Qwen adapter."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import sys
import time

from mcp.server.fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
sys.path.insert(0, '/home/arcosium/projects/exploration-bench')
from broker import Broker


class ComparisonBroker(Broker):
    def __init__(self, root, record):
        super().__init__(root, record)
        self.task = json.loads((self.record / 'task.json').read_text())
        self.delegations = 0

    def tool_delegate_task(self):
        if self.delegations:
            raise ValueError('Only one local delegation is allowed; verify and finish directly')
        self.delegations += 1
        sys.path.insert(0, '/home/arcosium/projects/claude-cooperation')
        import local_qwen as api
        original_state = api.STATE
        # Retain the installed shared inference lock, isolate all audit/cache artifacts.
        @contextlib.contextmanager
        def shared_slot():
            start = time.monotonic()
            with (original_state / 'qwen.lock').open('a') as f:
                while True:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() - start > api.CONFIG['queue_timeout_seconds']:
                            raise TimeoutError('Existing local worker is busy')
                        time.sleep(.1)
                yield
        api.STATE = self.record / 'local-state'
        api.STATE.mkdir(mode=0o700)
        api.CONFIG = dict(api.CONFIG, cache_seconds=0)
        api.local_slot = shared_slot
        question = self.task['question']
        if self.task['kind'] == 'documents':
            result = api.analyze_files(question, [str(self.root / x) for x in self.task['source_files']], 1600)
        else:
            result = api.explore_repository(question, str(self.root), 10)
        (self.record / 'local-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def serve():
    b = ComparisonBroker(os.environ['ROUTING_LAB_WORKSPACE'], os.environ['ROUTING_LAB_RECORD'])
    server = FastMCP('lab')

    @server.tool()
    def list_files(glob: str = '*') -> str:
        """List visible task source files and sizes, optionally filtered by glob."""
        return b.invoke('list_files', dict(glob=glob))

    @server.tool()
    def search(query: str, glob: str = '*', limit: int = 20) -> str:
        """Search literal source text; return exact file paths and line numbers."""
        return b.invoke('search', dict(query=query, glob=glob, limit=limit))

    @server.tool()
    def read_files(paths: list[str], start_line: int = 1, max_lines: int = 120) -> str:
        """Read up to six files with exact line numbers, 160 lines/file and 14000 chars/call."""
        return b.invoke('read_files', dict(paths=paths, start_line=start_line, max_lines=max_lines))

    @server.tool()
    def submit_answer(answer: dict, evidence: list[dict], uncertainty: str = '') -> str:
        """Submit final structured answer and at most 12 citations (claim/path/start_line/end_line/quote)."""
        return b.invoke('submit_answer', dict(answer=answer, evidence=evidence, uncertainty=uncertainty))

    if os.environ['ROUTING_LAB_ARM'] == 'mixed':
        @server.tool()
        def delegate_task() -> str:
            """Delegate this exact task once to installed local Qwen; inspect evidence before acceptance.

            Calls production analyze_files for documents or explore_repository for source.
            The task question and source inputs are fixed, identical across clients.
            Local inference can take up to five minutes. Do not duplicate or retry it.
            """
            return b.invoke('delegate_task', {})
    server.run(transport='stdio')


if __name__ == '__main__':
    serve()
