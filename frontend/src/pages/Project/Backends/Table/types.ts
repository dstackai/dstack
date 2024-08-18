export interface IProps {
    backends: IProjectBackend[];
    onClickAddBackend?: () => void;
    deleteBackends?: (backends: readonly IProjectBackend[] | IProjectBackend[]) => void;
    editBackend?: (backend: IProjectBackend) => void;
    isDisabledDelete?: boolean;
}
