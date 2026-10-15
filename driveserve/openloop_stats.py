"""Auditable all-attempt open-loop metrics; no timing hidden by failed requests."""
import math
from .benchmark import aggregate,percentile


def summarize(rows,epoch_ns,arrival_window_s,slo,*,measurement_end_ns=None):
    if (not rows or len({r['request_id'] for r in rows})!=len(rows)
            or not math.isfinite(arrival_window_s) or arrival_window_s<=0):
        raise ValueError('nonempty unique attempts and a finite positive arrival window required')
    if set(slo)!={'user_e2e_s','user_ttft_s'} or any(not math.isfinite(x) or x<=0 for x in slo.values()):
        raise ValueError('finite positive end-to-end and first-content SLOs required')
    assert all(r['status'] in ['completed','failed','timeout','cancelled'] for r in rows)
    finish=max(r['finished_ns'] for r in rows)
    if measurement_end_ns is not None and (type(measurement_end_ns) is not int or measurement_end_ns<finish):
        raise ValueError('group measurement end must cover all its attempts')
    duration=max(arrival_window_s,((measurement_end_ns if measurement_end_ns is not None else finish)-epoch_ns)/1e9)
    completed=[r for r in rows if r['status']=='completed']
    result=aggregate(rows,duration)
    result.update(cancelled=sum(r['status']=='cancelled' for r in rows),arrival_window_s=arrival_window_s,
                  window_scope='max(planned arrival horizon, last attempt finish - epoch); includes drain',
                  epoch_ns=epoch_ns,last_attempt_finished_ns=finish,slo=slo,
                  nominal_offered_requests_per_s=len(rows)/arrival_window_s,
                  attempts_per_s=len(rows)/duration,
                  quality_correct=sum(r['quality']['exact_match'] for r in completed),
                  success_json_valid=sum(r['quality']['json_valid'] for r in completed),
                  sent_requests=sum(r['sent_ns'] is not None for r in rows),
                  never_sent=sum(r['sent_ns'] is None for r in rows),
                  cancelled_before_arrival=sum(r['cancelled_before_arrival'] for r in rows))
    for key,subset in [('user_e2e_s',completed),('send_lag_s',rows)]:
        vals=[r[key] for r in subset if r[key] is not None]
        result[key]={'n':len(vals),'p50':percentile(vals,.5),'p99':percentile(vals,.99),'max':max(vals) if vals else None}
    all_lat=[r['user_e2e_s'] for r in rows]
    result['all_attempt_terminal_latency_s']={'n':len(rows),'p50':percentile(all_lat,.5),'p99':percentile(all_lat,.99),
        'scope':'time to terminal status; timeout/cancelled are not successful response latencies'}
    good=[r for r in completed if r['user_e2e_s']<=slo['user_e2e_s']
          and (r['first_content_ns']-r['planned_ns'])/1e9<=slo['user_ttft_s']]
    quality_good=[r for r in good if r['quality']['exact_match']]
    result.update(slo_success=len(good),slo_success_rate=len(good)/len(rows),slo_goodput_per_s=len(good)/duration,
                  quality_slo_success=len(quality_good),quality_slo_success_rate=len(quality_good)/len(rows),
                  quality_goodput_per_s=len(quality_good)/duration)
    result['endpoints']={endpoint:{'attempts':sum(r['endpoint']==endpoint for r in rows),
        'success':sum(r['endpoint']==endpoint for r in completed)} for endpoint in sorted({r['endpoint'] for r in rows})}
    if measurement_end_ns is not None:
        result['group_window_scope']='full parent-cell window, including other groups drain'
        result['parent_measurement_end_ns']=measurement_end_ns
    return result
