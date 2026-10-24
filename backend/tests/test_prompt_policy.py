import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prompt_policy import validate_h3_prompt,H3_POLICY
from server import validate_plan
import test_contracts as contracts
from test_contracts import structured_prompt

class PromptPolicyTests(unittest.TestCase):
 def test_h3_contract_accepts_role_separation(self):validate_h3_prompt(structured_prompt(),'motion')
 def test_missing_sections_rejected(self):
  with self.assertRaises(ValueError):validate_h3_prompt('motion_transfer: Replace <Picture 1>.','motion')
 def test_order_and_empty_sections_rejected(self):
  for prompt in [structured_prompt().replace('summary:','detailed_description:'),structured_prompt().replace('overall_soundscape: N/A','overall_soundscape:')]:
   with self.assertRaises(ValueError):validate_h3_prompt(prompt,'motion')
 def test_raw_prompt_not_formatted(self):
  fixtures=contracts.WorkflowContracts();r=fixtures.request();r['prompt']='  Meu texto <Picture 1>\nsem alterar. '
  result=validate_plan(fixtures.plan(),[1],{'enhance_prompt':False},r)
  self.assertEqual(result['prompt'],r['prompt'])
 def test_piano_and_keyboard_are_preserved(self):
  fixtures=contracts.WorkflowContracts();plan=fixtures.plan();plan['preserve_objects']=['piano','keyboard','unknown']
  self.assertEqual(validate_plan(plan,[1],{},fixtures.request())['preserve_objects'],['piano','keyboard'])
 def test_both_consumers_share_policy(self):
  self.assertIn('Kawarimi',H3_POLICY);self.assertIn('replace the entire source environment',H3_POLICY)

if __name__=='__main__':unittest.main()
