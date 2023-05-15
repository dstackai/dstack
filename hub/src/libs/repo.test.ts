import { getRepoDisplayName } from './repo';

const MOCK_DATA: IRepo[] = [
    {
        repo_id: 'dstack-playground-ge824g2a',
        last_run_at: 1683037176519,
        tags_count: 0,
        repo_info: {
            repo_type: RepoTypeEnum.REMOTE,
            repo_host_name: 'github.com',
            repo_port: null,
            repo_user_name: 'dstackai',
            repo_name: 'dstack-playground',
        },
    },
    {
        repo_id: 'test-aws-ymicjjos',
        last_run_at: 1683036892844,
        tags_count: 0,
        repo_info: {
            repo_type: RepoTypeEnum.LOCAL,
            repo_dir: '/Users/test-user/test-aws',
        },
    },
];

describe('test repo libs', () => {
    test('check get repo display name', () => {
        expect(getRepoDisplayName(MOCK_DATA[0])).toEqual('dstackai/dstack-playground');
        expect(getRepoDisplayName(MOCK_DATA[1])).toEqual('/Users/test-user/test-aws');
    });
});
