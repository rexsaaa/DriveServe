"""Independent arrivals with explicit client-queue accounting.

Requires the already locked aiohttp dependency. Failures and cancellation remain in the all-attempt denominator.
"""
import asyncio
import json
import math
import time
from urllib.parse import urlsplit

from driveserve.task import score


def trace_config():
    import aiohttp
    trace=aiohttp.TraceConfig()
    async def headers_sent(session,context,params):
        context.trace_request_ctx['sent_ns']=time.perf_counter_ns()
    trace.on_request_headers_sent.append(headers_sent)
    return trace


async def send(session,semaphore,endpoint,model,record,ordinal,planned_loop,planned_ns,
               timeout_s,max_tokens=64):
    url=urlsplit(endpoint)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('HTTP(S) base endpoint without credentials/query required')
    row={'request_id':record['request_id'],'scene_id':record['scene']['scene_id'],'ordinal':ordinal,
         'endpoint':endpoint,'planned_ns':planned_ns,'worker_start_ns':None,'dispatch_ns':None,'sent_ns':None,
         'first_content_ns':None,'last_content_ns':None,'finished_ns':None,
         'status':'failed','error':None,'text':'','chunks':[],'completion_tokens':None,'prompt_tokens':None,
         'finish_reason':None,'prompt_sha256':record['prompt_sha256'],'split':record['split'],
         'ttft_s':None,'tpot_s':None,'e2e_s':None,'user_e2e_s':None,'send_lag_s':None}
    try:
        # Every task sleeps to its own immutable arrival; no completion-driven
        # replenishment. The overall deadline includes admission/connect/stream.
        await asyncio.sleep(max(0,planned_loop-asyncio.get_running_loop().time()))
        async with asyncio.timeout_at(planned_loop+timeout_s):
            async with semaphore:
                # A semaphore release can race a deadline callback in the same
                # event-loop turn; never send an already expired request.
                if asyncio.get_running_loop().time()>=planned_loop+timeout_s:
                    raise TimeoutError('deadline expired while waiting for admission')
                row['worker_start_ns']=time.perf_counter_ns()
                body={'model':model,'prompt':record['tokens'],'temperature':0,'seed':37,'max_tokens':max_tokens,
                      'stream':True,'stream_options':{'include_usage':True}}
                row['dispatch_ns']=time.perf_counter_ns()
                async with session.post(endpoint.rstrip('/')+'/completions',json=body,trace_request_ctx=row,allow_redirects=False) as response:
                    if response.status!=200:
                        message=(await response.content.read(2048)).decode(errors='replace')
                        raise RuntimeError(f'HTTP {response.status}: {message}')
                    done=False
                    async for raw in response.content:
                        if not raw.startswith(b'data:'):continue
                        payload=raw[5:].strip()
                        if payload==b'[DONE]':done=True;break
                        if not payload:continue
                        event=json.loads(payload);stamp=time.perf_counter_ns()
                        row['chunks'].append({'received_ns':stamp,'event':event})
                        if 'error' in event:raise RuntimeError(str(event['error']))
                        for choice in event.get('choices',[]):
                            content=choice.get('text') or ''
                            if content:
                                row['text']+=content
                                if row['first_content_ns'] is None:row['first_content_ns']=stamp
                                row['last_content_ns']=stamp
                            if choice.get('finish_reason') is not None:row['finish_reason']=choice['finish_reason']
                        if event.get('usage') is not None:
                            row['completion_tokens']=event['usage'].get('completion_tokens')
                            row['prompt_tokens']=event['usage'].get('prompt_tokens')
                    n=row['completion_tokens']
                    if not done or row['finish_reason'] not in ('stop','length') or row['first_content_ns'] is None:
                        raise RuntimeError('incomplete or empty SSE stream')
                    if type(n) is not int or not 0<n<=max_tokens or type(row['prompt_tokens']) is not int or row['prompt_tokens']!=len(record['tokens']):
                        raise RuntimeError('missing or inconsistent token usage')
                    if row['sent_ns'] is None:raise RuntimeError('actual send timestamp absent')
                    row['ttft_s']=(row['first_content_ns']-row['sent_ns'])/1e9
                    if n>1:row['tpot_s']=(row['last_content_ns']-row['first_content_ns'])/1e9/(n-1)
                    row['status']='completed'
    except TimeoutError as exc:
        row['status']='timeout';row['error']='overall planned-arrival deadline: '+str(exc)
    except asyncio.CancelledError:
        row['status']='cancelled';row['error']='client task cancelled'
        # Caller logs returned rows after explicitly cancelling remaining tasks.
    except Exception as exc:
        row['error']=f'{type(exc).__name__}: {exc}'
    row['finished_ns']=time.perf_counter_ns()
    row['cancelled_before_arrival']=row['finished_ns']<planned_ns
    row['user_e2e_s']=max(0,(row['finished_ns']-planned_ns)/1e9)
    if row['sent_ns'] is not None:
        row['send_lag_s']=(row['sent_ns']-planned_ns)/1e9
        row['e2e_s']=(row['finished_ns']-row['sent_ns'])/1e9
    row['quality']=score(record['scene'],row['text'])
    return row


