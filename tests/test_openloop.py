"""Actual HTTP protocol/load-generator fixtures, never model benchmarks."""
import asyncio
import json
import time
import unittest
try:
    from aiohttp import web
except ImportError:
    web=None
from driveserve.openloop import run_arrivals
from driveserve.task import generate,digest

@unittest.skipIf(web is None, 'requires locked aiohttp; S5 release checks use project environment')
class OpenLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received=[];self.redirect_followed=False
        app=web.Application();app.router.add_post('/v1/completions',self.handler)
        app.router.add_get('/redirected',self.redirected)
        self.runner=web.AppRunner(app);await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        port=site._server.sockets[0].getsockname()[1]
        self.endpoint=f'http://127.0.0.1:{port}/v1'
        self.scene=generate()[0]['scene']

    async def asyncTearDown(self):await self.runner.cleanup()

    async def redirected(self,request):
        self.redirect_followed=True
        return web.Response(text='should not follow')

    async def handler(self,request):
        body=await request.json();mode=body['model'];ordinal=body['prompt'][0]
        self.received.append((ordinal,time.perf_counter_ns()))
        if mode=='http-error':return web.Response(status=500,text='fixture error')
        if mode=='redirect':raise web.HTTPFound('/redirected')
        response=web.StreamResponse(headers={'Content-Type':'text/event-stream'})
        await response.prepare(request)
        try:
            if mode=='slow-first' and ordinal==0:await asyncio.sleep(.15)
            if mode=='slow-drip':
                for byte in b'data: '+b' '*100:
                    await response.write(bytes([byte]));await asyncio.sleep(.02)
                await response.write_eof();return response
            content='{"action":"stop","speed_band":"stopped","must_yield":true}'
            events=[json.dumps({'choices':[{'text':content[:20],'finish_reason':None}]}),
                    json.dumps({'choices':[{'text':content[20:],'finish_reason':'stop'}]}),
                    json.dumps({'usage':{'prompt_tokens':len(body['prompt']),'completion_tokens':12}}),'[DONE]']
            if mode=='truncated':events.pop()
            if mode=='missing-usage':events.pop(2)
            if mode=='bad-json':events[1]='broken'
            if mode=='error-event':events[1]=json.dumps({'error':'fixture stream error'})
            if mode=='unknown-finish':events[1]=json.dumps({'choices':[{'text':content[20:],'finish_reason':'content_filter'}]})
            if mode=='bool-usage':events[2]=json.dumps({'usage':{'prompt_tokens':True,'completion_tokens':12}})
            if mode=='negative-usage':events[2]=json.dumps({'usage':{'prompt_tokens':1,'completion_tokens':-1}})
            if mode=='one-token':events[2]=json.dumps({'usage':{'prompt_tokens':len(body['prompt']),'completion_tokens':1}})
            for event in events:await response.write(('data: '+event+'\n\n').encode())
            await response.write_eof()
        except (ConnectionResetError,asyncio.CancelledError):pass
        return response

    def records(self,n):
        return [{'request_id':str(i),'scene':self.scene,'split':'fixture','tokens':[i],
                 'prompt_sha256':digest([i])} for i in range(n)]

    async def execute(self,mode,offsets,**kwargs):
        return await run_arrivals(self.records(len(offsets)),offsets,[self.endpoint],mode,**kwargs)

    async def test_independent_arrivals_and_actual_timestamps(self):
        result=await self.execute('slow-first',[0,.03,.06],max_inflight=3)
        rows={r['ordinal']:r for r in result['records']}
        self.assertTrue(all(r['status']=='completed' for r in rows.values()))
        self.assertEqual(rows[1]['planned_ns']-rows[0]['planned_ns'],30_000_000)
        self.assertLess(rows[1]['sent_ns'],rows[0]['finished_ns'])
        self.assertEqual(rows[0]['tpot_s'],(rows[0]['last_content_ns']-rows[0]['first_content_ns'])/1e9/11)

    async def test_client_admission_lag_is_visible(self):
        result=await self.execute('slow-first',[0,.03],max_inflight=1)
        rows={r['ordinal']:r for r in result['records']}
        self.assertGreater(rows[1]['send_lag_s'],.09)
        self.assertGreater(rows[1]['user_e2e_s'],rows[1]['e2e_s']+.09)

    async def test_global_deadline_interrupts_slow_drip_and_queue(self):
        started=time.perf_counter()
        result=await self.execute('slow-drip',[0,0],max_inflight=1,timeout_s=.12)
        self.assertLess(time.perf_counter()-started,.5)
        rows={r['ordinal']:r for r in result['records']}
        self.assertEqual(rows[0]['status'],'timeout');self.assertEqual(rows[1]['status'],'timeout')
        # Simultaneous arrivals do not imply ordinal wakeup/admission order.
        self.assertEqual(sum(r['sent_ns'] is None for r in rows.values()),1)

    async def test_invalid_protocol_and_http_remain_failures(self):
        for mode in ['truncated','missing-usage','bad-json','error-event','http-error','redirect','unknown-finish','bool-usage','negative-usage']:
            with self.subTest(mode=mode):
                r=(await self.execute(mode,[0]))['records'][0]
                self.assertEqual(r['status'],'failed');self.assertIsNotNone(r['error'])
        self.assertFalse(self.redirect_followed)

    async def test_one_token_has_no_tpot(self):
        r=(await self.execute('one-token',[0]))['records'][0]
        self.assertEqual(r['status'],'completed');self.assertIsNone(r['tpot_s'])

    async def test_invalid_plan_rejected_before_sending(self):
        for options in [dict(offsets_s=[float('nan')]),dict(offsets_s=[float('inf')]),
                dict(timeout_s=float('nan')),dict(timeout_s=float('inf')),
                dict(endpoints=['http://user:password@localhost']),dict(endpoints=['http://localhost:bad']),
                dict(max_tokens=True),dict(max_inflight=0)]:
            params=dict(records=self.records(1),offsets_s=[0],endpoints=[self.endpoint],model='normal')
            params.update(options)
            with self.subTest(options=options),self.assertRaises(ValueError):await run_arrivals(**params)
        records=self.records(2);records[1]['request_id']=records[0]['request_id']
        with self.assertRaises(ValueError):await run_arrivals(records,[0,0],[self.endpoint],'normal')
        self.assertEqual(self.received,[])

    async def test_cancelled_tasks_are_saved(self):
        rows=[]
        task=asyncio.create_task(self.execute('slow-drip',[0,.01,.02],max_inflight=1,on_result=rows.append))
        await asyncio.sleep(.1);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['status']=='cancelled' for r in rows))

if __name__=='__main__':unittest.main(verbosity=2)
