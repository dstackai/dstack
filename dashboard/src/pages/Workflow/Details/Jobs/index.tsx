import React from 'react';
import { useGetJobsQuery } from 'services/jobs';
import { POLLING_INTERVAL } from 'consts';
import Table from 'components/Table';
import TableContentSkeleton from 'components/TableContentSkeleton';
import columns from './columns';
import JobItem from 'pages/Runs/List/JobItem';

const LAST_JOBS_COUNT = 50;

export interface Props extends React.HTMLAttributes<HTMLDivElement> {
    runName?: IRun['run_name'];
    workflowName?: IRunWorkflow['workflow_name'];
}

const Jobs: React.FC<Props> = ({ className, runName, workflowName, ...props }) => {
    const { data: jobs, isLoading } = useGetJobsQuery(
        { count: LAST_JOBS_COUNT, runName, workflowName },
        {
            pollingInterval: POLLING_INTERVAL,
        },
    );

    return (
        <div className={className} {...props}>
            {isLoading && <TableContentSkeleton columns={columns} rowsCount={4} withRowBorders={false} />}

            {jobs && (
                <Table columns={columns}>
                    {jobs.map((job, index) => (
                        <JobItem columns={columns} job={job} key={index} />
                    ))}
                </Table>
            )}
        </div>
    );
};

export default Jobs;
