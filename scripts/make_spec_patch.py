"""Versioned actual-K and seeded multi-query sampler correction; native target/EOS retained."""
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
replace('''                for idx, sgm in enumerate(seq_group_metadata_list)
                if sgm.sampling_params.seed is not None
''', '''                for idx, original_idx in enumerate(spec_indices)
                for sgm in [seq_group_metadata_list[original_idx]]
                if sgm.sampling_params.seed is not None
''')
modified+='''\n\n# DriveServe actual-K hook; native verifier and engine output processors retained.\nimport os as _driveserve_os\n_driveserve_adaptive = _driveserve_os.environ.get("DRIVESERVE_SPEC_MODE") == "adaptive"\n_driveserve_spec_enabled = (_driveserve_adaptive\n                            or bool(_driveserve_os.environ.get("DRIVESERVE_TRACE_DIR")))\nif _driveserve_spec_enabled:\n    from driveserve.spec_control import (prepare_step as _driveserve_prepare_step,\n        observe_verification as _driveserve_observe_verification)\n'''
files=[(name,original,modified)]
name='vllm/model_executor/layers/sampler.py'
original=(root/'third_party'/('vllm-'+sha)/name).read_text()
# Patch only PyTorch categorical sampling; FlashInfer is explicitly off.
start=original.index('def _multinomial(')
end=original.index('def _top_k_top_p_multinomial_with_flashinfer',start)
part=original[start:end]
old='            stride = len(seq_ids) * num_samples'
assert part.count(old)==1
part=part.replace(old,"""            # MQA verifies multiple query tokens per sequence. Initializing
            # only len(seq_ids) leaves random noise rows uninitialized.
            stride = len(seq_group.sample_indices) * num_samples""")
part=part.replace('            sample_idx += stride\n', '            sample_idx += stride\n        assert sample_idx == q.shape[0], "seeded sampler row coverage mismatch"\n')
modified=original[:start]+part+original[end:]
files.append((name,original,modified))
patch=''.join(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/'+n,tofile='b/'+n)) for n,a,b in files)
(root/'patches/vllm-v0.8.5-spec.patch').write_text(patch)
(root/'patches/vllm-v0.8.5-spec.json').write_text(json.dumps({'vllm_commit':sha,'version':'0.8.5','patch':'vllm-v0.8.5-spec.patch','files':[{'path':n,'upstream_sha256':hashlib.sha256(a.encode()).hexdigest(),'patched_sha256':hashlib.sha256(b.encode()).hexdigest()} for n,a,b in files]},indent=2)+'\n')
