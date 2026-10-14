"""Answer-only LoRA sequence distillation with complete atomic training checkpoints."""
import argparse, fcntl, json, math, os, random, signal, sys, time, uuid
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from driveserve.evidence import Run, atomic_json, file_hash, now
from driveserve.task import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--teacher', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=Path, default=Path('/hy-tmp/driveserve/models/draft-aligned-v1'))
    parser.add_argument('--layer', type=Path, default=Path('/hy-tmp/driveserve/training-deps-v1'))
    parser.add_argument('--steps', type=int, default=128)
    parser.add_argument('--stop-after', type=int, help='controlled prefix run; keeps full scheduler horizon')
    parser.add_argument('--gpu', default='0')
    args = parser.parse_args()
    os.environ.update(CUDA_VISIBLE_DEVICES=args.gpu, CUBLAS_WORKSPACE_CONFIG=':4096:8',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    sys.path.insert(0, str(args.layer.resolve()))
    import torch
    import peft
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model, get_peft_model_state_dict, set_peft_model_state_dict
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output/'.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    provenance = json.load(open(args.base/'driveserve-provenance.json'))
    for entry in provenance['files']:
        assert file_hash(args.base/Path(entry['path']).name) == entry['sha256']
    teacher = json.load(open(args.teacher))
    assert teacher['records_sha256'] == digest(teacher['records'])
    assert teacher['next_index'] == len(teacher['records']) == 640
    train = [r for r in teacher['records'] if r['train_eligible']]
    dev = [r for r in teacher['records'] if r['split'] == 'dev' and not r['filter_reasons']]
    assert train and dev and all(r['split'] == 'train' and not r['filter_reasons'] for r in train)
    assert not {r['scene_id'] for r in train} & {r['scene_id'] for r in dev}
    recipe = dict(seed=3701, steps=args.steps, batch_size=2, accumulation=4, learning_rate=2e-4,
                  warmup=8, weight_decay=0, rank=8, alpha=16, dropout=0, dtype='bfloat16',
                  targets=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
                  loss='answer-only token mean per microbatch, incl exactly one EOS; equal microbatch weighting',
                  attention='sdpa', gradient_checkpointing=True, max_length=1024,
                  checkpoint_every=8, gradient_clip=1.0, data_order='one fixed seeded permutation repeated')
    identity = digest({'recipe':recipe, 'base':provenance, 'teacher_sha256':file_hash(args.teacher),
                       'training_layer':json.load(open(args.layer/'driveserve-training-layer.json'))})
    config = {'stage':'S2', 'requirement_ids':['M3-04'], 'hypothesis':'small teacher-labelled LoRA distillation with exact optimizer/RNG resume',
              'model':provenance, 'data':{'teacher_sha256':file_hash(args.teacher), 'train':len(train), 'dev':len(dev)},
              'recipe':recipe, 'identity':identity, 'gpu':args.gpu, 'stop_after':args.stop_after,
              'limitations':['synthetic proxy data; no final-test access', 'sequence-level distillation, no teacher logits',
                             'training loss is not task quality or speculative acceptance evidence']}
    latest = json.load(open(args.output/'latest.json')) if (args.output/'latest.json').exists() else None
    checkpoint = None
    if latest:
        checkpoint = args.output/latest['directory']
        manifest = json.load(open(checkpoint/'checkpoint.json'))
        assert manifest['identity'] == identity
        assert file_hash(checkpoint/'checkpoint.json') == latest['manifest_sha256']
        for entry in manifest['files']:
            assert file_hash(checkpoint/entry['name']) == entry['sha256']
    run = Run(Path.cwd(), 'draft-distillation', config, formal=True,
              previous_run_id=latest['run_id'] if latest else None)
    print(run.path, flush=True)
    stop = [False]
    signal.signal(signal.SIGTERM, lambda *a: stop.__setitem__(0, True))
    started = time.perf_counter()
    try:
        random.seed(recipe['seed']); torch.manual_seed(recipe['seed']); torch.cuda.manual_seed_all(recipe['seed'])
        tokenizer = AutoTokenizer.from_pretrained(args.base, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16,
                    attn_implementation='sdpa', local_files_only=True).to('cuda')
        model.config.use_cache = False
        model = get_peft_model(model, LoraConfig(r=recipe['rank'], lora_alpha=recipe['alpha'],
                    lora_dropout=recipe['dropout'], target_modules=recipe['targets'], bias='none', task_type='CAUSAL_LM'))
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                    lr=recipe['learning_rate'], weight_decay=recipe['weight_decay'])
        def lr_multiplier(step):
            if step < recipe['warmup']: return (step+1)/recipe['warmup']
            return max(0., (recipe['steps']-step)/(recipe['steps']-recipe['warmup']))
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_multiplier)
        order = list(range(len(train))); random.Random(recipe['seed']).shuffle(order)
        order_hash = digest(order)
        step = cursor = 0
        history = []
        if checkpoint:
            saved = torch.load(checkpoint/'state.pt', map_location='cpu', weights_only=False)
            assert saved['identity'] == identity and saved['order_hash'] == order_hash
            set_peft_model_state_dict(model, saved['adapter'])
            optimizer.load_state_dict(saved['optimizer']); scheduler.load_state_dict(saved['scheduler'])
            step, cursor, history = saved['step'], saved['cursor'], saved['history']
            random.setstate(saved['python_rng']); torch.set_rng_state(saved['cpu_rng'])
            torch.cuda.set_rng_state_all(saved['cuda_rng'])
        atomic_json(run.path/'training-start.json', {'step':step,'cursor':cursor,'resume':str(checkpoint) if checkpoint else None,
                    'order_sha256':order_hash,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
                    'total_parameters':sum(p.numel() for p in model.parameters()), 'torch':torch.__version__, 'peft':peft.__version__})

        def batch(records):
            tokens, labels = [], []
            for row in records:
                answer = list(row['completion_tokens'])
                while answer and answer[-1] == tokenizer.eos_token_id: answer.pop()
                answer.append(tokenizer.eos_token_id)
                ids = row['prompt_tokens'] + answer
                assert len(ids) <= recipe['max_length']
                tokens.append(ids); labels.append([-100]*len(row['prompt_tokens']) + answer)
            width = max(map(len, tokens))
            return {'input_ids':torch.tensor([v+[tokenizer.pad_token_id]*(width-len(v)) for v in tokens],device='cuda'),
                    'attention_mask':torch.tensor([[1]*len(v)+[0]*(width-len(v)) for v in tokens],device='cuda'),
                    'labels':torch.tensor([v+[-100]*(width-len(v)) for v in labels],device='cuda')}

        def save_checkpoint(reason):
            directory = f'checkpoint-{step:05d}-{uuid.uuid4().hex[:8]}'
            temporary = args.output/('.'+directory+'.partial'); temporary.mkdir()
            adapter = {k:v.detach().cpu().clone() for k,v in get_peft_model_state_dict(model).items()}
            saved = {'identity':identity, 'order_hash':order_hash, 'step':step, 'cursor':cursor, 'history':history,
                     'adapter':adapter, 'optimizer':optimizer.state_dict(), 'scheduler':scheduler.state_dict(),
                     'python_rng':random.getstate(), 'cpu_rng':torch.get_rng_state(), 'cuda_rng':torch.cuda.get_rng_state_all()}
            torch.save(saved, temporary/'state.pt')
            model.save_pretrained(temporary/'adapter', safe_serialization=True)
            files = [{'name':str(p.relative_to(temporary)), 'bytes':p.stat().st_size, 'sha256':file_hash(p)}
                     for p in sorted(temporary.rglob('*')) if p.is_file()]
            for entry in files:
                with (temporary/entry['name']).open('rb') as stream: os.fsync(stream.fileno())
            atomic_json(temporary/'checkpoint.json', {'identity':identity, 'step':step, 'cursor':cursor,
                        'reason':reason, 'created_at':now(), 'run_id':run.manifest['run_id'], 'files':files})
            temporary.rename(args.output/directory)
            pointer = {'directory':directory, 'manifest_sha256':file_hash(args.output/directory/'checkpoint.json'),
                       'step':step, 'cursor':cursor, 'run_id':run.manifest['run_id']}
            atomic_json(args.output/'latest.json', pointer)
            run.manifest['checkpoint'] = {'root':str(args.output), **pointer}; run.save()
            return pointer

        model.train(); target_step = min(args.stop_after or args.steps, args.steps)
        with (run.path/'steps.jsonl').open('a', buffering=1) as log:
            while step < target_step:
                optimizer.zero_grad(set_to_none=True)
                losses = []; actual_ids = []; tokens = 0; before = time.perf_counter()
                lr = optimizer.param_groups[0]['lr']
                for micro in range(recipe['accumulation']):
                    chosen = [train[order[(cursor+i)%len(order)]] for i in range(recipe['batch_size'])]
                    cursor += recipe['batch_size']; actual_ids.extend(r['scene_id'] for r in chosen)
                    inputs = batch(chosen); tokens += int((inputs['labels']!=-100).sum())
                    output = model(**inputs)
                    loss = output.loss
                    if not torch.isfinite(loss): raise RuntimeError('nonfinite loss')
                    losses.append(float(loss.detach()))
                    (loss/recipe['accumulation']).backward()
                    del output, loss, inputs
                norm = float(torch.nn.utils.clip_grad_norm_(model.parameters(), recipe['gradient_clip']))
                optimizer.step(); scheduler.step(); step += 1
                row = {'step':step, 'cursor':cursor, 'loss':sum(losses)/len(losses), 'micro_losses':losses,
                       'lr':lr,'next_lr':optimizer.param_groups[0]['lr'], 'gradient_norm':norm, 'answer_tokens':tokens,
                       'sample_ids':actual_ids, 'elapsed_s':time.perf_counter()-before}
                history.append(row); log.write(json.dumps(row)+'\n'); log.flush(); os.fsync(log.fileno())
                print(json.dumps({k:row[k] for k in ['step','loss','lr','elapsed_s']}), flush=True)
                run.manifest['heartbeat_at'] = now(); run.manifest['training_step'] = step; run.save()
                if step%recipe['checkpoint_every']==0 or stop[0] or step==target_step:
                    save_checkpoint('SIGTERM' if stop[0] else 'periodic-or-target')
                if stop[0]: break
        # Eval happens after checkpoint so it cannot perturb resumed training RNG.
        dev_result = None
        if not stop[0]:
            model.eval(); weighted_loss = total = 0
            with torch.no_grad():
                for i in range(0,len(dev),recipe['batch_size']):
                    inputs = batch(dev[i:i+recipe['batch_size']]); count = int((inputs['labels'][:,1:]!=-100).sum())
                    weighted_loss += float(model(**inputs).loss)*count; total += count
            dev_result = {'teacher_answer_loss':weighted_loss/total, 'answer_tokens':total, 'records':len(dev),
                          'scope':'oracle-correct natural-stop dev teacher subset; no gradients'}
        summary = {'step':step,'cursor':cursor, 'finished_schedule':step==args.steps,'sigterm_received':stop[0],
                   'elapsed_s':time.perf_counter()-started,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
                   'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'dev':dev_result,
                   'latest':json.load(open(args.output/'latest.json'))}
        atomic_json(run.path/'training-summary.json', summary)
        run.finish('interrupted' if stop[0] else 'completed', summary)
        if stop[0]: return 75
    except BaseException as exc:
        if run.manifest['status']=='running': run.finish('failed', {'error':str(exc)})
        raise
    return 0

if __name__=='__main__': sys.exit(main())
