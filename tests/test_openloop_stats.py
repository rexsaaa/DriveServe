import unittest
from driveserve.openloop_stats import summarize

class OpenLoopStatsTests(unittest.TestCase):
    def test_all_attempts_and_drain_change_goodput(self):
        quality={'json_valid':True,'exact_match':True,'fields':dict(action=True,speed_band=True,must_yield=True)}
        base=dict(prompt_tokens=4,completion_tokens=2,quality=quality,ttft_s=.1,tpot_s=.1,e2e_s=.4,
            planned_ns=1_000_000_000,first_content_ns=1_100_000_000,finish_reason='stop',
            sent_ns=1_000_000_000,send_lag_s=0.,cancelled_before_arrival=False,endpoint='fixture')
        rows=[dict(base,request_id='0',status='completed',finished_ns=1_400_000_000,user_e2e_s=.4),
              dict(base,request_id='1',status='timeout',finished_ns=4_000_000_000,user_e2e_s=3.,sent_ns=None),
              dict(base,request_id='2',status='cancelled',finished_ns=2_000_000_000,user_e2e_s=1.)]
        result=summarize(rows,1_000_000_000,1.,dict(user_e2e_s=1.,user_ttft_s=.5))
        self.assertEqual(result['measurement_s'],3.)
        self.assertEqual(result['slo_success_rate'],1/3)
        self.assertEqual(result['quality_goodput_per_s'],1/3)
        self.assertEqual(result['timeout'],1);self.assertEqual(result['cancelled'],1)
        self.assertEqual(result['e2e_s']['n'],1);self.assertEqual(result['never_sent'],1)
        # Client admission lag can violate user TTFT despite fast server TTFT.
        rows[0]['first_content_ns']=1_900_000_000
        result=summarize(rows,1_000_000_000,5.,dict(user_e2e_s=1.,user_ttft_s=.5))
        self.assertEqual(result['measurement_s'],5.)
        self.assertEqual(result['slo_success'],0)
