import unittest
from analyze import call_metrics, aggregate, paired, frontier_tokens


class Accounting(unittest.TestCase):
    def test_codex_cached_and_reasoning_tokens_not_double_counted(self):
        c={'provider':'codex','model_requested':'gpt-6-astra','usage':{
            'input_tokens':1000,'cached_input_tokens':700,'cache_write_input_tokens':100,
            'output_tokens':100,'reasoning_output_tokens':80}}
        m=call_metrics(c)
        self.assertEqual(m['fresh_input'],200)
        self.assertEqual(m['total_cloud_tokens'],1100)
        self.assertAlmostEqual(m['reference_usd'],(200*10+700+100*12.5+100*50)/1e6)

    def test_claude_auxiliary_model_is_included_exactly_once(self):
        c={'provider':'claude','role':'main','model_requested':'sonnet','usage':{'input_tokens':3},
           'model_usage':{'sonnet':{'inputTokens':10,'cacheCreationInputTokens':20,
             'cacheReadInputTokens':30,'outputTokens':40},'helper':{'inputTokens':100,'outputTokens':5}},
           'reference_cost_usd':0.25}
        m=call_metrics(c)
        self.assertEqual(m['total_cloud_tokens'],205)
        self.assertEqual(m['fresh_input'],110)
        self.assertEqual(m['reference_usd'],0.25)
        self.assertEqual(frontier_tokens(c),100)

    def test_negative_savings_are_reported(self):
        base={'provider':'codex','task':'incident','seed':1,'score':1,
              'total_cloud_tokens':100,'frontier_tokens':100,'fresh_input':100,
              'reference_usd':1,'wall_seconds':10}
        a=dict(base,arm='frontier');b=dict(base,arm='mixed',total_cloud_tokens=150,wall_seconds=20)
        result=paired([a,b])[0]
        self.assertEqual(result['total_cloud_tokens_saving_pct'],-50)
        self.assertEqual(result['wall_seconds_saving_pct'],-100)


if __name__=='__main__':unittest.main()
