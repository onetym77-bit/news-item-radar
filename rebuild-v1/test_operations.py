"""Check executable workflow boundaries without source or model API calls."""

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / '.github' / 'workflows'


def workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding='utf-8'))


def events(document):
    # YAML 1.1 parsers interpret GitHub's "on" as boolean true.
    return document.get('on', document.get(True, {})) or {}


class OperationsTests(unittest.TestCase):
    def test_all_scheduled_workflows_are_collection_only(self):
        scheduled = {
            path.name for path in WORKFLOWS.glob('*.yml')
            if events(workflow(path.name)).get('schedule')
        }
        self.assertEqual(scheduled, {
            'collect-signals.yml', 'district-council-watch.yml', 'collect-source-feed.yml',
        })

    def test_no_workflow_injects_a_paid_model_secret(self):
        for path in WORKFLOWS.glob('*.yml'):
            document = workflow(path.name)
            self.assertIsInstance(document['jobs'], dict, path.name)
            self.assertNotIn('secrets.OPENAI_API_KEY', path.read_text(encoding='utf-8'), path.name)
            self.assertNotIn('secrets.ANTHROPIC_API_KEY', path.read_text(encoding='utf-8'), path.name)

    def test_paid_jobs_cannot_run_from_dispatch_or_schedule(self):
        checks = {
            'editorial-v4.yml': 'review',
            'district-council-l3-context.yml': 'review',
            'district-council-recent-l3.yml': 'review',
            'citizen-proposal-shadow.yml': 'review',
        }
        for name, job in checks.items():
            self.assertEqual(workflow(name)['jobs'][job]['if'],
                             "${{ github.event_name == 'pull_request' }}", name)
        for name, job in {
            'editorial-v4-fresh-cycle.yml': 'collect-review-publish',
            'council-consolidation-diagnostic.yml': 'diagnose',
            'multi-agent-shadow-live.yml': 'run-shadow',
        }.items():
            self.assertEqual(workflow(name)['jobs'][job]['if'], '${{ false }}', name)

    def test_interest_collection_does_not_duplicate_youtube_or_interpret_news(self):
        steps = workflow('collect-interest-signals.yml')['jobs']['collect']['steps']
        paused = [step for step in steps if any(term in step.get('run', '') for term in
                  ('collect_source_material_v2_1.py', 'analyze_news_context.py'))]
        self.assertEqual(len(paused), 2)
        self.assertTrue(all(step.get('if') == '${{ false }}' for step in paused))
        self.assertTrue(any('collect_interest_signals.py' in step.get('run', '')
                            and step.get('if') != '${{ false }}' for step in steps))

    def test_council_archive_preserves_collection_but_never_relabels_old_analysis(self):
        document = workflow('council-issue-lifecycle.yml')
        self.assertNotIn('analysis_calls', events(document)['workflow_dispatch']['inputs'])
        steps = document['jobs']['archive']['steps']
        commands = '\n'.join(step.get('run', '') for step in steps)
        self.assertIn('council-archive-v1/archive.py', commands)
        self.assertIn('district-council-pilot/collect_pilot.py', commands)
        self.assertNotIn('council-archive-v1/analyze.py', commands)
        self.assertNotIn('analysis_latest.json', commands)
        uploads = '\n'.join(str(step.get('with', {}).get('path', '')) for step in steps)
        self.assertNotIn('analysis_latest.json', uploads)
        self.assertIn('new_documents.jsonl.gz', uploads)
        self.assertTrue(any(step.get('uses', '').startswith('actions/cache/save@')
                            for step in steps))

    def test_seoul_collection_does_not_mutate_editorial_state(self):
        document = workflow('collect-source-feed.yml')
        self.assertEqual(events(document)['schedule'][0]['timezone'], 'Asia/Seoul')
        self.assertEqual(events(document)['schedule'][0]['cron'], '30 7 * * 1,3')
        steps = document['jobs']['collect']['steps']
        self.assertTrue(any('--skip-review-queue' in step.get('run', '') for step in steps))
        self.assertFalse(any('compile_editorial_review.py' in step.get('run', '') or
                             'build_briefing.py' in step.get('run', '') for step in steps))
        self.assertFalse(any('OPENAI' in str(step.get('env', {})) for step in steps))


if __name__ == '__main__':
    unittest.main()
