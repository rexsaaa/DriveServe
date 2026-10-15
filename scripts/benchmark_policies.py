"""Four-way actual-engine policy experiment and separate intrusive lifecycle checks."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driveserve.evidence import Run, atomic_json, file_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stage', choices=['S2','S3','S4','S5'], default='S2')
    p.add_argument('--variant', choices=['native', 'cache', 'scheduler', 'both'], required=True)
    p.add_argument('--overlay', type=Path, default=Path('/hy-tmp/driveserve/vllm-policies-v2'))
    p.add_argument('--model', type=Path, default=Path('/hy-tmp/driveserve/models/target'))
    p.add_argument('--cache-implementation', choices=['scan','heap'], default='scan')
    p.add_argument('--trace', action='store_true')
    p.add_argument('--suite', choices=['core', 'lifecycle'], default='core')
    p.add_argument('--repeat', type=int, default=0)
    p.add_argument('--max-seqs', type=int, choices=[2,4,8], default=4)
    p.add_argument('--graph', action='store_true')
    p.add_argument('--upstream', action='store_true', help='untouched pinned wheel B0; only native without trace')
    args = p.parse_args()
    if args.cache_implementation=='heap' and args.variant not in ('cache','both'):
        p.error('heap is only applicable to cache/both variants')
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root/'configs/s2-policies.json').read_text())
    if args.upstream and (args.variant!='native' or args.trace or args.suite!='core'):
        p.error('untouched upstream B0 requires native core without trace')
    config.update(stage=args.stage, cache_implementation=args.cache_implementation, max_num_seqs=args.max_seqs, eager=not args.graph,
                  upstream=args.upstream)
    if args.upstream:
        config['baseline_scope']='untouched pinned vLLM wheel, no DriveServe source patch'
    overlay = args.overlay.resolve()
    lock = json.loads((overlay/'overlay-manifest.json').read_text())
    if lock['patch_sha256'] != file_hash(root/'patches/vllm-v0.8.5-policies.patch'):
        raise ValueError('overlay patch differs')
    for f in lock['lock']['files']:
        if file_hash(overlay/f['path']) != f['patched_sha256']:
            raise ValueError('overlay file differs')
    provenance = json.loads((args.model/'driveserve-provenance.json').read_text())
    for f in provenance['files']:
        if file_hash(args.model/Path(f['path']).name) != f['sha256']:
            raise ValueError('model file differs')
    config.update(variant=args.variant, overlay=lock if not args.upstream else None, model=provenance,
                  trace=args.trace, suite=args.suite, repeat=args.repeat)
    run = Run(root, 'vllm-policy-'+args.suite, config, formal=True)
    print(run.path, flush=True)
    try:
        os.environ.update(VLLM_USE_V1='0', VLLM_ATTENTION_BACKEND='FLASH_ATTN',
            CUDA_VISIBLE_DEVICES='0', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
            DRIVESERVE_CACHE_IMPL=args.cache_implementation,
            DRIVESERVE_CACHE_POLICY='cold_hot' if args.variant in ('cache','both') else 'native',
            DRIVESERVE_LENGTH_AGING='1' if args.variant in ('scheduler','both') else '0',
            DRIVESERVE_HOT_REUSES=str(config['hot_reuses']), DRIVESERVE_HOT_TTL_S=str(config['hot_ttl_s']),
            DRIVESERVE_AGING_S=str(config['aging_s']),
            PYTHONPATH=os.pathsep.join(([str(overlay)] if not args.upstream else [])+[str(root)]))
        os.environ.pop('DRIVESERVE_NVTX', None)
        if args.trace:
            os.environ['DRIVESERVE_TRACE_DIR'] = str(run.path/'engine-trace')
        else:
            os.environ.pop('DRIVESERVE_TRACE_DIR', None)
        if not args.upstream:
            sys.path.insert(0, str(overlay))
        from vllm import EngineArgs, LLMEngine, SamplingParams
        from vllm.core import scheduler
        from driveserve.engine_policies import gpu_allocator, assert_allocator_invariants, ColdHotEvictor
        from driveserve.engine_trace import close_traces
        if args.upstream:
            import importlib.metadata
            wheel = Path(importlib.metadata.distribution('vllm').locate_file('vllm')).resolve()
            assert Path(scheduler.__file__).resolve() == wheel/'core/scheduler.py'
            for f in lock['lock']['files']:
                assert file_hash(wheel.parent/f['path']) == f['upstream_sha256']
        else:
            assert Path(scheduler.__file__).resolve() == overlay/'vllm/core/scheduler.py'
        engine = LLMEngine.from_engine_args(EngineArgs(model=str(args.model), dtype='half',
            max_model_len=config['max_model_len'], max_num_seqs=config['max_num_seqs'],
            max_num_batched_tokens=config['max_num_batched_tokens'],
            num_gpu_blocks_override=config['num_gpu_blocks_override'], block_size=16,
            gpu_memory_utilization=0.4, enable_prefix_caching=True, enforce_eager=config['eager'],
            enable_chunked_prefill=False, seed=23, disable_log_stats=True,
            disable_async_output_proc=True))
        tokenizer = engine.get_tokenizer()
        manager = engine.scheduler[0].block_manager
        allocator = gpu_allocator(manager)
        workload, results, phases, snapshots = [], [], [], []
        submitted, observations = {}, {}

        def tokens(group, length):
            value = tokenizer.encode(f'{group}: ' + 'road dry lane clear speed moderate. '*400)[:length]
            assert len(value) == length
            return value

        def snapshot(label):
            state = assert_allocator_invariants(allocator)
            if isinstance(allocator.evictor, ColdHotEvictor):
                state.update(hot_metadata=len(allocator.evictor.reuse), evictions=allocator.evictor.evictions,
                    selection_ns=allocator.evictor.selection_ns, reused_blocks=allocator.evictor.reused_blocks)
                if hasattr(allocator.evictor, 'assert_index_invariants'):
                    state.update(allocator.evictor.assert_index_invariants())
            snapshots.append({'label':label, **state})
            # Every live table must reference a positive-refcount physical block.
            for table in manager.block_tables.values():
                for block in table.blocks:
                    assert allocator._refcounter.get(block.block_id) > 0
                    if block.content_hash is not None:
                        assert allocator._cached_blocks[block.content_hash] == block.block_id

        def submit(request_id, group, length, scenario, max_tokens=32):
            token_ids = tokens(group, length)
            submitted[request_id] = time.perf_counter_ns()
            observations[request_id] = []
            workload.append({'request_id':request_id, 'group':group, 'length':length,
                'scenario':scenario, 'output_tokens':max_tokens, 'tokens':token_ids})
            engine.add_request(request_id, {'prompt_token_ids':token_ids},
                SamplingParams(temperature=0, max_tokens=max_tokens, ignore_eos=True, seed=23,
                               repetition_penalty=1.05))

        def step():
            outputs = engine.step()
            after = time.perf_counter_ns()
            for output in outputs:
                if output.request_id not in submitted:
                    continue
                obs = observations[output.request_id]
                n = len(output.outputs[0].token_ids)
                if not obs or n != obs[-1]['tokens']:
                    obs.append({'elapsed_ns':after-submitted[output.request_id], 'tokens':n})
                if output.finished:
                    results.append({'request_id':output.request_id, 'status':'completed',
                        'elapsed_ns':after-submitted[output.request_id],
                        'num_cached_tokens':output.num_cached_tokens,
                        'output_token_ids':list(output.outputs[0].token_ids),
                        'finish_reason':output.outputs[0].finish_reason,
                        'metrics':asdict(output.metrics) if output.metrics else None,
                        'observations':obs})
            if args.suite == 'lifecycle':
                snapshot('step')

        def drain():
            count = 0
            while engine.has_unfinished_requests():
                step()
                count += 1
                if count > 8192:
                    raise RuntimeError('step limit exceeded')

        def reset(label):
            assert not engine.has_unfinished_requests()
            assert engine.reset_prefix_cache()
            snapshot(label+'-reset')

        def phase(name, entries, scenario):
            begin = time.perf_counter_ns()
            for i, (group,length) in enumerate(entries):
                submit(f'{name}-{i}',group,length,scenario)
            drain()
            phases.append({'phase':name,'scenario':scenario,'requests':len(entries),
                           'elapsed_ns':time.perf_counter_ns()-begin})
            snapshot(name+'-finished')
            atomic_json(run.path/'workload.json',workload)
            atomic_json(run.path/'results.json',results)
            atomic_json(run.path/'phases.json',phases)
            atomic_json(run.path/'snapshots.json',snapshots)
            print(json.dumps(phases[-1]),flush=True)

        # Unmeasured unrelated warmup; remove it from request/phase statistics.
        phase('warmup',[('warmup',128)],'warmup')
        workload.clear(); results.clear(); phases.clear(); observations.clear(); submitted.clear()
        atomic_json(run.path/'phases.json', phases)
        reset('measurement')
        if args.suite == 'core':
            for i in range(3):
                phase(f'hot-seed-{i}', [('hot-a',512),('hot-b',512)],'cache')
            for i in range(4):
                phase(f'cold-sweep-{i}', [(f'cold-{i}',1024)],'cache')
            phase('hot-probe',[('hot-a',512),('hot-b',512)],'cache')
            reset('mixed')
            for wave in range(3):
                lengths = [1024,96,768,128,1024,96,512,256]
                phase(f'mixed-{wave}',[(f'mixed-hot-{i}' if i in (0,3,6) else f'mixed-new-{wave}-{i}', n)
                    for i,n in enumerate(lengths)],'mixed')
        else:
            # Real active shared prefixes + waiting cancellation, then allocator reuse.
            phase('seed-shared',[('shared',512)],'lifecycle')
            for i in range(8):
                submit(f'cancel-{i}','shared' if i<2 else f'cancel-novel-{i}',512,'lifecycle',96)
            step()
            assert engine.scheduler[0].running and engine.scheduler[0].waiting
            active_id = engine.scheduler[0].running[0].request_id
            waiting_id = engine.scheduler[0].waiting[-1].request_id
            for request_id in (active_id, waiting_id):
                engine.abort_request(request_id)
                results.append({'request_id':request_id,'status':'cancelled',
                    'cancelled_from':'running' if request_id==active_id else 'waiting'})
                snapshot('cancel-'+request_id)
            drain()
            reset('after-cancel')
            # Age is real monotonic elapsed waiting, not a forged arrival_time.
            submit('aged-long','aged-long',1024,'aging')
            time.sleep(config['aging_s']+0.02)
            for i in range(4):
                submit(f'new-short-{i}',f'new-short-{i}',96,'aging')
            drain()
            snapshot('after-aging')
            reset('after-aging')
            # Almost all KV occupied at admission; decode growth may preempt.
            for i in range(2):
                submit(f'pressure-{i}',f'pressure-{i}',960,'pressure',256)
            drain()
            snapshot('after-pressure')
            atomic_json(run.path/'workload.json',workload)
            atomic_json(run.path/'results.json',results)
            atomic_json(run.path/'snapshots.json',snapshots)
        expected = {x['request_id']: x['output_tokens'] for x in workload}
        assert len(results)==len(expected)==len({r['request_id'] for r in results})
        assert all(r['status']=='cancelled' or len(r['output_token_ids'])==expected[r['request_id']] for r in results)
        snapshot('all-finished')
        assert snapshots[-1]['free_total']==snapshots[-1]['total']
        atomic_json(run.path/'snapshots.json',snapshots)
        os.environ.pop('DRIVESERVE_TRACE_DIR',None)
        close_traces()
        run.finish('completed',{'requests':len(results),'completed':sum(r['status']=='completed' for r in results),
            'cancelled':sum(r['status']=='cancelled' for r in results),'failed':0,
            'workload_sha256':file_hash(run.path/'workload.json')})
    except BaseException as exc:
        from driveserve.engine_trace import close_traces
        os.environ.pop('DRIVESERVE_TRACE_DIR',None)
        close_traces()
        run.finish('failed',{'error':str(exc)})
        raise


if __name__=='__main__':
    main()
