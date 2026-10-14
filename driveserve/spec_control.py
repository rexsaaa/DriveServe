"""Runtime draft-length controller; target verification remains native vLLM.

Window observations count the causal draft prefix, never bonus/recovery tokens.
All host serialization/synchronization costs remain in end-to-end measurements.
"""
from collections import deque
import os
from driveserve.engine_trace import emit


class DraftLengthController:
    def __init__(self, maximum=4, initial=2, window=8, hold=8, low=0.45, high=0.8):
        if not (1 <= initial <= maximum and window >= 1 and hold >= window and 0 <= low < high <= 1):
            raise ValueError('invalid controller parameters')
        self.maximum, self.k = maximum, initial
        self.window, self.hold, self.low, self.high = window, hold, low, high
        self.history = deque(maxlen=window)
        self.observed = self.last_change = 0
        self.fallback = False

    def observe(self, accepted, proposed):
        if not (isinstance(accepted,int) and isinstance(proposed,int) and 0<=accepted<=proposed):
            self.fallback=True
            self.k=self.maximum
            return
        if proposed:
            self.history.append((accepted,proposed))
            self.observed+=1

    def choose(self, reserved):
        if reserved<1:
            raise ValueError('decode must have positive reservation')
        previous=self.k
        ratio=None
        reason='hold'
        if self.fallback:
            self.k=self.maximum
            reason='invalid-observation-fixed-fallback'
        elif len(self.history)==self.window and self.observed-self.last_change>=self.hold:
            ratio=sum(a for a,p in self.history)/sum(p for a,p in self.history)
            if ratio<self.low:
                self.k=max(1,self.k-1);reason='low-acceptance'
            elif ratio>self.high:
                self.k=min(self.maximum,self.k+1);reason='high-acceptance'
            else:
                reason='hysteresis-band'
            # Even a saturated decision gets a hold period, preventing chatter.
            self.last_change=self.observed
        self.k=min(self.k,reserved)
        return {'k':self.k,'previous_k':previous,'reserved':reserved,'window_ratio':ratio,
                'observed_batches':self.observed,'reason':reason,'changed':self.k!=previous}


def accepted_prefix(row, proposed):
    """Native rejection output is [accepted prefix, recovery/bonus, -1...]."""
    if proposed==0:
        return 0
    if len(row)!=proposed+1:
        raise ValueError('verifier output width differs from actual proposal K')
    valid=next((i for i,x in enumerate(row) if x<0),len(row))
    if valid<1 or any(x!=-1 for x in row[valid:]):
        raise ValueError('verifier output is not a contiguous valid prefix')
    return valid-1


def prepare_step(worker, request):
    reserved=request.num_lookahead_slots
    if not reserved:
        return request
    mode=os.environ.get('DRIVESERVE_SPEC_MODE','fixed')
    if mode not in ('fixed','adaptive'):
        raise ValueError('unknown speculative mode')
    if len(request.seq_group_metadata_list)==0:
        return request
    if any(len(sg.seq_data)!=1 for sg in request.seq_group_metadata_list):
        raise ValueError('adaptive prototype requires one sequence per request')
    maximum=int(os.environ.get('DRIVESERVE_SPEC_MAX_K','4'))
    if reserved!=maximum:
        raise ValueError('scheduler reservation differs from configured maximum K')
    if not hasattr(worker,'_driveserve_controller'):
        worker._driveserve_controller=DraftLengthController(maximum=maximum,
            initial=min(2,maximum),window=8,hold=8)
        worker._driveserve_step=0
    controller=worker._driveserve_controller
    decision=controller.choose(reserved) if mode=='adaptive' else {
        'k':reserved,'reserved':reserved,'reason':'fixed','changed':False,
        'observed_batches':controller.observed,'window_ratio':None}
    worker._driveserve_step+=1
    worker._driveserve_decision=decision
    emit('spec.choose',step=worker._driveserve_step,mode=mode,
         request_ids=[sg.request_id for sg in request.seq_group_metadata_list],**decision)
    # Clone request shell so the engine's reserved maximum is not modified.
    result=request.clone(request.seq_group_metadata_list)
    result.num_lookahead_slots=decision['k']
    return result


def observe_verification(worker, request, proposals, accepted_token_ids):
    proposed_lengths=proposals.proposal_lens.tolist()
    emitted=accepted_token_ids.tolist()
    actual_k=request.num_lookahead_slots
    if proposals.proposal_token_ids.shape[1]!=actual_k or accepted_token_ids.shape[1]!=actual_k+1:
        raise ValueError('K must change actual proposal and verification tensor widths')
    rows=[]
    total_accepted=total_proposed=0
    for sg,n,row in zip(request.seq_group_metadata_list,proposed_lengths,emitted):
        if n not in (0,actual_k):
            raise ValueError('unsupported variable within-batch proposal length')
        accepted=accepted_prefix(row,n)
        total_accepted+=accepted;total_proposed+=n
        seq=next(iter(sg.seq_data.values()))
        params=sg.sampling_params
        remaining=params.max_tokens-seq.get_output_len()
        valid=[x for x in row if x>=0]
        eos_positions=[i for i,t in enumerate(valid) if t in params.all_stop_token_ids]
        # Engine output processors still perform EOS, string and length stops.
        # This diagnostic is verifier-level acceptance, not final emitted count.
        rows.append({'request_id':sg.request_id,'proposed':n,'accepted_draft_prefix':accepted,
            'verifier_valid_tokens':len(valid),'valid_token_ids':valid,
            'rejected':bool(n and accepted<n),'bonus':bool(n and accepted==n),
            'remaining_output_budget':remaining,'beyond_output_budget':max(0,len(valid)-remaining),
            'stop_token_positions':eos_positions,'ignore_eos':params.ignore_eos,
            'no_proposal':n==0})
    worker._driveserve_controller.observe(total_accepted,total_proposed)
    emit('spec.verify',step=worker._driveserve_step,actual_k=actual_k,
         proposal_width=proposals.proposal_token_ids.shape[1],verification_width=accepted_token_ids.shape[1],
         total_accepted=total_accepted,total_proposed=total_proposed,rows=rows,
         scope='causal verifier acceptance before engine EOS/string/length truncation; bonus excluded')
