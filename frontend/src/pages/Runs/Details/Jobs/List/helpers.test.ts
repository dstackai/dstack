jest.mock('App/helpers', () => ({ getBaseUrl: () => '' }));
jest.mock('libs/fleet', () => ({ formatBackend: () => '-' }));

import { getRunListItemResources } from '../../../List/helpers';
import { getJobListItemResources } from './helpers';

const instanceResources: IResources = {
    cpus: 4,
    memory_mib: 16 * 1024,
    gpus: [],
    spot: false,
};

const blockResources: IResources = {
    cpus: 1,
    memory_mib: 4 * 1024,
    gpus: [],
    spot: false,
};

const submission: IJobSubmission = {
    id: 'submission',
    submission_num: 0,
    status: 'running',
    submitted_at: 0,
    finished_at: null,
    job_provisioning_data: {
        backend: 'aws',
        instance_type: { name: 't3.xlarge', resources: instanceResources },
        instance_id: 'instance',
        hostname: 'localhost',
        region: 'us-east-1',
        price: 0,
        username: 'ubuntu',
        ssh_port: 22,
        dockerized: false,
    },
    job_runtime_data: {
        offer: { instance: { name: 'block', resources: blockResources } },
    },
};

const job = { job_spec: {}, job_submissions: [submission] } as IJob;

describe('job resource display', () => {
    test('uses allocated block resources when runtime offer is available', () => {
        expect(getJobListItemResources(job)).toBe('cpu=1 mem=4GB');
        expect(getRunListItemResources({ jobs: [job], latest_job_submission: submission } as IRun)).toBe('cpu=1 mem=4GB');
    });

    test('falls back to instance resources for older submissions', () => {
        const legacySubmission = { ...submission, job_runtime_data: null };
        const legacyJob = { ...job, job_submissions: [legacySubmission] } as IJob;
        expect(getJobListItemResources(legacyJob)).toBe('cpu=4 mem=16GB');
    });
});
