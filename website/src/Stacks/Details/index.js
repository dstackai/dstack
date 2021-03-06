// @flow

import React, {useEffect, useState, useRef, Fragment} from 'react';
import useSWR from 'swr';
import get from 'lodash/get';
import {useTranslation} from 'react-i18next';
import {Link, useHistory, useLocation, useParams} from 'react-router-dom';
import {connect} from 'react-redux';
import Helmet from 'react-helmet';
import Share from 'components/Share';
import AccessForbidden from 'components/AccessForbidden';
import NotFound from 'components/NotFound';
import StackDetails from 'components/stack/Details';
import StackDetailsApp from 'components/stack/DetailsApp';
import {isSignedIn, parseSearch, getStackCategory, dataFetcher} from 'utils';
import {deleteStack} from 'Stacks/List/actions';
import {fetchDetails, clearDetails, fetchFrame, update, updatePermissions} from './actions';
import routes from 'routes';
import config from 'config';

type Props = {
    attachmentRequestStatus: ?number,
    deleteStack: Function,
    fetchDetails: Function,
    fetchFrame: Function,
    clearDetails: Function,
    update: Function,
    requestStatus: ?number,
    frame: ?{},
    listData?: {},
    data?: {},
    frameRequestStatus: ?number,
    loadingFrame?: boolean,
    updatePermissions: Function,
}

const categoryMap = {
    app: 'applications',
    mlModel: 'models',
};

const dataFormat = data => data?.head;

