"""Check the image's fixed userland and optionally exercise actual GPU/model execution."""
import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--policy', type=Path, default=Path('/opt/driveserve/runtime.json'))
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--model', type=Path, help='Optional restored model for a real vLLM generation')
    parser.add_argument('--memory-fraction', type=float, default=.85,
                        help='Fraction of one GPU reserved for the model smoke test')
    args = parser.parse_args()
    if not 0 < args.memory_fraction < 1:
        parser.error('--memory-fraction must be between 0 and 1')
    policy = json.loads(args.policy.read_text())
    if platform.python_version() != policy['python']:
        raise RuntimeError('Python differs from the image policy')
    if platform.libc_ver() != ('glibc', policy['glibc']):
        raise RuntimeError('glibc differs from the image policy')
    packages = {name: metadata.version(name) for name in policy['packages']}
    if packages != policy['packages']:
        raise RuntimeError(f'Python package version mismatch: {packages}')
    compiler = subprocess.check_output([policy['cuda_home'] + '/bin/nvcc', '--version'], text=True)
    if 'V' + policy['nvcc'] not in compiler:
        raise RuntimeError('CUDA compiler differs from the image policy')
    import torch
    import vllm
    import transformers
    if torch.version.cuda != '12.4':
        raise RuntimeError('Unexpected PyTorch CUDA build')
    result = dict(status='passed', python=sys.version, executable=sys.executable,
                  libc=platform.libc_ver(), packages=packages, torch=torch.__version__,
                  torch_cuda=torch.version.cuda, compiler=compiler.strip(), gpu_tested=False)
    if args.gpu or args.model:
        drivers = subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version',
                                           '--format=csv,noheader'], text=True).splitlines()
        minimum = tuple(map(int, policy['driver_minimum'].split('.')))
        if not drivers or any(tuple(map(int, value.strip().split('.'))) < minimum for value in drivers):
            raise RuntimeError('Host NVIDIA driver is below the image migration policy')
        if not torch.cuda.is_available():
            raise RuntimeError('GPU unavailable: start with NVIDIA Container Toolkit and --gpus')
        devices = []
        for index in range(torch.cuda.device_count()):
            capability = torch.cuda.get_device_capability(index)
            if capability[0] >= 10:
                raise RuntimeError('This CUDA 12.4 image does not support Blackwell or later GPUs; '
                                   'use a separately upgraded and validated image')
            if capability < (7, 0):
                raise RuntimeError('This vLLM image requires compute capability >= 7.0')
            expected = torch.arange(256, dtype=torch.float32).reshape(16, 16)
            data = expected.to(f'cuda:{index}')
            torch.testing.assert_close((data @ data.T).cpu(), expected @ expected.T)
            devices.append(dict(index=index, name=torch.cuda.get_device_name(index),
                                compute_capability=list(capability),
                                memory=torch.cuda.get_device_properties(index).total_memory))
        result.update(gpu_tested=True, driver_versions=drivers, devices=devices)
        result['compatibility_note'] = ('Only RTX 4090 has project workload evidence. '
                                        'Passing this arithmetic check is not full workload validation.')
    if args.model:
        os.environ['HF_HUB_OFFLINE'] = '1'
        engine = vllm.LLM(model=str(args.model), dtype='half', max_model_len=512,
                          max_num_seqs=1, gpu_memory_utilization=args.memory_fraction, enforce_eager=True)
        outputs = engine.generate(['The capital of France is'],
                                  vllm.SamplingParams(temperature=0, max_tokens=8))
        if not outputs[0].outputs[0].token_ids:
            raise RuntimeError('Model returned no generated tokens')
        result['model_generation'] = outputs[0].outputs[0].text
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
