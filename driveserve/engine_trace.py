"""Opt-in observers for pinned vLLM V0. Durations are HOST calls, not GPU time.

The versioned source patch installs these only when DRIVESERVE_TRACE_DIR is set.
No prompt/output content is logged and no scheduler or allocator decision changes.
"""

from functools import wraps
import json
import os
from pathlib import Path
import threading
import time

_streams = {}
_lock = threading.Lock()


def close_traces():
    with _lock:
        for stream in _streams.values():
            stream.close()
        _streams.clear()


def emit(event, **fields):
    directory = os.environ.get("DRIVESERVE_TRACE_DIR")
    if not directory:
        return
    pid = os.getpid()
    with _lock:
        if pid not in _streams:
            Path(directory).mkdir(parents=True, exist_ok=True)
            _streams[pid] = (Path(directory) / f"events-{pid}.jsonl").open("a", buffering=1)
        _streams[pid].write(json.dumps({"schema_version": 1, "event": event, "pid": pid,
            "monotonic_ns": time.perf_counter_ns(), **fields}, separators=(",", ":")) + "\n")


def _observe(cls, name, before, after):
    original = getattr(cls, name)
    if getattr(original, "_driveserve_observer", False):
        raise RuntimeError(f"observer installed twice: {cls.__name__}.{name}")

    @wraps(original)
    def wrapped(self, *args, **kwargs):
        fields = before(self, args, kwargs)
        started = time.perf_counter_ns()
        try:
            result = original(self, *args, **kwargs)
        except BaseException as exc:
            emit(f"{cls.__name__}.{name}", started_ns=started,
                 host_call_ns=time.perf_counter_ns() - started, outcome="error",
                 error_type=type(exc).__name__, **fields)
            raise
        duration = time.perf_counter_ns() - started
        fields.update(after(self, args, kwargs, result))
        emit(f"{cls.__name__}.{name}", started_ns=started,
             host_call_ns=duration, outcome="ok", **fields)
        return result

    wrapped._driveserve_observer = True
    setattr(cls, name, wrapped)


def _queues(scheduler):
    return {name: len(getattr(scheduler, name)) for name in ("waiting", "running", "swapped")}


def instrument_scheduler(cls):
    def enqueued(self, args, kwargs):
        group = args[0] if args else kwargs["seq_group"]
        return {"request_id": group.request_id,
                "sequences": [{"seq_id": seq.seq_id, "prompt_tokens": seq.get_prompt_len()}
                              for seq in group.get_seqs()]}

    def scheduled(self, args, kwargs, result):
        metadata, outputs, _ = result
        return {"queues_after": _queues(self), "preempted": outputs.preempted,
                "num_batched_tokens": outputs.num_batched_tokens,
                "free_gpu_blocks_after": self.block_manager.get_num_free_gpu_blocks(),
                "scheduled": [{"request_id": entry.request_id, "is_prompt": entry.is_prompt,
                               "token_chunk_size": entry.token_chunk_size,
                               "computed_prefix_blocks": len(entry.computed_block_nums or []),
                               "sequence_ids": list(entry.block_tables)} for entry in metadata]}

    _observe(cls, "add_seq_group", enqueued, lambda *args: {})
    _observe(cls, "schedule", lambda self, args, kwargs: {"queues_before": _queues(self)}, scheduled)


def instrument_block_manager(cls):
    def before(self, args, kwargs):
        seq = args[0] if args else kwargs["seq"]
        table = self.block_tables.get(seq.seq_id)
        return {"seq_id": seq.seq_id, "status": str(seq.status),
                "blocks_before": list(table.physical_block_ids) if table else [],
                "free_gpu_blocks_before": self.get_num_free_gpu_blocks()}

    def after(self, args, kwargs, result):
        seq = args[0] if args else kwargs["seq"]
        table = self.block_tables.get(seq.seq_id)
        return {"blocks_after": list(table.physical_block_ids) if table else [],
                "free_gpu_blocks_after": self.get_num_free_gpu_blocks()}

    def allocated(self, args, kwargs, result):
        group = args[0] if args else kwargs["seq_group"]
        return {"request_id": group.request_id,
                "tables": {str(seq.seq_id): list(self.block_tables[seq.seq_id].physical_block_ids)
                           for seq in group.get_seqs() if seq.seq_id in self.block_tables},
                "free_gpu_blocks_after": self.get_num_free_gpu_blocks()}

    _observe(cls, "allocate", lambda self, args, kwargs: {
        "free_gpu_blocks_before": self.get_num_free_gpu_blocks()}, allocated)
    for method in ("append_slots", "free"):
        _observe(cls, method, before, after)


def instrument_model_runner(cls):
    def before(self, args, kwargs):
        model_input = args[0] if args else kwargs["model_input"]
        attn = model_input.attn_metadata
        return {"input_tokens": model_input.input_tokens.numel() if model_input.input_tokens is not None else 0,
                "num_prefill_tokens": getattr(attn, "num_prefill_tokens", None),
                "num_decode_tokens": getattr(attn, "num_decode_tokens", None),
                "is_prompt": model_input.is_prompt,
                "scope": "host execute_model including dispatch/sampling; no added GPU synchronization"}
    _observe(cls, "execute_model", before, lambda *args: {})


def instrument_engine(cls):
    _observe(cls, "step", lambda *args: {}, lambda self, args, kwargs, result: {
        "outputs": [{"request_id": output.request_id, "finished": output.finished,
                     "num_cached_tokens": getattr(output, "num_cached_tokens", None),
                     "output_tokens": [len(item.token_ids) for item in getattr(output, "outputs", [])]}
                    for output in result]})