async def run_arrivals(records,offsets_s,endpoints,model,*,max_inflight=64,timeout_s=30.,max_tokens=64,on_result=None):
    import aiohttp
    if (len(records)!=len(offsets_s) or not records or not endpoints or type(max_inflight) is not int or max_inflight<1
        or not math.isfinite(timeout_s) or timeout_s<=0 or type(max_tokens) is not int or max_tokens<1):
        raise ValueError('nonempty matching records/offsets/endpoints and positive limits required')
    if any(not math.isfinite(x) or x<0 for x in offsets_s) or list(offsets_s)!=sorted(offsets_s):raise ValueError('arrival offsets must be sorted nonnegative values')
    if len({r['request_id'] for r in records})!=len(records):raise ValueError('request IDs must be unique')
    for record in records:
        if not record['tokens'] or any(type(t) is not int or t<0 for t in record['tokens']):
            raise ValueError('nonempty token-ID prompts required')
        if not isinstance(record['scene'],dict) or not record['prompt_sha256'] or not record['split']:
            raise ValueError('scene/split/prompt hash required')
    for endpoint in endpoints:
        url=urlsplit(endpoint)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('HTTP(S) base endpoint without credentials/query required')
        _=url.port  # reject malformed ports before creating any request tasks
    loop=asyncio.get_running_loop();epoch_loop=loop.time()+.05
    # Pair the two monotonic clocks once. perf_counter_ns timestamps retain their
    # own origin; asyncio deadlines use loop.time rather than assuming origins.
    epoch_ns=time.perf_counter_ns()+round((epoch_loop-loop.time())*1e9)
    semaphore=asyncio.Semaphore(max_inflight);results=[]
    # No hidden connector queue; semaphore admission is measured explicitly.
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0),
            timeout=aiohttp.ClientTimeout(total=None),trace_configs=[trace_config()]) as session:
        tasks=[asyncio.create_task(send(session,semaphore,endpoints[i%len(endpoints)],model,record,i,
                epoch_loop+offset,epoch_ns+round(offset*1e9),timeout_s,max_tokens))
               for i,(record,offset) in enumerate(zip(records,offsets_s))]
        try:
            for task in asyncio.as_completed(tasks):
                result=await task;results.append(result)
                if on_result is not None:on_result(result)
        except BaseException:
            for task in tasks:
                if not task.done():task.cancel()
            remaining=await asyncio.gather(*tasks,return_exceptions=True)
            known={r['ordinal'] for r in results}
            for result in remaining:
                if isinstance(result,dict) and result['ordinal'] not in known:
                    results.append(result)
                    if on_result is not None:on_result(result)
            raise
    return {'epoch_ns':epoch_ns,'finished_ns':time.perf_counter_ns(),'records':results,
            'scope':'actual header-send timing; user latency includes planned-arrival wait, admission and connection setup'}