const Details = ({
    fetchDetails,
    fetchFrame,
    clearDetails,
    update,
    data = {},
    listData = {},
    frame,
    frameRequestStatus,
    loading,
    requestStatus,
    updatePermissions,
}: Props) => {
    let parsedAttachmentIndex;

    const params = useParams();
    const {push} = useHistory();
    const location = useLocation();
    const searchParams = parseSearch(location.search);
    const [hasUpdate, setHasUpdate] = useState(false);
    const [isCanceledUpdate, setIsCanceledUpdate] = useState(false);

    if (searchParams.a)
        parsedAttachmentIndex = parseInt(searchParams.a);

    const [attachmentIndex, setAttachmentIndex] = useState(parsedAttachmentIndex);
    const [selectedFrame, setSelectedFrame] = useState(searchParams.f);
    const [executionId, setExecutionId] = useState(searchParams['execution_id']);
    const [headId, setHeadId] = useState(null);

    const {t} = useTranslation();

    const [isShowShareModal, setIsShowShareModal] = useState(false);
    const isFirstChangeSearch = useRef(false);

    const {data: headData} = useSWR([
        config.API_URL + config.STACK_HEAD(params.user, params.stack),
        dataFormat,
    ], dataFetcher, {
        revalidateOnMount: false,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        refreshInterval: (!loading && data && !hasUpdate && !isCanceledUpdate) ? 1000 : 0,
    });


    useEffect(() => {
        if (headData && data?.head?.id && headData.id !== data.head.id)
            setHasUpdate(true);
    }, [headData]);

    useEffect(() => {
        if (isFirstChangeSearch.current) {
            let parsedAttachmentIndex;

            if (searchParams.a)
                parsedAttachmentIndex = parseInt(searchParams.a);

            if (parsedAttachmentIndex !== attachmentIndex)
                setAttachmentIndex(parsedAttachmentIndex);

            if (searchParams.f !== selectedFrame)
                setSelectedFrame(searchParams.f);

            if (searchParams['execution_id'] !== executionId)
                setExecutionId(searchParams['execution_id']);

        } else {
            isFirstChangeSearch.current = true;
        }
    }, [location.search]);

    useEffect(() => {
        let searchParams = {};

        if (attachmentIndex)
            searchParams.a = attachmentIndex;

        if (selectedFrame && selectedFrame !== headId)
            searchParams.f = selectedFrame;

        if (executionId)
            searchParams['execution_id'] = executionId;

        const searchString = Object
            .keys(searchParams)
            .map(key => `${key}=${searchParams[key]}`)
            .join('&');

        if (location.search.replace('?', '') !== searchString)
            push({search: searchString.length ? `?${searchString}` : ''});
    }, [attachmentIndex, selectedFrame, executionId, headId]);

    const fetchData = () => {
        fetchDetails(params.user, params.stack);
    };

    useEffect(() => {
        if (!data.head || !listData || (data.head.id !== listData.head))
            fetchData();
    }, [params.user, params.stack]);

    useEffect(() => {
        return () => clearDetails();
    }, []);

    const onUpdateReadme = readme => {
        update({
            stack: `${data.user}/${data.name}`,
            readme,
        });
    };

    useEffect(() => {
        if (selectedFrame)
            fetchFrame(params.user, params.stack, selectedFrame);
    }, [selectedFrame]);

    useEffect(() => {
        if (data && data.head)
            setHeadId(data.head.id);
    }, [data]);

    const toggleShareModal = () => setIsShowShareModal(val => !val);

    const changeAccessLevel = accessLevel => {
        update({
            stack: `${data.user}/${data.name}`,
            'access_level': accessLevel,
        });
    };

    const refresh = () => {
        setHasUpdate(false);
        fetchData();
        setAttachmentIndex();
        setExecutionId();
    };

    const cancelUpdate = () => {
        setIsCanceledUpdate(true);
        setHasUpdate(false);
    };

    if (!loading && requestStatus === 403)
        return <AccessForbidden>
            {t('youDontHaveAnAccessToThisStack')}.

            {isSignedIn() && (
                <Fragment>
                    <br />

                    <Link to={routes.categoryStacks(params.category)}>
                        {t('goToMyStacks')}
                    </Link>
                </Fragment>
            )}
        </AccessForbidden>;

    if (!loading && (requestStatus === 404 || frameRequestStatus === 404))
        return <NotFound>
            {t('theStackYouAreRookingForCouldNotBeFound')}
            {' '}
            {isSignedIn() && (
                <Fragment>
                    <Link to={routes.categoryStacks(params.category)}>
                        {t('goToMyStacks')}
                    </Link>.
                </Fragment>
            )}
        </NotFound>;

    const currentFrameId = selectedFrame ? selectedFrame : get(data, 'head.id');

    const contentType = get(data, 'head.attachments[0].content_type');
    const application = get(data, 'head.attachments[0].application');

    const category = getStackCategory({
        application,
        contentType,
    });

    const DetailsComponent = category === 'app' ? StackDetailsApp : StackDetails;

    return (
        <Fragment>
            <Helmet>
                <title>dstack.ai | {params.user} | {params.stack}</title>
            </Helmet>

            <DetailsComponent
                loading={loading || params?.stack !== data?.name}
                currentFrameId={currentFrameId}
                frame={frame}
                attachmentIndex={attachmentIndex || 0}
                executionId={executionId}
                data={data}
                toggleShare={toggleShareModal}
                backUrl={routes.categoryStacks(categoryMap[category])}
                onUpdateReadme={onUpdateReadme}
                onChangeExecutionId={setExecutionId}
                onChangeAttachmentIndex={setAttachmentIndex}
                updates={{
                    has: hasUpdate,
                    refreshAction: refresh,
                    cancelAction: cancelUpdate,
                }}
            />

            <Share
                isShow={isShowShareModal}
                instancePath={`${params.user}/${params.stack}`}
                stackName={params.stack}
                onChangeAccessLevel={changeAccessLevel}
                accessLevel={data['access_level']}
                defaultPermissions={data.permissions}
                close={toggleShareModal}

                urlParams={{
                    a: attachmentIndex || null,
                    f: frame?.id !== data?.head?.id ? frame?.id : null,
                    'execution_id': executionId || null,
                }}

                onUpdatePermissions={
                    permissions => updatePermissions(`${params.user}/${params.stack}`, permissions)
                }
            />
        </Fragment>
    );
};

export default connect(
    (state, props) => {
        const frame = state.stacks.details.frame;
        const stack = `${props.match.params.user}/${props.match.params.stack}`;

        return {
            data: get(state.stacks.details.data, stack),
            listData: state.stacks.list.data && state.stacks.list.data.find(i => `${i.user}/${i.name}` === stack),
            requestStatus: state.stacks.details.requestStatus,
            frame,
            frameRequestStatus: state.stacks.details.frameRequestStatus,
            loadingFrame: state.stacks.details.loadingFrame,
            attachmentRequestStatus: state.stacks.details.attachmentRequestStatus,
            loading: state.stacks.details.loading,
        };
    },

    {
        fetchDetails,
        clearDetails,
        deleteStack,
        fetchFrame,
        update,
        updatePermissions,
    },
)(Details);
