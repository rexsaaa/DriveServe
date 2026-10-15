"""Reject accidental partial/flexible final inference before any GPU/model startup."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE=[sys.executable,str(ROOT/'scripts/benchmark_speculation.py'),'--stage','S5','--mode','target',
      '--dataset',str(ROOT/'data/frozen-v1/test.jsonl'),'--split','test','--quality-only','--limit','256']

class FinalEvalGateTests(unittest.TestCase):
    def reject(self,args,expected):
        got=subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.assertNotEqual(got.returncode,0)
        self.assertIn(expected,got.stderr)
        self.assertNotIn('nvidia-smi',got.stderr)
        self.assertNotIn('experiments/runs',got.stdout)

    def test_final_requires_frozen_protocol(self):
        self.reject(BASE,'test requires S5 quality-only and a frozen final protocol')

    def test_wrong_split_cannot_silently_evaluate_zero_rows(self):
        cmd=BASE.copy();cmd[cmd.index('--dataset')+1]=str(ROOT/'data/frozen-v1/dev.jsonl')
        self.reject(cmd,'requested selection exceeds available split')

    def test_final_profile_cannot_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'protocol.json'
            path.write_text(json.dumps({'profiles':{'locked':{'configuration':{'mode':'fixed'}}}}))
            self.reject(BASE+['--final-protocol',str(path),'--final-profile','locked'],
                        'final invocation differs from frozen profile')
