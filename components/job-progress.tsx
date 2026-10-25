'use client';
import type {Language} from '../lib/design-copy';
import {jobStatusLabel, jobStageLabel, formatEta, formatSpeed} from '../lib/job-status';
import type {GenerationJob} from './generation-panel';

/** Status, sampler speed, time left and progress bar of a running job, shown under the live preview. */
export default function JobProgress({job, lang}: {job: GenerationJob; lang: Language}) {
  const left = {en: 'left', pt: 'restantes', es: 'restantes'}[lang];
  const details = [job.message, job.step_total ? `${job.step}/${job.step_total}` : '', job.seconds_per_step ? formatSpeed(job.seconds_per_step) : '', job.eta_seconds ? `~${formatEta(job.eta_seconds)} ${left}` : ''].filter(Boolean).join(' · ');
  return <div className="job-progress" aria-live="polite">
    <div className="job-progress-line"><strong>{jobStatusLabel(job.status, lang)}{job.status === 'running' ? ' · ' + jobStageLabel(job.stage, lang) : ''}</strong>{job.total_segments ? <span className="mono">{job.segment}/{job.total_segments}</span> : null}</div>
    {details && <p>{details}</p>}
    <progress max="1" value={job.progress || 0}/>
  </div>;
}
