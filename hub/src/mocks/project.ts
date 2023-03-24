const listSuccess: IProject[] = new Array(50).fill({}).map((i, index) => ({
    project_name: `project_${index}`,
    backend: {
        type: 'aws',
        access_key: `project_${index}_access_key`,
        secret_key: `project_${index}_secret_key`,
        region_name: `project_${index}_region_name`,
        region_name_title: `Project ${index} Region`,
        s3_bucket_name: `project_${index}_s3_bucket_name`,
        ec2_subnet_id: null,
    },

    members: ['test_user', 'old_user', 'new_user'].map((userName) => ({
        user_name: userName,
        project_role: (function () {
            const val = Math.random();
            let permission: TProjectRole = 'read';

            switch (true) {
                case val > 0.65 || index < 4:
                    permission = 'admin';
                    break;
                case val <= 0.65 && val >= 0.3:
                    permission = 'read';
                    break;
                case val < 0.3:
                    permission = 'run';
                    break;
            }

            return permission;
        })(),
    })),
}));

const backendValuesSuccess: IProjectBackendValues = {
    type: 'aws',
    region_name: {
        selected: 'region_1',
        values: new Array(10).fill({}).map((_, index) => ({ value: `region_${index}`, label: `Region ${index}` })),
    },
    s3_bucket_name: {
        selected: 's3://bucket_1',
        values: new Array(10).fill({}).map((_, index) => ({
            name: `bucket_${index}`,
            created: `bucket_${index}_date`,
            region: `bucket_${index}_region`,
        })),
    },
    ec2_subnet_id: {
        selected: null,
        values: new Array(10).fill({}).map((_, index) => ({ value: `subnet_${index}`, label: `Subnet ${index}` })),
    },
};

export default {
    list: {
        success: listSuccess,
    },
    backendValues: {
        success: backendValuesSuccess,
    },
};
