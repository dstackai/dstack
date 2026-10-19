import { getApplyCommand } from './helpers';

describe('getApplyCommand', () => {
    test('keeps the basic command without resource filters', () => {
        expect(getApplyCommand(new URLSearchParams('project_name=main'))).toBe('dstack apply -f .dstack.yml');
    });

    test('includes GPU ranges and all explicit backend and fleet filters', () => {
        const params = new URLSearchParams(
            'gpu_vendor=nvidia&gpu_name=H100&gpu_count=1..8&gpu_memory=80GB&backend=aws&backend=gcp&fleet=chosen&spot_policy=auto',
        );
        expect(getApplyCommand(params)).toBe(
            'dstack apply -f .dstack.yml --gpu nvidia:H100:1..8:80GB --backend aws --backend gcp --fleet chosen --spot-policy auto',
        );
    });

    test('CPU selection explicitly disables GPUs and keeps exact RAM', () => {
        const params = new URLSearchParams('gpu_count=0&cpu_count=2&cpu_arch=x86&memory=1.8564453125GB&region=cluster');
        expect(getApplyCommand(params)).toBe(
            'dstack apply -f .dstack.yml --gpu 0 --cpu x86:2 --memory 1.8564453125GB --region cluster',
        );
    });

    test('quotes shell metacharacters and single quotes from URL input', () => {
        const params = new URLSearchParams();
        params.set('fleet', "team's $(touch /tmp/unwanted); `echo bad`");
        expect(getApplyCommand(params)).toBe(
            "dstack apply -f .dstack.yml --fleet 'team'\\''s $(touch /tmp/unwanted); `echo bad`'",
        );
    });
});
