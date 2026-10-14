"""Versioned narrow speculative patch; no target/rejection/EOS algorithm changes."""
import difflib,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
commit=json.loads((root/'configs/upstream.json').read_text())
sha='ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d'
name='vllm/spec_decode/spec_decode_worker.py'
original=(root/'third_party'/('vllm-'+sha)/name).read_text()
modified=original
def replace(old,new):
 global modified
 assert modified.count(old)==1
 modified=modified.replace(old,new)
replace('        num_lookahead_slots = execute_model_req.num_lookahead_slots\n',
        '        if _driveserve_spec_enabled:\n            execute_model_req = _driveserve_prepare_step(self, execute_model_req)\n        num_lookahead_slots = execute_model_req.num_lookahead_slots\n')
replace('        stage_times = (proposal_timer.elapsed_time_ms / num_lookahead_slots,\n',
        '        if _driveserve_spec_enabled:\n            _driveserve_observe_verification(self, execute_model_req, proposals,\n                                             accepted_token_ids)\n\n        stage_times = (proposal_timer.elapsed_time_ms / num_lookahead_slots,\n')
replace('            self._metrics.maybe_collect_rejsample_metrics(k))\n',
        '            None if _driveserve_adaptive else\n'
        '            self._metrics.maybe_collect_rejsample_metrics(k))\n')
modified+='''\n\n# DriveServe actual-K hook; native verifier and engine output processors retained.\nimport os as _driveserve_os\n_driveserve_adaptive = _driveserve_os.environ.get("DRIVESERVE_SPEC_MODE") == "adaptive"\n_driveserve_spec_enabled = (_driveserve_adaptive\n                            or bool(_driveserve_os.environ.get("DRIVESERVE_TRACE_DIR")))\nif _driveserve_spec_enabled:\n    from driveserve.spec_control import (prepare_step as _driveserve_prepare_step,\n        observe_verification as _driveserve_observe_verification)\n'''
patch=''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(root/'patches/vllm-v0.8.5-spec.patch').write_text(patch)
(root/'patches/vllm-v0.8.5-spec.json').write_text(json.dumps({'vllm_commit':sha,'version':'0.8.5','patch':'vllm-v0.8.5-spec.patch','files':[{'path':name,'upstream_sha256':hashlib.sha256(original.encode()).hexdigest(),'patched_sha256':hashlib.sha256(modified.encode()).hexdigest()}]},indent=2)+'\n')
